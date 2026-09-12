"""Turning the properties into constraints Maya can use.

Two paths, as in Blender and for the same reason (spec §6.1): Bullet rigid body
constraints for tuning a ragdoll, and joint rotation limits for posing. The
second needs no plug-in at all -- ``transformLimits`` is core Maya -- which makes
it the one an animator can always use.
"""

import maya.cmds as cmds

from . import bodies, limits, mayaenv, schema
from .joint import Joint, all_transforms, joints_in
from .mayaenv import short_name


class Result:
    def __init__(self):
        self.built = 0
        self.skipped = 0
        self.bodies = 0
        self.problems = []

    def problem(self, name, why):
        self.skipped += 1
        self.problems.append("%s: %s" % (short_name(name), why))

    def __str__(self):
        text = "%d constraint%s" % (self.built, "" if self.built == 1 else "s")
        if self.bodies:
            text += ", %d bodies" % self.bodies
        if self.skipped:
            text += ", %d skipped" % self.skipped
        return text


def build_rigid_body_constraints(nodes=None, dynamic=False):
    """Build a Bullet constraint on every joint among *nodes*."""
    result = Result()

    if not mayaenv.bullet_available():
        result.problems.append(
            "the Bullet plug-in is not available, so there is nothing to build "
            "constraints with -- Build Joint Limits needs no plug-in")
        return result

    from maya.app.mayabullet import RigidBodyConstraint

    pool = list(nodes) if nodes else all_transforms()

    for node in joints_in(pool):
        joint = Joint(node)

        if limits.bullet_type_of(joint) is None:
            result.problem(node, "no Bullet equivalent for %r" % (joint.type or "unknown"))
            continue

        body_a = bodies.find_body(pool, joint.body_a_name)
        body_b = bodies.find_body(pool, joint.body_b_name)

        if body_a is None or body_b is None:
            missing = joint.body_a_name if body_a is None else joint.body_b_name
            result.problem(node, "body %r is not in the scene" % missing)
            continue

        shape_a = bodies.shape_of(body_a)
        shape_b = bodies.shape_of(body_b)

        if shape_a is None or shape_b is None:
            result.problem(node, "a body has no collision geometry to simulate")
            continue

        rigid = []

        for body, shape in ((body_a, shape_a), (body_b, shape_b)):
            existing = bodies.rigid_body_of(shape)
            if existing is None:
                existing = bodies.make_rigid_body(body, shape, dynamic)
                if existing is not None:
                    result.bodies += 1
            rigid.append(existing)

        rigid_a, rigid_b = rigid

        if rigid_a is None or rigid_b is None:
            result.problem(node, "Bullet would not make a rigid body for a shape")
            continue

        existing = _constraint_under(node)

        if existing is None:
            # Havok's entity A is the body the joint moves, and it goes first so
            # that the limits are expressed in the same body's frame as the file
            # expresses them in.
            created = RigidBodyConstraint.CreateRigidBodyConstraint.command(
                rigidBodyA=rigid_a, rigidBodyB=rigid_b, parent=node)
            existing = _first(created) or _constraint_under(node)

        if existing is None:
            result.problem(node, "Bullet would not make a constraint")
            continue

        written = _apply(existing, joint)
        _remember(node, limits.signature(written, _frame_of(node)))
        result.built += 1

    return result


def _apply(constraint, joint):
    """Write the plan onto a Bullet constraint node, converting angles once."""
    written = []

    for setting in limits.plan(joint):
        attribute, value = setting[0], setting[1]
        is_angle = len(setting) > 2 and setting[2] == "angle"
        full = "%s.%s" % (constraint, attribute)

        if not cmds.objExists(full):
            continue

        try:
            cmds.setAttr(full, mayaenv.to_ui_angle(full, value) if is_angle else value)
        except (RuntimeError, ValueError):
            continue

        written.append((attribute, value))

    return written


