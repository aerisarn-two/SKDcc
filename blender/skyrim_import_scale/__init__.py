"""Repair the scale Blender's FBX importer gives hidden objects.

Blender scales an imported FBX into the scene's units and skips that for any
object it imports hidden, which leaves it a hundred times too big in a Skyrim
export -- collision proxies and anything the NIF marks invisible. The file is
not at fault: strip the visibility flags and nothing else, and every object
comes in at one scale.

One button, in Object properties.
"""

bl_info = {
    "name": "Skyrim Import Scale",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Object",
    "description": "Rescale objects Blender imported hidden",
    "category": "Import-Export",
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
