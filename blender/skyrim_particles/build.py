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

from . import schema, simulation


#: The material an emitter volume wears so that it emits without being seen.
INVISIBLE_MATERIAL = "skp_emitter_invisible"


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
    obj[schema.GENERATED] = 1
    obj[schema.DCC_GENERATED] = 1

    # Not "WIRE", tempting as it is for a box nobody wants to look at. An
    # object's display type governs how its *particle instances* are drawn as
    # well as the object, so a wireframe emitter draws every particle it emits
    # as a wireframe too -- an effect whose flames are black outlined rectangles
    # hanging in the air, which is exactly what it looked like.
    #
    # The box is kept out of the way by the material it wears instead: see
    # `_invisible`. That leaves it invisible wherever materials are shown and a
    # plain box in solid shading, which is the right way round -- the fire is
    # what someone is looking at.
    obj.display_type = "TEXTURED"

    # Shown as a wireframe rather than hidden from the render. Hiding an object
    # from the render takes its particle systems with it -- measured: an emitter
    # with `hide_render` set renders no particles at all -- so a volume hidden
    # this way produced an effect that was correct in every number and invisible.
    #
    # What should not be drawn is the box, and Blender used to have
    # `use_render_emitter` for exactly that. 5.0 removed it, so the box is made
    # invisible the way anything else is: a material that is not there.
    obj.hide_render = False
    obj.data.materials.append(_invisible())

    return obj


def _invisible():
    """A material that renders nothing, for the emitter volume to wear.

    Shared, because every volume wants the same one and a material per emitter
    is a material per emitter to clean up.
    """
    existing = bpy.data.materials.get(INVISIBLE_MATERIAL)

    if existing is not None:
        return existing

    material = bpy.data.materials.new(INVISIBLE_MATERIAL)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()

    transparent = tree.nodes.new("ShaderNodeBsdfTransparent")
    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (260, 0)
    tree.links.new(transparent.outputs[0], output.inputs["Surface"])

    for name, value in (("blend_method", "BLEND"), ("surface_render_method", "BLENDED")):
        if hasattr(material, name):
            try:
                setattr(material, name, value)
            except (TypeError, ValueError):
                pass

    material[schema.GENERATED] = 1
    material[schema.DCC_GENERATED] = 1

    return material


def _units_of(obj):
    """How many Blender units one of the file's units is worth, here.

    A NIF is in the game's own units and Blender imports it into metres, so
    every length in a particle's fields -- a speed, a radius, an acceleration --
    is a hundred times what it should be if it is used as it stands. The factor
    is not written down anywhere in this add-on: it is the world scale the
    frame already has, which is whatever the importer decided and stays right if
    that ever changes.

    The average of the three axes, because a node may be scaled unevenly and a
    speed has only one number.
    """
    scale = obj.matrix_world.to_scale()

    return (abs(scale[0]) + abs(scale[1]) + abs(scale[2])) / 3.0


def _fps(scene):
    return scene.render.fps / max(scene.render.fps_base, 1e-6)


def _seconds_to_frames(scene, seconds):
    """A duration in seconds, as a number of frames.

    At least one: a particle that lives no frames is not a particle.
    """
    return max(1, int(round(seconds * _fps(scene))))


def _seconds_to_frame(scene, seconds):
    """A moment in the effect's own time, as a frame on this scene's timeline.

    Second zero of the effect is wherever the scene starts, which need not be
    frame one -- so this is an offset from ``frame_start`` rather than a count,
    and is the other half of the pair with :func:`_seconds_to_frames`.
    """
    return scene.frame_start + int(round(seconds * _fps(scene)))


def _controllers(system_node):
    """The structural controllers on a system's node, as dicts of their fields.

    NIFBX carries a particle system's own controllers here rather than as scene
    animation, because they are the effect's settings rather than a clip: there
    is no clip, and the stack it used to invent for them is the first thing a
    DCC tool throws away. See ``FbxNodeControllers.Write``.
    """
    try:
        count = int(_get(system_node, schema.CONTROLLER_COUNT, 0) or 0)
    except (TypeError, ValueError):
        return []

    found = []

    for i in range(count):
        prefix = f"{schema.CONTROLLER_PREFIX}{i}_"
        fields = {}

        for key in system_node.keys():
            if key.startswith(prefix):
                fields[key[len(prefix):]] = system_node[key]

        if fields.get("type"):
            found.append(fields)

    return found


