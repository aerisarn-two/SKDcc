"""Writing an edited UConstraint back into the properties.

Rules R1-R5 of ``dcc-constraint-interop-spec.md``. Max has one wrinkle the other
hosts do not: a lopsided plane limit was centred to fit a symmetric Swing Y, so
the range has to be *uncentred* on the way out using the offset the build
recorded. Guessing it instead would recentre the joint a little on every trip.
"""

from pymxs import runtime as rt

from . import bodies, limits, maxenv, schema
from .joint import Joint, joints_in, read_float


class Baked:
    def __init__(self):
        self.rewritten = 0
        self.unchanged = 0
        self.renamed = 0
        self.problems = []

    def __str__(self):
        text = "%d rewritten, %d unchanged" % (self.rewritten, self.unchanged)
        if self.renamed:
            text += ", %d renamed" % self.renamed
        if self.problems:
            text += ", %d problem%s" % (len(self.problems),
                                        "" if len(self.problems) == 1 else "s")
        return text


def bake(nodes=None):
    """Write every edited constraint back to its properties."""
    result = Baked()
    pool = list(nodes) if nodes else maxenv.scene_nodes()

    for node in joints_in(pool):
        constraint = _existing(node)

        if constraint is None:
            continue

        joint = Joint(node)
        offset = read_float(node, schema.SWING_OFFSET, 0.0) or 0.0
        current = _read(constraint, joint)

        live = limits.signature(current, offset, list(node.transform))

        if maxenv.read_raw(node, schema.SIGNATURE) == live:
            result.unchanged += 1
            continue

        _write_names(node, joint, constraint, result)
        _write_limits(node, joint, dict(current), offset)
        _write_far_frame(node, joint, pool)

        maxenv.write_raw(node, schema.SIGNATURE,
                         limits.signature(_read(constraint, joint), offset,
                                          list(node.transform)))
        result.rewritten += 1

    return result


def _read(constraint, joint):
    """The constraint's live values, in radians, in the plan's own order."""
    values = []
    settings, _ = limits.plan(joint)

    for setting in settings:
        name, is_angle = setting[0], len(setting) > 2 and setting[2] == "angle"
        try:
            raw = rt.getProperty(constraint, name)
        except (RuntimeError, TypeError):
            continue
        values.append((name, maxenv.radians(raw) if is_angle else raw))

    return values


# --- R3 --------------------------------------------------------------------


def _write_names(node, joint, constraint, result):
    """Rebuild the body names and the node name from the constraint's own bodies.

    ``body0``/``body1`` are node references, and a reference does not care what
    anything is called, so the names in the file are regenerated from them.
    """
    body_a = _body_name_for(constraint.body1)
    body_b = _body_name_for(constraint.body0)

    if body_a is None or body_b is None:
        result.problems.append(
            "%s: a constraint body does not lead back to a Havok body" % node.name)
        return

    maxenv.write_raw(node, schema.BODY_A, body_a)
    maxenv.write_raw(node, schema.BODY_B, body_b)

    wanted = "%s%s%s%s" % (body_b, schema.NAME_SEPARATOR, body_a, schema.ATTACH_SUFFIX)

    if str(node.name) == wanted:
        return

    far = joint.far_frame
    node.name = wanted

    if far is not None:
        far.name = wanted + schema.FAR_FRAME_SUFFIX

    result.renamed += 1


def _body_name_for(shape):
    """The Havok body a collision shape belongs to: itself, or its parent."""
    if shape is None:
        return None

    name = str(shape.name)

    if name.endswith((schema.BODY_SUFFIX, schema.PHANTOM_SUFFIX)):
        return name

    parent = shape.parent

    if parent is None:
        return None

    name = str(parent.name)
    return name if name.endswith((schema.BODY_SUFFIX, schema.PHANTOM_SUFFIX)) else None


# --- R1 --------------------------------------------------------------------


def _write_limits(node, joint, current, offset):
    """Put the edited angles back under both spellings, and touch nothing else.

    The twist pair comes back as two magnitudes and is reassembled into a signed
    range. The plane limit comes back as a half-angle about a frame that may have
    been turned, so the recorded offset puts it back where Havok had it.
    """
    twist = None
    if "twistAngleLow" in current and "twistAngleHigh" in current:
        twist = (-abs(current["twistAngleLow"]), abs(current["twistAngleHigh"]))

    plane = None
    if "swing1Angle" in current:
        plane = limits.uncentre(offset, abs(current["swing1Angle"]))

    cone = current.get("swing2Angle")

    if joint.type == "Ragdoll":
        _pair(node, twist, schema.TWIST_MIN, schema.TWIST_MAX,
              "Twist Min Angle", "Twist Max Angle")
        _pair(node, plane, schema.PLANE_MIN, schema.PLANE_MAX,
              "Plane Min Angle", "Plane Max Angle")
        if cone is not None:
            _scalar(node, abs(cone), schema.CONE_MAX, "Cone Max Angle")

    elif joint.type == "LimitedHinge":
        _pair(node, twist, schema.MIN_ANGLE, schema.MAX_ANGLE,
              "Min Angle", "Max Angle")


def _pair(node, limit, min_property, max_property, min_field, max_field):
    if limit is None:
        return
    lower, upper = sorted(limit)
    _scalar(node, lower, min_property, min_field)
    _scalar(node, upper, max_property, max_field)


def _scalar(node, value, shared_property, field_name):
    """One angle, under both names, each in the form its reader expects.

    The shared property is a number because that is what NIFBX writes; the
    ``hkc_`` field is a string because the descriptor dump is strings throughout
    and a reader meeting a double there will not parse it. A user-property buffer
    stores everything as text either way, which is harmless -- both readers parse.
    """
    maxenv.write_raw(node, shared_property, float(value))

    field = schema.field(field_name)
    if maxenv.has_property(node, field):
        maxenv.write_raw(node, field, repr(float(value)))


# --- R4 --------------------------------------------------------------------


def _write_far_frame(node, joint, pool):
    """Recompute frame A from where the joint now is.

    Max's ``Matrix3`` is row-vector, as Maya's is, so the relative transform is
    ``joint * inverse(bodyA)`` -- the reverse of what the same derivation needs in
    Blender. Backwards gives a frame nothing about the file would show to be wrong.

    The joint's own transform is used rather than the constraint's, because the
    constraint may have been turned to centre a lopsided swing and that rotation
    is an artefact of Max's limits rather than part of the joint.
    """
    far = joint.far_frame

    if far is None:
        return

    body_a = bodies.find_body(pool, joint.body_a_name)

    if body_a is None:
        return

    far.transform = node.transform * rt.inverse(body_a.transform)


def _existing(node):
    for child in list(node.children or []):
        if str(rt.classOf(child)) == "UConstraint":
            return child
    return None
