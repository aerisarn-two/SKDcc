"""The property names NIFBX writes for a particle system, and what they mean.

Mirror of ``FbxParticleWriter``. Nothing here is guessed: every name was read
out of the properties of 40 converted effect meshes, and the semantics are in
``nif-particle-semantics-spec.md`` in NIFBX.

A NIF particle system is a node carrying the system's own fields, with its
modifiers hanging under it as child nodes -- one per modifier, each carrying its
own fields unprefixed. The order of the stack is in each modifier's ``order``.
"""

# --- what marks a node ------------------------------------------------------

#: On the system's node: the block type, e.g. ``NiParticleSystem``.
SYSTEM = "particle_system"

#: On the system's node: its data block's type, e.g. ``NiPSysData``.
DATA = "particle_data"

#: On a modifier's node: the block type. Also what tells a modifier from a bone.
MODIFIER = "particle_modifier"

#: On a modifier's node: the name a controller binds to, which is not the node's.
MODIFIER_NAME = "particle_modifier_name"

#: On a collider's node: the block type.
COLLIDER = "particle_collider"

#: Prefix on the system block's own fields.
SYSTEM_PREFIX = "nps_"

#: Prefix on the data block's fields.
DATA_PREFIX = "npsd_"

#: Suffix on a property naming what a link pointed at.
LINK_SUFFIX = "_ref"

# --- the fields every emitter has -------------------------------------------

SPEED = "speed"
SPEED_VARIATION = "speed_variation"
DECLINATION = "declination"
DECLINATION_VARIATION = "declination_variation"
PLANAR_ANGLE = "planar_angle"
PLANAR_ANGLE_VARIATION = "planar_angle_variation"
INITIAL_RADIUS = "initial_radius"

# On NiPSysData: "Sets aspect ratio for Subtexture Offset UV quads".
ASPECT_RATIO = "npsd_aspect_ratio"
RADIUS_VARIATION = "radius_variation"
LIFE_SPAN = "life_span"
LIFE_SPAN_VARIATION = "life_span_variation"
INITIAL_COLOR = "initial_color"

#: On every modifier: where it sits in the stack, and whether it runs at all.
ORDER = "order"
ACTIVE = "active"

#: The axis every emitter births along, stated by the engine rather than by the
#: file. ``NiPSEmitter::EmitParticles`` builds the direction as
#:
#:     kDir = (0, 0, 1)
#:     if declination != 0:
#:         kDir = (sin(dec)cos(plan), sin(dec)sin(plan), cos(dec))
#:
#: so declination is the polar angle from **local +Z** and the planar angle is
#: the azimuth about it. A declination of zero is straight up the axis, not a
#: random direction.
EMISSION_AXIS = (0.0, 0.0, 1.0)

#: The volume an emitter births into. Box has all three; cylinder has the last
#: two; a sphere has only its radius.
WIDTH = "width"
DEPTH = "depth"
HEIGHT = "height"
RADIUS = "radius"

#: A volume emitter births inside the object this names, and the direction it
#: births along is that object's local +Z -- see EMISSION_AXIS.
EMITTER_OBJECT = "emitter_object" + LINK_SUFFIX

#: ``NiPSysMeshEmitter``: where a particle's first velocity comes from.
#: ``NiPSMeshEmitter.h`` names them: 0 is VELOCITY_USE_NORMALS, 1 RANDOM,
#: 2 DIRECTION.
INITIAL_VELOCITY_TYPE = "initial_velocity_type"
USE_NORMALS = 0

#: A mesh emitter births from the surface of named objects.
NUM_EMITTER_MESHES = "num_emitter_meshes"
EMITTER_MESHES = "emitter_meshes_"

#: The emitters, by block type. A volume emitter has no mesh of its own.
EMITTERS = (
    "NiPSysBoxEmitter",
    "NiPSysCylinderEmitter",
    "NiPSysSphereEmitter",
    "NiPSysMeshEmitter",
)

# --- the modifiers this reads ----------------------------------------------

AGE_DEATH = "NiPSysAgeDeathModifier"
GRAVITY = "NiPSysGravityModifier"
DRAG = "NiPSysDragModifier"
ROTATION = "NiPSysRotationModifier"
SPAWN = "NiPSysSpawnModifier"
SCALE = "BSPSysScaleModifier"

#: "Particle modifier that adds rotations to particles."
ROTATION = "NiPSysRotationModifier"
ROTATION_SPEED = "rotation_speed"
ROTATION_SPEED_VARIATION = "rotation_speed_variation"
ROTATION_ANGLE = "rotation_angle"
ROTATION_ANGLE_VARIATION = "rotation_angle_variation"
RANDOM_ROTATION_SIGN = "random_rot_speed_sign"
COLOR = "BSPSysSimpleColorModifier"
SUBTEX = "BSPSysSubTexModifier"

