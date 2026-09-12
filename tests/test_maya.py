"""The Maya scripts, against a real ragdoll, on a machine with no Maya.

    python3 tests/test_maya.py

The scene is built from ``fixtures/skeleton_cow.json``, which was extracted from
a vanilla creature skeleton converted by NIFBX, so the numbers are real. The
``maya.cmds`` underneath is :mod:`fakemaya`, which records every ``setAttr``.

What this proves: the attribute names, the enum values, the unit conversion, the
axis assignment, R1 to R4, and that a build followed by a bake is a no-op. What
it cannot prove is Maya's own behaviour -- whether Bullet is content with a
six-DOF constraint built this way is a question only Maya answers, and it has not
been asked.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "maya"))

import fakemaya

FAILURES = []


def check(name, condition, detail=""):
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if not detail else "   (%s)" % detail))
    if not condition:
        FAILURES.append(name)


def load_fixture():
    with open(os.path.join(HERE, "fixtures", "skeleton_cow.json")) as handle:
        return json.load(handle)


def build_scene(fixture):
    """The fixture as a Maya scene: joints under bodies under joints."""
    scene = fakemaya.install()

    scene.add("skeleton", "joint")

    for body_name, body in sorted(fixture["bodies"].items()):
        bone = "bone_%s" % (body.get("bone") or body_name)
        if bone not in scene.nodes:
            scene.add(bone, "joint", parent="skeleton")
        scene.add(body_name, "transform", parent=bone)
        for key, value in body["properties"].items():
            scene.set_user_attr(body_name, key, value)
        for shape in body["shapes"]:
            scene.add(shape, "transform", parent=body_name)
            scene.add(shape + "Shape", "mesh", parent=shape)

    for joint in fixture["joints"]:
        parent = joint["parent"] if joint["parent"] in scene.nodes else None
        scene.add(joint["name"], "transform", parent=parent)
        for key, value in joint["properties"].items():
            scene.set_user_attr(joint["name"], key, value)
        scene.nodes[joint["name"]].matrix = _flat(joint["matrix_local"])
        if joint["far_frame"] is not None:
            far = joint["name"] + "_frame_a"
            scene.add(far, "transform", parent=joint["name"])
            scene.set_user_attr(far, "constraint_frame", "A")
            scene.nodes[far].matrix = _flat(joint["far_frame"])

    return scene


def _flat(rows):
    """Blender gives a column-vector matrix; Maya wants the row-vector form."""
    return [rows[c][r] for r in range(4) for c in range(4)]


def fake_bullet(scene):
    """Stand in for ``maya.app.mayabullet``, making nodes the real one would."""
    import maya.app.mayabullet as mayabullet
    import types

    constraint_attrs = (
        ["constraintType", "useReferenceFrame"]
        + ["%sConstraint%s" % (k, a) for k in ("linear", "angular") for a in "XYZ"]
        + ["%sConstraint%s%s" % (k, b, a) for k in ("linear", "angular")
           for b in ("Min", "Max") for a in "XYZ"])

    body_attrs = ["bodyType", "colliderShapeType", "mass", "friction",
                  "restitution", "linearDamping", "angularDamping"]

    class RigidBody:
        class CreateRigidBody:
            @staticmethod
            def command(transformName=None, **kwargs):
                name = transformName + "_bullet"
                scene.add(name, "bulletRigidBodyShape", parent=transformName)
                for attribute in body_attrs:
                    scene.set_user_attr(name, attribute, 0.0)
                return [name]

    class RigidBodyConstraint:
        class CreateRigidBodyConstraint:
            @staticmethod
            def command(rigidBodyA=None, rigidBodyB=None, parent=None, **kwargs):
                name = "%s_rbc" % parent
                scene.add(name, "bulletRigidBodyConstraintShape", parent=parent)
                for attribute in constraint_attrs:
                    kind = "doubleAngle" if "Constraint" in attribute and (
                        attribute.endswith(tuple("XYZ")) and "angular" in attribute
                        and ("Min" in attribute or "Max" in attribute)) else "double"
                    scene.set_user_attr(name, attribute, 0.0, kind)
                scene.set_user_attr(name, "rigidBodyA", "")
                scene.set_user_attr(name, "rigidBodyB", "")
                import maya.cmds as cmds
                cmds.connectAttr(rigidBodyA + ".outRigidBodyData", name + ".rigidBodyA")
                cmds.connectAttr(rigidBodyB + ".outRigidBodyData", name + ".rigidBodyB")
                return [name]

    body_module = types.ModuleType("maya.app.mayabullet.RigidBody")
    body_module.CreateRigidBody = RigidBody.CreateRigidBody
    constraint_module = types.ModuleType("maya.app.mayabullet.RigidBodyConstraint")
    constraint_module.CreateRigidBodyConstraint = RigidBodyConstraint.CreateRigidBodyConstraint

    mayabullet.RigidBody = body_module
    mayabullet.RigidBodyConstraint = constraint_module
    sys.modules["maya.app.mayabullet.RigidBody"] = body_module
    sys.modules["maya.app.mayabullet.RigidBodyConstraint"] = constraint_module


def main():
    fixture = load_fixture()
    scene = build_scene(fixture)
    fake_bullet(scene)

    from skhk_maya import bake as bake_module
    from skhk_maya import bodies, build, limits, mayaenv, schema
    from skhk_maya.joint import Joint, joints_in

    nodes = list(scene.nodes)
    joints = joints_in(nodes)

    check("the fixture's joints are all found", len(joints) == len(fixture["joints"]),
          "%d of %d" % (len(joints), len(fixture["joints"])))

    far_framed = [j for j in joints if Joint(j).far_frame is not None]
    check("each joint finds its far frame", len(far_framed) == len(joints),
          "%d of %d" % (len(far_framed), len(joints)))

    typed = {}
    for node in joints:
        typed.setdefault(Joint(node).type, 0)
        typed[Joint(node).type] += 1
    check("both constraint kinds are present",
          typed.get("Ragdoll", 0) > 0 and typed.get("LimitedHinge", 0) > 0, str(typed))

    # --- the mapping -------------------------------------------------------

    hinge = next(Joint(n) for n in joints if Joint(n).type == "LimitedHinge")
    plan = dict((s[0], s[1]) for s in limits.plan(hinge))

    check("a hinge maps to six-DOF, not cone-twist",
          plan["constraintType"] == mayaenv.SIX_DOF,
          "cone-twist has no angularConstraintMin, and Havok's hinge range is asymmetric")

    low, high = sorted(hinge.hinge_range)
    check("the hinge range lands on the twist axis in radians",
          abs(plan["angularConstraintMinX"] - low) < 1e-9
          and abs(plan["angularConstraintMaxX"] - high) < 1e-9,
          "%.6f..%.6f" % (plan["angularConstraintMinX"], plan["angularConstraintMaxX"]))

    check("a hinge is locked across its axis",
          plan["angularConstraintY"] == mayaenv.LOCKED
          and plan["angularConstraintZ"] == mayaenv.LOCKED)

    check("a hinge's pivot cannot slide",
          all(plan["linearConstraint%s" % a] == mayaenv.LOCKED for a in "XYZ"))

    ragdoll = next(Joint(n) for n in joints if Joint(n).type == "Ragdoll")
    plan = dict((s[0], s[1]) for s in limits.plan(ragdoll))
    twist_lo, twist_hi = sorted(ragdoll.twist_range)
    plane_lo, plane_hi = sorted(ragdoll.plane_range)

    check("a ragdoll's twist goes on X",
          abs(plan["angularConstraintMinX"] - twist_lo) < 1e-9
          and abs(plan["angularConstraintMaxX"] - twist_hi) < 1e-9)
    check("its plane limit goes on Y, asymmetric and intact",
          abs(plan["angularConstraintMinY"] - plane_lo) < 1e-9
          and abs(plan["angularConstraintMaxY"] - plane_hi) < 1e-9,
          "%.4f..%.4f" % (plane_lo, plane_hi))
    check("its cone becomes a symmetric limit on Z",
          abs(plan["angularConstraintMaxZ"] - ragdoll.cone_max) < 1e-9
          and abs(plan["angularConstraintMinZ"] + ragdoll.cone_max) < 1e-9,
          "+/-%.4f" % ragdoll.cone_max)

    # The reason six-DOF rather than cone-twist matters, in numbers. The cow's
    # stifle runs -45 to +9 degrees; a symmetric span cannot hold that, and
    # centring the frame to fake it is what spec §5.3 has to do for Max.
    lopsided = []
    for node in joints:
        candidate = Joint(node)
        for low, high in (candidate.hinge_range, candidate.plane_range,
                          candidate.twist_range):
            if low is None or high is None:
                continue
            if abs(abs(low) - abs(high)) > 1e-6:
                lopsided.append((node, candidate, low, high))

    check("the corpus has lopsided ranges at all", len(lopsided) > 0,
          "%d of them" % len(lopsided))

    worst = max(lopsided, key=lambda row: abs(abs(row[2]) - abs(row[3])))
    worst_plan = dict((s[0], s[1]) for s in limits.plan(worst[1]))
    lower, upper = sorted((worst[2], worst[3]))
    kept = any(abs(worst_plan.get("angularConstraintMin%s" % a, 1e9) - lower) < 1e-9
               and abs(worst_plan.get("angularConstraintMax%s" % a, 1e9) - upper) < 1e-9
               for a in "XYZ")

    check("and the most lopsided one survives intact", kept,
          "%.1f to %.1f degrees on %s"
          % (math.degrees(lower), math.degrees(upper), Joint(worst[0]).name[:34]))

    # --- the build ---------------------------------------------------------

    result = build.build_rigid_body_constraints(nodes)
    print("     build ->", result)
    check("every joint built", result.built == len(joints),
          "%d of %d; %s" % (result.built, len(joints), "; ".join(result.problems[:2])))

    made = [(n, a, v) for n, a, v in scene.set_calls if a == "constraintType"]
    check("a constraint type was written per joint", len(made) == len(joints),
          "%d writes" % len(made))
    check("and it was six-DOF every time",
          all(v == mayaenv.SIX_DOF for _, _, v in made))

    # --- the unit conversion, which is the likeliest thing to be wrong -----

    degrees_written = [(n, a, v) for n, a, v in scene.set_calls
                       if a == "angularConstraintMaxX"]
    check("an angle reached the node in degrees, not radians",
          any(abs(v) > math.pi for _, _, v in degrees_written),
          "largest %.3f" % max(abs(v) for _, _, v in degrees_written))

    hinge_node = next(n for n in joints if Joint(n).type == "LimitedHinge")
    constraint = bake_module._constraint_under(hinge_node)
    wrote = scene.nodes[constraint].attrs["angularConstraintMaxX"]
    wanted = math.degrees(sorted(Joint(hinge_node).hinge_range)[1])
    check("and it is exactly the right number of degrees",
          abs(wrote - wanted) < 1e-6, "%.6f vs %.6f" % (wrote, wanted))

    # --- R2 ----------------------------------------------------------------

    baked = bake_module.bake(nodes)
    print("     bake (untouched) ->", baked)
    check("R2: an untouched constraint bakes to nothing",
          baked.rewritten == 0 and baked.unchanged == len(joints), str(baked))

    edited = math.degrees(sorted(Joint(hinge_node).hinge_range)[1]) + 10.0
    scene.nodes[constraint].attrs["angularConstraintMaxX"] = edited
    before = Joint(hinge_node).hinge_range[1]

    baked = bake_module.bake(nodes)
    print("     bake (one edit) ->", baked)
    check("R2: an edited constraint is rewritten", baked.rewritten == 1, str(baked))

    after = Joint(hinge_node).hinge_range[1]
    check("the edit came back as radians in the shared property",
          abs(after - math.radians(edited)) < 1e-6,
          "%.6f -> %.6f (wanted %.6f)" % (before, after, math.radians(edited)))

    hkc = scene.nodes[hinge_node].attrs.get(schema.field("Max Angle"))
    check("and reached the hkc_ field, still a string",
          isinstance(hkc, str) and abs(float(hkc) - after) < 1e-6, repr(hkc))

    # --- R1 ----------------------------------------------------------------

    untouched = scene.nodes[hinge_node].attrs
    check("R1: the fields this does not understand are untouched",
          untouched.get(schema.field("Motor Type")) is not None
          and untouched.get(schema.field("Pivot B")) is not None
          and untouched.get(schema.field("Perp Axis In B1")) is not None,
          "motor_type=%r" % untouched.get(schema.field("Motor Type")))

    # --- R3 ----------------------------------------------------------------

    victim = next(n for n in joints if Joint(n).type == "Ragdoll")
    joint = Joint(victim)
    body_a, body_b = joint.body_a_name, joint.body_b_name
    at = victim.find(schema.NAME_SEPARATOR)
    mangled = victim[:at + len(schema.NAME_SEPARATOR) + 3] + "4f2a91c6"
    import maya.cmds as cmds
    cmds.rename(victim, mangled)

    victim_constraint = bake_module._constraint_under(mangled)
    scene.nodes[victim_constraint].attrs["angularConstraintMaxZ"] += 5.0

    baked = bake_module.bake(list(scene.nodes))
    rebuilt = "%s%s%s%s" % (body_b, schema.NAME_SEPARATOR, body_a, schema.ATTACH_SUFFIX)
    check("R3: a truncated name is rebuilt from the rigid body connections",
          rebuilt in scene.nodes, "%s -> %s" % (mangled, rebuilt))

    # --- R4 ----------------------------------------------------------------

    nodes = list(scene.nodes)
    mover = next(n for n in joints_in(nodes) if Joint(n).far_frame is not None)
    joint = Joint(mover)
    far = joint.far_frame
    body = bodies.find_body(nodes, joint.body_a_name)

    scene.nodes[mover].matrix[12] += 3.0
    scene.nodes[bake_module._constraint_under(mover)].attrs["angularConstraintMaxX"] += 1.0

    bake_module.bake(nodes)

    import maya.api.OpenMaya as om
    joint_world = om.MMatrix(scene.nodes[mover].matrix)
    body_world = om.MMatrix(scene.nodes[body].matrix)
    wanted = joint_world * body_world.inverse()
    got = scene.nodes[far].matrix
    drift = max(abs(a - b) for a, b in zip(wanted, got))
    check("R4: the far frame is recomputed as joint * inverse(bodyA)", drift < 1e-6,
          "Maya is row-vector, so the order is the reverse of Blender's; drift %.2e" % drift)

    # --- the posing path ---------------------------------------------------

    scene2 = build_scene(fixture)
    fake_bullet(scene2)
    limited = build.build_joint_limits(list(scene2.nodes))
    print("     joint limits ->", limited)
    check("joint limits are built", limited.built == len(fixture["joints"]),
          "%d; %s" % (limited.built, "; ".join(limited.problems[:2])))

    check("they went on joint nodes, not on the bodies",
          all(scene2.nodes[n].kind == "joint" for n in scene2.limits),
          "%d nodes limited" % len(scene2.limits))

    sample = next(iter(scene2.limits.values()))
    check("a limit is enabled on both ends of an axis",
          sample.get("enableRotationX") == (True, True)
          or sample.get("enableRotationY") == (True, True), str(sorted(sample))[:80])

    degrees_ok = any(abs(v) > math.pi
                     for options in scene2.limits.values()
                     for key, value in options.items() if key.startswith("rotation")
                     for v in value)
    check("and its numbers are degrees", degrees_ok)

    cleared = build.clear_joint_limits(list(scene2.nodes))
    check("joint limits can be cleared again", cleared == limited.built,
          "%d cleared" % cleared)

    print("\n%d checks failed" % len(FAILURES))
    for name in FAILURES:
        print("   FAILED:", name)
    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
