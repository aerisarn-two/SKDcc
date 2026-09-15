"""Putting one of a creature's clips on its rig.

A creature arrives with every animation its project has -- 216 on a draugr --
as actions, and one of them assigned. Changing which one plays is two steps in
two editors and a frame range typed by hand, and getting the range wrong is
silent: the clip ends and the rig sits on its last frame for the rest of the
scene.
"""

import bpy


def rig_of(scene):
    """The armature the clips drive.

    The selected one when that is an armature, because a scene may hold several
    and the person clicking has already said which. Otherwise the one with the
    most bones: a creature imports as an armature per file it came from, and the
    two that are not the skeleton have no bones at all.
    """
    active = bpy.context.active_object

    if active is not None and active.type == "ARMATURE" and len(active.data.bones):
        return active

    rigs = [o for o in scene.objects if o.type == "ARMATURE" and len(o.data.bones)]

    return max(rigs, key=lambda o: len(o.data.bones)) if rigs else None


def clips():
    """Every clip in the file, by name."""
    return sorted(bpy.data.actions, key=lambda a: a.name)


def play(scene, name):
    """Assign a clip and set the scene to its own length.

    The range is the point. A clip is as long as it is -- a draugr's idle runs
    287 frames and its one-handed attack 52 -- and a scene left at another
    clip's length plays past the end, where the rig holds its last pose and
    looks stuck rather than finished.
    """
    rig = rig_of(scene)

    if rig is None:
        return None, "there is no armature with bones in this scene"

    clip = bpy.data.actions.get(name)

    if clip is None:
        return None, f"no clip called {name!r}"

    data = rig.animation_data or rig.animation_data_create()
    data.action = clip

    start, stop = (int(round(v)) for v in clip.frame_range)

    scene.frame_start = start
    scene.frame_end = max(stop, start)
    scene.frame_set(start)

    return clip, None


def clear(scene):
    """Take the clip off, so the NLA tracks are what drives the rig.

    An assigned action is evaluated after the tracks and wins, so unmuting a
    track while one is assigned does nothing at all -- which reads as the track
    being broken rather than as the action being in front of it.
    """
    rig = rig_of(scene)

    if rig is None or rig.animation_data is None:
        return False

    rig.animation_data.action = None

    return True
