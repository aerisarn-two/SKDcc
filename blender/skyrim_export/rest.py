"""Undoing, on the way out, what the importer had to do on the way in.

A Skyrim bone is a transform: no length, no direction. Blender has to invent a
direction to draw one, and invents the best one there is -- it aims each bone at
the bone below it, which is what turns 92 sticks all pointing one way into a
skeleton somebody can pose. It then writes the aimed pose back out, and its
exporter has no per-bone inverse for it, so the rig that leaves is not the rig
that arrived: 44 of skeleton_cow's 48 nodes come back turned, 82 of a draugr's
93, the worst by 180 degrees.

The file it arrived in was right. Nothing in the conversion turned those bones
and nothing there can put them back, because from outside Blender an aimed bone
and a bone somebody turned on purpose are the same thing: one joint, two frames.
Inside Blender they are not the same thing at all, because this is where the
aiming happened, so this is where it is undone.

Both poses are had by reading the file twice. The first pass asks for no aiming
and gives the rest pose as the file states it, bone for bone; it is thrown away
at once, keeping only the numbers. The second is the import the person actually
gets, aimed and posable. At export the first pose goes back in for the duration
and the aimed one returns afterwards, so what lands in the FBX is the rig that
came out of the NIF and what stays on screen is the rig somebody can work with.

Two things move with the bones and have to be held still. Anything parented to a
bone hangs off that bone's tail -- which is the invention -- so a draugr's 19
ragdoll bodies swing a quarter turn when the tails go back; they are put back by
world matrix afterwards. And a pose channel means a rotation from the rest pose,
so changing the rest changes every animation that refers to it. That one is not
handled here, and does not need to be yet: `at_rest` holds the rig in its rest
pose for the export, and every action Blender bakes under it comes out flat --
measured, 216 actions, widest value spread 217.1 going in and 0.0 coming out.
Whoever fixes that has to conjugate each channel by this same correction.
"""

import contextlib

import bpy
import mathutils

#: The rest pose as the file states it, kept on the armature. Per-bone custom
#: properties are no use for this: Blender's importer drops a bone model's own,
#: measured at 0 of 92 kept, and keeps only what is on the node it spends on the
#: armature object.
STATED = "sk_bone_rest"


def _table(entries):
    return ";".join("%s=%s" % (name, ",".join(repr(x) for x in row))
                    for name, row in entries)


def _entries(text):
    table = {}

    for entry in (text or "").split(";"):
        name, sep, value = entry.partition("=")

        if not (sep and name):
            continue

        try:
            numbers = [float(x) for x in value.split(",")]
        except ValueError:
            continue

        if len(numbers) == 18:
            table[name] = numbers

    return table


def _pose(bone):
    """A bone's rest matrix, length and connectedness, as eighteen numbers.

    Connectedness belongs with the pose rather than beside it. A connected
    bone's head is not its own -- Blender pins it to the parent's tail and
    refuses to move it -- so a pose written over a rig connected for a
    different pose lands on 1 bone in 7. It is switched off while the rest
    pose is being written and put back once the heads are where the pose says,
    which is where the tails are, so putting it back moves nothing.
    """
    return ([x for row in bone.matrix_local for x in row]
            + [bone.length, 1.0 if bone.use_connect else 0.0])


def _wear(armature, table):
    """Put `table`'s rest pose on the armature, returning the one replaced."""
    previous = [(bone.name, _pose(bone)) for bone in armature.data.bones]

    # Whatever hangs off a bone hangs off its tail, and the tail is about to
    # move. Held by world matrix rather than by parent offset, because the
    # offset is stated against the frame that is changing.
    hanging = [(obj, obj.matrix_world.copy())
               for obj in bpy.data.objects
               if obj.parent is armature and obj.parent_type == "BONE"]

    mode = armature.mode
    active = bpy.context.view_layer.objects.active
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    try:
        for edit in armature.data.edit_bones:
            edit.use_connect = False

        for edit in armature.data.edit_bones:
            wanted = table.get(edit.name)

            if wanted is None:
                continue

            # A Matrix, not the four lists it is made of: assigning the lists
            # reads them as columns, which lands every bone transposed and with
            # its head at the origin.
            edit.matrix = mathutils.Matrix(
                (wanted[0:4], wanted[4:8], wanted[8:12], wanted[12:16]))
            edit.length = wanted[16]

        for edit in armature.data.edit_bones:
            wanted = table.get(edit.name)

            if wanted is not None and wanted[17] > 0.5:
                edit.use_connect = True
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = active

        if mode != "OBJECT":
            pass

    for obj, where in hanging:
        obj.matrix_world = where

    bpy.context.view_layer.update()

    return dict(previous)


def harvest(path):
    """The rest pose `path` states, read without any aiming and thrown away.

    Blender's importer is asked for the file twice rather than being asked to
    keep both answers, because it cannot: the aiming is not recorded anywhere,
    it is applied. The unaimed pass is the cheap one -- no animation, no
    properties, nothing kept but the numbers -- and the file is the same file,
    so the bones come back under the same names.
    """
    before = set(bpy.data.objects)

    bpy.ops.import_scene.fbx(
        filepath=path,
        automatic_bone_orientation=False,
        use_anim=False,
        use_custom_props=False,
        ignore_leaf_bones=False)

    arrived = [o for o in bpy.data.objects if o not in before]

    stated = {
        obj.name: _table((bone.name, _pose(bone)) for bone in obj.data.bones)
        for obj in arrived
        if obj.type == "ARMATURE"
    }

    for obj in arrived:
        bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.outliner.orphans_purge(do_local_ids=True, do_recursive=True)

    return stated


def remember(armature, stated):
    """Keep the stated pose on `armature`, where the export will look for it."""
    armature[STATED] = stated


@contextlib.contextmanager
def restored(scene):
    """Wear the stated rest pose for the duration, and take it off after."""
    worn = []

    for obj in scene.objects:
        if obj.type != "ARMATURE":
            continue

        table = _entries(obj.get(STATED))

        if table:
            worn.append((obj, _wear(obj, table)))

    try:
        yield worn
    finally:
        for obj, aimed in worn:
            _wear(obj, aimed)
