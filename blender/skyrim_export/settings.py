"""How a Skyrim scene has to leave Blender.

Every value here was measured by converting the result back to NIF with
``se-cmd importnpc`` and comparing the world position of every node against the
file that went in. A draugr's skeleton has 92 of them; the settings below put
all 92 back within 0.0001 units, and each wrong setting is recorded beside the
right one with what it costs, because none of this is guessable from the
exporter's dialog.
"""

import contextlib

import bpy
import mathutils

#: The scene leaves in the frame it is in, which is what the game's converters
#: read. NIFBX writes ``UpAxis = 2`` into an FBX's global settings and its reader
#: does not consult the field at all: `FbxToNif` takes the numbers as Z-up
#: because Skyrim is Z-up, so whatever a file *declares*, what it is read as is
#: fixed. Blender is the other way round -- its importer honours the declaration
#: and its exporter writes whichever frame it is asked for.
#:
#: So a Blender round trip hides this completely. Export with the exporter's
#: defaults, read it back in Blender, and nothing has moved, because the
#: conversion out and the conversion in cancel. Convert that same file to NIF
#: and 90 of a draugr's 92 skeleton nodes are in the wrong place, the worst 193
#: units out: a capsule at (0, 32.45, 104.06) comes back at (0, 104.06, -32.45),
#: which is -90 degrees about X, which is Z-up written as Y-up.
#:
#: Measured on the way to NIF, which is the only place it shows: ``-Y``/``Z``
#: fixes the up axis and leaves the scene spun 180 degrees about it, ``X`` and
#: ``-X`` are worse again, and ``Y``/``Z`` -- Blender's own frame, written out
#: unchanged -- puts all 92 back within 0.0001 units.
AXIS_FORWARD = "Y"
AXIS_UP = "Z"


def options(**overrides):
    """The keyword arguments for ``bpy.ops.export_scene.fbx``.

    In one place because these are four independent facts about the format, and
    a caller who retypes three of them is the caller who finds out about the
    fourth the hard way.
    """
    settings = {
        "axis_forward": AXIS_FORWARD,
        "axis_up": AXIS_UP,

        # The properties are the file. A Havok body's mass, a constraint's two
        # bodies, the nif block each node was, which file it came from: all of
        # it rides as custom properties, and without this the FBX that comes
        # out is geometry and nothing else.
        "use_custom_props": True,

        # Blender invents a tail for every bone that has no child and can write
        # each one out as a bone of its own. A draugr gains 21 that the skeleton
        # never had, and they arrive in the NIF as nodes.
        "add_leaf_bones": False,
    }

    settings.update(overrides)

    return settings


@contextlib.contextmanager
def at_rest(scene):
    """Put every armature back to its rest pose for the duration.

    A bone's node in the FBX carries where the bone *is*, not where it rests, so
    a rig exported while an action is applied writes the pose into the skeleton
    and the creature is rebuilt standing in whatever frame happened to be
    current. On a draugr holding 216 clips that is 83 of 92 nodes out of place,
    the worst 39 units -- and the file still looks like a draugr, which is what
    makes it worth doing something about rather than noticing later.

    The pose is emptied rather than switched off. Setting ``pose_position`` to
    ``REST`` does put the skeleton right, and it also tells Blender to ignore
    poses while it bakes: every action comes out flat. Measured on the draugr,
    216 actions with a widest value spread of 217.1 going in and 0.0 coming out,
    which is every animation in the file silently lost. Emptying the channels
    instead leaves the rig standing at rest for the skeleton, and leaves the
    baking to read the actions as it should -- same 216 actions, spread 217.1,
    and bones landing within 0.0011 units of where they started.

    Bone constraints are muted with it. They are the other thing ``REST`` used to
    switch off, and a rig posed by a constraint is one whose rest pose is not
    what its channels say.

    The action is unlinked as well as the channels emptied: an action left linked
    simply fills them in again on the next evaluation.
    """
    changed = []
    posed = []
    muted = []

    for obj in scene.objects:
        if obj.type != "ARMATURE":
            continue

        action = obj.animation_data.action if obj.animation_data else None
        changed.append((obj, action))

        if obj.animation_data:
            obj.animation_data.action = None

        for bone in obj.pose.bones:
            posed.append((bone, bone.matrix_basis.copy()))
            bone.matrix_basis = mathutils.Matrix.Identity(4)

            for constraint in bone.constraints:
                if not constraint.mute:
                    muted.append(constraint)
                    constraint.mute = True

    if changed:
        bpy.context.view_layer.update()

    try:
        yield
    finally:
        for constraint in muted:
            constraint.mute = False

        for bone, basis in posed:
            bone.matrix_basis = basis

        for obj, action in changed:
            if action is not None and obj.animation_data:
                obj.animation_data.action = action

        if changed:
            bpy.context.view_layer.update()
