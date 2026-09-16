"""Reading a Skyrim scene in, so that it can go back out again.

The import settings matter as much as the export ones and are less visible,
because a wrong one here looks fine on screen and only shows up as a corrupted
file two steps later.

Bone orientation is the whole of it. Left off, every bone is drawn along the
same axis and the rig is a heap of sticks -- correct, and not something anyone
can pose. Turned on, Blender aims each bone down its own chain and the rig is
usable, at the cost of rewriting the rest pose; `rest.py` is how that cost is
paid back, and why the file is read twice. So it is turned on here, and the
pose the file states is taken off the unaimed pass and kept.
"""

import bpy

from . import rest


def options(**overrides):
    settings = {
        # A bone aimed at the bone below it, rather than along a fixed axis.
        # This is what makes the rig posable, and it rewrites the rest pose to
        # do it -- see `rest.py`, which is why that is affordable.
        "automatic_bone_orientation": True,

        # The properties are the file: the nif block each node was, the Havok
        # body it carries, the clips it plays. Without this an FBX comes in as
        # geometry and cannot be turned back into a creature.
        "use_custom_props": True,
    }

    settings.update(overrides)

    return settings


def read(path):
    """Import `path`, keeping the rest pose the aiming is about to overwrite."""
    stated = rest.harvest(path)

    before = set(bpy.data.objects)

    bpy.ops.import_scene.fbx(**options(filepath=path))

    armatures = [o for o in bpy.data.objects
                 if o not in before and o.type == "ARMATURE"]

    kept = 0

    for armature in armatures:
        if armature.name in stated:
            rest.remember(armature, stated[armature.name])
            kept += 1

    return kept, len(armatures)
