"""Reading a Skyrim scene in, so that it can go back out again.

The import settings matter as much as the export ones and are less visible,
because a wrong one here looks fine on screen and only shows up as a corrupted
file two steps later.

Bone orientation is the whole of it, and the answer is the opposite of the
obvious one. Blender can aim each bone at the bone below it, which is the only
way it will draw a Skyrim rig as a skeleton rather than as 92 sticks all
pointing one way -- and it re-writes the rest pose to do it, with no per-bone
inverse on the way out. Measured on a draugr: 82 of 93 nodes come back turned,
the worst by 180 degrees, and not one of them has moved, because aiming a bone
spins its frame about its own joint.

So the aiming is off. A Skyrim bone states no direction, Blender has to invent
one either way, and `skyrim_rig` invents a better one for the drawing alone --
every bone drawn down its own chain, by a shape that is turned while the bone
is not. That leaves the rest pose exactly as the file states it, which is worth
more than a rig that looks right and converts back wrong: with the aiming on and
nothing else done, 44 of skeleton_cow's 48 nodes are lost; with it off, none.
"""

import bpy


def options(**overrides):
    settings = {
        # Off, deliberately. It rewrites the rest pose and cannot undo it, and
        # `skyrim_rig` draws the bones down their chains without moving them.
        "automatic_bone_orientation": False,

        # The properties are the file: the nif block each node was, the Havok
        # body it carries, the clips it plays. Without this an FBX comes in as
        # geometry and cannot be turned back into a creature.
        "use_custom_props": True,

        # The animation is most of a creature. Without this a draugr arrives
        # with none of its 216 clips.
        "use_anim": True,

        # Blender drops a bone it decides is a leaf. A Skyrim skeleton is full
        # of them -- WEAPON, SHIELD, the magic nodes -- and they are bones the
        # file names and the clips key.
        "ignore_leaf_bones": False,
    }

    settings.update(overrides)

    return settings


def read(path):
    """Import `path` with the settings a Skyrim scene has to arrive with."""
    before = set(bpy.data.objects)

    bpy.ops.import_scene.fbx(**options(filepath=path))

    return sum(1 for o in bpy.data.objects
               if o not in before and o.type == "ARMATURE")
