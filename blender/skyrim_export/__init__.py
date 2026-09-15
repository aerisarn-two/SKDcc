"""Skyrim export: the settings a Skyrim scene has to leave Blender with.

Blender's FBX importer reads a Skyrim scene without converting its axes, and
Blender's FBX exporter converts them on the way out. Nothing says so, and the
result still looks like a creature -- lying on its face, 193 units from where it
was. Two more settings are as quiet: a rig exported while an action is applied
writes that pose into the skeleton, and an export without custom properties
writes geometry where the file was mostly properties.

So the four of them live in one place and behind one menu entry, with what each
wrong value costs measured on a draugr. See `settings.py`.
"""

bl_info = {
    "name": "Skyrim Export",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "File > Export > Skyrim (.fbx)",
    "description": "Export FBX the way the NIF and Havok converters expect it",
    "category": "Import-Export",
}

from . import ops  # noqa: E402


def register():
    ops.register()


def unregister():
    ops.unregister()
