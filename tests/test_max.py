"""The Max scripts, against a real ragdoll, on a machine with no Max.

    python3 tests/test_max.py

The scene comes from ``fixtures/skeleton_cow.json``, extracted from a vanilla
creature skeleton converted by NIFBX, and ``pymxs`` underneath is
:mod:`fakemax`, which records every property write.

What this proves: the property names, the mode enums, degrees, the axis
assignment, the centre/uncentre round trip, R1 to R4, and that a build followed by
a bake is a no-op. What it cannot prove is Max's own behaviour.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "max"))

import fakemax

FAILURES = []


def check(name, condition, detail=""):
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if not detail else "   (%s)" % detail))
    if not condition:
        FAILURES.append(name)


def build_scene(fixture):
    scene = fakemax.install()
    root = scene.add("skeleton", "BoneGeometry")

    for body_name, body in sorted(fixture["bodies"].items()):
        bone_name = "bone_%s" % (body.get("bone") or body_name)
        bone = scene.find(bone_name) or scene.add(bone_name, "BoneGeometry", root)
        node = scene.add(body_name, "Dummy", bone)
        node.user_properties.update({k: v for k, v in body["properties"].items()})
        for shape in body["shapes"]:
            scene.add(shape, "Editable_Mesh", node)

    for joint in fixture["joints"]:
        parent = scene.find(joint["parent"]) if joint["parent"] else None
        node = scene.add(joint["name"], "Dummy", parent)
        node.user_properties.update({k: v for k, v in joint["properties"].items()})
        node.transform = fakemax.Matrix3(_flat(joint["matrix_local"]))
        if joint["far_frame"] is not None:
            far = scene.add(joint["name"] + "_frame_a", "Dummy", node)
            far.user_properties["constraint_frame"] = "A"
            far.transform = fakemax.Matrix3(_flat(joint["far_frame"]))

    return scene


def _flat(rows):
    """Blender gives a column-vector matrix; Max wants the row-vector form."""
    return [rows[c][r] for r in range(4) for c in range(4)]


def main():
    with open(os.path.join(HERE, "fixtures", "skeleton_cow.json")) as handle:
        fixture = json.load(handle)

    scene = build_scene(fixture)

    from skhk_max import bake as bake_module
    from skhk_max import bodies, build, limits, maxenv, schema
    from skhk_max.joint import Joint, joints_in

    nodes = list(scene.nodes)
    joints = joints_in(nodes)

    check("the fixture's joints are all found", len(joints) == len(fixture["joints"]),
          "%d of %d" % (len(joints), len(fixture["joints"])))
    check("each joint finds its far frame",
          all(Joint(n).far_frame is not None for n in joints))

    # --- the mapping -------------------------------------------------------

    hinge = next(Joint(n) for n in joints if Joint(n).type == "LimitedHinge")
    settings, offset = limits.plan(hinge)
    plan = dict((s[0], s[1]) for s in settings)

    low, high = sorted(hinge.hinge_range)
    check("a hinge's range goes on the asymmetric twist pair, exactly",
          abs(plan["twistAngleLow"] - abs(low)) < 1e-9
          and abs(plan["twistAngleHigh"] - abs(high)) < 1e-9,
          "%.4f / %.4f rad as magnitudes" % (plan["twistAngleLow"], plan["twistAngleHigh"]))
    check("and needs no frame centring", offset == 0.0)
    check("a hinge is locked across its axis",
          plan["swing1Mode"] == maxenv.LOCKED and plan["swing2Mode"] == maxenv.LOCKED)
    check("Max counts Locked first, unlike Bullet",
          maxenv.LOCKED == 0 and maxenv.LIMITED == 1 and maxenv.FREE == 2)

    ragdoll = next(Joint(n) for n in joints if Joint(n).type == "Ragdoll")
    settings, offset = limits.plan(ragdoll)
    plan = dict((s[0], s[1]) for s in settings)
    check("a ragdoll's cone is a single symmetric swing",
          abs(plan["swing2Angle"] - ragdoll.cone_max) < 1e-9,
          "%.4f rad" % plan["swing2Angle"])

    # --- the one approximation Max needs, and its inverse ------------------

    lopsided = []
    for node in joints:
        candidate = Joint(node)
        if candidate.type != "Ragdoll":
            continue
        low, high = candidate.plane_range
        if low is not None and high is not None and abs(abs(low) - abs(high)) > 1e-6:
            lopsided.append((node, candidate, low, high))

    check("the corpus has lopsided plane limits", len(lopsided) > 0,
          "%d of %d ragdolls" % (len(lopsided),
                                 sum(1 for n in joints if Joint(n).type == "Ragdoll")))

    node, candidate, low, high = lopsided[0]
    settings, offset = limits.plan(candidate)
    plan = dict((s[0], s[1]) for s in settings)

    check("a lopsided plane limit turns the frame instead of being flattened",
          offset != 0.0, "offset %.4f rad on %s" % (offset, candidate.name[:32]))

    recovered = limits.uncentre(offset, plan["swing1Angle"])
    check("and centring is exactly invertible",
          abs(recovered[0] - min(low, high)) < 1e-9
          and abs(recovered[1] - max(low, high)) < 1e-9,
          "%.6f..%.6f -> %.6f..%.6f" % (low, high, recovered[0], recovered[1]))

    check("a symmetric limit is left alone", limits.centre((-0.5, 0.5))[0] == 0.0)
    check("a one-sided range is detected, not silently flattened",
          limits.one_sided((0.2, 0.7)) and not limits.one_sided((-0.2, 0.7)))

    # --- the build ---------------------------------------------------------

    result = build.build_constraints(nodes)
    print("     build ->", result)
    check("every joint built", result.built == len(joints),
          "%d of %d; %s" % (result.built, len(joints), "; ".join(result.problems[:2])))
    check("only the lopsided ones had their frame centred",
          result.centred == len(lopsided), "%d centred" % result.centred)

    modifiers = [w for w in scene.writes if w[0] == "MassFX_RBody" and w[1] == "type"]
    check("a rigid body modifier went on per body",
          len(modifiers) == len(fixture["bodies"]),
          "%d of %d" % (len(modifiers), len(fixture["bodies"])))
    check("and it is Static, not Dynamic",
          all(v == maxenv.STATIC_BODY for _, _, v in modifiers))

    # --- degrees, which is the likeliest thing to be wrong -----------------

    hinge_node = next(n for n in joints if Joint(n).type == "LimitedHinge")
    constraint = bake_module._existing(hinge_node)
    wanted = math.degrees(abs(min(Joint(hinge_node).hinge_range)))
    check("an angle reached the constraint in degrees",
          abs(constraint.properties["twistAngleLow"] - wanted) < 1e-6,
          "%.4f vs %.4f" % (constraint.properties["twistAngleLow"], wanted))

    # --- R2 ----------------------------------------------------------------

    baked = bake_module.bake(nodes)
    print("     bake (untouched) ->", baked)
    check("R2: an untouched constraint bakes to nothing",
          baked.rewritten == 0 and baked.unchanged == len(joints), str(baked))

    # R2 again, on the joint whose frame was centred: the approximation must not
    # drift when nobody has touched it.
    centred_node = lopsided[0][0]
    before = Joint(centred_node).plane_range
    baked = bake_module.bake(nodes)
    after = Joint(centred_node).plane_range
    check("R2: and the centred one has not drifted",
          abs(before[0] - after[0]) < 1e-12 and abs(before[1] - after[1]) < 1e-12,
          "%.8f..%.8f" % after)

    constraint.properties["twistAngleHigh"] += 10.0
    baked = bake_module.bake(nodes)
    print("     bake (one edit) ->", baked)
    check("R2: an edited constraint is rewritten", baked.rewritten == 1, str(baked))

    check("the edit came back as radians in the shared property",
          abs(Joint(hinge_node).hinge_range[1]
              - math.radians(constraint.properties["twistAngleHigh"])) < 1e-6,
          "%.6f" % Joint(hinge_node).hinge_range[1])

    hkc = maxenv.read_raw(hinge_node, schema.field("Max Angle"))
    check("and reached the hkc_ field, still a string",
          isinstance(hkc, str)
          and abs(float(hkc) - Joint(hinge_node).hinge_range[1]) < 1e-6, repr(hkc))

    # A centred joint, edited, must come back uncentred against its own offset.
    centred_constraint = bake_module._existing(centred_node)
    centred_constraint.properties["swing1Angle"] += 5.0
    bake_module.bake(nodes)
    span = math.radians(centred_constraint.properties["swing1Angle"])
    stored_offset = float(maxenv.read_raw(centred_node, schema.SWING_OFFSET))
    expected = limits.uncentre(stored_offset, span)
    got = Joint(centred_node).plane_range
    check("an edited centred limit is uncentred against its recorded offset",
          abs(got[0] - expected[0]) < 1e-6 and abs(got[1] - expected[1]) < 1e-6,
          "%.6f..%.6f" % got)

    # --- R1 ----------------------------------------------------------------

    check("R1: the fields this does not understand are untouched",
          maxenv.read_raw(hinge_node, schema.field("Motor Type")) is not None
          and maxenv.read_raw(hinge_node, schema.field("Pivot B")) is not None)

    # --- R3 ----------------------------------------------------------------

    victim = next(n for n in joints if Joint(n).type == "Ragdoll" and n is not centred_node)
    joint = Joint(victim)
    body_a, body_b = joint.body_a_name, joint.body_b_name
    at = victim.name.find(schema.NAME_SEPARATOR)
    victim.name = victim.name[:at + len(schema.NAME_SEPARATOR) + 3] + "4f2a91c6"
    mangled = victim.name
    bake_module._existing(victim).properties["swing2Angle"] += 3.0

    bake_module.bake(nodes)
    rebuilt = "%s%s%s%s" % (body_b, schema.NAME_SEPARATOR, body_a, schema.ATTACH_SUFFIX)
    check("R3: a truncated name is rebuilt from the constraint's bodies",
          victim.name == rebuilt, "%s -> %s" % (mangled, victim.name))

    # --- R4 ----------------------------------------------------------------

    mover = next(n for n in joints if Joint(n).far_frame is not None)
    joint = Joint(mover)
    far = joint.far_frame
    body = bodies.find_body(nodes, joint.body_a_name)
    # Moved and nothing else: the signature covers the joint's placement, so this
    # alone has to count as an edit or frame A would keep its old position.
    mover.transform = fakemax.Matrix3(list(mover.transform))
    mover.transform[12] += 3.0

    baked = bake_module.bake(nodes)
    check("R4: moving a joint alone counts as an edit", baked.rewritten >= 1,
          str(baked))

    expected = mover.transform * fakemax.inverse(body.transform)
    drift = max(abs(a - b) for a, b in zip(expected, far.transform))
    check("R4: the far frame is recomputed as joint * inverse(bodyA)", drift < 1e-6,
          "Max is row-vector like Maya, so the reverse of Blender's order; "
          "drift %.2e" % drift)

    # --- the posing path ---------------------------------------------------

    scene2 = build_scene(fixture)
    limited = build.build_rotation_limits(list(scene2.nodes))
    print("     rotation limits ->", limited)
    check("rotation limits are built", limited.built == len(fixture["joints"]),
          "%d; %s" % (limited.built, "; ".join(limited.problems[:2])))

    tracks = [n.controller.tracks["Rotation"] for n in scene2.nodes
              if n.controller.tracks["Rotation"].ranges]
    check("they went on rotation tracks", len(tracks) > 0, "%d tracks" % len(tracks))
    check("and their numbers are degrees",
          any(abs(v) > math.pi for track in tracks
              for pair in track.ranges.values() for v in pair))

    cleared = build.clear_rotation_limits(list(scene2.nodes))
    check("rotation limits can be cleared again", cleared == limited.built,
          "%d cleared" % cleared)

    print("\n%d checks failed" % len(FAILURES))
    for name in FAILURES:
        print("   FAILED:", name)
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
