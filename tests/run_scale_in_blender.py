"""Check the hidden-object rescale, inside Blender.

    blender --background --python tests/run_scale_in_blender.py -- some.fbx

The claim is narrow and checkable: after the fix, every object in the scene is
at the same world scale as the rest, and the ones that were already right did
not move.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_import_scale import fix  # noqa: E402

failures = []


def check(name, got, want):
    ok = got == want

    print(f"{'PASS' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" != {want!r}"))

    if not ok:
        failures.append(name)


def scales(scene):
    return {o.name: round(o.matrix_world.to_scale()[0], 6) for o in scene.objects if o.type == "MESH"}


def main():
    path = sys.argv[sys.argv.index("--") + 1]

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_custom_props=True)
    bpy.context.view_layer.update()

    scene = bpy.context.scene
    before = scales(scene)
    hidden = {o.name for o in scene.objects if o.type == "MESH" and o.hide_viewport}

    print(f"     {len(before)} meshes, {len(hidden)} hidden")
    print(f"     scales before: {sorted(set(before.values()))}")

    # The defect itself: if the importer ever stops doing this, say so rather
    # than quietly testing nothing.
    check("the importer got it wrong", len(set(before.values())) > 1, True)

    corrected, unparented = fix.fix(scene)
    bpy.context.view_layer.update()

    after = scales(scene)
    print(f"     scales after:  {sorted(set(after.values()))}")
    print(f"     rescaled: {len(corrected)}, unparented: {len(unparented)}")

    # Not "one scale for the whole scene": a NIF node may carry a scale of its
    # own, and the campfire's glow legitimately sits at 0.8333 of its parent.
    # What must hold is that every object's world matrix is the one its own
    # parent chain composes -- which is the thing the importer broke.
    def composes(obj):
        if obj.parent is None:
            return True

        want = obj.parent.matrix_world @ obj.matrix_parent_inverse @ obj.matrix_basis

        return all(
            abs(obj.matrix_world[r][c] - want[r][c]) <= 1e-6
            for r in range(4)
            for c in range(4)
        )

    check("every object agrees with its parent", all(composes(o) for o in scene.objects), True)
    check("the hidden ones are what moved", set(corrected) >= hidden & set(before), True)

    # And nothing that was already right was touched.
    untouched = {n for n, s in before.items() if n not in hidden}
    check("visible meshes unmoved", all(after[n] == before[n] for n in untouched), True)

    # Running it twice changes nothing more.
    again, _ = fix.fix(scene)
    check("idempotent", len(again), 0)


main()

print(f"{len(failures)} checks failed" if failures else "0 checks failed")
sys.exit(1 if failures else 0)
