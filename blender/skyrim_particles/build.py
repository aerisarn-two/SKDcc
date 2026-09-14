"""Turn a NIF particle system's properties into a Blender particle system.

Blender emits from a mesh and Skyrim emits from a volume or from a named mesh,
so the first thing this does is give the system something to sit on: the object
a mesh emitter names, or a primitive matching the volume a box, cylinder or
sphere emitter describes. The node itself stays an empty, with its properties
untouched, exactly as the constraints add-on leaves the ragdoll's.

What maps, maps. What does not is reported rather than approximated -- a
particle's colour and size over its life are curves Blender keeps on a material
and in geometry nodes, not on the system, and inventing a flat value for them
would look like a translation and behave like a guess.
"""

import math

import bpy
from mathutils import Vector

from . import schema


class Report:
    """What was built, and what could not be."""

    def __init__(self):
        self.systems = []
        self.skipped = []
        self.notes = []

    def __str__(self):
        text = f"{len(self.systems)} particle system(s)"

        if self.skipped:
            text += f", {len(self.skipped)} skipped"

        return text


def _get(obj, name, fallback=None):
    """A custom property, or the fallback where the node has none."""
    try:
        value = obj[name]
    except (KeyError, TypeError):
        return fallback

    return fallback if value is None else value


def _float(obj, name, fallback=0.0):
    value = _get(obj, name, fallback)

    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def is_system(obj):
    return bool(_get(obj, schema.SYSTEM, ""))


def modifiers_of(obj):
    """The modifier nodes under a system, in the order the stack runs them."""
    found = [child for child in obj.children if _get(child, schema.MODIFIER, "")]

    return sorted(found, key=lambda m: _float(m, schema.ORDER, 0.0))


def emitter_of(obj):
    """The one modifier that births particles, or None."""
    for modifier in modifiers_of(obj):
        if _get(modifier, schema.MODIFIER, "") in schema.EMITTERS:
            return modifier

    return None


#: What NIFBX substitutes for the four characters an FBX name cannot carry,
#: from ``NameEncoding``. A link is written in the file's spelling and the node
#: in the scene's, so one has to be put into the other.
_ESCAPES = ((" ", "_s_"), ("[", "_ob_"), ("]", "_cb_"), (":", "_dd_"))

#: NIFBX appends this to the node that carries a mesh's geometry.
_SUPPORT = "_support"


def _sanitize(name):
    """A NIF name as the scene spells it."""
    for character, escape in _ESCAPES:
        name = name.replace(character, escape)

    return name


def _plain(name):
    """A scene name with what the scene added to it taken back off.

    Blender appends ``.001`` to the second object of a name, and NIFBX appends
    ``_support`` to the node that holds geometry. Neither is part of what a link
    names, so neither may stand between a link and the object it points at.
    """
    if "." in name:
        head, _, tail = name.rpartition(".")

        if head and tail.isdigit():
            name = head

    if name.endswith(_SUPPORT):
        name = name[: -len(_SUPPORT)]

    return name


def _named(scene_objects, name):
    """The object a link names, matched the way every other link here is."""
    if not name:
        return None

    if name in scene_objects:
        return scene_objects[name]

    wanted = _sanitize(name)

    for candidate in (wanted, wanted + _SUPPORT):
        if candidate in scene_objects:
            return scene_objects[candidate]

    # And last, against what the scene's own names reduce to. A link naming
    # ``EmitGeo:0`` has to reach ``EmitGeo_dd_0_support.001`` if that is what
    # importing twice has left behind.
    for key, obj in scene_objects.items():
        if _plain(key) == wanted:
            return obj

    return None


def _named_frame(scene, name):
    """The frame a link names, which may not be an object at all.

    An emitter's frame is usually an empty and sometimes a bone: NIFBX writes a
    node as a ``LimbNode`` where the NIF has it in a skeleton, and Blender turns
    every LimbNode into a bone inside an armature rather than into an object. A
    candle's ``CandleFlame01-Emitter`` is one of those, and looking only among
    objects finds nothing and quietly falls back to the wrong frame.

    Returns ``(object, matrix)``: the object to parent to, and the world matrix
    the frame actually has.
    """
    objects = {obj.name: obj for obj in scene.objects}
    found = _named(objects, name)

    if found is not None:
        return found, found.matrix_world.copy()

    wanted = _sanitize(str(name))

    for obj in scene.objects:
        if obj.type != "ARMATURE":
            continue

        for bone in obj.data.bones:
            if bone.name in (name, wanted) or _plain(bone.name) == wanted:
                return obj, obj.matrix_world @ bone.matrix_local

    return None, None


