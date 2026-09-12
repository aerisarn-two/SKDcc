"""The 3ds Max facts this needs, in one place so they can be checked in one place.

Written against the MAXScript reference for ``UConstraint`` and
``MassFX_RBody``, read rather than remembered. Every enum value and property name
below is quoted from it.

Python rather than MAXScript, through ``pymxs``: it lets the same architecture and
the same kind of test serve all three hosts, and Max has shipped Python since
2015.
"""

import math

from pymxs import runtime as rt

# --- UConstraint, "Connection" and limit rollouts --------------------------

#: ``linearModeX/Y/Z``, ``swing1Mode``, ``swing2Mode``, ``twistMode``.
#: Note the order: Max counts Locked first, where Maya's Bullet counts Free
#: first. Copying one host's numbers into the other is silent and wrong.
LOCKED = 0
LIMITED = 1
FREE = 2

# --- MassFX_RBody ---------------------------------------------------------

#: ``MassFX_RBody.type``. The modifier's default is 1, and the UI's default body
#: is Dynamic, so 1 is Dynamic and the panel's order gives the rest.
DYNAMIC_BODY = 1
KINEMATIC_BODY = 2
STATIC_BODY = 3

#: ``MassFX_RBody.meshType``. The default is 4 and the UI's default mesh is
#: Convex, which fixes the numbering against the panel's list.
MESH_SPHERE = 1
MESH_BOX = 2
MESH_CAPSULE = 3
MESH_CONVEX = 4
MESH_COMPOSITE = 5
MESH_ORIGINAL = 6
MESH_CUSTOM = 7


def degrees(radians):
    """MAXScript angle properties are floats in degrees, without exception.

    Unlike Maya, there is nothing to ask: ``swing1Angle`` and the twist pair are
    plain floats and the panel shows degrees, so the conversion is unconditional.
    """
    return math.degrees(radians)


def radians(value):
    return math.radians(value)


def massfx_available():
    """Whether MassFX can be reached at all."""
    return bool(rt.classOf(rt.UConstraint)) and hasattr(rt, "MassFX_RBody")


# --- properties -----------------------------------------------------------
#
# Max has two places a foreign FBX property can land and the importer's choice is
# not documented either way, so both are read. A custom attribute is a real typed
# property on the node; a user-defined property is a line in a text buffer. The
# scripts never have to know which arrived.


def read_raw(node, name):
    """One property, from wherever Max put it, or None."""
    if rt.isProperty(node, name):
        try:
            return rt.getProperty(node, name)
        except (RuntimeError, TypeError):
            pass

    value = rt.getUserProp(node, name)

    if value is not None:
        return value

    return _from_buffer(node, name)


def _from_buffer(node, name):
    """The user-property buffer, parsed by hand.

    ``getUserProp`` has misread booleans and numbers for many versions, and a
    property written by something other than Max may not be in the ``key = value``
    shape it expects at all. Reading the buffer is the way round both.
    """
    text = rt.getUserPropBuffer(node)

    if not text:
        return None

    for line in str(text).replace("\r", "\n").split("\n"):
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()

    return None


def write_raw(node, name, value):
    """Put a property back where it came from, preferring the typed slot."""
    if rt.isProperty(node, name):
        try:
            rt.setProperty(node, name, value)
            return
        except (RuntimeError, TypeError):
            pass

    rt.setUserProp(node, name, value)


def has_property(node, name):
    return read_raw(node, name) is not None


def scene_nodes():
    return list(rt.objects)
