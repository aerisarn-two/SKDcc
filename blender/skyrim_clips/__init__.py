"""Skyrim clips: play one of a creature's animations.

A creature arrives with every animation its Havok project has -- 216 on a
draugr -- as actions, with one assigned and the rest as muted NLA tracks.
Swapping which one plays means finding the armature that holds them, changing
the action in a second editor, and typing the frame range, because Blender has
no button that sets the scene to the length of the clip on it. Get that last
part wrong and the clip ends early: the rig holds its final pose and reads as
stuck rather than finished.

One panel, one list, one button.
"""

bl_info = {
    "name": "Skyrim Clips",
    "author": "Aerisarn",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > Skyrim",
    "description": "Put one of a creature's clips on its rig, at that clip's length",
    "category": "Animation",
}

from . import ops  # noqa: E402


def register():
    ops.register()


def unregister():
    ops.unregister()