def _emitter_mesh(emitter, scene_objects):
    """The object a mesh emitter births from, if the scene still has it."""
    count = int(_float(emitter, schema.NUM_EMITTER_MESHES, 0.0))

    for i in range(max(count, 1)):
        named = _get(emitter, f"{schema.EMITTER_MESHES}{i}{schema.LINK_SUFFIX}", "")

        # A link is written as ``Name:index``, and the colon is one of the four
        # characters the scene escapes -- ``EmitGeo:0`` is ``EmitGeo_dd_0`` on
        # the node. So the whole thing is looked up, index and all, and only the
        # bare name is tried if that finds nothing.
        if named:
            text = str(named)
            found = _named(scene_objects, text) or _named(scene_objects, text.rsplit(":", 1)[0])

            if found is not None and found.type == "MESH":
                return found

    return None


def _volume_for(emitter, kind, name):
    """A mesh matching the volume a box, cylinder or sphere emitter describes."""
    if kind == "NiPSysBoxEmitter":
        bpy.ops.mesh.primitive_cube_add(size=1.0)
        obj = bpy.context.object
        obj.scale = (
            max(_float(emitter, schema.WIDTH, 1.0), 1e-4),
            max(_float(emitter, schema.DEPTH, 1.0), 1e-4),
            max(_float(emitter, schema.HEIGHT, 1.0), 1e-4),
        )
    elif kind == "NiPSysCylinderEmitter":
        bpy.ops.mesh.primitive_cylinder_add(
            radius=max(_float(emitter, schema.RADIUS, 1.0), 1e-4),
            depth=max(_float(emitter, schema.HEIGHT, 1.0), 1e-4),
        )
        obj = bpy.context.object
    else:
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=max(_float(emitter, schema.RADIUS, 1.0), 1e-4)
        )
        obj = bpy.context.object

    obj.name = name
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj[schema.GENERATED] = 1

    return obj


def _seconds_to_frames(scene, seconds):
    fps = scene.render.fps / max(scene.render.fps_base, 1e-6)

    return max(1, int(round(seconds * fps)))


def _apply_emitter(settings, emitter, system_node, scene, report):
    """Speed, life and size: the four fields every Skyrim emitter carries."""
    life = _float(emitter, schema.LIFE_SPAN, 1.0)
    settings.lifetime = _seconds_to_frames(scene, life)

    spread = _float(emitter, schema.LIFE_SPAN_VARIATION, 0.0)

    if life > 0.0:
        settings.lifetime_random = min(1.0, max(0.0, spread / life))

    #
    # Which way they go. NiPSEmitter::EmitParticles builds the direction as
    # (0,0,1) turned by the declination and planar angles, so a particle leaves
    # along the emitter's local +Z unless the declination says otherwise -- a
    # candle flame with a declination of zero goes straight up.
    #
    # Blender's normal_factor is speed along the emitting *normal*, and a volume
    # has none: it emits in every direction, which is what a torch converted this
    # way looked like. object_align_factor is speed along the emitter object's
    # own axes, which is the same statement the engine makes, so that is what
    # carries the speed.
    #
    # A mesh emitter is the exception the engine makes too: with
    # VELOCITY_USE_NORMALS it births along the surface normal, and there
    # normal_factor is exactly right.
    speed = _float(emitter, schema.SPEED, 0.0)
    kind = _get(emitter, schema.MODIFIER, "")

    along_normals = (
        kind == "NiPSysMeshEmitter"
        and int(_float(emitter, schema.INITIAL_VELOCITY_TYPE, 0.0)) == schema.USE_NORMALS
    )

    if along_normals:
        settings.normal_factor = speed
        settings.object_align_factor = (0.0, 0.0, 0.0)
    else:
        settings.normal_factor = 0.0
        settings.object_align_factor = tuple(a * speed for a in schema.EMISSION_AXIS)

    settings.factor_random = _float(emitter, schema.SPEED_VARIATION, 0.0)

    radius = _float(emitter, schema.INITIAL_RADIUS, 1.0)
    settings.particle_size = max(radius, 1e-4)

    if radius > 0.0:
        variation = _float(emitter, schema.RADIUS_VARIATION, 0.0)
        settings.size_random = min(1.0, max(0.0, variation / radius))

    # The buffer the engine fills is the particle budget: NiPSysData holds no
    # vertices on disk, only the capacity for them.
    count = int(_float(system_node, schema.MAX_VERTICES, 0.0))

    if count > 0:
        settings.count = count

    # A cone Blender cannot express. Its emission is along the normal with a
    # random factor; there is no half-angle, so saying so is better than
    # pretending the spread is the speed variation.
    declination = _float(emitter, schema.DECLINATION, 0.0)
    planar = _float(emitter, schema.PLANAR_ANGLE, 0.0)

    if abs(declination) > 1e-6 or abs(planar) > 1e-6:
        report.notes.append(
            f"{system_node.name}: emits in a cone "
            f"({math.degrees(declination):.0f}° declination, "
            f"{math.degrees(planar):.0f}° planar), which Blender's emitter has no "
            "field for -- the speed and its variation are carried, the angle is not"
        )


