"""Aim a NiBillboardNode at the camera, the way the engine does.

The engine turns one of these to face the viewer every frame. A converted scene
has it as an ordinary node with whatever rotation the file happened to store, so
it is right from one direction and wrong from every other -- the campfire's glow
sits in a plane across the fire and vanishes when you orbit past it.

Blender's equivalent is a constraint, and which one depends on the mode: the
modes that rotate about the up axis keep the node upright and turn to face you,
which is Locked Track; the rest face the viewer outright, which is Track To.

Which way round is worked out from the mesh rather than assumed. A NIF billboard
carries its quad under it at whatever orientation the artist left, so the axis
that should point at the camera is the one the geometry's own normal runs along.

Nothing here is written back. NIFBX carries a billboard's authored rotation and
prefers it over whatever a scene leaves, because Blender's FBX exporter writes
the *evaluated* transform -- a plane authored at no rotation came back at
111.8, 0, -143.1 after a round trip through a Track To. So aiming these changes
what you see and not what the file says.
"""

import bpy

from . import schema


class Report:
    def __init__(self):
        self.aimed = []
        self.skipped = []
        self.notes = []

    def __str__(self):
        text = f"{len(self.aimed)} billboard(s)"

        if self.skipped:
            text += f", {len(self.skipped)} skipped"

        return text


def is_billboard(obj):
    return str(obj.get(schema.BLOCK_TYPE, "")) == schema.BILLBOARD


def _mode(obj):
    try:
        return int(float(obj.get(schema.MODE, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _facing_axis(obj):
    """Which of the node's local axes its geometry looks along.

    Averaged over the child meshes' normals and taken in the node's own space,
    so a quad laid down however the artist laid it still points the right way.
    Falls back to +Y, which is where a plane built in the XZ plane looks.
    """
    total = [0.0, 0.0, 0.0]
    found = False

    for child in obj.children_recursive:
        if child.type != "MESH" or not child.data.polygons:
            continue

        to_node = obj.matrix_world.inverted() @ child.matrix_world

        for polygon in child.data.polygons:
            normal = (to_node.to_3x3() @ polygon.normal).normalized()

            for i in range(3):
                total[i] += normal[i]

            found = True

    if not found:
        return "TRACK_Y"

    axis = max(range(3), key=lambda i: abs(total[i]))
    sign = total[axis] >= 0.0

    return ("TRACK_X" if sign else "TRACK_NEGATIVE_X",
            "TRACK_Y" if sign else "TRACK_NEGATIVE_Y",
            "TRACK_Z" if sign else "TRACK_NEGATIVE_Z")[axis]


def _up_axis(obj, facing):
    """A local axis to hold upright, which must not be the one that faces out.

    Tracking along an axis while calling the same axis "up" is degenerate --
    Blender has nothing left to resolve the roll with, and the plane comes out
    edge-on to the camera rather than square to it, which is what it did.

    So the up is chosen from the two axes that are left, taking whichever points
    most nearly at the world's own up. A flame then stays upright while it turns.
    """
    index = {"X": 0, "Y": 1, "Z": 2}[facing[-1]]
    basis = obj.matrix_world.to_3x3()

    best, score = None, -1.0

    for axis, i in (("X", 0), ("Y", 1), ("Z", 2)):
        if i == index:
            continue

        upness = abs(basis.col[i].normalized().z)

        if upness > score:
            best, score = axis, upness

    return best or ("Z" if index != 2 else "Y")


def build(scene):
    """Aim every billboard in the scene at its camera."""
    report = Report()
    camera = scene.camera

    billboards = [o for o in scene.objects if is_billboard(o)]

    if not billboards:
        return report

    if camera is None:
        report.skipped.append(
            "no camera in the scene: a billboard has nothing to face, so none were "
            "aimed -- add one and build again"
        )
        return report

    for obj in billboards:
        for existing in list(obj.constraints):
            if existing.name.startswith(schema.CONSTRAINT_NAME):
                obj.constraints.remove(existing)

        mode = _mode(obj)
        axis = _facing_axis(obj)

        up = _up_axis(obj, axis)

        if mode in schema.ABOUT_UP:
            # Upright, turning about its own up to face the viewer.
            constraint = obj.constraints.new("LOCKED_TRACK")
            constraint.lock_axis = f"LOCK_{up}"
        else:
            constraint = obj.constraints.new("TRACK_TO")
            constraint.up_axis = f"UP_{up}"

        constraint.name = schema.CONSTRAINT_NAME
        constraint.target = camera
        constraint.track_axis = axis

        report.aimed.append(obj.name)
        report.notes.append(
            f"{obj.name}: billboard mode {mode}, aimed with "
            f"{'Locked Track' if mode in schema.ABOUT_UP else 'Track To'} along {axis}, "
            f"up {up}"
        )

    return report


def clear(scene):
    """Take the aiming away, leaving the file's own rotations."""
    removed = 0

    for obj in scene.objects:
        for constraint in list(obj.constraints):
            if constraint.name.startswith(schema.CONSTRAINT_NAME):
                obj.constraints.remove(constraint)
                removed += 1

    return removed
