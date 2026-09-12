"""Finding and making MassFX rigid bodies.

Max's rigid body is a **modifier** rather than a node, which is the one structural
difference from the other two hosts: ``MassFX_RBody`` goes on the collision shape
mesh, and the Havok body is still the transform above it carrying the properties.
"""

import re

from pymxs import runtime as rt

from . import maxenv, schema
from .joint import read_float

#: MassFX's mesh type for each shape ``schema`` recognises. The suffix table is
#: shared with the other hosts and yields a neutral token; only the last step from
#: token to mesh type is Max's own.
MESH_TYPES = {
    "SPHERE": maxenv.MESH_SPHERE,
    "BOX": maxenv.MESH_BOX,
    "CAPSULE": maxenv.MESH_CAPSULE,
    "CONVEX_HULL": maxenv.MESH_CONVEX,
    "MESH": maxenv.MESH_ORIGINAL,
}

RIGID_BODY_MODIFIER = "MassFX_RBody"


def mesh_type_of(name):
    return MESH_TYPES.get(schema.collision_shape_of(str(name)), maxenv.MESH_CONVEX)


def _key(name):
    """A name reduced to what survives being a node name.

    NIFBX escapes what needs escaping, so this is usually the identity; a file from
    another tool may have been mangled, and Max's own numeric suffix for a
    duplicate is a Max fact rather than part of the file.
    """
    reduced = re.sub(r"[^A-Za-z0-9]+", "_", str(name))
    return re.sub(r"\d+$", "", reduced).rstrip("_").lower()


def find_body(nodes, name):
    """The body node of that name, however Max spelled it."""
    if not name:
        return None

    for node in nodes:
        if str(node.name) == name:
            return node

    wanted = _key(name)
    matches = [node for node in nodes if _key(node.name) == wanted]
    return matches[0] if len(matches) == 1 else None


def shape_of(body):
    """The child node holding the body's collision geometry.

    Max wants something with a mesh to put the modifier on, so this returns the
    geometry node rather than the body transform.
    """
    if body is None:
        return None

    if _is_geometry(body):
        return body

    for child in list(body.children or []):
        if _is_geometry(child):
            return child

    return None


def _is_geometry(node):
    try:
        return bool(rt.superClassOf(node) == rt.GeometryClass)
    except (RuntimeError, TypeError):
        return False


def rigid_body_of(node):
    """The ``MassFX_RBody`` already on a node, if any."""
    for modifier in list(node.modifiers or []):
        if str(rt.classOf(modifier)) == RIGID_BODY_MODIFIER:
            return modifier
    return None


def make_rigid_body(body, shape, dynamic=False):
    """Put a MassFX rigid body on a shape, carrying the Havok settings.

    Static unless asked otherwise, for the reason the other two hosts use passive
    and static bodies: a Skyrim body is parented into the rig, Max's parenting
    wins over the simulation, and a dynamic body would be created and then not
    move -- which reads as a bug in the script. Spec R7.
    """
    existing = rigid_body_of(shape)

    if existing is None:
        existing = rt.MassFX_RBody()
        rt.addModifier(shape, existing)

    existing.type = maxenv.DYNAMIC_BODY if dynamic else maxenv.STATIC_BODY
    existing.meshType = mesh_type_of(shape.name)

    mass = read_float(body, schema.RB_MASS)
    if mass is not None and mass > 0.0:
        existing.mass = mass

    friction = read_float(body, schema.RB_FRICTION)
    if friction is not None:
        # Max splits Havok's one friction into a static and a dynamic coefficient
        # and has nothing to distinguish them with, so both take the same value.
        existing.staticFriction = max(0.0, friction)
        existing.dynamicFriction = max(0.0, friction)

    restitution = read_float(body, schema.RB_RESTITUTION)
    if restitution is not None:
        existing.bounciness = min(max(restitution, 0.0), 1.0)

    linear = read_float(body, schema.RB_LINEAR_DAMPING)
    if linear is not None:
        existing.LinearDamping = max(0.0, linear)

    angular = read_float(body, schema.RB_ANGULAR_DAMPING)
    if angular is not None:
        # AngularDamping is in degrees per second in Max and its default of
        # 2.86479 is one radian per second, so the Havok value is converted the
        # same way every other angle here is.
        existing.AngularDamping = maxenv.degrees(max(0.0, angular))

    maxenv.write_raw(shape, schema.GENERATED, "1")
    return existing


def was_generated(node):
    return maxenv.read_raw(node, schema.GENERATED) is not None


def clear_rigid_body(node):
    """Remove a rigid body this script added, leaving one it did not."""
    modifier = rigid_body_of(node)

    if modifier is None or not was_generated(node):
        return False

    rt.deleteModifier(node, modifier)
    return True
