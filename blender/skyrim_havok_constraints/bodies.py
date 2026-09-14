"""Finding and making rigid bodies.

A Havok body is an empty in the scene -- ``<bone>_rb``, bone-parented to the
armature -- with its collision shape as a child mesh. Blender's rigid body is
a property of a *mesh*, so the two do not sit on the same object:

    L_Humerus_rb                  the Havok body: properties, bone parenting
      L_Humerus_rb_capsule        the shape: geometry, and Blender's rigid body
      L_Humerus_rb_con_..._attach_point
"""

import bpy

from . import schema
from .blender_compat import active, ensure_rigid_body_world
from .joint import read_float


def find_body(objects, name):
    """The body of that name, tolerating Blender's rename suffix.

    Importing into a scene that already holds a body of the same name gets a
    ``.001`` while the property still says the original, so an exact match is
    tried first and the suffixed one only when it is unambiguous.
    """
    if not name:
        return None

    for obj in objects:
        if obj.name == name:
            return obj

    prefix = name + "."
    matches = [o for o in objects
               if o.name.startswith(prefix) and o.name[len(prefix):].isdigit()]

    if len(matches) == 1:
        return matches[0]

    # By the name Havok knows it by, which is not the name the NIF knows it by.
    # A creature exported together with its skeleton.hkx has the ragdoll names
    # read out of Havok rather than inferred, so its constraints ask for
    # `Ragdoll_Pelvis01` while the object in the scene is `Pelvis_rb` -- and
    # every joint on the chicken was skipped for a body that was right there.
    # The body itself carries the mapping.
    named = [o for o in objects if str(o.get(schema.RAGDOLL_BONE, "")) == name]

    return named[0] if len(named) == 1 else None


def shape_of(body):
    """The child mesh holding the body's collision geometry.

    Every vanilla skeleton body has exactly one. A list shape tessellates to
    several, and then the first is taken, because Blender's rigid body is one
    shape per object -- recorded rather than hidden, since it means a list
    shape simulates as its first child until somebody joins them.
    """
    if body is None:
        return None
    if body.type == "MESH":
        return body
    meshes = [c for c in body.children if c.type == "MESH"]
    return meshes[0] if meshes else None


def make_rigid_body(scene, body, shape, dynamic=False):
    """Give a shape mesh a Blender rigid body carrying the Havok settings.

    Passive and kinematic unless asked otherwise. A Skyrim body is bone
    parented, and Blender's parenting overrides the simulation, so an active
    body would be created and then not move -- which looks like a bug in this
    add-on rather than the two systems disagreeing. Passive is honest: the
    shapes are there, the constraints are there, and turning the ragdoll on is
    a deliberate act that starts with unparenting.
    """
    ensure_rigid_body_world(scene)

    if shape.rigid_body is None:
        with active(shape):
            bpy.ops.rigidbody.object_add()

    rb = shape.rigid_body
    rb.type = "ACTIVE" if dynamic else "PASSIVE"
    rb.kinematic = not dynamic
    rb.collision_shape = schema.collision_shape_of(shape.name)

    mass = read_float(body, schema.RB_MASS)
    if mass is not None and mass > 0.0:
        rb.mass = mass

    friction = read_float(body, schema.RB_FRICTION)
    if friction is not None:
        rb.friction = max(0.0, friction)

    restitution = read_float(body, schema.RB_RESTITUTION)
    if restitution is not None:
        rb.restitution = min(max(restitution, 0.0), 1.0)

    linear = read_float(body, schema.RB_LINEAR_DAMPING)
    if linear is not None:
        rb.linear_damping = min(max(linear, 0.0), 1.0)

    angular = read_float(body, schema.RB_ANGULAR_DAMPING)
    if angular is not None:
        rb.angular_damping = min(max(angular, 0.0), 1.0)

    shape[schema.GENERATED] = 1
    return rb


def clear_rigid_body(shape):
    """Remove a rigid body this add-on added, leaving one it did not."""
    if shape.rigid_body is None or schema.GENERATED not in shape.keys():
        return False
    with active(shape):
        bpy.ops.rigidbody.object_remove()
    del shape[schema.GENERATED]
    return True
