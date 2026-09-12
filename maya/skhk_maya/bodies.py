"""Finding and making Bullet rigid bodies.

A Havok body is a transform with properties and its collision shape as a child
mesh; Maya's Bullet rigid body is a shape node under a transform that has
geometry. So, as in Blender, the two do not sit on the same node: the properties
are read off ``<bone>_rb`` and the rigid body is made on ``<bone>_rb_capsule``.
"""

import re

import maya.cmds as cmds

from . import mayaenv, schema
from .joint import read_float, read_string
from .mayaenv import short_name

#: Bullet's collider for each shape ``schema`` recognises. The suffix table is
#: shared with the Blender add-on and yields a neutral token; only the last step
#: from token to enum is Maya's own.
COLLIDERS = {
    "SPHERE": mayaenv.COLLIDER_SPHERE,
    "BOX": mayaenv.COLLIDER_BOX,
    "CAPSULE": mayaenv.COLLIDER_CAPSULE,
    "CONVEX_HULL": mayaenv.COLLIDER_HULL,
    "MESH": mayaenv.COLLIDER_MESH,
}


def collider_of(name):
    return COLLIDERS.get(schema.collision_shape_of(short_name(name)),
                         mayaenv.COLLIDER_HULL)


def _key(name):
    """A name reduced to what survives being a Maya node name.

    NIFBX already escapes the characters Maya rejects, so this should be the
    identity -- but a file that has been through another tool may not have been
    escaped, and Maya will have replaced the offending characters with
    underscores. Comparing on the reduced form matches either spelling. Maya's
    own numeric suffix for a duplicate name is stripped as well, since that is a
    Maya fact and not part of the file.
    """
    reduced = re.sub(r"[^A-Za-z0-9]+", "_", short_name(name))
    return re.sub(r"\d+$", "", reduced).rstrip("_").lower()


def find_body(nodes, name):
    """The body node of that name, however Maya spelled it."""
    if not name:
        return None

    for node in nodes:
        if short_name(node) == name:
            return node

    wanted = _key(name)
    matches = [node for node in nodes if _key(node) == wanted]
    return matches[0] if len(matches) == 1 else None


def shape_of(body):
    """The child transform holding the body's collision geometry.

    Maya's Bullet wants something with geometry, so what is returned is the
    transform above a mesh rather than the mesh shape itself -- that is what
    ``RigidBody.CreateRigidBody`` takes.
    """
    if body is None:
        return None

    if cmds.listRelatives(body, children=True, shapes=True, type="mesh"):
        return body

    for child in cmds.listRelatives(body, children=True, fullPath=True,
                                    type="transform") or []:
        if cmds.listRelatives(child, children=True, shapes=True, type="mesh"):
            return child

    return None


def rigid_body_of(transform):
    """The ``bulletRigidBodyShape`` under a transform, if it already has one."""
    shapes = cmds.listRelatives(transform, children=True, fullPath=True,
                                type=mayaenv.BODY_NODE) or []
    return shapes[0] if shapes else None


def make_rigid_body(body, shape, dynamic=False):
    """Give a shape transform a Bullet rigid body carrying the Havok settings.

    Static unless asked otherwise, for the reason the Blender add-on uses passive
    bodies: a Skyrim body is parented to a joint and the parenting wins over the
    simulation, so a dynamic body would be created and then not move. Spec R7.
    """
    from maya.app.mayabullet import RigidBody

    existing = rigid_body_of(shape)

    if existing is None:
        created = RigidBody.CreateRigidBody.command(
            transformName=shape,
            bAttachSelected=False,
            colliderShapeType=collider_of(shape),
            bodyType=mayaenv.DYNAMIC_BODY if dynamic else mayaenv.STATIC_BODY,
            autoFit=True,
        )
        existing = created[0] if isinstance(created, (list, tuple)) and created else created

    if existing is None:
        existing = rigid_body_of(shape)

    if existing is None:
        return None

    _set(existing, "bodyType",
         mayaenv.DYNAMIC_BODY if dynamic else mayaenv.STATIC_BODY)
    _set(existing, "colliderShapeType", collider_of(shape))

    mass = read_float(body, schema.RB_MASS)
    if mass is not None and mass > 0.0:
        _set(existing, "mass", mass)

    friction = read_float(body, schema.RB_FRICTION)
    if friction is not None:
        _set(existing, "friction", max(0.0, friction))

    restitution = read_float(body, schema.RB_RESTITUTION)
    if restitution is not None:
        _set(existing, "restitution", min(max(restitution, 0.0), 1.0))

    linear = read_float(body, schema.RB_LINEAR_DAMPING)
    if linear is not None:
        _set(existing, "linearDamping", min(max(linear, 0.0), 1.0))

    angular = read_float(body, schema.RB_ANGULAR_DAMPING)
    if angular is not None:
        _set(existing, "angularDamping", min(max(angular, 0.0), 1.0))

    mark_generated(existing)
    return existing


def mark_generated(node):
    """Record that this add-on made a node, so it can clean up only its own."""
    attribute = "%s.%s" % (node, schema.GENERATED)
    if not cmds.objExists(attribute):
        cmds.addAttr(node, longName=schema.GENERATED, attributeType="bool")
    cmds.setAttr(attribute, True)


def was_generated(node):
    attribute = "%s.%s" % (node, schema.GENERATED)
    return cmds.objExists(attribute) and bool(cmds.getAttr(attribute))


def _set(node, attribute, value):
    """Set an attribute if the node has it, quietly if it does not.

    Bullet's attribute set has moved between Maya versions, and a script that
    dies because one damping attribute was renamed is worse than one that sets
    the eleven it recognises.
    """
    full = "%s.%s" % (node, attribute)
    if not cmds.objExists(full):
        return False
    try:
        cmds.setAttr(full, value)
        return True
    except (RuntimeError, ValueError):
        return False
