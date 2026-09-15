"""The add-on exercised against a real export, inside Blender.

Run it as::

    blender --background --python tests/run_in_blender.py -- path/to/skeleton.fbx

There is no mocking and no fixture: the file is a vanilla creature skeleton
converted by NIFBX, which is the only thing that proves any of this works.
Every check prints PASS or FAIL and the exit code is the number of failures.
"""

import math
import os
import sys

import mathutils

import addon_utils
import bpy

FAILURES = []


def check(name, condition, detail=""):
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if not detail else "   (%s)" % detail), flush=True)
    if not condition:
        FAILURES.append(name)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fbx = os.path.abspath(argv[0]) if argv else None

    if not fbx or not os.path.exists(fbx):
        print("need a path to an FBX", flush=True)
        return 2

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"))
    addon_utils.enable("io_scene_fbx", default_set=False, persistent=False)

    import skyrim_havok_constraints as addon
    from skyrim_havok_constraints import bake, build, limits, schema
    from skyrim_havok_constraints.joint import Joint, joints_in

    addon.register()

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)

    scene = bpy.context.scene
    objects = list(scene.objects)

    joints = joints_in(objects)
    check("the scene has joints", len(joints) > 0, "%d found" % len(joints))

    far = [j for j in joints if Joint(j).far_frame is not None]
    check("every joint states its far frame", len(far) == len(joints),
          "%d of %d" % (len(far), len(joints)))

    named = [j for j in joints if Joint(j).body_a_name and Joint(j).body_b_name]
    check("every joint names both bodies", len(named) == len(joints),
          "%d of %d" % (len(named), len(joints)))

    # --- build -------------------------------------------------------------

    result = build.build_rigid_body_constraints(scene, objects)
    print("     build ->", result, flush=True)
    check("all joints built", result.built == len(joints),
          "%d of %d; %s" % (result.built, len(joints), "; ".join(result.problems[:3])))

    built = [j for j in joints if j.rigid_body_constraint is not None]
    check("each joint carries a constraint", len(built) == len(joints))

    pointed = [j for j in built
               if j.rigid_body_constraint.object1 is not None
               and j.rigid_body_constraint.object2 is not None]
    check("every constraint points at two objects", len(pointed) == len(built),
          "%d of %d" % (len(pointed), len(built)))

    distinct = [j for j in pointed
                if j.rigid_body_constraint.object1 != j.rigid_body_constraint.object2]
    check("no constraint joins a body to itself", len(distinct) == len(pointed))

    bodied = [j for j in pointed
              if j.rigid_body_constraint.object1.rigid_body is not None
              and j.rigid_body_constraint.object2.rigid_body is not None]
    check("both objects are rigid bodies", len(bodied) == len(pointed),
          "%d of %d" % (len(bodied), len(pointed)))

    # --- the limits actually arrived ---------------------------------------

    # Only where the file has any. A chicken's ragdoll is six Ragdoll joints and
    # not one hinge, and this suite had only ever been run on creatures that had
    # both -- so it asserted that every skeleton has a knee.
    hinges = [j for j in built if Joint(j).type == "LimitedHinge"]

    if hinges:
        check("the corpus has limited hinges", len(hinges) > 0, "%d" % len(hinges))
    else:
        print("     no limited hinges in this skeleton, so there are none to check")

    exact = 0
    for obj in hinges:
        joint = Joint(obj)
        rbc = obj.rigid_body_constraint
        low, high = joint.hinge_range
        if low is None:
            continue
        if (abs(rbc.limit_ang_x_lower - min(low, high)) < 1e-6
                and abs(rbc.limit_ang_x_upper - max(low, high)) < 1e-6):
            exact += 1
    check("hinge limits transfer exactly", exact == len(hinges),
          "%d of %d" % (exact, len(hinges)))

    locked = all(h.rigid_body_constraint.use_limit_ang_y
                 and h.rigid_body_constraint.limit_ang_y_lower == 0.0
                 and h.rigid_body_constraint.limit_ang_y_upper == 0.0
                 for h in hinges)
    check("a hinge is locked across its axis", locked)

    generic = all(h.rigid_body_constraint.type == "GENERIC" for h in hinges)
    check("a hinge is GENERIC, not HINGE", generic,
          "Blender's HINGE turns about Z, Havok's about the frame's X")

    # --- the frame is the empty's own transform ----------------------------

    aligned = 0
    for obj in built:
        axis = obj.get(schema.field("Axis B")) or obj.get(schema.field("Twist B"))
        if not axis:
            continue
        wanted = [float(v) for v in str(axis).split()[:3]]
        got = [obj.matrix_local.col[0][i] for i in range(3)]
        if max(abs(a - b) for a, b in zip(wanted, got)) < 1e-4:
            aligned += 1
    check("the joint's local X is the Havok axis", aligned == len(built),
          "%d of %d" % (aligned, len(built)))

    # --- R2: an untouched constraint bakes to nothing ----------------------

    baked = bake.bake(objects)
    print("     bake (untouched) ->", baked, flush=True)
    check("R2: nothing is rewritten when nothing changed",
          baked.rewritten == 0 and baked.unchanged == len(built), str(baked))

    # --- R2: an edit is written back --------------------------------------

    target = hinges[0]
    before = float(target[schema.MAX_ANGLE])
    target.rigid_body_constraint.limit_ang_x_upper = before + 0.25

    baked = bake.bake(objects)
    print("     bake (one edit) ->", baked, flush=True)
    check("R2: an edited constraint is rewritten", baked.rewritten == 1, str(baked))

    after = float(target[schema.MAX_ANGLE])
    check("the edited angle reached the shared property",
          abs(after - (before + 0.25)) < 1e-5, "%.6f -> %.6f" % (before, after))

    hkc = target.get(schema.field("Max Angle"))
    check("and the hkc_ field, still as a string",
          isinstance(hkc, str) and abs(float(hkc) - after) < 1e-5, repr(hkc))

    # --- R1: nothing else was touched -------------------------------------

    check("R1: the untouched fields are untouched",
          target.get(schema.field("Motor Type")) is not None
          and target.get(schema.field("Pivot B")) is not None,
          "motor_type=%r" % target.get(schema.field("Motor Type")))

    # --- R3: a mangled name is rebuilt from the pointers -------------------

    from skyrim_havok_constraints import bodies as bodies_module

    victim = hinges[1]
    body_a = Joint(victim).body_a_name
    body_b = Joint(victim).body_b_name

    # Two vocabularies, and the check has to hold both. A creature exported with
    # its skeleton.hkx has been through SKAssets' joint bridge: the properties
    # name the bodies as the *ragdoll* knows them (`Ragdoll_Neck03`) because that
    # is what HKFBX reads, while the node names stay as the *mesh* knows them
    # (`Neck2_rb`). So the properties must come back in ragdoll names and the
    # node name in mesh names, and asking either to be the other is wrong.
    object_a = bodies_module.find_body(objects, body_a)
    object_b = bodies_module.find_body(objects, body_b)
    at = victim.name.find(schema.NAME_SEPARATOR)
    victim.name = victim.name[:at + len(schema.NAME_SEPARATOR) + 3] + "4f2a91c6"
    mangled = victim.name
    victim.rigid_body_constraint.limit_ang_x_upper += 0.01  # so it counts as edited

    baked = bake.bake(objects)
    rebuilt = "%s%s%s%s" % (object_b.name, schema.NAME_SEPARATOR,
                            object_a.name, schema.ATTACH_SUFFIX)

    # The bodies come back from the pointers whatever the name does -- that is
    # the part that matters, and the only part that can be relied on: a draugr's
    # forearm-to-hand name wants 85 bytes and Blender holds 63, so on that rig
    # the name cannot be restored at all.
    check("R3: the bodies are rebuilt from the object pointers",
          (victim.get(schema.BODY_A), victim.get(schema.BODY_B)) == (body_a, body_b),
          "got %r/%r wanted %r/%r" % (victim.get(schema.BODY_A),
                                      victim.get(schema.BODY_B), body_a, body_b))

    if len(rebuilt.encode("utf-8")) <= bake.NAME_LIMIT:
        check("R3: and so is the name, where Blender can hold it",
              victim.name == rebuilt, "%s -> %s" % (mangled, victim.name))
    else:
        # It must still look like an attachment point, or a reader that goes by
        # name stops seeing it.
        check("R3: a name too long to restore still says what it is",
              schema.NAME_SEPARATOR in victim.name and len(victim.name) <= bake.NAME_LIMIT,
              True)
        print(f"     the full name needs {len(rebuilt.encode('utf-8'))} bytes; "
              f"kept {victim.name!r}")

    # --- R4: the far frame follows the joint -------------------------------
    #
    # Every joint, not a chosen one. Six of the cow's bodies arrive hidden and a
    # hidden object has no evaluated transform, which is what made an earlier
    # version of this derivation miss by a whole unit; bake forces evaluation, so
    # all of them must now come out right.
    moved = []
    for candidate in built:
        far_node = Joint(candidate).far_frame
        body = bodies_module.find_body(objects, Joint(candidate).body_a_name)
        if far_node is None or body is None:
            continue
        candidate.location = (candidate.location[0] + 0.5,
                              candidate.location[1], candidate.location[2])
        moved.append((candidate, far_node, body))

    check("there are joints to move", len(moved) == len(built),
          "%d of %d" % (len(moved), len(built)))

    baked = bake.bake(objects)
    print("     bake (all moved) ->", baked, flush=True)

    with __import__("skyrim_havok_constraints.blender_compat", fromlist=["x"]).evaluated(objects):
        worst = 0.0
        worst_name = ""
        for joint_obj, far_node, body in moved:
            relative = body.matrix_world.inverted_safe() @ joint_obj.matrix_world
            location, rotation, _ = relative.decompose()
            wanted = (mathutils.Matrix.Translation(location)
                      @ rotation.to_matrix().to_4x4())
            got = far_node.matrix_basis
            drift = max(abs(wanted[r][c] - got[r][c]) for r in range(4) for c in range(4))
            if drift > worst:
                worst, worst_name = drift, joint_obj.name

    check("R4: every far frame is recomputed from its moved joint", worst < 1e-5,
          "worst %.2e on %s" % (worst, worst_name or "-"))

    check("R4: no joint was skipped for an unreadable transform",
          not any("frame A not updated" in problem for problem in baked.problems),
          "; ".join(baked.problems[:2]) or "none skipped")

    # --- the posing path ---------------------------------------------------

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)
    objects = list(bpy.context.scene.objects)

    limited = build.build_bone_limits(objects)
    print("     bone limits ->", limited, flush=True)
    check("bone limits are built", limited.built > 0,
          "%d; %s" % (limited.built, "; ".join(limited.problems[:3])))

    # Every armature, not the first one: a creature arrives as several nifs and
    # imports as an armature each -- hair, body, skeleton -- and only the
    # skeleton carries the ragdoll. Which one comes first is not fixed, so
    # asking the first alone found a draugr's hair, said none of the seventeen
    # limits had been built, and passed on the creatures that happen to have one.
    constrained = [b
                   for armature in objects if armature.type == "ARMATURE"
                   for b in armature.pose.bones
                   if b.constraints.get(schema.BONE_LIMIT_NAME) is not None]
    check("the limits are on pose bones", len(constrained) == limited.built,
          "%d bones" % len(constrained))

    one = constrained[0].constraints[schema.BONE_LIMIT_NAME]
    check("a bone limit is in local space", one.owner_space == "LOCAL")

    removed = build.clear_bone_limits(objects)
    check("bone limits can be removed again", removed == limited.built,
          "%d removed" % removed)

    # --- and the whole thing survives a Blender round trip ----------------

    out = os.path.join(os.path.dirname(fbx), "addon_roundtrip.fbx")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)
    objects = list(bpy.context.scene.objects)
    build.build_rigid_body_constraints(bpy.context.scene, objects)
    bake.bake(objects)
    bpy.ops.export_scene.fbx(filepath=out, use_custom_props=True, add_leaf_bones=False)

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=out, use_custom_props=True)
    again = joints_in(bpy.context.scene.objects)
    check("every joint survives export and reimport", len(again) == len(joints),
          "%d of %d" % (len(again), len(joints)))

    whole = [j for j in again if Joint(j).body_a_name and Joint(j).far_frame is not None]
    check("with its bodies named and its far frame", len(whole) == len(again),
          "%d of %d" % (len(whole), len(again)))

    addon.unregister()

    print("\n%d checks failed" % len(FAILURES), flush=True)
    for name in FAILURES:
        print("   FAILED:", name, flush=True)
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
