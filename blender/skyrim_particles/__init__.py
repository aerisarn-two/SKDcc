"""Skyrim particle systems, as particle systems Blender can play.

An FBX written by NIFBX carries a NIF particle system as properties: the system
on its own node, and one child node per modifier in the stack. FBX has no
emitter and nothing that means what ``NiPSysCylinderEmitter`` means, so there is
no conversion in the file -- only a choice between losing the system and
carrying it across intact, and NIFBX carries it. The semantics are in
``nif-particle-semantics-spec.md`` in NIFBX.

This add-on is the other half: it reads those properties and builds a Blender
particle system, so an effect can be looked at and tuned rather than guessed at
from a table of numbers.

It is one direction. Blender's particle system is not a superset of Skyrim's --
no cone half-angle, no colour or size curve on the system itself -- so a bake
back would have to invent what it could not read, and what it cannot represent
is reported instead.
"""

bl_info = {
    "name": "Skyrim Particles",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Particles",
    "description": "Build Blender particle systems from NIFBX particle properties",
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
