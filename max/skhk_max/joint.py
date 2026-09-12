"""Reading a joint out of a Max scene.

The same model as the other two hosts', over Max nodes. Everything comes off the
node's properties, whether Max's FBX importer filed them as custom attributes or
as user-defined properties -- :mod:`maxenv` reads both.
"""

from pymxs import runtime as rt

from . import maxenv, schema


def read_float(node, name, default=None):
    """A property as a number, whichever way it was written.

    NIFBX writes the shared limits as doubles and ck-cmd writes them as strings,
    and a user-property buffer turns everything back into text regardless.
    """
    value = maxenv.read_raw(node, name)

    if value is None:
        return default

    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_string(node, name, default=""):
    value = maxenv.read_raw(node, name)
    return default if value is None else str(value)


def _hkc_float(node, field_name, default=None):
    return read_float(node, schema.field(field_name), default)


def is_attachment_point(node):
    """Whether a node is a joint rather than half of one."""
    if read_string(node, schema.FRAME) == "A":
        return False
    if maxenv.has_property(node, schema.TYPE):
        return True
    return schema.NAME_SEPARATOR in str(node.name)


def joints_in(nodes):
    return sorted((n for n in nodes if is_attachment_point(n)), key=lambda n: str(n.name))


class Joint:
    """One Havok constraint, as the scene holds it."""

    def __init__(self, node):
        self.node = node
        self.name = str(node.name)
        self.type = read_string(node, schema.TYPE) or self._type_from_fields()
        self.wrapper = read_string(node, schema.WRAPPER)
        self.body_a_name = read_string(node, schema.BODY_A)
        self.body_b_name = read_string(node, schema.BODY_B)

        if not self.body_a_name or not self.body_b_name:
            self._names_from_node_name()

    def _type_from_fields(self):
        if maxenv.has_property(self.node, schema.CONE_MAX):
            return "Ragdoll"
        if maxenv.has_property(self.node, schema.MIN_ANGLE):
            return "LimitedHinge"
        return ""

    def _names_from_node_name(self):
        name = self.name
        for suffix in (schema.ATTACH_SUFFIX, schema.FAR_FRAME_SUFFIX):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
        at = name.find(schema.NAME_SEPARATOR)
        if at < 0:
            return
        if not self.body_b_name:
            self.body_b_name = name[:at]
        if not self.body_a_name:
            self.body_a_name = name[at + len(schema.NAME_SEPARATOR):]

    @property
    def cone_max(self):
        return read_float(self.node, schema.CONE_MAX,
                          _hkc_float(self.node, "Cone Max Angle"))

    @property
    def plane_range(self):
        return (read_float(self.node, schema.PLANE_MIN, _hkc_float(self.node, "Plane Min Angle")),
                read_float(self.node, schema.PLANE_MAX, _hkc_float(self.node, "Plane Max Angle")))

    @property
    def twist_range(self):
        return (read_float(self.node, schema.TWIST_MIN, _hkc_float(self.node, "Twist Min Angle")),
                read_float(self.node, schema.TWIST_MAX, _hkc_float(self.node, "Twist Max Angle")))

    @property
    def hinge_range(self):
        return (read_float(self.node, schema.MIN_ANGLE, _hkc_float(self.node, "Min Angle")),
                read_float(self.node, schema.MAX_ANGLE, _hkc_float(self.node, "Max Angle")))

    @property
    def max_friction(self):
        return read_float(self.node, schema.MAX_FRICTION,
                          _hkc_float(self.node, "Max Friction"))

    @property
    def far_frame(self):
        """The child node carrying frame A, or None if the scene has none."""
        for child in list(self.node.children or []):
            if read_string(child, schema.FRAME) == "A":
                return child
            if str(child.name).endswith(schema.FAR_FRAME_SUFFIX):
                return child
        return None

    def __repr__(self):
        return "<Joint %s %s: %s -> %s>" % (
            self.name, self.type or "?", self.body_b_name, self.body_a_name)
