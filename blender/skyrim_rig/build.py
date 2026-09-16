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

A bone with no child has an invented *direction* as well as an invented length,
and that is the one people notice. An importer aiming a bone at the bone below
it has nothing to aim a leaf at, so the leaf keeps whatever way its own node
faced: measured on a draugr, 18 of 39 leaves point more than 30 degrees off the
bone above them -- both `ForearmTwist1` at 90 degrees, `WEAPON` and `SHIELD` at
90, the pauldrons at 88, the three weapon nodes at 126 and the beard at 170.
They are drawn sticking out of the body, and a viewer reading the same FBX draws
them correctly, because it draws a joint and no direction at all.

So this invents one, for the drawing only. A leaf is given a shape to be drawn
as in place of its octahedron, and that shape is turned to carry on the line the
bone above it arrives on -- which is where the limb goes, and what a viewer
showing the same file draws.

Display only, which is the whole reason it is allowed to guess. A bone's shape
is turned by `custom_shape_rotation_euler`, and the bone is not: its rest pose,
its roll and its matrix are exactly as they were imported, so every pose channel
still means what it meant, all 216 of a draugr's clips still play, and the FBX
written afterwards is byte for byte what it would have been. Nothing has to be
undone on the way out because nothing was done.
"""

import math
import statistics

import bpy
import mathutils

from . import schema


class Report:
    """What a run did."""

    def __init__(self):
        self.armatures = 0
        self.sockets = 0
        self.trimmed = 0
        self.marked = 0
        self.notes = []

    def __str__(self):
        text = f"{self.sockets} socket(s) on {self.armatures} armature(s)"

        if self.trimmed:
            text += f", {self.trimmed} shortened"

        if self.marked:
            text += f", {self.marked} drawn as joints"

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
            report.marked += _mark_joints(armature, cap)

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


def _marker():
    """The shape a directionless bone is drawn as, made once and shared.

    A bone: an octahedron a unit long down +Y, which is the way Blender draws
    one, so a leaf carrying it looks like every other bone in the rig rather
    than like a marker somebody bolted on.

    Never linked to a collection. A custom shape does not have to be in the
    scene to be drawn, and one that is in the scene is one the FBX exporter
    writes out as a mesh -- a stray object in every converted creature.
    """
    existing = bpy.data.objects.get(schema.MARKER)

    if existing is not None:
        return existing

    mesh = bpy.data.meshes.new(schema.MARKER)

    w = 0.1
    mesh.from_pydata(
        [(0, 0, 0), (w, 0.2, w), (-w, 0.2, w), (-w, 0.2, -w), (w, 0.2, -w), (0, 1, 0)],
        [(0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1),
         (1, 5), (2, 5), (3, 5), (4, 5)],
        [])
    mesh.update()

    return bpy.data.objects.new(schema.MARKER, mesh)


#: How far a bone may be drawn from where it ought to point before it is worth
#: overriding. Blender aims most bones well and this leaves those alone; what it
#: catches is the handful it cannot get right, where a bone has several children
#: or one sitting on top of it.
SKEW = 30.0


def _onward(bone):
    """Which way this bone ought to be drawn pointing.

    Down its own chain: at its children, averaged, which for a pelvis with two
    thighs is straight down between them and for a bone with one child is that
    child. A bone with no children carries on the line its parent arrives on,
    which is where the limb was heading. Children sitting on the bone's own head
    -- a twist bone does -- say nothing about direction and are left out.
    """
    onward = mathutils.Vector((0.0, 0.0, 0.0))

    for child in bone.children:
        along = child.head_local - bone.head_local

        if along.length > 1e-4:
            onward += along.normalized()

    if onward.length > 1e-6:
        return onward.normalized()

    parent = bone.parent

    if parent is None:
        return None

    along = bone.head_local - parent.head_local

    if along.length < 1e-4:
        along = parent.tail_local - parent.head_local

    return along.normalized() if along.length > 1e-6 else None


def _drawn(bone):
    """The way the bone is drawn now, before any shape is put on it."""
    along = bone.tail_local - bone.head_local

    return along.normalized() if along.length > 1e-9 else None


def _mark_joints(armature, cap):
    """Draw every bone whose direction is invented pointing down its chain."""
    if armature.pose is None:
        return 0

    marker = _marker()
    marked = 0

    for posed in armature.pose.bones:
        bone = posed.bone
        onward = _onward(bone)

        if onward is None:
            continue

        # A bone with children is usually aimed at them already, and redrawing
        # one that is right gains nothing and risks looking worse.
        if bone.children:
            drawn = _drawn(bone)

            if drawn is None or math.degrees(math.acos(
                    max(-1.0, min(1.0, drawn.dot(onward))))) <= SKEW:
                continue

        # The shape is turned, not the bone. Expressed in the bone's own frame,
        # because that is the frame a custom shape is drawn in, and measured
        # from +Y, because that is the way a bone points.
        local = bone.matrix_local.to_3x3().inverted_safe() @ onward
        posed.custom_shape_rotation_euler = (
            mathutils.Vector((0.0, 1.0, 0.0)).rotation_difference(local).to_euler())

        posed.custom_shape = marker

        # Not scaled by the bone, whose length is invented too: a socket cut to
        # the cap and a finger tip a tenth as long would be drawn a tenth the
        # size, and the small ones would vanish.
        posed.use_custom_shape_bone_size = False

        # A bone with children is drawn to reach the nearest of them, so the
        # joint it leads to is where the drawing stops. A leaf has no such
        # length and takes the cap, like its tail.
        reach = min((child.head_local - bone.head_local).length
                    for child in bone.children) if bone.children else cap
        size = reach if reach > 1e-4 else cap
        posed.custom_shape_scale_xyz = (size, size, size)
        marked += 1

    return marked


def _unmark_joints(armature):
    """Give every bone its octahedron back."""
    if armature.pose is None:
        return

    for bone in armature.pose.bones:
        if bone.custom_shape is not None and bone.custom_shape.name == schema.MARKER:
            bone.custom_shape = None
            bone.use_custom_shape_bone_size = True
            bone.custom_shape_rotation_euler = (0.0, 0.0, 0.0)
            bone.custom_shape_scale_xyz = (1.0, 1.0, 1.0)


def clear(scene):
    """Put every marked bone back to deforming, and forget the marks."""
    restored = 0

    for armature in [o for o in scene.objects if o.type == "ARMATURE"]:
        if schema.MARKED not in armature.keys():
            continue

        _unmark_joints(armature)

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
