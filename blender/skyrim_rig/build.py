"""Telling a creature's sockets apart from its bones.

A Skyrim skeleton is a tree of ``NiNode``, and the file says nothing about which
of them deform anything. A third of a draugr's -- 31 of 92 -- carry no weight at
all: ``WEAPON``, ``SHIELD``, ``QUIVER``, the magic nodes, the pauldrons, the
beard and ponytail attachments, the toe pivots. The game hangs a sword off
``WeaponSword`` by parenting to it, exactly as it hangs skin off ``Spine2`` by
weighting to it, and there is no flag distinguishing the two.

The FBX carries that distinction where FBX carries it -- every node is a
``LimbNode`` and the skin's clusters name the ones that deform -- so Blender
imports all of them as bones. Which is correct, and looks wrong: a bone needs a
tail, the importer invents one for a bone with no child, and a socket ends up a
metre long sticking out of a body a metre and a half tall.

They are not empties, tempting as that is. 18 of the draugr's 21 non-deforming
leaves are keyframed in all 216 of its clips -- the weapon node swings when the
character swings -- and an empty parented to a bone cannot carry a bone's
animation. They are animated bones that deform nothing, which is a thing Blender
already has a word for: ``use_deform``.

So this marks them: the flag off, gathered into a collection that can be hidden
in one click, and their invented tails cut to the length of the bones that have
a real one. Nothing about the skinning or the animation changes -- the weights
they do not have cannot be lost, and the channels stay where they are.
"""

import statistics

import bpy

from . import schema


class Report:
    """What a run did."""

    def __init__(self):
        self.armatures = 0
        self.sockets = 0
        self.trimmed = 0
        self.notes = []

    def __str__(self):
        text = f"{self.sockets} socket(s) on {self.armatures} armature(s)"

        if self.trimmed:
            text += f", {self.trimmed} shortened"

        return text


def deforming_names(armature, scene_objects):
    """Every bone name some mesh actually weights to."""
    found = set()

    for obj in scene_objects:
        if obj.type != "MESH":
            continue

        if not any(m.type == "ARMATURE" and m.object is armature for m in obj.modifiers):
            continue

        groups = {g.index: g.name for g in obj.vertex_groups}

        for vertex in obj.data.vertices:
            for group in vertex.groups:
                if group.weight > 0.0:
                    found.add(groups.get(group.group, ""))

    return found


def sockets_of(armature, scene_objects):
    """The bones that deform nothing, in name order."""
    deforming = deforming_names(armature, scene_objects)

    return sorted(
        (b for b in armature.data.bones if b.name not in deforming),
        key=lambda b: b.name,
    )


def build(scene):
    """Mark every armature's sockets, and cut their invented tails."""
    report = Report()

    for armature in [o for o in scene.objects if o.type == "ARMATURE"]:
        report.armatures += 1

        # Nothing skinned to it means no evidence either way, not evidence that
        # every bone is a socket. A skeleton.nif on its own has no mesh at all,
        # and marking the whole rig would be true by vacuum and useless.
        if not deforming_names(armature, scene.objects):
            report.notes.append(
                f"{armature.name}: nothing is skinned to it, so which bones deform "
                "cannot be told -- import it with a body to find out")
            continue

        sockets = sockets_of(armature, scene.objects)

        if not sockets:
            report.notes.append(f"{armature.name}: every bone deforms something")
            continue

        # The length a bone has when it has a child to point at. A socket's
        # length is invented, so this is the only honest number to give it.
        real = [b.length for b in armature.data.bones if b.children and b.length > 0.0]
        cap = statistics.median(real) if real else 0.0

        names = {b.name for b in sockets}

        for bone in armature.data.bones:
            if bone.name in names:
                bone.use_deform = False
                bone[schema.SOCKET] = 1
                report.sockets += 1
            elif schema.SOCKET in bone.keys():
                del bone[schema.SOCKET]

        _collect(armature, names)

        if cap > 0.0:
            report.trimmed += _trim(armature, names, cap)

        armature[schema.MARKED] = 1
        armature[schema.CAP] = cap

    return report


def _collect(armature, names):
    """Gather them where they can be hidden in one go."""
    data = armature.data

    if not hasattr(data, "collections"):
        return

    existing = data.collections.get(schema.COLLECTION)
    group = existing or data.collections.new(schema.COLLECTION)

    for bone in data.bones:
        if bone.name in names:
            group.assign(bone)


def _trim(armature, names, cap):
    """Cut an invented tail back, without moving the head or the roll.

    Only the tail, and only along the direction it already had, so the bone's
    matrix is unchanged and nothing that rides it can move.
    """
    previous = bpy.context.view_layer.objects.active
    mode = armature.mode

    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode="EDIT")

    trimmed = 0

    for bone in armature.data.edit_bones:
        if bone.name not in names or bone.children or bone.length <= cap:
            continue

        direction = (bone.tail - bone.head).normalized()
        bone.tail = bone.head + direction * cap
        trimmed += 1

    bpy.ops.object.mode_set(mode="OBJECT")

    if previous is not None:
        bpy.context.view_layer.objects.active = previous

    return trimmed


def clear(scene):
    """Put every marked bone back to deforming, and forget the marks."""
    restored = 0

    for armature in [o for o in scene.objects if o.type == "ARMATURE"]:
        if schema.MARKED not in armature.keys():
            continue

        for bone in armature.data.bones:
            if schema.SOCKET in bone.keys():
                bone.use_deform = True
                del bone[schema.SOCKET]
                restored += 1

        if hasattr(armature.data, "collections"):
            group = armature.data.collections.get(schema.COLLECTION)

            if group is not None:
                armature.data.collections.remove(group)

        del armature[schema.MARKED]

        if schema.CAP in armature.keys():
            del armature[schema.CAP]

    return restored