def _frame_of(node):
    """The joint's own placement, for the signature. See limits.signature."""
    try:
        return cmds.xform(node, query=True, matrix=True, worldSpace=True)
    except (RuntimeError, ValueError):
        return None


def _constraint_under(node):
    found = cmds.listRelatives(node, children=True, fullPath=True,
                               type=mayaenv.CONSTRAINT_NODE) or []
    return found[0] if found else None


def _first(created):
    if isinstance(created, (list, tuple)):
        return created[0] if created else None
    return created


def _remember(node, signature):
    attribute = "%s.%s" % (node, schema.SIGNATURE)
    if not cmds.objExists(attribute):
        cmds.addAttr(node, longName=schema.SIGNATURE, dataType="string")
    cmds.setAttr(attribute, signature, type="string")


def clear_rigid_body_constraints(nodes=None):
    """Undo the build, leaving every property alone."""
    removed = 0
    pool = list(nodes) if nodes else all_transforms()

    for node in joints_in(pool):
        constraint = _constraint_under(node)
        if constraint is not None:
            cmds.delete(constraint)
            removed += 1

        attribute = "%s.%s" % (node, schema.SIGNATURE)
        if cmds.objExists(attribute):
            cmds.deleteAttr(attribute)

    for node in pool:
        for shape in cmds.listRelatives(node, children=True, fullPath=True,
                                        type=mayaenv.BODY_NODE) or []:
            if bodies.was_generated(shape):
                cmds.delete(shape)

    return removed


# --- the animation path ----------------------------------------------------


def build_joint_limits(nodes=None):
    """Put each joint's angular ranges on the Maya joint the body rides.

    ``transformLimits`` is core Maya, so this works with no plug-in and in every
    version. It is the path an animator wants: the limits clamp the pose as the
    rig is handled, with nothing simulating.
    """
    result = Result()
    pool = list(nodes) if nodes else all_transforms()

    for node in joints_in(pool):
        joint = Joint(node)
        body_a = bodies.find_body(pool, joint.body_a_name)

        if body_a is None:
            result.problem(node, "body %r is not in the scene" % joint.body_a_name)
            continue

        target = _joint_above(body_a)

        if target is None:
            result.problem(node, "%s does not hang off a joint" % short_name(body_a))
            continue

        angular = limits.angular_limits(joint)

        if all(limit is None for limit in angular):
            result.problem(node, "nothing to limit")
            continue

        for axis, limit in zip(limits.AXES, angular):
            lower = "%s.rotate%s" % (target, axis)
            enable = {"enableRotation%s" % axis: (limit is not None, limit is not None)}

            if limit is None:
                cmds.transformLimits(target, **enable)
                continue

            low, high = sorted(limit)
            cmds.transformLimits(
                target,
                **{"rotation%s" % axis: (mayaenv.to_ui_angle(lower, low),
                                         mayaenv.to_ui_angle(lower, high)),
                   "enableRotation%s" % axis: (True, True)})

        result.built += 1

    return result


def _joint_above(node):
    """The nearest ``joint`` at or above a node.

    Maya's FBX import makes the armature's bones into ``joint`` nodes and parents
    the body transform under one of them, so the joint to limit is found by
    walking up rather than by reading a parent-bone property as in Blender.
    """
    current = node

    while current:
        if cmds.nodeType(current) == "joint":
            return current
        parents = cmds.listRelatives(current, parent=True, fullPath=True)
        current = parents[0] if parents else None

    return None


def clear_joint_limits(nodes=None):
    """Turn off only the limits this add-on turned on."""
    cleared = 0
    pool = list(nodes) if nodes else all_transforms()

    for node in joints_in(pool):
        joint = Joint(node)
        body_a = bodies.find_body(pool, joint.body_a_name)
        target = _joint_above(body_a) if body_a else None

        if target is None:
            continue

        cmds.transformLimits(target, enableRotationX=(False, False),
                             enableRotationY=(False, False),
                             enableRotationZ=(False, False))
        cleared += 1

    return cleared
