"""The two places Blender's API has to be handled rather than called.

Both were found by running this add-on headless against Blender 5.0.1, and
both are load-bearing: without them the operators either fail or take the
whole process down.
"""

import contextlib

import bpy


@contextlib.contextmanager
def active(obj):
    """Make one object the active, sole-selected object, then put it back.

    ``bpy.context.temp_override`` is the documented way to do this and it
    **segfaults Blender 5.0.1 in background mode** when a rigid body operator
    runs inside it. Setting the view layer's active object directly does not,
    so that is what this does. Tested: ``rigidbody.constraint_add`` crashes
    under temp_override and succeeds here.
    """
    view_layer = bpy.context.view_layer
    previous = view_layer.objects.active
    selected = [o for o in bpy.context.selected_objects]

    # A collision shape arrives hidden -- NIFBX marks it so, because nobody
    # wants a capsule drawn over the mesh -- and every rigid body operator
    # refuses with "Cannot edit hidden object". So it is shown for exactly as
    # long as the operator takes and hidden again afterwards.
    was_hidden_viewport = obj.hide_viewport
    was_hidden = obj.hide_get()

    obj.hide_viewport = False
    obj.hide_set(False)

    for other in selected:
        other.select_set(False)

    view_layer.objects.active = obj
    obj.select_set(True)
    try:
        yield obj
    finally:
        obj.select_set(False)
        obj.hide_set(was_hidden)
        obj.hide_viewport = was_hidden_viewport
        for other in selected:
            if other.name in bpy.context.view_layer.objects:
                other.select_set(True)
        if previous is not None and previous.name in bpy.context.view_layer.objects:
            view_layer.objects.active = previous


def ensure_rigid_body_world(scene):
    """The scene's rigid body world, created if absent.

    A rigid body constraint cannot exist without one -- the operator reports
    "No Rigid Body World to add Rigid Body Constraint to" -- and the world's
    two collections are created by the operators themselves. Creating them by
    hand and assigning them is another way to crash the process, so they are
    left alone here.
    """
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    return scene.rigidbody_world


@contextlib.contextmanager
def evaluated(objects):
    """Make sure every object's transform can be read, then put it all back.

    A collision shape and some of the bodies arrive with ``hide_viewport`` set,
    and **a hidden object has no evaluated transform**: ``matrix_world`` comes
    back with an identity scale rather than the armature's, silently. On the cow
    skeleton six of twenty-four bodies read a scale of 1.0 instead of 0.01 that
    way, which is enough to put a derived joint frame a whole unit out of place.

    Nothing warns about it. The transform simply is not there to read, so
    anything deriving one matrix from another has to force evaluation first.
    """
    hidden = [(obj, obj.hide_viewport) for obj in objects if obj.hide_viewport]

    for obj, _ in hidden:
        obj.hide_viewport = False

    if hidden:
        bpy.context.view_layer.update()

    try:
        yield
    finally:
        for obj, was in hidden:
            obj.hide_viewport = was
