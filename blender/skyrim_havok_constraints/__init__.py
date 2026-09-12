"""Skyrim Havok constraints, as constraints Blender can use.

An FBX written by NIFBX or HKFBX carries a creature's ragdoll as properties on
empty objects, because FBX has no way to carry it as anything else -- its own
constraint objects are animation constraints with no limits, no friction and no
second frame, and Blender's importer discards them regardless. The reasoning
and the measurements are in ``dcc-constraint-interop-spec.md`` in NIFBX.

This add-on is the other half of that decision: it turns those properties into
real Blender constraints on the way in, and writes them back on the way out.
Inside Blender the link between two bodies is then an object pointer, which is
what makes it survive renaming -- something no name-based scheme in the file can
promise.
"""

bl_info = {
    "name": "Skyrim Havok Constraints",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Physics, Properties > Object",
    "description": "Build Blender constraints from NIFBX/HKFBX Havok properties",
    "category": "Physics",
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
