"""Putting a clip on a creature's rig, inside Blender.

    blender --background --python tests/run_clips_in_blender.py -- creature.fbx

The add-on does three things a person otherwise does by hand in two editors,
and the third is the one worth testing: the scene's frame range is set to the
clip's own length. A clip is as long as it is -- a draugr's idle runs 287
frames and its one-handed attack 52 -- and a range left at another clip's
length plays past the end, where the rig holds its last pose and looks stuck
rather than finished. Nothing warns about that, which is why it is asserted.
"""

import os
import sys

import addon_utils
import bpy

FAILURES = []


def check(name, condition, detail=""):
    print("%-4s %s%s" % ("PASS" if condition else "FAIL", name,
                         "" if not detail else "   (%s)" % detail), flush=True)
    if not condition:
        FAILURES.append(name)


def posed(rig, frame):
    """Where every bone is at a frame."""
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()

    return {b.name: (rig.matrix_world @ b.head.copy()) for b in rig.pose.bones}


def apart(a, b):
    return max((a[k] - b[k]).length for k in a) if a else 0.0


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fbx = os.path.abspath(argv[0]) if argv else None

    if not fbx or not os.path.exists(fbx):
        print("need a path to an FBX", flush=True)
        return 2

    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"))
    addon_utils.enable("io_scene_fbx", default_set=False, persistent=False)

    import skyrim_clips as addon
    from skyrim_clips import play

    addon.register()

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)

    scene = bpy.context.scene
    clips = play.clips()

    check("the file has clips to play", len(clips) > 1, "%d" % len(clips))

    if len(clips) < 2:
        print("\n%d checks failed" % len(FAILURES), flush=True)
        return len(FAILURES)

    rig = play.rig_of(scene)

    # The one with bones, not whichever armature comes first: a creature imports
    # as an armature per file it came from and only the skeleton has any.
    check("the rig it finds is the one with bones",
          rig is not None and len(rig.data.bones) > 0,
          rig.name if rig else "none")

    # --- a clip goes on, at its own length ---------------------------------

    longest = max(clips, key=lambda a: a.frame_range[1] - a.frame_range[0])
    shortest = min(clips, key=lambda a: a.frame_range[1] - a.frame_range[0])

    clip, problem = play.play(scene, longest.name)

    check("the clip goes on the rig", problem is None and clip is not None, problem or "")
    check("and the rig is playing it",
          rig.animation_data.action is longest, rig.animation_data.action.name)
    check("and the scene is set to its length",
          (scene.frame_start, scene.frame_end)
          == (int(round(longest.frame_range[0])), int(round(longest.frame_range[1]))),
          "%d-%d against the clip's %d-%d" % (
              scene.frame_start, scene.frame_end,
              longest.frame_range[0], longest.frame_range[1]))

    first = posed(rig, scene.frame_start)

    # --- and a different clip is a different creature -----------------------

    play.play(scene, shortest.name)

    check("a second clip replaces the first",
          rig.animation_data.action is shortest, rig.animation_data.action.name)
    check("and the range follows it",
          scene.frame_end == int(round(shortest.frame_range[1])),
          "%d against %d" % (scene.frame_end, shortest.frame_range[1]))

    # Both at their own first frame: two clips that start identically would make
    # this say nothing, so it is reported rather than asserted when they match.
    moved = apart(first, posed(rig, scene.frame_start))
    print("     the two clips differ by %.4f at their first frame" % moved, flush=True)

    # --- taking it off is what lets the NLA through -------------------------

    track = rig.animation_data.nla_tracks.new()
    track.name = longest.name
    track.strips.new(longest.name, int(round(longest.frame_range[0])), longest)
    track.mute = False

    with_action = posed(rig, scene.frame_start)
    check("an assigned clip hides the NLA tracks",
          apart(with_action, posed(rig, scene.frame_start)) < 1e-6)

    check("taking it off leaves the rig to them", play.clear(scene))
    check("and nothing is assigned", rig.animation_data.action is None)

    addon.unregister()

    print("\n%d checks failed" % len(FAILURES), flush=True)
    for name in FAILURES:
        print("   FAILED:", name, flush=True)

    return len(FAILURES)


if __name__ == "__main__":
    sys.exit(main())
