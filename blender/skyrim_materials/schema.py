"""The property names NIFBX writes for a material, and what they mean.

Mirror of ``FbxMaterialWriter`` and ``FbxEffectShader``. Nothing here is guessed:
the names were read out of converted meshes, the flag bits out of ``nif.xml``,
and the meanings out of NifSkope's own GLSL -- ``shaders/sk_default.frag`` and
``shaders/sk_effectshader.frag`` -- and the property code that feeds it,
``glproperty.cpp``.

A NIF shader is a ``BSLightingShaderProperty`` or a ``BSEffectShaderProperty``.
Blender's FBX importer keeps a material's user-defined properties, so all of
these arrive intact even though the shader itself cannot travel: FBX has no node
graph, and a Blender node tree exported to FBX comes back flattened to a
Principled BSDF. So the parameters travel and the tree is rebuilt here.
"""

# --- which shader this is ---------------------------------------------------

#: Written only for a shader the common material form does not cover, naming its
#: block: ``BSEffectShaderProperty``, ``BSWaterShaderProperty``. A material
#: without it is a ``BSLightingShaderProperty``.
SHADER_BLOCK = "shader_block"

EFFECT_SHADER = "BSEffectShaderProperty"
LIGHTING_SHADER = "BSLightingShaderProperty"

#: Prefix on an effect shader's own fields, carried flat.
EFFECT_PREFIX = "es_"

#: The lighting shader's shading path, by name. Gates several of the flags
#: below: a glow map counts only on a glow shader, a cubemap only on an
#: environment one (``glproperty.cpp:1153,1192``).
SHADER_TYPE = "shader_type"

ST_ENVIRONMENT = "Environment Map"
ST_GLOW = "Glow Shader"
ST_HEIGHTMAP = "Heightmap"
ST_EYE_ENVMAP = "Eye Envmap"

# --- the two flag words -----------------------------------------------------

#: Signed, because FBX has no unsigned property type: 0x82400301 arrives as
#: -2109734143 and two's complement makes it exact again.
SHADER_FLAGS_1 = "shader_flags_1"
SHADER_FLAGS_2 = "shader_flags_2"

#: ``SkyrimShaderPropertyFlags1``, by bit, from nif.xml. Only the ones the
#: renderer reads are named.
SF1_SPECULAR = 0
SF1_VERTEX_ALPHA = 3
SF1_GREYSCALE_TO_PALETTE_COLOR = 4
SF1_GREYSCALE_TO_PALETTE_ALPHA = 5
SF1_USE_FALLOFF = 6
SF1_ENVIRONMENT_MAPPING = 7
SF1_PARALLAX = 11
SF1_MODEL_SPACE_NORMALS = 12
SF1_REFRACTION = 15
SF1_FIRE_REFRACTION = 16
SF1_EYE_ENVIRONMENT_MAPPING = 17
SF1_OWN_EMIT = 22

#: ``SkyrimShaderPropertyFlags2``.
SF2_DOUBLE_SIDED = 4
SF2_VERTEX_COLORS = 5
SF2_GLOW_MAP = 6
SF2_WEAPON_BLOOD = 17
SF2_MULTI_LAYER_PARALLAX = 24
SF2_SOFT_LIGHTING = 25
SF2_RIM_LIGHTING = 26
SF2_BACK_LIGHTING = 27
SF2_EFFECT_LIGHTING = 30

# --- the lighting shader's own numbers --------------------------------------

#: The emissive colour and multiple, the glossiness and the specular strength go
#: into FBX's *standard* material slots, which means Blender's importer consumes
#: them rather than passing them through: they are never custom properties, and
#: an add-on looking for them by these names finds nothing and falls back to a
#: default. They arrive on the Principled BSDF instead, which is where
#: ``build._imported_shading`` reads them from.
#:
#: Kept here named so the mistake is not made twice.
CONSUMED_BY_THE_IMPORTER = (
    "EmissiveColor", "EmissiveFactor", "SpecularColor", "SpecularFactor",
    "ShininessExponent", "TransparencyFactor",
)

#: ``lightingEffect1`` and ``lightingEffect2`` in the GLSL: the softlight wrap
#: and the rimlight power.
LIGHTING_EFFECT_1 = "lighting_effect_1"
LIGHTING_EFFECT_2 = "lighting_effect_2"

#: ``envReflection``: how much of the cubemap reaches the albedo.
ENVIRONMENT_MAP_SCALE = "environment_map_scale"

#: How UVs outside 0..1 behave, as the NIF's packed value.
TEXTURE_CLAMP_MODE = "texture_clamp_mode"

# --- the texture set --------------------------------------------------------

#: Slots 0 and 1 connect to FBX's standard DiffuseColor and NormalMap
#: properties, so Blender wires them into the node tree itself. Slots past the
#: second have no standard property: the export names one after the slot and
#: Blender declines the connection ("material link 'slot5' ignored"), but keeps
#: the path written beside it as a user property. That property is the only
#: record of them that survives, which is why they are read from here.
#:
#: Named ``slot{n+1}``, one-based, which is the exporter's spelling.
def slot_property(slot):
    """The property a texture slot's path arrives under, or None for 0 and 1."""
    return None if slot < 2 else f"slot{slot + 1}"


#: What each slot holds, from BSShaderTextureSet.
SLOT_DIFFUSE = 0
SLOT_NORMAL = 1
SLOT_GLOW = 2
SLOT_HEIGHT = 3
SLOT_ENVIRONMENT = 4
SLOT_ENVIRONMENT_MASK = 5
SLOT_TINT = 6
SLOT_BACKLIGHT = 7

