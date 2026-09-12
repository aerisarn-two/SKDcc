"""Reading a joint out of a Maya scene.

The same model as the Blender add-on's, over Maya nodes instead of Blender
objects. The properties arrive as extra attributes on the transform the FBX null
became, which is the one node type Maya's FBX plug-in carries custom properties
on at all -- shape node attributes cannot make the trip, because ``FbxGeometry``
has no user properties.
"""

import maya.cmds as cmds

from . import schema
from .mayaenv import short_name, user_attributes


def read_raw(node, attribute):
    """One extra attribute, or None if the node does not carry it."""
    full = "%s.%s" % (node, attribute)
    if not cmds.objExists(full):
        return None
    try:
        return cmds.getAttr(full)
    except (RuntimeError, ValueError):
        return None


def read_float(node, attribute, default=None):
    """An attribute as a number, whichever way it was written.

    NIFBX writes the shared limits as doubles and ck-cmd writes them as strings,
    and both arrive here (spec §3.1).
    """
    value = read_raw(node, attribute)

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


def read_string(node, attribute, default=""):
    value = read_raw(node, attribute)
    return default if value is None else str(value)


def _hkc_float(node, field_name, default=None):
    return read_float(node, schema.field(field_name), default)


def is_attachment_point(node):
    """Whether a node is a joint rather than half of one."""
    if cmds.nodeType(node) != "transform":
        return False
    if read_string(node, schema.FRAME) == "A":
        return False
    if read_raw(node, schema.TYPE) is not None:
        return True
    return schema.NAME_SEPARATOR in short_name(node)


def joints_in(nodes):
    """Every joint among *nodes*, in name order for stable results."""
    return sorted((n for n in nodes if is_attachment_point(n)), key=short_name)


def all_transforms():
    return cmds.ls(type="transform", long=True) or []


class Joint:
    """One Havok constraint, as the scene holds it."""

    def __init__(self, node):
        self.node = node
        self.name = short_name(node)
        self.type = read_string(node, schema.TYPE) or self._type_from_fields()
        self.wrapper = read_string(node, schema.WRAPPER)
        self.body_a_name = read_string(node, schema.BODY_A)
        self.body_b_name = read_string(node, schema.BODY_B)

        if not self.body_a_name or not self.body_b_name:
            self._names_from_node_name()

    def _type_from_fields(self):
        if read_raw(self.node, schema.CONE_MAX) is not None:
            return "Ragdoll"
        if read_raw(self.node, schema.MIN_ANGLE) is not None:
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

    # -- the limits ---------------------------------------------------------

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
        for child in cmds.listRelatives(self.node, children=True, fullPath=True,
                                        type="transform") or []:
            if read_string(child, schema.FRAME) == "A":
                return child
            if short_name(child).endswith(schema.FAR_FRAME_SUFFIX):
                return child
        return None

    def __repr__(self):
        return "<Joint %s %s: %s -> %s>" % (
            self.name, self.type or "?", self.body_b_name, self.body_a_name)
