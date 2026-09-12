"""Reading a joint out of the scene.

One class, built from the properties on an attachment point. Everything the
rest of the add-on does is a function of this; nothing else parses properties.
"""

import math

from . import schema


def read_float(obj, key, default=None):
    """A property as a number, whichever way it was written.

    NIFBX writes the shared limits as doubles and ck-cmd writes them as
    strings, and both arrive here. The spec (§3.1) says both are legal, so
    both are read.
    """
    if key not in obj.keys():
        return default
    value = obj[key]
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _hkc_float(obj, field_name, default=None):
    """A descriptor field, which is always a string."""
    return read_float(obj, schema.field(field_name), default)


def is_attachment_point(obj):
    """Whether an object is a joint rather than half of one.

    The same test ``FbxConstraintReader.IsAttachmentPoint`` makes: the
    separator in the name, and not the child node carrying the far frame --
    which inherits its parent's name, separator and all.
    """
    if obj.type not in {"EMPTY", "MESH"}:
        return False
    if schema.FRAME in obj.keys() and obj[schema.FRAME] == "A":
        return False
    if schema.TYPE in obj.keys():
        return True
    return schema.NAME_SEPARATOR in obj.name


def joints_in(objects):
    """Every joint among the given objects, in name order for stable results."""
    return sorted((o for o in objects if is_attachment_point(o)), key=lambda o: o.name)


class Joint:
    """One Havok constraint, as the scene holds it."""

    def __init__(self, obj):
        self.obj = obj
        self.type = str(obj.get(schema.TYPE, "")) or self._type_from_fields()
        self.wrapper = str(obj.get(schema.WRAPPER, ""))
        self.body_a_name = str(obj.get(schema.BODY_A, ""))
        self.body_b_name = str(obj.get(schema.BODY_B, ""))

        if not self.body_a_name or not self.body_b_name:
            self._names_from_node_name()

    # -- identification -----------------------------------------------------

    def _type_from_fields(self):
        """A scene from ck-cmd names the type; one that has lost the property
        is identified by which limits it carries, which is the next best
        thing and is how the six-limit form was told apart before."""
        if schema.CONE_MAX in self.obj.keys():
            return "Ragdoll"
        if schema.MIN_ANGLE in self.obj.keys():
            return "LimitedHinge"
        return ""

    def _names_from_node_name(self):
        """``<B>_con_<A>_attach_point``. Only reached when the properties are
        absent, i.e. a scene from ck-cmd, because Blender truncates a long
        name and the properties are the reason they exist (spec §4.6)."""
        name = self.obj.name
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

    # -- the limits ---------------------------------------------------------

    @property
    def cone_max(self):
        return read_float(self.obj, schema.CONE_MAX, _hkc_float(self.obj, "Cone Max Angle"))

    @property
    def plane_range(self):
        lo = read_float(self.obj, schema.PLANE_MIN, _hkc_float(self.obj, "Plane Min Angle"))
        hi = read_float(self.obj, schema.PLANE_MAX, _hkc_float(self.obj, "Plane Max Angle"))
        return lo, hi

    @property
    def twist_range(self):
        lo = read_float(self.obj, schema.TWIST_MIN, _hkc_float(self.obj, "Twist Min Angle"))
        hi = read_float(self.obj, schema.TWIST_MAX, _hkc_float(self.obj, "Twist Max Angle"))
        return lo, hi

    @property
    def hinge_range(self):
        lo = read_float(self.obj, schema.MIN_ANGLE, _hkc_float(self.obj, "Min Angle"))
        hi = read_float(self.obj, schema.MAX_ANGLE, _hkc_float(self.obj, "Max Angle"))
        return lo, hi

    @property
    def max_friction(self):
        return read_float(self.obj, schema.MAX_FRICTION, _hkc_float(self.obj, "Max Friction"))

    # -- the far frame ------------------------------------------------------

    @property
    def far_frame(self):
        """The child node carrying frame A, or None if the scene has none."""
        for child in self.obj.children:
            if child.get(schema.FRAME) == "A":
                return child
            if child.name.endswith(schema.FAR_FRAME_SUFFIX):
                return child
        return None

    def __repr__(self):
        return "<Joint %s %s: %s -> %s>" % (
            self.obj.name, self.type or "?", self.body_b_name, self.body_a_name)


def degrees(value):
    return None if value is None else math.degrees(value)
