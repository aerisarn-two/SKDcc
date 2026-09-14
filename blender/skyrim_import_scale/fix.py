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

What that means in Blender's terms is narrower than "repair", and worth being
plain about, because the name of this add-on promises more. ``matrix_world`` is
derived, and assigning it sets ``matrix_basis`` to whatever produces it -- so
assigning a value computed *from* ``matrix_basis`` writes back the basis that
was already there. Measured on the campfire: every object it reports as
corrected comes out with the same ``matrix_basis`` it went in with, give or
take the rounding of composing a matrix and decomposing it again -- the
difference is below 1e-6 and above 1e-9, which is the signature of a round trip
through floating point rather than of a repair.

The durable data was never wrong. What was wrong was the cached
``matrix_world`` hanging off it, and only on hidden objects -- ``hide_viewport``
takes an object out of the depsgraph, so nothing ever recomputes its cache and
a bare ``view_layer.update()`` moves none of them. Anything that reads
``obj.matrix_world`` on one of those gets whatever the importer left there,
which is how a 2 metre collision hull measured 197.

So this makes those reads true, and that is all it does. It is a snapshot: move
the parent of a hidden object afterwards and the cache is stale again.
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
    """Refresh the world matrix of every object whose cache disagrees with it.

    In practice that is the hidden ones and nothing else -- see the module
    docstring for why the stored transform was never the thing that was wrong.

    Returns the objects refreshed, and the ones that could not be: an object at
    the top of the scene has no parent to recompute from, and one parented to a
    bone or a vertex is placed by a composition this does not do.
    """
    corrected = []
    unparented = []

    for obj in _top_down(list(scene.objects)):
        if obj.parent is None:
            if obj.hide_viewport:
                unparented.append(obj.name)

            continue

        # Only where the composition below is the one Blender uses. A bone-
        # parented object is placed by the bone's own matrix and the bone's
        # length, not by the armature's world matrix -- a cow skeleton hangs all
        # 24 of its ragdoll bodies off bones, and recomputing those this way
        # wrote a wrong matrix onto every one of them and then did it again on
        # the next pass, because the value it wrote was never the value it would
        # read back. Vertex parenting is the same story.
        if obj.parent_type != "OBJECT":
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
        if not obj.hide_viewport:
            continue

        if not obj.hide_render:
            obj.hide_render = True

        # And hidden the other way, which is the half that makes the repair
        # stick. Blender has two kinds of hiding and they are not the same
        # thing: `hide_viewport` -- the monitor icon -- takes the object out of
        # the depsgraph entirely, so nothing ever evaluates it and its cached
        # world matrix stays whatever the importer left. `hide_set` -- the eye
        # icon, per view layer -- only stops it being drawn.
        #
        # The importer uses the first. So a cow's collision capsule reads 88
        # metres against a skeleton 1.8 metres tall, `fix` corrects it, the file
        # is saved, and on reopening it is 88 metres again: the correction was a
        # cache refresh and the cache is not evaluated. Moving the hiding to the
        # eye leaves the object evaluated, so it comes out right and stays right.
        obj.hide_viewport = False

        try:
            obj.hide_set(True)
        except RuntimeError:
            # No view layer to hide it in -- put it back rather than leave it
            # visible, since being seen is worse than being stale.
            obj.hide_viewport = True

        hidden.append(obj.name)

    return hidden
