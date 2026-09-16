"""Keeping a rig's rest pose, which Blender cannot keep by itself.

A Skyrim bone is a transform: no length, no direction. Blender has to invent a
direction to draw one, and invents the best one there is -- it aims each bone at
the bone below it, which is what turns 92 sticks all pointing the same way into
a skeleton somebody can animate. It then writes the aimed pose back out, and its
exporter has no per-bone inverse for it, so the rig that leaves is not the rig
that arrived: 83 of a draugr's 93 nodes come back rotated.

Nothing is lost by the aiming. Re-aiming a bone spins its frame about its own
joint and never moves a joint, so the NIF's own numbers are still right and only
have to survive the trip. NIFBX sends them in ``nif_bone_rest``, one table on
the node Blender spends on the armature object -- the only node whose custom
properties Blender's importer keeps; a bone's own are dropped, measured at 0 of
92 kept.

What NIFBX cannot do is decide when to use them. Turning a node in place is a
real edit -- somebody rotating ``WEAPON`` so a sword sits differently -- and
from inside the file it looks exactly like the importer's aiming: same joint,
different frame. Guessing costs somebody their edit either way round.

Here it is not a guess. The pose is written down as the importer left it, before
anyone has touched anything, so at export a bone that still matches its snapshot
was turned by the importer and a bone that does not was turned by a person. Only
the first kind is answered for, in ``sk_bone_rest``; the rest is the scene's to
say, as it always was.
"""

import contextlib

#: The pose the NIF wrote, put here by NIFBX for us to hand back.
REFERENCE = "nif_bone_rest"

#: The pose Blender's importer made of it, recorded before anyone edits.
IMPORTED = "sk_bone_imported"

#: The pose the converter should use, which is what this module is for.
AUTHORED = "sk_bone_rest"

#: How far a rest matrix may drift and still be the one that was imported.
#: A saved and reloaded .blend agrees with itself far inside this; a person
#: moving a bone is far outside it.
TOLERANCE = 1e-5


def _entries(text):
    """A ``name=value;name=value`` table as a dict, values left as text."""
    table = {}

    for entry in (text or "").split(";"):
        name, sep, value = entry.partition("=")

        if sep and name:
            table[name] = value

    return table


def _numbers(text):
    try:
        return [float(x) for x in text.split(",")]
    except ValueError:
        return []


def record(armature):
    """Write down each bone's rest matrix as the importer left it.

    Called once, on the way in. Calling it later records edits as if they were
    the importer's and hands them to the converter to overwrite, so it is not
    called again -- an armature that already has a snapshot keeps it.
    """
    if armature.get(IMPORTED):
        return 0

    armature[IMPORTED] = ";".join(
        "%s=%s" % (bone.name, ",".join(repr(x) for row in bone.matrix_local for x in row))
        for bone in armature.data.bones)

    return len(armature.data.bones)


def unmoved(armature):
    """The NIF's own rest transform for every bone nobody has moved.

    The values are NIFBX's and are passed back untouched: they are in the NIF's
    frame, not Blender's, and nothing here has any business interpreting them.
    """
    reference = _entries(armature.get(REFERENCE))
    imported = _entries(armature.get(IMPORTED))

    if not reference or not imported:
        return []

    kept = []

    for bone in armature.data.bones:
        stated = reference.get(bone.name)
        was = _numbers(imported.get(bone.name, ""))

        if stated is None or len(was) != 16:
            continue

        now = [x for row in bone.matrix_local for x in row]

        if all(abs(a - b) <= TOLERANCE for a, b in zip(now, was)):
            kept.append((bone.name, stated))

    return kept


@contextlib.contextmanager
def stated(scene):
    """Answer for every unmoved bone for the duration of an export."""
    written = []

    for obj in scene.objects:
        if obj.type != "ARMATURE":
            continue

        kept = unmoved(obj)

        if kept:
            obj[AUTHORED] = ";".join("%s=%s" % pair for pair in kept)
            written.append(obj)

    try:
        yield written
    finally:
        for obj in written:
            del obj[AUTHORED]
