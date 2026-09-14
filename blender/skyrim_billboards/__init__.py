"""Skyrim billboard nodes, aimed the way the engine aims them.

A ``NiBillboardNode`` turns to face the viewer every frame. FBX has no such
node, so a converted scene shows one as an ordinary node holding whatever
rotation the file happened to store -- right from one direction and wrong from
every other. The campfire has two: the glow over the fire and the heat haze
above it.

This puts a constraint on each, which is Blender's own way of saying the same
thing. It changes what you see and not what the file says: NIFBX carries a
billboard's authored rotation and prefers it on the way back, because Blender's
FBX exporter writes the evaluated transform and would otherwise bake the aim in.
"""

bl_info = {
    "name": "Skyrim Billboards",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Object Constraints",
    "description": "Aim NiBillboardNode objects at the camera",
    "category": "Object",
}

import bpy

from . import ops, ui

CLASSES = ops.CLASSES + ui.CLASSES


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
