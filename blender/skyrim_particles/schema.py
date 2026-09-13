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
RADIUS_VARIATION = "radius_variation"
LIFE_SPAN = "life_span"
LIFE_SPAN_VARIATION = "life_span_variation"
INITIAL_COLOR = "initial_color"

#: On every modifier: where it sits in the stack, and whether it runs at all.
ORDER = "order"
ACTIVE = "active"

#: The volume an emitter births into. Box has all three; cylinder has the last
#: two; a sphere has only its radius.
WIDTH = "width"
DEPTH = "depth"
HEIGHT = "height"
RADIUS = "radius"

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
