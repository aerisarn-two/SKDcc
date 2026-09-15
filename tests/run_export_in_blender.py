"""The export settings, against a real creature, inside Blender.

    blender --background --python tests/run_export_in_blender.py -- creature.fbx

Two different kinds of check, because the two mistakes hide differently.

The pose is caught by measuring. A creature FBX arrives with an action applied,
and a rig exported like that writes the pose into the skeleton; export, read the
file back, and everything bone-parented has moved. That is a real measurement
and it fails by a fifth of a unit on a draugr.

The axes cannot be caught that way, and it is worth being clear about why.
Blender's importer honours the up axis a file declares and its exporter declares
whichever frame it is asked for, so the conversion out and the conversion back
in cancel exactly: export a Skyrim scene with the exporter's defaults, reimport
it, and nothing has moved. NIFBX's reader does not consult the field -- Skyrim is
Z-up, so it reads the numbers as Z-up -- and the same file converts to a NIF with
90 of 92 nodes in the wrong place. Only the trip to NIF shows it, and that is not
a trip Blender can make. So the axis settings are held here as the values that
were measured there, and `settings.py` records the measurement.
"""

import os
import sys

import addon_utils
import bpy

FAILURES = []


def check(name, condition, detail=""):
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if not detail else "   (%s)" % detail), flush=True)
    if not condition:
        FAILURES.append(name)


def placements():
    """Every object's world position, by name.

    Hidden objects are shown first. A collision shape arrives with
    ``hide_viewport`` set -- NIFBX marks it so, because nobody wants a capsule
    drawn over the mesh -- and **a hidden object has no evaluated transform**:
    ``matrix_world`` comes back stale rather than absent, so a draugr's foot
    body reads (0, -13.7, 0) and both feet read the same place. Measuring that
    and calling it a position is how this check first reported a capsule 16,516
    units out of a scene that was fine.
    """
    hidden = [o for o in bpy.context.scene.objects if o.hide_viewport]

    for obj in hidden:
        obj.hide_viewport = False

    bpy.context.view_layer.update()

    try:
        return {o.name: o.matrix_world.translation.copy()
                for o in bpy.context.scene.objects}
    finally:
        for obj in hidden:
            obj.hide_viewport = True


def worst(before, after):
    """The furthest an object moved, and which one."""
    far, name = 0.0, "-"

    for key, position in before.items():
        if key not in after:
            continue

        moved = (after[key] - position).length

        if moved > far:
            far, name = moved, key

    return far, name


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fbx = os.path.abspath(argv[0]) if argv else None

    if not fbx or not os.path.exists(fbx):
        print("need a path to an FBX", flush=True)
        return 2

    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"))
    addon_utils.enable("io_scene_fbx", default_set=False, persistent=False)

    import skyrim_export as addon
    from skyrim_export import export, settings

    addon.register()

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)

    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    posed = [o for o in armatures if o.data.pose_position == "POSE"]

    # Measured at rest, because that is what the export writes. A creature FBX
    # arrives with an action applied, and everything bone-parented -- which is
    # every rigid body and every joint on it -- then sits where the pose puts it
    # rather than where the skeleton does. Comparing a posed scene against a
    # file written at rest reports 47 objects moved and none of them did.
    with settings.at_rest(bpy.context.scene):
        before = placements()

    check("the scene came in", len(before) > 0, "%d objects" % len(before))

    # A creature carries its file in properties, so a sample of them is taken to
    # compare after the trip: losing them is losing the file.
    props = {o.name: dict(o.items()) for o in bpy.context.scene.objects if len(o.keys())}
    check("the scene carries properties", len(props) > 0, "%d objects have them" % len(props))

    out = os.path.join(os.path.dirname(fbx), "export_roundtrip.fbx")
    report = export.write(bpy.context.scene, out)
    print("     export ->", report, flush=True)

    # --- the rig is put back ----------------------------------------------

    check("the armatures are left posed as they were",
          [o for o in armatures if o.data.pose_position == "POSE"] == posed,
          "%d of %d in pose position" % (len(posed), len(armatures)))

    # --- and the scene comes back where it was ----------------------------

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=out, use_custom_props=True)

    after = placements()

    check("every object came back", len(after) >= len(before),
          "%d out, %d back" % (len(before), len(after)))

    far, name = worst(before, after)
    check("nothing moved on the way out and back", far < 1e-3,
          "worst %.5f units on %s" % (far, name))

    # --- the properties came back too -------------------------------------

    kept = 0
    lost = []

    for owner, values in props.items():
        obj = bpy.data.objects.get(owner)

        if obj is None:
            lost.append(owner)
            continue

        for key in values:
            if key in obj.keys():
                kept += 1
            else:
                lost.append("%s.%s" % (owner, key))

    total = sum(len(v) for v in props.values())
    check("the properties came back", kept == total,
          "%d of %d; missing %s" % (kept, total, lost[:3] or "none"))

    # --- and the settings are the ones that were measured -----------------

    # --- and the clips are still named -------------------------------------
    #
    # Named on its own rather than left inside the count above, because it is the
    # one property the whole animation set depends on. A Havok clip is identified
    # by properties on its animation stack, which Blender has nowhere to keep, so
    # SKAssets writes the same list on a node as well -- 17,846 bytes of it on a
    # draugr -- and losing that turns 216 clips into 216 anonymous actions.

    clips = "sk_clips"
    sent = next((v[clips] for v in props.values() if clips in v), None)

    if sent is None:
        print("     no clip list in this file, so there is none to lose", flush=True)
    else:
        back = next((obj[clips] for obj in bpy.data.objects if clips in obj.keys()), None)
        rows = len(str(sent).splitlines())

        check("the clip list came back whole", back == sent,
              "%d clips, %d bytes" % (rows, len(str(sent))))

    check("the axes are Blender's own, written out unchanged",
          (settings.AXIS_FORWARD, settings.AXIS_UP) == ("Y", "Z"),
          "%s / %s" % (settings.AXIS_FORWARD, settings.AXIS_UP))

    chosen = settings.options()
    check("leaf bones are not invented", chosen["add_leaf_bones"] is False)
    check("custom properties are written", chosen["use_custom_props"] is True)

    addon.unregister()

    print("\n%d checks failed" % len(FAILURES), flush=True)
    for name in FAILURES:
        print("   FAILED:", name, flush=True)

    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