def _apply_modifiers(settings, modifiers, system_node, report):
    """The rest of the stack, where Blender has somewhere to put it."""
    has_gravity = False

    for modifier in modifiers:
        kind = _get(modifier, schema.MODIFIER, "")

        if not int(_float(modifier, schema.ACTIVE, 1.0)):
            continue

        if kind == schema.GRAVITY:
            has_gravity = True
            _gravity_field(modifier, system_node, report)

        elif kind == schema.DRAG:
            settings.damping = min(1.0, max(0.0, _float(modifier, schema.PERCENTAGE, 0.0)))

        elif kind == schema.ROTATION:
            settings.use_rotations = True
            settings.rotation_mode = "VEL"
            settings.angular_velocity_factor = _float(modifier, schema.ROTATION_SPEED, 0.0)
            settings.angular_velocity_mode = (
                "RAND" if int(_float(modifier, schema.RANDOM_AXIS, 0.0)) else "VELOCITY"
            )
            settings.rotation_factor_random = min(
                1.0, max(0.0, _float(modifier, schema.ROTATION_ANGLE_VARIATION, 0.0) / math.pi)
            )

        elif kind == schema.SPAWN:
            most = int(_float(modifier, schema.MAX_TO_SPAWN, 0.0))

            if most > 0:
                settings.child_type = "SIMPLE"
                settings.child_percent = most
                settings.rendered_child_count = most

        elif kind in (schema.SCALE, schema.COLOR, schema.SUBTEX):
            report.notes.append(
                f"{system_node.name}: {kind} is a curve over a particle's life, "
                "which Blender keeps on the material rather than on the system -- "
                "its keys are still on the node and nothing here reads them"
            )

    # Scene gravity is off either way. Blender pulls every particle down by
    # default and Skyrim has no such default: what a Skyrim system has instead
    # is whatever its gravity modifier says, along the axis that modifier names,
    # which is a field of its own and not a weight on this one. A campfire's
    # flames lift along +Z at 112.5 and its smoke at 7.2; run them under scene
    # gravity and the fire falls into the ground.
    settings.effector_weights.gravity = 0.0

    if not has_gravity:
        return


def _vector(modifier, name, fallback=(0.0, 0.0, 1.0)):
    """A three-number property, which arrives as a string of three numbers."""
    raw = _get(modifier, name, None)

    if raw is None:
        return fallback

    try:
        parts = [float(p) for p in str(raw).replace(",", " ").split()]
    except ValueError:
        return fallback

    return tuple(parts[:3]) if len(parts) >= 3 else fallback


