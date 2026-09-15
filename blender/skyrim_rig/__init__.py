"""Skyrim rig: tell a creature's sockets from its bones.

A Skyrim skeleton is a tree of named transforms and says nothing about which of
them deform anything. A third of a draugr's do not: weapon and shield nodes,
magic nodes, pauldron and beard attachments, toe pivots. Blender imports them as
bones, because that is what they are in the FBX, and draws each one a tail it
had to invent.

This marks them -- ``use_deform`` off, gathered in a ``Sockets`` collection,
invented tails cut back -- without touching a weight or an animation channel.
"""

bl_info = {
    "name": "Skyrim Rig",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "Properties > Data (Armature) > Skyrim Rig",
    "description": "Tell a creature's attachment nodes from its deforming bones",
    "category": "Rigging",
}

from . import ops, ui  # noqa: E402


def register():
    ops.register()
    ui.register()


def unregister():
    ui.unregister()
    ops.unregister()
