"""Writing the scene out."""

import bpy

from . import rest, settings


class Exported:
    def __init__(self, path, objects, armatures, animated):
        self.path = path
        self.objects = objects
        self.armatures = armatures
        self.animated = animated

    def __str__(self):
        text = "%d objects, %d armatures" % (self.objects, self.armatures)

        if self.animated:
            text += ", %d actions" % self.animated

        return text


def write(scene, path, animations=True):
    """Export the scene to `path` the way the game's converters expect it.

    Animations are written, because a creature's clips are part of it. They did
    not used to survive: a Havok clip is identified by properties on the FBX's
    animation stack, Blender reads a stack as an action and an action has
    nowhere to keep them, and the stacks Blender writes out are new ones it
    named itself. A draugr went out with 216 clips and came back with 216
    anonymous animations, which the import counted as none.

    SKAssets now writes the same list on a node as well, where it survives like
    every other custom property, and a stack that has lost its own properties is
    found there by name. Measured on the draugr: 216 out, 216 back.

    Turning them off is for when the animation genuinely is not wanted -- it is
    most of the file's size and most of its export time.

    The rest pose goes out with it. Blender's importer re-aims every bone to
    draw it and cannot put it back, so `rest.py` puts the stated pose on for
    the duration of the write: the rig that lands in the NIF is the rig that
    came out of it, and the rig on screen afterwards is the one somebody can
    pose.
    """
    with settings.at_rest(scene), rest.restored(scene):
        bpy.ops.export_scene.fbx(**settings.options(
            filepath=path,
            bake_anim=animations,
            bake_anim_use_all_actions=animations,
        ))

    return Exported(
        path,
        len(scene.objects),
        sum(1 for o in scene.objects if o.type == "ARMATURE"),
        len(bpy.data.actions) if animations else 0)
