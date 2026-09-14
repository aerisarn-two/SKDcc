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
    #
    # Only for a file that has hidden meshes to get wrong. A cow skeleton hangs
    # its collision off bones, and a bone-parented object is placed by a
    # composition this add-on does not do, so it is left alone and the file
    # shows no disagreement to find.
    fixable = [
        o for o in scene.objects
        if o.type == "MESH" and o.parent is not None and o.parent_type == "OBJECT"
    ]

    # It takes both: something hidden to be wrong and something visible to be
    # wrong against. A cow skeleton is collision and nothing else, so every mesh
    # in it is hidden and there is no contrast to find.
    contrast = (any(o.hide_viewport for o in fixable)
                and any(not o.hide_viewport for o in fixable))

    if contrast:
        check("the importer got it wrong", len(set(before.values())) > 1, True)
    else:
        print("     no hidden mesh here has a visible one to disagree with, so the "
              "defect this repairs cannot be seen in this file")

    basis_before = {o.name: o.matrix_basis.copy() for o in scene.objects}

    corrected, unparented = fix.fix(scene)
    bpy.context.view_layer.update()

    # Nothing durable is written, and that is the point rather than an
    # oversight: matrix_world is derived, so assigning a value computed out of
    # matrix_basis puts back the basis that was already there. What this fixes
    # is the cache hanging off it, which hide_viewport leaves stale because the
    # object is out of the depsgraph. If this ever starts writing a scale, the
    # add-on has stopped doing what its docstring says.
    # Relative, because the matrices are not all the same size: a collision
    # proxy imported at a hundred times scale has entries in the hundreds, and
    # composing one and decomposing it again loses more of the last digits than
    # a matrix of ones does. Measured on the lumbermill, the worst entry is 385
    # and the worst absolute difference 3e-05, which is 8e-08 of it.
    def rewritten(name, before):
        now = bpy.data.objects[name].matrix_basis
        biggest = max(abs(before[r][c]) for r in range(4) for c in range(4))

        return any(
            abs(before[r][c] - now[r][c]) > 1e-4 * max(biggest, 1.0)
            for r in range(4)
            for c in range(4)
        )

    moved = [n for n, m in basis_before.items() if rewritten(n, m)]

    check("no stored transform is rewritten", moved, [])

    after = scales(scene)
    print(f"     scales after:  {sorted(set(after.values()))}")
    print(f"     rescaled: {len(corrected)}, unparented: {len(unparented)}")

    # Not "one scale for the whole scene": a NIF node may carry a scale of its
    # own, and the campfire's glow legitimately sits at 0.8333 of its parent.
    # What must hold is that every object's world matrix is the one its own
    # parent chain composes -- which is the thing the importer broke.
    def composes(obj):
        # Object parenting only: a bone-parented object is placed by the bone's
        # matrix and length, which is not the composition below and not one this
        # add-on claims to repair.
        if obj.parent is None or obj.parent_type != "OBJECT":
            return True

        want = obj.parent.matrix_world @ obj.matrix_parent_inverse @ obj.matrix_basis

        return all(
            abs(obj.matrix_world[r][c] - want[r][c]) <= 1e-6
            for r in range(4)
            for c in range(4)
        )

    check("every object agrees with its parent", all(composes(o) for o in scene.objects), True)
    if contrast:
        repairable = hidden & {o.name for o in fixable}

        check("the hidden ones are what moved", set(corrected) >= repairable, True)

    # And nothing that was already right was touched.
    untouched = {n for n, s in before.items() if n not in hidden}
    check("visible meshes unmoved", all(after[n] == before[n] for n in untouched), True)

    # Running it twice changes nothing more.
    again, _ = fix.fix(scene)
    check("idempotent", len(again), 0)

    # And the half that makes any of it stick. Blender hides two ways and only
    # one of them keeps evaluating the object: hide_viewport takes it out of the
    # depsgraph, so its transform is never recomputed and the repair above is a
    # cache refresh that a save and a reopen throws away. A cow's collision
    # capsule read 88 metres against a skeleton 1.8 metres tall, was corrected,
    # and was 88 metres again on reopening.
    moved_out = fix.hide_from_render(scene)
    bpy.context.view_layer.update()

    check("nothing is left out of the depsgraph",
          [o.name for o in scene.objects if o.hide_viewport], [])

    check("what was hidden is still not drawn",
          all(bpy.data.objects[n].hide_get() for n in moved_out), True)

    check("what was hidden is still not rendered",
          all(bpy.data.objects[n].hide_render for n in moved_out), True)

    # Which is what the scales say once everything is evaluated: a NIF is one
    # model at one scale, give or take a node that carries its own.
    final = [s for s in scales(scene).values() if s > 0]

    if final:
        check("no mesh is left a hundred times its siblings",
              max(final) / min(final) < 10.0, True)


main()

print(f"{len(failures)} checks failed" if failures else "0 checks failed")
sys.exit(1 if failures else 0)
