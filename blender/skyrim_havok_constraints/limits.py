"""Havok's limits as Blender's.

The joint's frame is the attachment point's own transform, and its axes are
the Havok frame's axes -- verified against a vanilla export, where the empty's
local X, Y and Z came back exactly equal to ``hkc_axis_b``,
``hkc_perp_axis_in_b1`` and ``hkc_perp_axis_in_b2``. So no remapping is
needed: axis 0 is Havok's twist or hinge axis, 1 the plane axis, 2 the motor
axis.

Everything is in radians, in the file and in Blender both. Nothing here
converts, and that is deliberate: the degrees conversion belongs in the Maya
and Max scripts, not in this one.
"""


#: Blender's type for each Havok constraint.
#:
#: ``GENERIC`` almost throughout, rather than the seemingly obvious ``HINGE``
#: for a hinge. Blender's ``HINGE`` rotates about the constraint's **Z** axis
#: while Havok's hinge axis is the frame's **X**, so using it would mean
#: rotating the frame a quarter turn and then un-rotating it on the way back
#: out. ``GENERIC`` is a six-degree-of-freedom joint whose three angular
#: limits sit on the frame's own axes, which is what Havok's atoms are, so the
#: frame passes through untouched. A locked axis is a limit of zero.
BLENDER_TYPES = {
    "Ragdoll": "GENERIC",
    "LimitedHinge": "GENERIC",
    "Hinge": "GENERIC",
    "Prismatic": "GENERIC",
    "StiffSpring": "GENERIC_SPRING",
    "BallAndSocket": "POINT",
    "BallSocketConstraintChain": "POINT",
}

LOCKED = (0.0, 0.0)


def blender_type_of(joint):
    """The Blender constraint type, or None if this joint has no useful one."""
    return BLENDER_TYPES.get(joint.type)


def angular_limits(joint):
    """The three angular limits, as ``(lower, upper)`` or None for free.

    Returned in frame-axis order: X twist, Y plane, Z cone.
    """
    if joint.type == "Ragdoll":
        twist = _range(joint.twist_range)
        plane = _range(joint.plane_range)
        cone = joint.cone_max

        # The cone is a cone: one half-angle capping the deviation of the
        # twist axis in every direction at once. Blender has no cone, so it
        # becomes a symmetric limit on the remaining axis. That is the one
        # approximation in this mapping, and it is why the hkc_ properties
        # stay authoritative -- see spec R1 and R2.
        return (twist, plane, (-cone, cone) if cone is not None else None)

    if joint.type == "LimitedHinge":
        return (_range(joint.hinge_range), LOCKED, LOCKED)

    if joint.type == "Hinge":
        # Free about the hinge axis, locked across it.
        return (None, LOCKED, LOCKED)

    if joint.type == "Prismatic":
        return (LOCKED, LOCKED, LOCKED)

    return (None, None, None)


def linear_limits(joint):
    """The three linear limits. Every Havok joint but the prismatic is a
    pivot: the bodies may not slide apart at all."""
    if joint.type == "Prismatic":
        return (None, LOCKED, LOCKED)
    return (LOCKED, LOCKED, LOCKED)


def _range(pair):
    lower, upper = pair
    if lower is None and upper is None:
        return None
    return (lower if lower is not None else 0.0,
            upper if upper is not None else 0.0)


def apply(rbc, joint):
    """Set every limit on a Blender constraint from a joint."""
    rbc.type = blender_type_of(joint) or "GENERIC"

    if rbc.type == "POINT":
        return

    for axis, limit in zip("xyz", linear_limits(joint)):
        _set(rbc, "lin", axis, limit)

    for axis, limit in zip("xyz", angular_limits(joint)):
        _set(rbc, "ang", axis, limit)

    if rbc.type == "GENERIC_SPRING":
        # A stiff spring is a distance constraint, and the only thing the
        # NIF records is that distance; stiffness and damping are Havok's
        # solver defaults, which Blender has no equivalent of. Left at
        # Blender's own defaults rather than invented.
        rbc.use_spring_x = True


def _set(rbc, kind, axis, limit):
    use = "use_limit_%s_%s" % (kind, axis)
    lower = "limit_%s_%s_lower" % (kind, axis)
    upper = "limit_%s_%s_upper" % (kind, axis)

    if limit is None:
        setattr(rbc, use, False)
        return

    setattr(rbc, use, True)
    low, high = limit
    # Blender treats lower > upper as locked rather than inverted, and a
    # Havok range can arrive either way round after a frame has been edited.
    setattr(rbc, lower, min(low, high))
    setattr(rbc, upper, max(low, high))


def signature(obj):
    """A fingerprint of everything a build sets on *obj*.

    Stored on the joint when the constraint is built, and recomputed when it
    is read back: equal means nobody touched it, so the properties are written
    back verbatim instead of being regenerated from an approximation. Spec R2.

    The joint's own placement is part of it, because moving the empty moves the
    joint frame, and that has to be written back as surely as a changed limit.
    """
    rbc = obj.rigid_body_constraint

    if rbc is None:
        return ""

    parts = [rbc.type]

    for row in obj.matrix_local:
        parts.extend("%.5g" % value for value in row)

    if rbc.type != "POINT":
        for kind in ("lin", "ang"):
            for axis in "xyz":
                used = getattr(rbc, "use_limit_%s_%s" % (kind, axis))
                parts.append("1" if used else "0")
                if used:
                    parts.append("%.7g" % getattr(rbc, "limit_%s_%s_lower" % (kind, axis)))
                    parts.append("%.7g" % getattr(rbc, "limit_%s_%s_upper" % (kind, axis)))

    parts.append(rbc.object1.name if rbc.object1 else "")
    parts.append(rbc.object2.name if rbc.object2 else "")
    return "|".join(parts)
