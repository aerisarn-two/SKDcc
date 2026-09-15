"""Mark a creature's sockets, inside Blender.

    blender --background --python tests/run_rig_in_blender.py -- some.fbx

The claim is narrow: the bones that weight nothing stop claiming to deform, they
end up somewhere they can be hidden, and their invented tails get cut -- while
every weight, every animation channel and every vertex stays exactly where it
was. The last part is the whole point, so it is measured rather than asserted.
"""

import os
import re
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_rig import build, schema  # noqa: E402

failures = []


def check(name, got, want, tolerance=1e-4):
    ok = abs(got - want) <= tolerance if isinstance(want, float) else got == want

    print(f"{'PASS' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" != {want!r}"))

    if not ok:
        failures.append(name)


def curves(action):
    """An action's curves, whichever Blender holds them under."""
    if hasattr(action, "fcurves"):
        return list(action.fcurves)

    found = []

    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                found += list(bag.fcurves)

    return found


def main():
    path = sys.argv[sys.argv.index("--") + 1]

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_custom_props=True,
                             automatic_bone_orientation=True)

    scene = bpy.context.scene
    armatures = [o for o in scene.objects if o.type == "ARMATURE"]

    print(f"     {len(armatures)} armature(s), {len(bpy.data.actions)} action(s)")

    if not armatures:
        print("FAIL: no armature in this file")
        failures.append("any armature")
        return

    armature = armatures[0]

    # What must not change: the weights, the channels, and where the mesh is.
    def weights():
        found = {}

        for obj in scene.objects:
            if obj.type != "MESH":
                continue

            groups = {g.index: g.name for g in obj.vertex_groups}

            for vertex in obj.data.vertices:
                for group in vertex.groups:
                    name = groups.get(group.group, "")
                    found[name] = found.get(name, 0.0) + group.weight

        return found

    def channels():
        pattern = re.compile(r'pose\.bones\["([^"]+)"\]')
        found = set()

        for action in bpy.data.actions:
            for curve in curves(action):
                match = pattern.match(curve.data_path)

                if match:
                    found.add((action.name, curve.data_path, curve.array_index))

        return found

    def vertices():
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()
        places = []

        for obj in scene.objects:
            if obj.type != "MESH":
                continue

            evaluated = obj.evaluated_get(graph)
            world = evaluated.matrix_world
            places += [world @ v.co for v in evaluated.data.vertices]

        return places

    scene.frame_set(scene.frame_start)
    before_weights, before_channels, before_places = weights(), channels(), vertices()

    report = build.build(scene)
    print(f"     {report}")

    for line in report.notes:
        print(f"     note: {line}")

    # A skeleton with no body proves nothing about which bones deform, and must
    # say so rather than mark the whole rig.
    skinned = bool(build.deforming_names(armature, scene.objects))

    if not skinned:
        check("a rig with no body is left alone", report.sockets, 0)
        check("and it says why", any("skinned to it" in n for n in report.notes), True)
        return

    check("the creature has sockets", report.sockets > 0, True)

    marked = {b.name for b in armature.data.bones if schema.SOCKET in b.keys()}
    deforming = build.deforming_names(armature, scene.objects)

    check("nothing marked deforms anything", marked & deforming, set())
    check("every marked bone stopped claiming to deform",
          all(not armature.data.bones[n].use_deform for n in marked), True)

    # And the bones that do deform still say so.
    check("deforming bones still deform",
          all(armature.data.bones[n].use_deform for n in deforming
              if n in armature.data.bones), True)

    if hasattr(armature.data, "collections"):
        group = armature.data.collections.get(schema.COLLECTION)
        check("there is a collection to hide them by", group is not None, True)

        if group is not None:
            check("it holds them all", {b.name for b in group.bones}, marked)

    # The invented tails are cut to the length of bones that have a real one.
    cap = armature.get(schema.CAP, 0.0)
    leaves = [b for b in armature.data.bones if b.name in marked and not b.children]

    if cap > 0 and leaves:
        # Relative: a trimmed tail lands exactly on the cap, and at a length of
        # seven an absolute 1e-6 is finer than a 32-bit float can hold.
        check("no invented tail is longer than a real one",
              max(b.length for b in leaves) <= cap * (1.0 + 1e-5), True)

    # Nothing paid for it.
    after_weights, after_channels, after_places = weights(), channels(), vertices()

    check("not one weight changed", after_weights, before_weights)
    check("not one animation channel was lost", after_channels, before_channels)

    drift = max((a - b).length for a, b in zip(before_places, after_places))
    print(f"     the mesh moved {drift * 1000:.5f} mm")
    check("the mesh did not move", drift < 1e-5, True)

    # And it comes off again.
    restored = build.clear(scene)
    check("cleared", restored, len(marked))
    check("every bone deforms again",
          all(b.use_deform for b in armature.data.bones), True)
    check("the mark is gone", schema.MARKED in armature.keys(), False)


main()

print(f"\n{len(failures)} checks failed")

if failures:
    print("FAILED: " + ", ".join(failures))

sys.exit(len(failures))