SLOT_COUNT = 9

# --- the effect shader's own fields -----------------------------------------

#: Carried flat under EFFECT_PREFIX, as text -- NifFieldCodec writes every field
#: as a string whatever its type.
ES_SOURCE_TEXTURE = "source_texture"
ES_GREYSCALE_TEXTURE = "greyscale_texture"

#: ``glowColor`` in the GLSL. RGBA: the alpha is squared into ``alphaMult``.
ES_BASE_COLOR = "base_color"

#: ``glowMult``: the whole result is multiplied by it at the end.
ES_BASE_COLOR_SCALE = "base_color_scale"

#: ``falloffParams`` = (start angle, stop angle, start opacity, stop opacity).
#: The GLSL builds the falloff as
#:
#:     falloff = smoothstep(stopAngle, startAngle, abs(viewDir.z))
#:     falloff = mix(max(stopOpacity, 0), min(startOpacity, 1), falloff)
ES_FALLOFF_START_ANGLE = "falloff_start_angle"
ES_FALLOFF_STOP_ANGLE = "falloff_stop_angle"
ES_FALLOFF_START_OPACITY = "falloff_start_opacity"
ES_FALLOFF_STOP_OPACITY = "falloff_stop_opacity"

ES_UV_OFFSET = "uv_offset"
ES_UV_SCALE = "uv_scale"

#: Its own copy of the flag words, as text.
ES_SHADER_FLAGS_1 = "shader_flags_1"
ES_SHADER_FLAGS_2 = "shader_flags_2"

# --- the colour curve over a particle's life ------------------------------

#: ``BSPSysSimpleColorModifier``, which is what makes a particle appear and go
#: away rather than blink into being. It hangs on the system's node as a child,
#: like every other modifier.
COLOR_MODIFIER = "BSPSysSimpleColorModifier"

#: Three RGBA colours the particle passes through over its life. Their *alphas*
#: are the fade: the campfire's flames run 0 -> 1 -> 0.
COLORS = ("colors_0", "colors_1", "colors_2")

#: Where each colour band sits, as a fraction of the particle's life.
#:
#: nif.xml names these "Color 1 End Percent", "Color 1 Start Percent",
#: "Color 2 End Percent", "Color 2 Start Percent" in that file order, which
#: cannot be right: the campfire holds 0, 0.5, 0.51, 0.8, ascending. So they are
#: read as two ascending bounds in the order the file stores them, and the names
#: are taken to be swapped rather than the data to be nonsense.
COLOR_BOUNDS = (
    "color_1_end_percent",
    "color_1_start_percent",
    "color_2_end_percent",
    "color_2_start_percent",
)

#: Extra fade at each end, on top of whatever the colours' alphas do.
FADE_IN = "fade_in_percent"
FADE_OUT = "fade_out_percent"

# --- the alpha property -----------------------------------------------------

#: A NiAlphaProperty, spread across properties because FBX has nowhere to put a
#: packed flags word.
ALPHA_BLEND = "color_blending_enable"
SOURCE_BLEND = "source_blend_mode"
DESTINATION_BLEND = "destination_blend_mode"
ALPHA_TEST = "alpha_test_enable"
ALPHA_TEST_THRESHOLD = "alpha_test_threshold"

#: The blend pair every additive effect in the game uses: what the engine calls
#: SRC_ALPHA/ONE. Blender has no additive blend mode, so a material with this
#: pair is built to an Emission with no transparency mix instead -- which is
#: what additive looks like when the renderer will not add.
BLEND_SRC_ALPHA = "SRC_ALPHA"
BLEND_ONE = "ONE"

# --- written by this add-on, never by the exporter --------------------------

#: Marks what this created, so it can be taken away again.
GENERATED = "skm_generated"

#: On a rebuilt material: which shader it was built from.
SOURCE = "skm_source"

#: What NIFBX calls a node a DCC tool built for itself. Anything this add-on
#: creates carries it, so converting the scene back does not turn the
#: scaffolding into model -- an emitter volume, a force field and a sprite are
#: things Blender needs to show the effect and things the NIF has never heard of.
#:
#: Owned by NIFBX (``FbxNodeType.GeneratedProperty``) rather than by this add-on,
#: so a second tool needs no second rule.
DCC_GENERATED = "skdcc_generated"

#: What the particle simulation publishes on each instance: how far through its
#: life that particle is, 0 at birth and 1 at death. Mirror of
#: ``skyrim_particles.simulation.PARTICLE_AGE``; read with an Attribute node of
#: type INSTANCER, which Eevee implements where Particle Info is not.
PARTICLE_AGE = "ParticleAge"

#: And one number per particle that does not change as it ages. Mirror of
#: ``skyrim_particles.simulation.PARTICLE_SEED``.
PARTICLE_SEED = "ParticleSeed"

#: BSPSysSubTexModifier: "Similar to a Flip Controller, this handles particle
#: texture animation on a single texture atlas". A system with subtexture
#: offsets and no such modifier does not flip at all.
SUBTEX_MODIFIER = "BSPSysSubTexModifier"
SUBTEX_START = "start_frame"
SUBTEX_START_FUDGE = "start_frame_fudge"
SUBTEX_END = "end_frame"
SUBTEX_LOOP_START = "loop_start_frame"
SUBTEX_FRAME_COUNT = "frame_count"