#: ``NiPSysGravityModifier``. Vanilla stores Strength 0 on all 615 of them and
#: animates it with a controller instead -- see the spec, section 4.4 -- so a
#: build that reads only this field finds nothing and must not conclude there is
#: no gravity.
STRENGTH = "strength"
GRAVITY_AXIS = "gravity_axis"
FORCE_TYPE = "force_type"
DECAY = "decay"
TURBULENCE = "turbulence"
WORLD_ALIGNED = "world_aligned"

#: ``NiPSysDragModifier``: a velocity-proportional damping, 0..1.
PERCENTAGE = "percentage"

#: ``NiPSysRotationModifier``.
ROTATION_SPEED = "rotation_speed"
ROTATION_SPEED_VARIATION = "rotation_speed_variation"
ROTATION_ANGLE = "rotation_angle"
ROTATION_ANGLE_VARIATION = "rotation_angle_variation"
RANDOM_AXIS = "random_axis"
AXIS = "axis"

#: ``NiPSysSpawnModifier``: particles born from particles.
MIN_TO_SPAWN = "min_num_to_spawn"
MAX_TO_SPAWN = "max_num_to_spawn"
SPAWN_GENERATIONS = "num_spawn_generations"
PERCENTAGE_SPAWNED = "percentage_spawned"

#: ``NiPSysData``: the buffer the engine fills, which is the particle count.
MAX_VERTICES = DATA_PREFIX + "bs_max_vertices"

# --- written by this add-on, never by the exporter --------------------------

#: Marks what this created, so it can clean up after itself.
GENERATED = "skp_generated"

#: On the object carrying the system: the particle node it was built from.
SOURCE = "skp_source"

# --- the controllers that configure the system ------------------------------

#: On the system's node: how many structural controllers it carries. Mirror of
#: ``FbxNodeControllers``.
CONTROLLER_COUNT = "particle_controllers"

#: Prefix on one of them, before its index: ``npc_0_type``, ``npc_0_flags``...
CONTROLLER_PREFIX = "npc_"

#: ``NiPSysEmitterCtlr``: when the system emits, and how fast.
EMITTER_CTLR = "NiPSysEmitterCtlr"
MULTI_TARGET_EMITTER_CTLR = "BSPSysMultiTargetEmitterCtlr"

#: On a controller: the span it runs over, in seconds.
START_TIME = "start_time"
STOP_TIME = "stop_time"

# Bits 1-2 of a NiTimeController's flags word.
CTLR_FLAGS = "flags"
CYCLE_LOOP = "LOOP"
CYCLE_REVERSE = "REVERSE"
CYCLE_CLAMP = "CLAMP"

#: The birth rate, in particles per second. Almost always a bare value with no
#: data block behind it -- 1,600 of the game's 1,704 emitter controllers -- so
#: the interpolator's own ``value`` is the rate.
RATE = "interpolator_value"

#: The emitter-active track: 1 while emitting, 0 while not. Carried whole, so
#: the keys are readable -- ``..._data_data_keys_0_time`` and ``_value``. 1,055
#: of the 1,704 have no data block at all, which means always on.
WINDOW = "visibility_interpolator_data_data_"
WINDOW_KEYS = WINDOW + "keys_"
WINDOW_KEY_COUNT = WINDOW + "num_keys"

#: Prefix on the fields of a controller a *sequence* drives. NIFBX carries the
#: class's own fields here and leaves the span and the keys to the clip, so a
#: node with one of these has an emitter controller whose window is in an
#: animation rather than on the node.
SEQUENCED_PREFIX = "nac_"
SEQUENCED_EMITTER = SEQUENCED_PREFIX + EMITTER_CTLR

#: What a sequenced controller's constants are called on the node. NIFBX mirrors
#: them there because they live on the animation stack in the file, and Blender
#: keeps none of a stack's user properties.
SEQUENCED_BIRTH_RATE = "BirthRate"
SEQUENCED_EMITTER_ACTIVE = "EmitterActive"
SEQUENCED_FLAGS_SUFFIX = "_flags"

#: What NIFBX calls a node a DCC tool built for itself. Anything this add-on
#: creates carries it, so converting the scene back does not turn the
#: scaffolding into model -- an emitter volume, a force field and a sprite are
#: things Blender needs to show the effect and things the NIF has never heard of.
#:
#: Owned by NIFBX (``FbxNodeType.GeneratedProperty``) rather than by this add-on,
#: so a second tool needs no second rule.
DCC_GENERATED = "skdcc_generated"
