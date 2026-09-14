"""Skyrim shader properties, as Blender materials.

An FBX written by NIFBX carries a NIF shader as properties on the material: the
flag words, the shading path, the blend modes, the effect shader's own fields,
and the path of every texture slot FBX has nowhere standard to put. Blender's
importer keeps all of them.

It has to be that way round. FBX has no node graph, and a Blender node tree
exported to FBX comes back flattened -- seven nodes in, three out, measured. So
the shader itself cannot travel; the parameters travel and this rebuilds the
tree from them.

An effect shader is rebuilt faithfully, because NifSkope's own fragment shader
for it has no lighting in it and every operation has a Blender node. A lighting
shader is mapped onto a Principled BSDF instead, which is not what NifSkope
draws and is deliberately not trying to be: see ``build.py``.

One direction. Nothing here writes back to the properties, so an edit made to a
node tree is an edit to the picture and not to the file.
"""

bl_info = {
    "name": "Skyrim Materials",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Material",
    "description": "Rebuild Blender materials from NIFBX shader properties",
    "category": "Material",
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