def _gravity_field(modifier, system_node, report):
    """A gravity modifier, as the force field Blender would call it.

    Not ``effector_weights.gravity``: that turns on *Blender's* gravity, which
    points down at 9.81 and knows nothing about the axis the modifier names. A
    Skyrim gravity modifier is a constant acceleration along its own axis and
    lifts as often as it drops -- flames and smoke both rise -- so it becomes a
    wind field pointed along that axis, or a point force where the modifier says
    Force Type 1.
    """
    strength = _float(modifier, schema.STRENGTH, 0.0)

    if not strength:
        # Vanilla stores zero here and animates it: of the 615 gravity modifiers
        # in the game's effect folders every one is zero, and 72 take their real
        # value from a NiPSysGravityStrengthCtlr. A zero is a modifier waiting
        # for its controller, not an absence, and the controller is in the
        # animation rather than in the scene.
        report.notes.append(
            f"{system_node.name}: its gravity modifier stores a strength of zero, "
            "which is how the game's effect meshes ship -- the value is in a "
            "NiPSysGravityStrengthCtlr and no field is built for it"
        )

        return None

    point = int(_float(modifier, schema.FORCE_TYPE, 0.0)) == 1
    axis = _vector(modifier, schema.GRAVITY_AXIS)

    bpy.ops.object.effector_add(type="FORCE" if point else "WIND")
    field = bpy.context.object
    field.name = f"{system_node.name}_gravity"
    field.field.strength = strength

    if not point:
        # A wind field blows along its own +Z, so the object is turned to put
        # +Z on the axis the modifier names.
        field.rotation_mode = "QUATERNION"
        field.rotation_quaternion = Vector((0.0, 0.0, 1.0)).rotation_difference(
            Vector(axis).normalized() if Vector(axis).length > 1e-9 else Vector((0.0, 0.0, 1.0))
        )

    field.parent = system_node
    field.matrix_parent_inverse.identity()
    field.hide_render = True
    field[schema.GENERATED] = 1
    field[schema.SOURCE] = system_node.name

    return field


def build_system(system_node, scene, scene_objects, report):
    """One NIF particle system, as a Blender particle system."""
    emitter = emitter_of(system_node)

    if emitter is None:
        report.skipped.append(f"{system_node.name}: no emitter in its stack")
        return None

    kind = _get(emitter, schema.MODIFIER, "")
    carrier = _emitter_mesh(emitter, scene_objects) if kind == "NiPSysMeshEmitter" else None
    own = False

    if carrier is None:
        if kind == "NiPSysMeshEmitter":
            report.skipped.append(
                f"{system_node.name}: emits from a mesh the scene does not have"
            )
            return None

        carrier = _volume_for(emitter, kind, f"{system_node.name}_emitter")

        # Under the frame the emitter names, where it names one. That frame is
        # what the direction is measured in -- the engine turns (0,0,1) by the
        # declination in *its* axes -- so hanging the volume anywhere else
        # points the particles somewhere else.
        named = _get(emitter, schema.EMITTER_OBJECT, "")
        frame, where = _named_frame(scene, str(named)) if named else (None, None)

        if frame is None:
            carrier.parent = system_node
            carrier.matrix_parent_inverse.identity()
        else:
            # Placed at the frame rather than bone-parented to it: Blender hangs
            # a bone's children off its *tail*, and these belong at the head.
            carrier.parent = frame
            carrier.matrix_parent_inverse = frame.matrix_world.inverted()
            carrier.matrix_basis = where

        own = True

    # Through the modifier rather than bpy.ops.object.particle_system_add: the
    # operator wants the object selected, visible and active, and an imported
    # effect is routinely none of those -- "Cannot edit hidden object" is what a
    # hidden emitter mesh gets. This does the same thing and asks for nothing.
    carrier.modifiers.new(name=system_node.name, type="PARTICLE_SYSTEM")

    system = carrier.particle_systems[-1]
    system.name = system_node.name
    settings = system.settings
    settings.name = f"{system_node.name}_settings"

    settings.type = "EMITTER"
    settings.physics_type = "NEWTON"
    settings.render_type = "HALO"
    settings.emit_from = "VOLUME" if own else "FACE"
    settings.frame_start = scene.frame_start
    settings.frame_end = scene.frame_end

    _apply_emitter(settings, emitter, system_node, scene, report)
    _apply_modifiers(settings, modifiers_of(system_node), system_node, report)

    settings[schema.GENERATED] = 1
    settings[schema.SOURCE] = system_node.name
    carrier[schema.SOURCE] = system_node.name

    report.systems.append(system_node.name)

    return system


def build(scene):
    """Every particle system in the scene."""
    report = Report()
    objects = {obj.name: obj for obj in scene.objects}

    for obj in list(scene.objects):
        if is_system(obj):
            build_system(obj, scene, objects, report)

    return report


def clear(scene):
    """Undo a build: the systems it added and the volumes it made for them."""
    removed = 0

    for obj in list(scene.objects):
        for modifier in list(obj.modifiers):
            if modifier.type != "PARTICLE_SYSTEM":
                continue

            settings = getattr(modifier.particle_system, "settings", None)

            if settings is not None and schema.GENERATED in settings:
                obj.modifiers.remove(modifier)
                removed += 1

    for obj in list(scene.objects):
        if schema.GENERATED in obj:
            bpy.data.objects.remove(obj, do_unlink=True)

    return removed