def emission_of(system_node):
    """When the system emits and how fast, or None when nothing says.

    Returns ``(start, stop, rate)`` in seconds and particles per second. The
    emitter-active track is preferred over the controller's own span, because
    the span is when the controller *runs* and the track is when it *emits* --
    they agree in every vanilla file measured, but the track is the statement.

    A track with no keys means always on, which is what 1,055 of the game's
    1,704 emitter controllers say.
    """
    for fields in _controllers(system_node):
        if fields.get("type") not in (schema.EMITTER_CTLR, schema.MULTI_TARGET_EMITTER_CTLR):
            continue

        start = _as_float(fields.get(schema.START_TIME), 0.0)
        stop = _as_float(fields.get(schema.STOP_TIME), 0.0)
        rate = _as_float(fields.get(schema.RATE), 0.0)

        on, off = _window(fields)

        if on is not None:
            start, stop = on, off

        return start, stop, rate

    return None


def cycle_of(system_node):
    """How the emitter controller repeats: LOOP, REVERSE, CLAMP, or None.

    Bits 1-2 of the controller's flags word, and the difference between a fire
    and a fire that goes out. The campfire's emitter runs for 3.3 seconds and
    loops, so it burns for as long as the animation does; read as a single
    window it emitted for a hundred frames of a two hundred and fifty frame
    scene and the last particle died at 161.
    """
    for fields in _controllers(system_node):
        if fields.get("type") not in (schema.EMITTER_CTLR, schema.MULTI_TARGET_EMITTER_CTLR):
            continue

        try:
            flags = int(_as_float(fields.get(schema.CTLR_FLAGS), 0.0))
        except (TypeError, ValueError):
            return schema.CYCLE_CLAMP

        return {
            0: schema.CYCLE_LOOP,
            1: schema.CYCLE_REVERSE,
        }.get((flags >> 1) & 0x3, schema.CYCLE_CLAMP)

    return None


def cycle_span(system_node):
    """The controller's own span in seconds, which is one turn of the loop.

    Not the same as the emission window: the window can be a stretch inside the
    span, and it is the span that repeats.
    """
    for fields in _controllers(system_node):
        if fields.get("type") not in (schema.EMITTER_CTLR, schema.MULTI_TARGET_EMITTER_CTLR):
            continue

        return (_as_float(fields.get(schema.START_TIME), 0.0),
                _as_float(fields.get(schema.STOP_TIME), 0.0))

    return None


def _window(fields):
    """The first on-period of the emitter-active track, or (None, None).

    One period, because a Blender particle system has one emission window and
    cannot express a second. Only a dozen or so of the game's effects blink at
    all; the caller reports those rather than pretending to carry them.
    """
    try:
        count = int(_as_float(fields.get(schema.WINDOW_KEY_COUNT), 0.0))
    except (TypeError, ValueError):
        return None, None

    keys = []

    for i in range(count):
        time = fields.get(f"{schema.WINDOW_KEYS}{i}_time")
        value = fields.get(f"{schema.WINDOW_KEYS}{i}_value")

        if time is None or value is None:
            continue

        keys.append((_as_float(time, 0.0), _as_float(value, 0.0) != 0.0))

    keys.sort(key=lambda k: k[0])

    on = None

    for time, emitting in keys:
        if emitting and on is None:
            on = time
        elif not emitting and on is not None:
            return on, time

    return (on, None) if on is not None else (None, None)


def _pulses(system_node):
    """How many separate on-periods the emitter-active track has."""
    for fields in _controllers(system_node):
        if fields.get("type") not in (schema.EMITTER_CTLR, schema.MULTI_TARGET_EMITTER_CTLR):
            continue

        try:
            count = int(_as_float(fields.get(schema.WINDOW_KEY_COUNT), 0.0))
        except (TypeError, ValueError):
            return 1

        seen, on = 0, False

        for i in range(count):
            value = fields.get(f"{schema.WINDOW_KEYS}{i}_value")

            if value is None:
                continue

            emitting = _as_float(value, 0.0) != 0.0

            if emitting and not on:
                seen += 1

            on = emitting

        return max(seen, 1)

    return 1


