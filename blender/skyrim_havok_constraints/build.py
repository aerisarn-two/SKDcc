"""Turning the properties into constraints Blender can use.

Two paths, because two different people want this and they want different
things (spec §6.1):

* the **rigid body** path, for tuning a ragdoll: real bodies, real
  constraints, a simulation;
* the **bone limit** path, for hand animation: the same cone and twist ranges
  as pose-bone limits, clamping the pose live, with no physics at all.

Both are reversible and neither touches a property. The properties are the
truth; these are a view of them.
"""

import bpy

from . import bodies, limits, schema
from .blender_compat import active, ensure_rigid_body_world
from .joint import Joint, joints_in


class Result:
    """What a build did, for the operator to report."""

    def __init__(self):
        self.built = 0
        self.skipped = 0
        self.bodies = 0
        self.problems = []

    def problem(self, joint, why):
        self.skipped += 1
        self.problems.append("%s: %s" % (joint.obj.name, why))

    def __str__(self):
        text = "%d constraint%s" % (self.built, "" if self.built == 1 else "s")
        if self.bodies:
            text += ", %d bodies" % self.bodies
        if self.skipped:
            text += ", %d skipped" % self.skipped
        return text


def build_rigid_body_constraints(scene, objects, dynamic=False):
    """Build a Blender rigid body constraint on every joint among *objects*."""
    result = Result()
    ensure_rigid_body_world(scene)
    pool = list(objects)

    for obj in joints_in(pool):
        joint = Joint(obj)

        if limits.blender_type_of(joint) is None:
            result.problem(joint, "no Blender equivalent for %r" % (joint.type or "unknown"))
            continue

        body_a = bodies.find_body(pool, joint.body_a_name)
        body_b = bodies.find_body(pool, joint.body_b_name)

        if body_a is None or body_b is None:
            missing = joint.body_a_name if body_a is None else joint.body_b_name
            result.problem(joint, "body %r is not in the scene" % missing)
            continue

        shape_a = bodies.shape_of(body_a)
        shape_b = bodies.shape_of(body_b)

        if shape_a is None or shape_b is None:
            result.problem(joint, "a body has no collision shape to simulate")
            continue

        for body, shape in ((body_a, shape_a), (body_b, shape_b)):
            if shape.rigid_body is None:
                bodies.make_rigid_body(scene, body, shape, dynamic)
                result.bodies += 1

        rbc = _ensure_constraint(obj)

        # Havok's entity A is the body the joint moves, and Blender's object1
        # is the first of the pair; keeping A first means the two agree about
        # which body the limits are expressed in.
        rbc.object1 = shape_a
        rbc.object2 = shape_b

        limits.apply(rbc, joint)

        obj[schema.SIGNATURE] = limits.signature(obj)
        result.built += 1

    return result


def _ensure_constraint(obj):
    if obj.rigid_body_constraint is None:
        with active(obj):
            bpy.ops.rigidbody.constraint_add()
    return obj.rigid_body_constraint


def clear_rigid_body_constraints(scene, objects, remove_bodies=True):
    """Undo :func:`build_rigid_body_constraints`, leaving the properties."""
    removed = 0
    pool = list(objects)

    for obj in joints_in(pool):
        if obj.rigid_body_constraint is not None:
            with active(obj):
                bpy.ops.rigidbody.constraint_remove()
            removed += 1
        if schema.SIGNATURE in obj.keys():
            del obj[schema.SIGNATURE]

    if remove_bodies:
        for obj in pool:
            if obj.type == "MESH":
                bodies.clear_rigid_body(obj)

    return removed


# --- the animation path ----------------------------------------------------


def build_bone_limits(objects):
    """Put the joint's angular ranges on the pose bone the body rides.

    A Limit Rotation constraint clamps the bone while the animator poses it,
    which is what the limits are for outside a simulation. The bone is the one
    the moving body -- Havok's entity A -- is parented to, because that is the
    bone the joint restrains.

    Approximate in the same way and for the same reason as
    :func:`limits.angular_limits`: a Blender bone's rotation limits are per
    axis in the bone's own space, and a Havok cone is not. Good enough to stop
    an elbow bending backwards, which is the point.
    """
    result = Result()
    pool = list(objects)

    for obj in joints_in(pool):
        joint = Joint(obj)
        body_a = bodies.find_body(pool, joint.body_a_name)

        if body_a is None:
            result.problem(joint, "body %r is not in the scene" % joint.body_a_name)
            continue

        if body_a.parent is None or body_a.parent.type != "ARMATURE" or not body_a.parent_bone:
            result.problem(joint, "%s is not parented to a bone" % body_a.name)
            continue

        armature = body_a.parent
        pose_bone = armature.pose.bones.get(body_a.parent_bone)

        if pose_bone is None:
            result.problem(joint, "bone %r is not in %s" % (body_a.parent_bone, armature.name))
            continue

        angular = limits.angular_limits(joint)

        if all(limit is None for limit in angular):
            result.problem(joint, "nothing to limit")
            continue

        constraint = pose_bone.constraints.get(schema.BONE_LIMIT_NAME)
        if constraint is None:
            constraint = pose_bone.constraints.new("LIMIT_ROTATION")
            constraint.name = schema.BONE_LIMIT_NAME

        constraint.owner_space = "LOCAL"

        for axis, limit in zip("xyz", angular):
            setattr(constraint, "use_limit_%s" % axis, limit is not None)
            if limit is not None:
                lower, upper = limit
                setattr(constraint, "min_%s" % axis, min(lower, upper))
                setattr(constraint, "max_%s" % axis, max(lower, upper))

        result.built += 1

    return result


def clear_bone_limits(objects):
    """Remove only the constraints this add-on named, never a rigger's own."""
    removed = 0

    for armature in {o for o in objects if o.type == "ARMATURE"}:
        for pose_bone in armature.pose.bones:
            constraint = pose_bone.constraints.get(schema.BONE_LIMIT_NAME)
            if constraint is not None:
                pose_bone.constraints.remove(constraint)
                removed += 1

    return removed
