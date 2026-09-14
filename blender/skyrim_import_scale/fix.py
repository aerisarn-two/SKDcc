"""Put hidden objects back at the scale the rest of the scene is at.

Blender's FBX importer converts the file's units into the scene's -- a Skyrim
NIF arrives in centimetres and Blender works in metres, so everything is scaled
by 0.01 on the way in. It does not do that for an object it imports **hidden**.
Those keep world scale 1.0 and come out a hundred times too big.

A collision proxy is hidden, and so is every node the NIF marks invisible -- the
blood decals on a dagger, the MOPP mesh around a campfire -- so a converted mesh
routinely opens with a correctly sized model sitting inside a proxy a hundred
times its size. It looks like the export got the units wrong. It did not: the
FBX gives every one of those nodes ``Lcl Scaling = 1`` under a root of scale 1,
and stripping the visibility flags alone -- changing nothing else in the file --
brings every object back to the same scale.

The repair is to recompute a world matrix the way Blender itself would:

    matrix_world = parent.matrix_world @ matrix_parent_inverse @ matrix_basis

which for a correctly imported object gives back what it already has, and for a
hidden one gives the scale it should have had. Nothing is guessed and no factor
is written down: the number comes from the parent the object already has.
"""

import bpy


def _top_down(objects):
    """Parents before children, so a corrected parent feeds its children."""
    ordered = []
    seen = set()

    def visit(obj):
        if obj.name in seen:
            return

        if obj.parent is not None:
            visit(obj.parent)

        seen.add(obj.name)
        ordered.append(obj)

    for obj in objects:
        visit(obj)

    return ordered


def _differs(a, b, tolerance=1e-6):
    return any(abs(a[r][c] - b[r][c]) > tolerance for r in range(4) for c in range(4))


def fix(scene):
    """Every object whose world matrix disagrees with its own parent chain.

    Returns the objects corrected, and the ones that could not be: a hidden
    object at the top of the scene has no parent to recompute from, and this
    will not invent a scale for it.
    """
    corrected = []
    unparented = []

    for obj in _top_down(list(scene.objects)):
        if obj.parent is None:
            if obj.hide_viewport:
                unparented.append(obj.name)

            continue

        want = obj.parent.matrix_world @ obj.matrix_parent_inverse @ obj.matrix_basis

        if _differs(obj.matrix_world, want):
            obj.matrix_world = want
            corrected.append(obj.name)

    if corrected:
        bpy.context.view_layer.update()

    return corrected, unparented


def hide_from_render(scene):
    """Keep out of renders what the file says is not render geometry.

    A NIF marks its collision proxies and its invisible nodes hidden, and the
    FBX carries that as the model's visibility. Blender's importer applies it to
    the *viewport* only -- ``hide_viewport`` -- and leaves ``hide_render`` alone,
    so a campfire's MOPP hull is absent while you work and then covers the fire
    the moment you render it.

    It took a while to notice because the two disagree exactly where it is
    hardest to see: every render made while testing had an untextured collision
    hull sitting over the model, and it read as the lighting being wrong.

    Returns what was hidden.
    """
    hidden = []

    for obj in scene.objects:
        if obj.hide_viewport and not obj.hide_render:
            obj.hide_render = True
            hidden.append(obj.name)

    return hidden
