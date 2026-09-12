"""Havok's limits as a MassFX UConstraint's.

Max's joint is a PhysX D6 and its three rotational limits do not agree about
symmetry, which is the whole story of this module:

* **Twist**, about the constraint's local X, is a ``twistAngleLow`` /
  ``twistAngleHigh`` pair. Asymmetric, so a Havok twist or hinge range goes
  across exactly.
* **Swing Y** and **Swing Z**, about local Y and Z, are a *single*
  ``swing1Angle`` / ``swing2Angle``. "If you set Angle Limit to 45 degrees, the
  total allowed rotation equals 90" -- a half-angle, symmetric about the frame.

The Havok frame is the attachment point's own transform: local X is the twist or
hinge axis, Y the plane axis, Z the motor axis, verified against a vanilla export.
That lines up almost perfectly. The twist range is exact. The cone is already a
symmetric half-angle, so Swing Z is exact too. **Only the plane limit can be
lopsided against a symmetric Swing Y**, and that is the one place spec §5.3's
frame-centring is needed:

    offset = (max + min) / 2      rotate the constraint frame by this
    span   = (max - min) / 2      the symmetric limit

which reproduces the range exactly at the cost of moving the frame. The offset is
recorded on the joint so the bake can undo it rather than guess -- without that,
every round trip would quietly recentre the joint again.

Angles are radians throughout here. Degrees happen once, where a property is
written.
"""

from . import maxenv

#: Which joints have a UConstraint worth making. All of them are the same helper
#: -- Max's presets only preset it -- so what varies is the limits, not the type.
SUPPORTED = ("Ragdoll", "LimitedHinge", "Hinge", "Prismatic", "StiffSpring",
             "BallAndSocket", "BallSocketConstraintChain")

LOCKED_RANGE = (0.0, 0.0)


def supported(joint):
    return joint.type in SUPPORTED


def twist_range(joint):
    """The range for the X axis: a hinge's swing, or a ragdoll's twist."""
    if joint.type == "Ragdoll":
        return _range(joint.twist_range)
    if joint.type == "LimitedHinge":
        return _range(joint.hinge_range)
    if joint.type == "Hinge":
        return None
    return LOCKED_RANGE


def plane_range(joint):
    """The range for the Y axis, which is the one that may need centring."""
    if joint.type == "Ragdoll":
        return _range(joint.plane_range)
    if joint.type in ("LimitedHinge", "Hinge"):
        return LOCKED_RANGE
    if joint.type in ("BallAndSocket", "BallSocketConstraintChain"):
        return None
    return LOCKED_RANGE


def cone_span(joint):
    """The half-angle for the Z axis, already symmetric in Havok's own terms."""
    if joint.type == "Ragdoll":
        return joint.cone_max
    if joint.type in ("BallAndSocket", "BallSocketConstraintChain"):
        return None
    return 0.0


def centre(limit):
    """A range as ``(offset, span)``: what to rotate the frame by, and the limit.

    ``offset`` is zero for a range that is already symmetric, which is most of
    them, and then nothing is rotated and nothing has to be undone.
    """
    if limit is None:
        return None, None

    lower, upper = sorted(limit)
    offset = (upper + lower) / 2.0
    span = (upper - lower) / 2.0

    return (0.0 if abs(offset) < 1e-9 else offset), span


def uncentre(offset, span):
    """The range a recorded offset and a live span stand for. Inverse of
    :func:`centre`, and the reason the offset is recorded at all."""
    offset = offset or 0.0
    return (offset - span, offset + span)


def one_sided(limit):
    """Whether a range fails to straddle zero.

    Max's twist pair is two magnitudes, one per edge, so a range entirely to one
    side of zero -- 10 to 40 degrees, say -- cannot be spelled. None of the 34
    ranges in the vanilla cow skeleton is like that, but a hand-authored one could
    be, and it has to be reported rather than flattened.
    """
    if limit is None:
        return False
    lower, upper = sorted(limit)
    return not (lower <= 0.0 <= upper)


def _range(pair):
    lower, upper = pair
    if lower is None and upper is None:
        return None
    return (lower if lower is not None else 0.0,
            upper if upper is not None else 0.0)


def mode_of(limit):
    """Max's per-axis mode for one range."""
    if limit is None:
        return maxenv.FREE
    lower, upper = limit
    if lower == 0.0 and upper == 0.0:
        return maxenv.LOCKED
    return maxenv.LIMITED


def plan(joint):
    """Everything to be written, as ``(property, value)`` pairs in radians.

    Separated from the writing so what this decides can be checked without Max.
    The swing offset is returned alongside, because it is not a property of the
    constraint but of the frame.
    """
    settings = []

    if not supported(joint):
        return settings, 0.0

    # Every Havok joint but the prismatic is a pivot: the bodies may not slide.
    sliding = joint.type in ("Prismatic", "StiffSpring")
    for axis in "XYZ":
        free = sliding and axis == "X"
        settings.append(("linearMode%s" % axis, maxenv.FREE if free else maxenv.LOCKED))

    twist = twist_range(joint)
    settings.append(("twistMode", mode_of(twist)))
    if twist is not None and mode_of(twist) == maxenv.LIMITED:
        lower, upper = sorted(twist)
        # Two magnitudes, one per edge of the limit, so the signs go away here.
        settings.append(("twistAngleLow", abs(lower), "angle"))
        settings.append(("twistAngleHigh", abs(upper), "angle"))

    plane = plane_range(joint)
    offset, span = centre(plane)
    settings.append(("swing1Mode", mode_of(plane)))
    if plane is not None and mode_of(plane) == maxenv.LIMITED:
        settings.append(("swing1Angle", span, "angle"))

    cone = cone_span(joint)
    settings.append(("swing2Mode", maxenv.FREE if cone is None
                     else maxenv.LOCKED if cone == 0.0 else maxenv.LIMITED))
    if cone:
        settings.append(("swing2Angle", cone, "angle"))

    return settings, (offset or 0.0)


def signature(values, offset, frame=None):
    """A fingerprint of what a build wrote, for spec R2.

    Takes the plan's entries or the values read back off a constraint, which are
    the same names in the same order but without the angle marker, so only the
    first two elements of each are used.

    The joint's own placement is part of it when given. Moving the joint moves the
    frame, and frame A has to be rewritten for that as surely as for a changed
    limit -- without it, a joint that was dragged somewhere new keeps the frame A
    it had in its old position and the ragdoll is quietly wrong.
    """
    parts = []

    for entry in values:
        name, value = entry[0], entry[1]
        parts.append("%s=%.7g" % (name, value) if isinstance(value, float)
                     else "%s=%s" % (name, value))

    parts.append("offset=%.7g" % offset)

    if frame is not None:
        parts.extend("%.5g" % value for value in frame)

    return "|".join(parts)