def _as_float(value, fallback=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _apply_emission(settings, system_node, scene, report):
    """The emission window and the birth rate, as Blender states them.

    ``frame_start``/``frame_end`` is Blender's emission window and is exactly
    what the emitter-active track says. ``count`` is the number emitted over
    that window, where the NIF gives a rate per second -- so the two are the
    same statement once multiplied by the window's length.

    Without this the window was the whole scene range and the count was the
    engine's buffer capacity, which is a cap rather than a number emitted: a
    campfire that emits for 3.3 seconds ran for the scene's 250 frames.
    """
    emission = emission_of(system_node)

    if emission is None:
        # An emitter controller a sequence drives leaves its span to the clip,
        # and only its class's own fields on the node -- so there is a window,
        # and it is not here. The windmill's splinters are the case: they fly
        # from 18.8 to 22.5 seconds of `Break`, and Blender imports no curve for
        # a custom property, so nothing in this scene knows that.
        #
        # Said rather than passed over, because the emission window that results
        # is the whole timeline and looks as authoritative as a real one.
        if any(k.startswith(schema.SEQUENCED_EMITTER) for k in system_node.keys()):
            report.notes.append(
                f"{system_node.name}: its emitter controller belongs to an "
                "animation, so the emission window is in that clip rather than "
                "on the node -- emitting over the whole timeline instead"
            )

        return False

    start, stop, rate = emission

    settings.frame_start = _seconds_to_frame(scene, start)

    if stop is not None and stop > start:
        settings.frame_end = _seconds_to_frame(scene, stop)
    else:
        # No off key: it emits for as long as there is anything to emit for.
        settings.frame_end = scene.frame_end

    if rate > 0.0:
        span = (stop - start) if stop is not None and stop > start else 0.0

        if span > 0.0:
            # Blender's `count` is the total emitted between frame_start and
            # frame_end, and the NIF gives a rate per second, so the two are the
            # same statement once multiplied by the window.
            #
            # Not bounded by the data block's buffer, which _apply_emitter put
            # here first. That buffer is the engine's allocation for particles
            # alive *at once* -- roughly rate x lifetime, which is what the
            # vanilla numbers show: the campfire's small flames emit 15 a second
            # and live 0.47 of one, so seven are up at a time and the buffer is
            # nine. Capping the total by it made that flame emit nine particles
            # over three and a third seconds instead of fifty.
            settings.count = max(1, int(round(rate * span)))

    pulses = _pulses(system_node)

    if pulses > 1:
        report.notes.append(
            f"{system_node.name}: emits in {pulses} bursts; Blender has one "
            "emission window, so the first is used"
        )

    return True


def _apply_emitter(settings, emitter, system_node, scene, report, units):
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
    speed = _float(emitter, schema.SPEED, 0.0) * units
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

    settings.factor_random = _float(emitter, schema.SPEED_VARIATION, 0.0) * units

    radius = _float(emitter, schema.INITIAL_RADIUS, 1.0) * units
    settings.particle_size = max(radius, 1e-6)

    if radius > 0.0:
        # A ratio, so the units cancel and only the two raw numbers matter.
        variation = _float(emitter, schema.RADIUS_VARIATION, 0.0)
        settings.size_random = min(
            1.0, max(0.0, variation / _float(emitter, schema.INITIAL_RADIUS, 1.0))
        )

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


def _apply_modifiers(settings, modifiers, system_node, report, units):
    """The rest of the stack, where Blender has somewhere to put it."""
    has_gravity = False

    for modifier in modifiers:
        kind = _get(modifier, schema.MODIFIER, "")

        if not int(_float(modifier, schema.ACTIVE, 1.0)):
            continue

        if kind == schema.GRAVITY:
            has_gravity = True
            _gravity_field(modifier, system_node, report, units)

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


def _gravity_field(modifier, system_node, report, units):
    """A gravity modifier, as the force field Blender would call it.

    Not ``effector_weights.gravity``: that turns on *Blender's* gravity, which
    points down at 9.81 and knows nothing about the axis the modifier names. A
    Skyrim gravity modifier is a constant acceleration along its own axis and
    lifts as often as it drops -- flames and smoke both rise -- so it becomes a
    wind field pointed along that axis, or a point force where the modifier says
    Force Type 1.
    """
    strength = _float(modifier, schema.STRENGTH, 0.0) * units

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
    field[schema.DCC_GENERATED] = 1
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

    # A geometry-nodes simulation rather than a particle system. Blender's
    # particle system is legacy and every limit this add-on met was one of its
    # own: no fade over a particle's life (Eevee does not implement the Particle
    # Info node -- driving anything from it renders nothing at all), no
    # billboard, no way to step an animation sheet. See `simulation`.
    units = _units_of(system_node)
    settings = _simulation_settings(system_node, emitter, scene, report, units)

    sprite = _sprite(scene, system_node, settings)

    host = bpy.data.objects.new(system_node.name + "_particles", bpy.data.meshes.new(
        system_node.name + "_particles"))
    scene.collection.objects.link(host)

    # Under the system's own node, with nothing of its own. That node's frame is
    # the one the file's numbers are in -- it carries exactly the file-to-scene
    # scale `units` measures -- so a speed in game units put into this space
    # comes out right in metres.
    #
    # Not under the emitter volume, tempting as that is for something that emits
    # from it: a mesh emitter's carrier is a scene mesh at scene scale, and a
    # host parented there ran the simulation at a scale of one, which is a
    # hundred times too big. Where the emitter sits relative to the node is
    # carried as the spawn centre instead.
    host.parent = system_node
    host.matrix_parent_inverse.identity()
    host.matrix_basis.identity()

    settings["centre"] = tuple(
        (system_node.matrix_world.inverted() @ carrier.matrix_world).translation)

    if settings["camera"] is None:
        report.notes.append(
            f"{system_node.name}: no camera in the scene, so its quads face one way "
            "rather than turning to the view -- add a camera and build again to "
            "billboard them"
        )

    # Re-parenting does not move `matrix_world` until the depsgraph catches up,
    # and anything reading the host before then sees where it used to be.
    bpy.context.view_layer.update()

    modifier = host.modifiers.new(name=system_node.name, type="NODES")
    modifier.node_group = simulation.build_group(
        f"{system_node.name}_simulation", settings, sprite)

    host[schema.GENERATED] = 1
    host[schema.DCC_GENERATED] = 1
    host[schema.SOURCE] = system_node.name
    carrier[schema.SOURCE] = system_node.name

    report.systems.append(system_node.name)

    return host


def _simulation_settings(system_node, emitter, scene, report, units):
    """The NIF's numbers, as the simulation wants them.

    Lengths are **not** converted here, unlike everywhere else in this add-on.
    The simulation runs on a host parented into the emitter's own frame, and
    that frame already carries the file-to-scene scale -- so a speed in the
    game's units put into that space comes out right in metres, and converting
    it first applies the scale twice. It did: every particle spawned within a
    hundredth of the emitter's origin and travelled a hundredth of its speed,
    which read as a stack of them sitting still.

    ``units`` is still taken, because the sprite is a sibling rather than a
    child and has to be sized in the same space the instances land in.
    """
    fps = _fps(scene)

    life = _float(emitter, schema.LIFE_SPAN, 1.0)
    spread = _float(emitter, schema.LIFE_SPAN_VARIATION, 0.0)

    speed = _float(emitter, schema.SPEED, 0.0)
    wobble = _float(emitter, schema.SPEED_VARIATION, 0.0)

    emission = emission_of(system_node)

    cycle = 0

    if emission is not None:
        start, stop, rate = emission
        first = _seconds_to_frame(scene, start)
        last = _seconds_to_frame(scene, stop) if stop is not None and stop > start \
            else scene.frame_end

        # And then again. A looping emitter controller emits for its span, goes
        # back to the beginning and emits for it again, so its window is one
        # turn rather than the whole of it: the campfire's is 3.3 seconds of a
        # scene that runs for eight, and taken as a one-shot the fire went out
        # at frame 101 and the last ember died at 161.
        #
        # `cycle` is how many frames a turn is; the spawn gate wraps the frame
        # into it. The window usually fills the turn -- the emitter-active track
        # is on from its first key to its last -- and then this is simply
        # continuous emission, which is what a campfire does.
        if cycle_of(system_node) in (schema.CYCLE_LOOP, schema.CYCLE_REVERSE):
            span = cycle_span(system_node)

            if span is not None and span[1] > span[0]:
                turn = _seconds_to_frame(scene, span[1]) - _seconds_to_frame(scene, span[0])

                if 0 < turn < scene.frame_end - scene.frame_start:
                    cycle = turn
                    last = scene.frame_end
    else:
        first, last, rate = scene.frame_start, scene.frame_end, 0.0

        if any(k.startswith(schema.SEQUENCED_EMITTER) for k in system_node.keys()):
            report.notes.append(
                f"{system_node.name}: its emitter controller belongs to an animation, "
                "so the emission window is in that clip rather than on the node -- "
                "emitting over the whole timeline instead"
            )

    # A rate per second becomes a count per frame -- and most of these are
    # slower than the frame rate, so rounding to a whole number per frame is
    # wrong in the expensive direction. The campfire's embers are 7.5 a second
    # and were being born 24 times a second, three times too many, which is what
    # turned a handful of sprites into an opaque mass.
    #
    # Below the frame rate, one particle every few frames instead.
    if rate <= 0:
        per_frame, period = 1, 1
    elif rate >= fps:
        per_frame, period = max(1, int(round(rate / fps))), 1
    else:
        per_frame, period = 1, max(1, int(round(fps / rate)))

    return {
        "step": 1.0 / fps,
        "per_frame": per_frame,

        # One spawn every this many frames, for an emitter slower than the
        # frame rate.
        "period": period,
        "start_frame": first,
        "end_frame": last,

        # How long one turn of a looping emitter is, in frames; 0 for one that
        # runs its window once and stops.
        "cycle": cycle,
        "on_frames": (last - first) if not cycle else (
            _seconds_to_frame(scene, emission[1]) - first
            if emission and emission[1] and emission[1] > emission[0] else cycle),
        "life": max(life, 1e-3),
        "life_variation": max(spread, 0.0),
        "speed": speed,
        "speed_variation": max(wobble, 0.0),
        "gravity": _gravity_vector(system_node),
        "half_extent": _half_extent(emitter),
        "centre": (0.0, 0.0, 0.0),

        # Who the quads turn to face. None leaves them fixed, which is what a
        # scene with no camera has to settle for.
        "camera": scene.camera,
        "size": max(_float(emitter, schema.INITIAL_RADIUS, 1.0), 1e-4),
        "aspect": _aspect(system_node),
        "scale_over_life": _scale_curve(system_node),
    }


def _scale_curve(system_node):
    """How a particle's size changes over its life, as (start, end).

    ``BSPSysScaleModifier`` stores a curve -- the campfire's flames run 28 points
    from 1.0 down to 0.5 -- and the engine walks it as the particle ages. Two
    ends of a straight line are a fair reading of curves this shape and cost two
    nodes rather than twenty-eight; the whole table is still on the node for
    anything that wants it.
    """
    for modifier in modifiers_of(system_node):
        if _get(modifier, schema.MODIFIER, "") != schema.SCALE:
            continue

        try:
            count = int(float(_get(modifier, "num_scales", 0) or 0))
        except (TypeError, ValueError):
            continue

        if count < 2:
            continue

        first = _float(modifier, "scales_0", 1.0)
        last = _float(modifier, f"scales_{count - 1}", 1.0)

        return (max(first, 0.0), max(last, 0.0))

    return (1.0, 1.0)


def _half_extent(emitter):
    """Half the emitter volume, as a box.

    A box has all three, a cylinder a radius and a height, a sphere only its
    radius -- and the simulation spawns in a box for all three. At the size
    these are used the difference is a few centimetres; the shape itself is
    still carried on the modifier's node for anything that wants it.
    """
    kind = _get(emitter, schema.MODIFIER, "")

    if kind == "NiPSysBoxEmitter":
        return (
            _float(emitter, schema.WIDTH, 0.0) / 2.0,
            _float(emitter, schema.DEPTH, 0.0) / 2.0,
            _float(emitter, schema.HEIGHT, 0.0) / 2.0,
        )

    radius = _float(emitter, schema.RADIUS, 0.0)

    if kind == "NiPSysCylinderEmitter":
        return (radius, radius, _float(emitter, schema.HEIGHT, 0.0) / 2.0)

    return (radius, radius, radius)


def _gravity_vector(system_node):
    """The gravity modifiers, summed into one acceleration."""
    total = [0.0, 0.0, 0.0]

    for modifier in modifiers_of(system_node):
        if _get(modifier, schema.MODIFIER, "") != schema.GRAVITY:
            continue

        strength = _float(modifier, schema.STRENGTH, 0.0)
        axis = _vector(modifier, schema.GRAVITY_AXIS)

        for i in range(3):
            total[i] += axis[i] * strength

    return tuple(total)


def _aspect(system_node):
    """How wide the quad is against its height, from ``NiPSysData``.

    nif.xml: "Sets aspect ratio for Subtexture Offset UV quads". It is not
    decoration -- the campfire's fire column says 0.5 and its atlas cells are 64
    pixels wide by 128 tall, exactly that. Drawn on a square quad the artwork
    comes out at twice its width, which is what made every flame a rectangle.

    Across the two samples it runs 0.5, 0.6, 0.9 and 1.25, so it is a shape each
    system chooses rather than a constant worth ignoring.
    """
    return max(_float_str(system_node.get(schema.ASPECT_RATIO), 1.0), 1e-3)


def _float_str(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _sprite(scene, system_node, settings):
    """The quad each particle is.

    Made here rather than by the material add-on, which only dresses it: the
    simulation needs something to instance before anything has been shaded.
    """
    name = f"{system_node.name}_sprite"
    existing = bpy.data.objects.get(name)

    if existing is not None:
        return existing

    # The radius gives the height and the aspect narrows or widens it. Which of
    # the two dimensions the radius pins is not in the file; height is the one
    # that makes the artwork come out its own shape, since a flame column's
    # cells are taller than they are wide and the aspect matches that exactly.
    half = settings["size"]
    wide = half * settings["aspect"]

    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(
        [(-wide, 0.0, -half), (wide, 0.0, -half), (wide, 0.0, half), (-wide, 0.0, half)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()

    uv = mesh.uv_layers.new(name="UVMap")

    for i, pair in enumerate(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))):
        uv.data[i].uv = pair

    sprite = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(sprite)

    sprite[schema.GENERATED] = 1
    sprite[schema.DCC_GENERATED] = 1
    sprite[schema.SOURCE] = system_node.name

    # Only the instances should be seen.
    sprite.hide_render = True
    sprite.hide_set(True)

    return sprite


def build(scene):
    """Every particle system in the scene."""
    report = Report()
    objects = {obj.name: obj for obj in scene.objects}

    for obj in list(scene.objects):
        if is_system(obj):
            build_system(obj, scene, objects, report)

    return report


def bake(scene):
    """Run the simulations through the timeline and keep the result.

    A simulation zone only steps when the frame advances by one, so a file that
    has never been played holds whatever state it was left in -- scrub to the
    middle of an effect and almost nothing is there. Baking walks the frames
    once and caches what comes out, so the timeline can then be scrubbed like
    any other animation.

    Quiet about failing: baking wants a context the add-on may not have when it
    is driven from a script, and an effect that has to be played rather than
    scrubbed is still an effect.
    """
    hosts = [o for o in scene.objects if o.get(schema.GENERATED) and o.modifiers]

    if not hosts:
        return 0

    baked = 0

    for host in hosts:
        if not any(m.type == "NODES" for m in host.modifiers):
            continue

        try:
            with bpy.context.temp_override(
                    scene=scene, object=host, selected_objects=[host],
                    active_object=host):
                bpy.ops.object.simulation_nodes_cache_bake()

            baked += 1
        except (RuntimeError, TypeError):
            continue

    return baked


def clear(scene):
    """Undo a build: everything it added, and the node groups behind it.

    The objects go first and the groups after, because a group with a modifier
    still pointing at it has a user and will not be removed.
    """
    removed = 0

    for obj in list(scene.objects):
        if schema.GENERATED in obj:
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1

    for group in list(bpy.data.node_groups):
        if group.users == 0 and group.name.endswith("_simulation"):
            bpy.data.node_groups.remove(group)

    # The invisible material the emitter volumes wore, once nothing wears it.
    material = bpy.data.materials.get(INVISIBLE_MATERIAL)

    if material is not None and material.users == 0:
        bpy.data.materials.remove(material)

    return removed
