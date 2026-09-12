"""Turning the properties into constraints Max can use.

Two paths, as in the other hosts (spec §6.1): MassFX UConstraints for tuning a
ragdoll, and rotation controller limits for posing.
"""

from pymxs import runtime as rt

from . import bodies, limits, maxenv, schema
from .joint import Joint, joints_in


class Result:
    def __init__(self):
        self.built = 0
        self.skipped = 0
        self.bodies = 0
        self.centred = 0
        self.problems = []

    def problem(self, node, why):
        self.skipped += 1
        self.problems.append("%s: %s" % (node.name if hasattr(node, "name") else node, why))

    def __str__(self):
        text = "%d constraint%s" % (self.built, "" if self.built == 1 else "s")
        if self.bodies:
            text += ", %d bodies" % self.bodies
        if self.centred:
            text += ", %d frames centred" % self.centred
        if self.skipped:
            text += ", %d skipped" % self.skipped
        return text


def build_constraints(nodes=None, dynamic=False):
    """Build a MassFX UConstraint on every joint among *nodes*."""
    result = Result()

    if not maxenv.massfx_available():
        result.problems.append(
            "MassFX is not available, so there is nothing to build constraints "
            "with -- Build Rotation Limits needs no plug-in")
        return result

    pool = list(nodes) if nodes else maxenv.scene_nodes()

    for node in joints_in(pool):
        joint = Joint(node)

        if not limits.supported(joint):
            result.problem(node, "no MassFX equivalent for %r" % (joint.type or "unknown"))
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

        for body, shape in ((body_a, shape_a), (body_b, shape_b)):
            if bodies.rigid_body_of(shape) is None:
                bodies.make_rigid_body(body, shape, dynamic)
                result.bodies += 1

        for label, limit in (("twist", limits.twist_range(joint)),
                             ("plane", limits.plane_range(joint))):
            if limits.one_sided(limit):
                result.problems.append(
                    "%s: the %s range %.1f to %.1f degrees is entirely on one "
                    "side of zero, and Max's limits are magnitudes about the "
                    "frame -- it has been centred, which moves the frame"
                    % (node.name, label, maxenv.degrees(min(limit)),
                       maxenv.degrees(max(limit))))

        constraint = _existing(node) or _create(node, joint)

        # body0 is the Parent Body and body1 the Child. Havok's entity A is the
        # body the joint moves, so it is the child: the limits are expressed as
        # what A may do relative to B.
        constraint.body0 = shape_b
        constraint.body1 = shape_a

        settings, offset = limits.plan(joint)
        _apply(constraint, settings)
        _place(constraint, node, offset)

        if offset:
            result.centred += 1

        maxenv.write_raw(node, schema.SWING_OFFSET, repr(offset))
        maxenv.write_raw(node, schema.SIGNATURE,
                         limits.signature(settings, offset, list(node.transform)))
        result.built += 1

    return result


def _create(node, joint):
    constraint = rt.UConstraint()
    constraint.name = "%s_uc" % node.name
    constraint.parent = node
    return constraint


def _existing(node):
    for child in list(node.children or []):
        if str(rt.classOf(child)) == "UConstraint":
            return child
    return None


def _apply(constraint, settings):
    for setting in settings:
        name, value = setting[0], setting[1]
        is_angle = len(setting) > 2 and setting[2] == "angle"
        try:
            rt.setProperty(constraint, name,
                           maxenv.degrees(value) if is_angle else value)
        except (RuntimeError, TypeError):
            continue


def _place(constraint, node, offset):
    """Put the constraint on the joint, rotated by the swing offset if there is one.

    The joint's own transform is the Havok frame, so the constraint sits exactly
    there -- except where a lopsided plane limit had to be centred, and then the
    frame turns about its local Y by the midpoint so that a symmetric Swing Y
    covers the real range. That rotation is what :data:`schema.SWING_OFFSET`
    records, and what the bake undoes.
    """
    constraint.transform = node.transform

    if offset:
        turn = rt.rotateYMatrix(maxenv.degrees(offset))
        constraint.transform = turn * node.transform


def clear_constraints(nodes=None):
    """Undo the build, leaving every property alone."""
    removed = 0
    pool = list(nodes) if nodes else maxenv.scene_nodes()

    for node in joints_in(pool):
        constraint = _existing(node)
        if constraint is not None:
            rt.delete(constraint)
            removed += 1

    for node in pool:
        bodies.clear_rigid_body(node)

    return removed


# --- the animation path ----------------------------------------------------


def build_rotation_limits(nodes=None):
    """Put each joint's angular ranges on the bone the body rides.

    Max's rotation limits live on the node's rotation controller rather than in a
    constraint object, so this needs no plug-in and works in every version. It is
    the path an animator wants: the limits clamp the pose as the rig is handled,
    with nothing simulating.
    """
    result = Result()
    pool = list(nodes) if nodes else maxenv.scene_nodes()

    for node in joints_in(pool):
        joint = Joint(node)
        body_a = bodies.find_body(pool, joint.body_a_name)

        if body_a is None:
            result.problem(node, "body %r is not in the scene" % joint.body_a_name)
            continue

        target = body_a.parent

        if target is None:
            result.problem(node, "%s has no parent to limit" % body_a.name)
            continue

        ranges = (limits.twist_range(joint), limits.plane_range(joint), None)
        cone = limits.cone_span(joint)

        if cone:
            ranges = (ranges[0], ranges[1], (-cone, cone))

        if all(limit is None for limit in ranges):
            result.problem(node, "nothing to limit")
            continue

        for axis, limit in zip("XYZ", ranges):
            _limit_axis(target, axis, limit)

        result.built += 1

    return result


def _limit_axis(node, axis, limit):
    """One rotation limit, through the Limit Controller Max puts on a track.

    ``setLimitRange`` and the limit flags live on the controller rather than the
    node, so the track has to be reached first. A track with no limit controller
    gets one.
    """
    track = rt.getPropertyController(node.controller, "Rotation")

    if track is None:
        return False

    try:
        if limit is None:
            rt.setLimitEnabled(track, axis, False)
            return True

        lower, upper = sorted(limit)
        rt.setLimitEnabled(track, axis, True)
        rt.setLimitRange(track, axis,
                         maxenv.degrees(lower), maxenv.degrees(upper))
        return True
    except (RuntimeError, TypeError, AttributeError):
        return False


def clear_rotation_limits(nodes=None):
    cleared = 0
    pool = list(nodes) if nodes else maxenv.scene_nodes()

    for node in joints_in(pool):
        joint = Joint(node)
        body_a = bodies.find_body(pool, joint.body_a_name)
        target = body_a.parent if body_a is not None else None

        if target is None:
            continue

        for axis in "XYZ":
            _limit_axis(target, axis, None)

        cleared += 1

    return cleared
