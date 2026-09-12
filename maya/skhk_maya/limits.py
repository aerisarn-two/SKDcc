"""Havok's limits as Maya Bullet's.

Six degrees of freedom, not cone-twist. Cone-twist is the obvious choice for a
ragdoll joint and it is the wrong one here for a concrete reason: Maya's Bullet
node exposes ``angularConstraintMaxX/Y/Z`` for a cone-twist but
``angularConstraintMinX/Y/Z`` **only** for the six-DOF types. Bullet's cone-twist
spans are symmetric half-angles, and Havok's plane and twist limits are not --
they are an independent minimum and maximum. Forcing them through a cone-twist
means centring the frame on the midpoint and halving the range (spec §5.3),
which changes the frame and then has to be undone on export. Six-DOF takes the
two bounds directly and leaves the frame alone.

Which axis is which is not a guess. The attachment point's own transform is the
Havok frame: its local X, Y and Z come back exactly equal to ``hkc_axis_b``,
``hkc_perp_axis_in_b1`` and ``hkc_perp_axis_in_b2`` on a vanilla export. So axis
X is the twist or hinge axis, Y the plane axis, Z the motor axis.

Angles are radians everywhere in this module. The conversion to whatever unit a
Maya attribute wants happens at the single point that writes one --
:func:`mayaenv.to_ui_angle` -- and nowhere else.
"""

from . import mayaenv

#: Maya Bullet's constraint type for each Havok constraint.
BULLET_TYPES = {
    "Ragdoll": mayaenv.SIX_DOF,
    "LimitedHinge": mayaenv.SIX_DOF,
    "Hinge": mayaenv.SIX_DOF,
    "Prismatic": mayaenv.SIX_DOF,
    "StiffSpring": mayaenv.SIX_DOF,
    "BallAndSocket": mayaenv.POINT,
    "BallSocketConstraintChain": mayaenv.POINT,
}

LOCKED_RANGE = (0.0, 0.0)

AXES = ("X", "Y", "Z")


def bullet_type_of(joint):
    """The Bullet constraint type, or None if this joint has no useful one."""
    return BULLET_TYPES.get(joint.type)


def angular_limits(joint):
    """The three angular limits in radians, as ``(lower, upper)`` or None.

    Frame-axis order: X twist or hinge, Y plane, Z cone.
    """
    if joint.type == "Ragdoll":
        cone = joint.cone_max
        return (_range(joint.twist_range),
                _range(joint.plane_range),
                (-cone, cone) if cone is not None else None)

    if joint.type == "LimitedHinge":
        return (_range(joint.hinge_range), LOCKED_RANGE, LOCKED_RANGE)

    if joint.type == "Hinge":
        return (None, LOCKED_RANGE, LOCKED_RANGE)

    if joint.type == "Prismatic":
        return (LOCKED_RANGE, LOCKED_RANGE, LOCKED_RANGE)

    return (None, None, None)


def linear_limits(joint):
    """The three linear limits. Every Havok joint but the prismatic is a pivot."""
    if joint.type == "Prismatic":
        return (None, LOCKED_RANGE, LOCKED_RANGE)
    return (LOCKED_RANGE, LOCKED_RANGE, LOCKED_RANGE)


def _range(pair):
    lower, upper = pair
    if lower is None and upper is None:
        return None
    return (lower if lower is not None else 0.0,
            upper if upper is not None else 0.0)


def limit_type(limit):
    """Bullet's per-axis limit enum for one range."""
    if limit is None:
        return mayaenv.FREE
    lower, upper = limit
    if lower == 0.0 and upper == 0.0:
        return mayaenv.LOCKED
    return mayaenv.LIMITED


def plan(joint):
    """Everything to be written, as ``(attribute suffix, value)`` pairs.

    Separated from the writing so that what this decides can be checked without
    Maya: the pairs are plain names and plain numbers in radians, and a test can
    compare them against a fixture taken off a real ragdoll.
    """
    settings = []
    kind = bullet_type_of(joint)

    if kind is None:
        return settings

    settings.append(("constraintType", kind))

    if kind == mayaenv.POINT:
        return settings

    for axis, limit in zip(AXES, linear_limits(joint)):
        settings.append(("linearConstraint%s" % axis, limit_type(limit)))
        if limit is not None:
            lower, upper = sorted(limit)
            settings.append(("linearConstraintMin%s" % axis, lower))
            settings.append(("linearConstraintMax%s" % axis, upper))

    for axis, limit in zip(AXES, angular_limits(joint)):
        settings.append(("angularConstraint%s" % axis, limit_type(limit)))
        if limit is not None:
            lower, upper = sorted(limit)
            settings.append(("angularConstraintMin%s" % axis, lower, "angle"))
            settings.append(("angularConstraintMax%s" % axis, upper, "angle"))

    return settings


def signature(values, frame=None):
    """A fingerprint of the values a build wrote, for spec R2.

    Takes the already-read numbers rather than a node, so the same format is
    produced whether it is being made at build time or compared at bake time.

    The joint's own placement is part of it when given. Moving the joint moves the
    frame, and frame A has to be rewritten for that as surely as for a changed
    limit -- without it, a joint that was dragged somewhere new keeps the frame A
    it had in its old position and the ragdoll is quietly wrong.
    """
    parts = ["%s=%.7g" % (name, value) if isinstance(value, float)
             else "%s=%s" % (name, value) for name, value in values]

    if frame is not None:
        parts.extend("%.5g" % value for value in frame)

    return "|".join(parts)
