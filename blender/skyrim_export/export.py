"""Writing the scene out."""

import bpy

from . import settings


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


def write(scene, path, animations=False):
    """Export the scene to `path` the way the game's converters expect it.

    Animations are off by default, and that is not a performance choice. The
    clips a creature scene arrives with are Havok clips, recorded on the FBX's
    animation stacks as properties; Blender reads the curves and drops the
    properties, so what leaves is 216 stacks that no longer say which clip each
    one is, and the import counts none of them. Exporting them is still the
    right thing when the animation is the point -- it just is not a round trip,
    so it is asked for.
    """
    with settings.at_rest(scene):
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
