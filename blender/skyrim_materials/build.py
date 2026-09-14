"""Skyrim shader properties, as a Blender node tree.

Two shaders, and they deserve different treatment.

``BSEffectShaderProperty`` is what every flame, glow, magic effect and particle
in the game uses, and NifSkope's ``sk_effectshader.frag`` is a hundred lines
with no lighting in it at all::

    color.rgb = baseMap.rgb * C.rgb * glowColor.rgb
    color.a   = baseMap.a * C.a * falloff * glowColor.a^2
    falloff   = smoothstep(stopAngle, startAngle, abs(viewDir.z))
                mixed between stopOpacity and startOpacity
    out.rgb   = color.rgb * glowMult

Every one of those is a Blender node, so this one is rebuilt faithfully: an
emission, faded by view angle, mixed against transparency. What you see is what
NifSkope shows.

``BSLightingShaderProperty`` is not translatable the same way, and pretending
otherwise would be the lie. ``sk_default.frag`` is a forward pipeline with the
light's ambient and diffuse arriving as uniforms (``A + D * NdotL``), a
Blinn-Phong specular (``pow(NdotH, glossiness)``), and an Uncharted-2 filmic
tonemap *inside the fragment shader*. Blender has real lights, a GGX specular,
and tonemapping in the view transform. Reproducing the GLSL exactly would mean
an emission-only material that ignores every light in the scene and tonemaps
twice.

So that one is mapped onto a Principled BSDF instead: base colour, normal,
emission, specular and alpha, which is what those parameters mean. It responds
to Blender's lights and can be edited and rendered. It is not pixel-identical to
NifSkope, and is not meant to be.

Nothing here writes back. A node tree does not survive FBX -- Blender's exporter
flattens one to a Principled BSDF, measured at seven nodes in and three out --
so the parameters are the record and the tree is built from them each time.
"""

import os

import bpy

from . import schema


class Report:
    """What was built, and what could not be."""

    def __init__(self):
        self.materials = []
        self.skipped = []
        self.notes = []
        self.attached = 0
        self.refracting = False

    def __str__(self):
        text = f"{len(self.materials)} material(s)"

        if self.attached:
            text += f", {self.attached} given to particles"

        if self.skipped:
            text += f", {len(self.skipped)} skipped"

        return text


# --- reading the properties -------------------------------------------------


def _get(material, name, fallback=None):
    try:
        value = material[name]
    except KeyError:
        return fallback

    return fallback if value is None else value


def _float(material, name, fallback=0.0):
    try:
        return float(_get(material, name, fallback))
    except (TypeError, ValueError):
        return fallback


def _effect(material, field, fallback=""):
    """One of the effect shader's own fields, which travel as text."""
    return str(_get(material, schema.EFFECT_PREFIX + field, fallback) or fallback)


def _effect_float(material, field, fallback=0.0):
    try:
        return float(_effect(material, field, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def _as_float(value, fallback=0.0):
    """A number that arrived as whatever the codec wrote it as."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _numbers(text):
    """A NIF vector as the codec writes it: numbers separated by spaces."""
    found = []

    for part in str(text).replace(",", " ").split():
        try:
            found.append(float(part))
        except ValueError:
            pass

    return found


def _flags(material, name, effect=False):
    """One of the two flag words, as an unsigned 32-bit value.

    FBX has no unsigned property type, so the exporter casts through a signed
    int and anything with the top bit set arrives negative. An effect shader
    carries its own copy as text instead.
    """
    if effect:
        raw = _effect(material, name, "0")
    else:
        raw = _get(material, name, 0)

    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return 0

    return value & 0xFFFFFFFF


def _bit(word, index):
    return bool(word & (1 << index))


def is_skyrim_material(material):
    """Whether NIFBX wrote this material's parameters."""
    return (
        material is not None
        and (
            schema.SHADER_BLOCK in material.keys()
            or schema.SHADER_FLAGS_1 in material.keys()
            or schema.SHADER_TYPE in material.keys()
        )
    )


def is_effect_shader(material):
    return _get(material, schema.SHADER_BLOCK, "") == schema.EFFECT_SHADER


# --- finding the images -----------------------------------------------------


def _leaf(path):
    return os.path.basename(str(path).replace("\\", "/")).lower()


def _image_named(path):
    """The imported image a NIF texture path refers to, or None.

    By leaf name without its extension, which is what Blender names an image it
    unpacks from embedded media or finds beside the FBX. Blender also suffixes a
    duplicate with ``.001``, so those match too -- they are the same file
    imported once per slot that named it.
    """
    if not path:
        return None

    want = os.path.splitext(_leaf(path))[0]

    if not want:
        return None

    for image in bpy.data.images:
        name = image.name.lower()
        stem = name.split(".")[0] if name.count(".") else name

        if stem == want or os.path.splitext(name)[0] == want:
            return image

    return None


def _slot_path(material, slot):
    """The texture in one slot of the set, as the NIF named it.

    Slots 0 and 1 arrive as connected images rather than as paths, because FBX
    has standard properties for them; the caller reads those off the node tree.
    """
    name = schema.slot_property(slot)

    return "" if name is None else str(_get(material, name, "") or "")


def _imported_shading(material):
    """What Blender's FBX importer already worked out, before the tree is cleared.

    The emissive colour, the emissive multiple, the glossiness and the specular
    strength are standard FBX material properties, so the importer *consumes*
    them -- they never appear as custom properties, and reading them from there
    finds nothing. It puts them on the Principled BSDF instead, correctly:
    ``EmissiveColor``/``EmissiveFactor`` become emission colour and strength
    (``import_fbx.py:2106``), and the NIF's glossiness arrives as a roughness.

    So they are read off the node rather than recomputed. Reading them from the
    wrong place is what put a white emission at full strength on every surface
    in the file, which swamped the textures and made a campfire render as a
    featureless white shape with its texture correctly wired underneath.
    """
    found = {}

    if not material.use_nodes:
        return found

    node = next((n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)

    if node is None:
        return found

    for name in ("Emission Color", "Emission Strength", "Roughness", "Metallic",
                 "Specular IOR Level", "Alpha", "IOR"):
        if name in node.inputs and not node.inputs[name].links:
            value = node.inputs[name].default_value
            found[name] = list(value) if hasattr(value, "__len__") else float(value)

    return found


def _existing_images(material):
    """The images Blender's importer already wired in, by the socket it used."""
    found = {}

    if not material.use_nodes:
        return found

    for node in material.node_tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue

        for link in node.outputs[0].links:
            found.setdefault(link.to_socket.name, []).append(node.image)

    return found


# --- building ---------------------------------------------------------------


class _Tree:
    """A node tree being laid out left to right, so it can be read."""

    def __init__(self, material):
        material.use_nodes = True
        self.tree = material.node_tree
        self.tree.nodes.clear()
        self.column = 0

    def add(self, kind, column=None, row=0, **fields):
        node = self.tree.nodes.new(kind)
        node.location = (((self.column if column is None else column) * 260), -row * 230)

        for key, value in fields.items():
            setattr(node, key, value)

        return node

    def link(self, output, node_in, socket):
        self.tree.links.new(output, node_in.inputs[socket])

    def step(self, columns=1):
        self.column += columns


def _texture(tree, image, column, row, non_color=False, mapping=None):
    node = tree.add("ShaderNodeTexImage", column=column, row=row)
    node.image = image
    node.label = image.name

    if non_color:
        node.image.colorspace_settings.name = "Non-Color"

    if mapping is not None:
        tree.link(mapping.outputs["Vector"], node, "Vector")

    return node


def _uv_mapping(tree, offset, scale, column=0):
    """The GLSL's ``gl_TexCoord[0].st * uvScale + uvOffset``."""
    if tuple(offset) == (0.0, 0.0) and tuple(scale) == (1.0, 1.0):
        return None

    coords = tree.add("ShaderNodeTexCoord", column=column)
    mapping = tree.add("ShaderNodeMapping", column=column + 1)

    mapping.inputs["Location"].default_value = (offset[0], offset[1], 0.0)
    mapping.inputs["Scale"].default_value = (scale[0], scale[1], 1.0)

    tree.link(coords.outputs["UV"], mapping, "Vector")

    return mapping


def build_effect_material(material, report):
    """``sk_effectshader.frag``, as nodes.

    Faithful, because it can be: there is no lighting in that shader, so nothing
    has to be reinterpreted for a renderer that lights things differently.
    """
    images = _existing_images(material)
    source = _effect(material, schema.ES_SOURCE_TEXTURE)
    greyscale = _effect(material, schema.ES_GREYSCALE_TEXTURE)

    base_image = _image_named(source) or (images.get("Base Color") or [None])[0]

    flags1 = _flags(material, schema.ES_SHADER_FLAGS_1, effect=True)
    flags2 = _flags(material, schema.ES_SHADER_FLAGS_2, effect=True)

    colour = _numbers(_effect(material, schema.ES_BASE_COLOR, "1 1 1 1")) or [1.0, 1.0, 1.0, 1.0]
    colour = (colour + [1.0, 1.0, 1.0, 1.0])[:4]
    glow_mult = _effect_float(material, schema.ES_BASE_COLOR_SCALE, 1.0)

    offset = (_numbers(_effect(material, schema.ES_UV_OFFSET, "0 0")) + [0.0, 0.0])[:2]
    scale = (_numbers(_effect(material, schema.ES_UV_SCALE, "1 1")) + [1.0, 1.0])[:2]

    tree = _Tree(material)

    # An animation sheet walked by age beats the shader's own UV transform,
    # which in these files is the identity anyway.
    sheet = _subtexture_sheet(material)

    mapping = (
        _atlas_mapping(tree, material, sheet, column=-10, row=0)
        if sheet is not None
        else _uv_mapping(tree, offset, scale)
    )

    # color.rgb = baseMap.rgb * glowColor.rgb   (vertex colour C is left out:
    # Blender applies it through a Color Attribute only when the mesh has one,
    # and most effect meshes do not.)
    if base_image is not None:
        base = _texture(tree, base_image, column=2, row=0, mapping=mapping)
        rgb_source, alpha_source = base.outputs["Color"], base.outputs["Alpha"]
    else:
        base = tree.add("ShaderNodeRGB", column=2)
        base.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
        rgb_source, alpha_source = base.outputs[0], None
        report.notes.append(f"{material.name}: no source texture in the scene, using white")

    tint = tree.add("ShaderNodeMixRGB", column=3, row=0, blend_type="MULTIPLY")
    tint.inputs["Fac"].default_value = 1.0
    tint.inputs["Color2"].default_value = (colour[0], colour[1], colour[2], 1.0)
    tree.link(rgb_source, tint, "Color1")

    # C in the GLSL: the mesh's own colour, which multiplies both.
    vertex_rgb, vertex_alpha = _vertex_colour(tree, material, column=0, row=2)

    # color.a *= falloff * glowColor.a^2
    alpha = tree.add("ShaderNodeMath", column=3, row=1, operation="MULTIPLY")
    alpha.inputs[1].default_value = colour[3] * colour[3]

    if alpha_source is not None:
        tree.link(alpha_source, alpha, 0)
    else:
        alpha.inputs[0].default_value = 1.0

    if vertex_rgb is not None and _bit(flags2, schema.SF2_VERTEX_COLORS):
        shaded = tree.add("ShaderNodeMixRGB", column=4, row=2, blend_type="MULTIPLY")
        shaded.inputs["Fac"].default_value = 1.0
        tree.link(tint.outputs["Color"], shaded, "Color1")
        tree.link(vertex_rgb, shaded, "Color2")
        tint = shaded

    if vertex_alpha is not None and _bit(flags1, schema.SF1_VERTEX_ALPHA):
        shaped = tree.add("ShaderNodeMath", column=4, row=3, operation="MULTIPLY")
        tree.link(alpha.outputs[0], shaped, 0)
        tree.link(vertex_alpha, shaped, 1)
        alpha = shaped

    # Kept as a socket rather than multiplied in straight away: the two
    # greyscale branches below read the falloff into a gradient coordinate
    # instead of scaling anything by it.
    falloff = (
        _falloff_nodes(tree, material, column=3, row=2)
        if _bit(flags1, schema.SF1_USE_FALLOFF)
        else None
    )

    if falloff is not None:
        combined = tree.add("ShaderNodeMath", column=4, row=1, operation="MULTIPLY")
        tree.link(alpha.outputs[0], combined, 0)
        tree.link(falloff, combined, 1)
        alpha_out = combined.outputs[0]
    else:
        alpha_out = alpha.outputs[0]

    # What the particle wears as it ages. Only a particle system has a life to
    # read, so a glow plane wearing the same shader is left alone.
    #
    # Built here, before the palette, because this ramp is C in the GLSL and
    # that is where the shader spends C: both greyscale branches throw away the
    # colour they were handed and read the gradient at a coordinate made of it.
    modifier = _colour_modifier(material)
    ramp, fraction = None, None

    if modifier is not None:
        ramp, fraction = _life_ramp(tree, modifier, column=0, row=4)

    palette = _image_named(greyscale) if greyscale else None

    if palette is None and greyscale:
        report.notes.append(
            f"{material.name}: greyscale palette '{greyscale}' is not in the scene"
        )

    #   if ( greyscaleColor ) color.rgb = colorLookup(baseMap.g, C.g * falloff * glowColor.r).rgb
    #
    # A replacement, not a tint: everything mixed into `tint` above is thrown
    # away. That is what lets a base colour of 0.137 grey read as fire -- the
    # gradient holds the colour and the emissive only says where to read it.
    by_palette = (
        _bit(flags1, schema.SF1_GREYSCALE_TO_PALETTE_COLOR)
        and palette is not None
        and base.type == "TEX_IMAGE"
    )

    if by_palette:
        rgb_out = _palette_lookup(
            tree, palette,
            _channel(tree, base.outputs["Color"], "Green", column=3, row=3),
            _lookup_coordinate(
                tree, colour[0],
                _channel(tree, ramp.outputs["Color"], "Green", column=1, row=3)
                if ramp is not None else None,
                falloff, column=2, row=3),
            column=4, row=3).outputs["Color"]
    else:
        rgb_out = tint.outputs["Color"]

    #   if ( greyscaleAlpha ) color.a = colorLookup(baseMap.a, C.a * falloff * alphaMult).a
    #
    # The half that was missing, and the campfire is mostly it: both flame
    # systems set this bit and neither sets the colour one, so their opacity
    # came straight off the base texture's alpha and the fire hardly burned.
    # The gradient's alpha channel is a curve over that value, and reading it is
    # the difference between a flame and a smudge.
    alpha_by_palette = (
        _bit(flags1, schema.SF1_GREYSCALE_TO_PALETTE_ALPHA)
        and palette is not None
        and alpha_source is not None
    )

    if alpha_by_palette:
        alpha_out = _palette_lookup(
            tree, palette, alpha_source,
            _lookup_coordinate(
                tree, colour[3] * colour[3],
                ramp.outputs["Alpha"] if ramp is not None else None,
                falloff, column=2, row=5),
            column=4, row=5).outputs["Alpha"]

    if modifier is not None:
        if not by_palette:
            over_life = tree.add("ShaderNodeMixRGB", column=5, row=4, blend_type="MULTIPLY")
            over_life.inputs["Fac"].default_value = 1.0
            tree.link(rgb_out, over_life, "Color1")
            tree.link(ramp.outputs["Color"], over_life, "Color2")
            rgb_out = over_life.outputs["Color"]

        if not alpha_by_palette:
            dimmed = tree.add("ShaderNodeMath", column=5, row=5, operation="MULTIPLY")
            tree.link(alpha_out, dimmed, 0)
            tree.link(ramp.outputs["Alpha"], dimmed, 1)
            alpha_out = dimmed.outputs[0]

        # Only when the colours do not already fade. Their alphas usually carry
        # it -- the campfire's run 0 -> 1 -> 0 -- and multiplying the fade
        # percentages on top of that squares it: every particle spent most of
        # its life invisible and the fire went out.
        already = [
            (_numbers(_get(modifier, name, "")) + [1.0, 1.0, 1.0, 1.0])[3]
            for name in schema.COLORS
        ]

        ends = (
            None
            if max(already) - min(already) > 0.05
            else _fade(tree, fraction, modifier, column=3, row=6)
        )

        if ends is not None:
            faded = tree.add("ShaderNodeMath", column=4, row=6, operation="MULTIPLY")
            tree.link(alpha_out, faded, 0)
            tree.link(ends.outputs[0], faded, 1)
            alpha_out = faded.outputs[0]

        report.notes.append(
            f"{material.name}: fades in and out over a particle's life, as its "
            "colour modifier says"
        )

    output = tree.add("ShaderNodeOutputMaterial", column=7)
    transparent = tree.add("ShaderNodeBsdfTransparent", column=5, row=2)

    # How the engine composites it. Nearly every effect in the game is
    # SRC_ALPHA/ONE, which is `dst + src.rgb * src.a`: the background passes
    # through untouched and the effect is *added* on top. That is why fire in
    # Skyrim is bright -- overlapping flames accumulate.
    additive = (
        _get(material, schema.SOURCE_BLEND, "") == schema.BLEND_SRC_ALPHA
        and _get(material, schema.DESTINATION_BLEND, "") == schema.BLEND_ONE
    )

    if additive:
        # An Add Shader is the one node that reproduces it. Mixing a Transparent
        # BSDF with an Emission -- the usual advice, and what this did -- is not
        # additive: the mix factor scales the emission *and* darkens the
        # background by its complement, so the result lands between the two
        # layers instead of above them. Over a grey backdrop, measured:
        # mix 0.682, add 0.929, either layer alone below both.
        #
        # Add takes the transmittance from the Transparent BSDF, so the
        # background is untouched, and the radiance from the Emission. The alpha
        # then belongs on the emission, exactly as `src.rgb * src.a` says.
        scaled = tree.add("ShaderNodeMixRGB", column=4, row=1, blend_type="MULTIPLY")
        scaled.inputs["Fac"].default_value = 1.0
        tree.link(rgb_out, scaled, "Color1")
        tree.link(alpha_out, scaled, "Color2")

        emission = tree.add("ShaderNodeEmission", column=5, row=0)
        emission.inputs["Strength"].default_value = max(glow_mult, 0.0)
        tree.link(scaled.outputs["Color"], emission, "Color")

        combine = tree.add("ShaderNodeAddShader", column=6)
        tree.link(transparent.outputs[0], combine, 0)
        tree.link(emission.outputs[0], combine, 1)
        tree.link(combine.outputs[0], output, "Surface")
    else:
        emission = tree.add("ShaderNodeEmission", column=5, row=0)
        emission.inputs["Strength"].default_value = max(glow_mult, 0.0)
        tree.link(rgb_out, emission, "Color")

        combine = tree.add("ShaderNodeMixShader", column=6)
        tree.link(alpha_out, combine, "Fac")
        tree.link(transparent.outputs[0], combine, 1)
        tree.link(emission.outputs[0], combine, 2)
        tree.link(combine.outputs[0], output, "Surface")

    _apply_alpha_mode(material, blended=True)
    _mark(material, schema.EFFECT_SHADER)

    return True


def _falloff_nodes(tree, material, column, row):
    """``smoothstep(stopAngle, startAngle, abs(E.b))``, then mixed.

    ``abs(E.b)`` is the facing ratio -- the view direction's component along the
    surface normal -- which is what Blender's Layer Weight node calls Facing.
    """
    start_angle = _effect_float(material, schema.ES_FALLOFF_START_ANGLE, 1.0)
    stop_angle = _effect_float(material, schema.ES_FALLOFF_STOP_ANGLE, 1.0)
    start_opacity = _effect_float(material, schema.ES_FALLOFF_START_OPACITY, 1.0)
    stop_opacity = _effect_float(material, schema.ES_FALLOFF_STOP_OPACITY, 0.0)

    facing = tree.add("ShaderNodeLayerWeight", column=column, row=row)
    facing.inputs["Blend"].default_value = 0.5

    ramp = tree.add("ShaderNodeMapRange", column=column + 1, row=row)
    ramp.interpolation_type = "SMOOTHSTEP"
    ramp.clamp = True
    ramp.inputs["From Min"].default_value = stop_angle
    ramp.inputs["From Max"].default_value = start_angle
    ramp.inputs["To Min"].default_value = max(stop_opacity, 0.0)
    ramp.inputs["To Max"].default_value = min(start_opacity, 1.0)

    tree.link(facing.outputs["Facing"], ramp, "Value")

    return ramp.outputs["Result"]


def _channel(tree, colour, name, column, row):
    """One channel of a colour, as a socket."""
    separate = tree.add("ShaderNodeSeparateColor", column=column, row=row)
    tree.link(colour, separate, "Color")

    return separate.outputs[name]


def _lookup_coordinate(tree, value, *sockets, column, row):
    """``value`` times whichever of ``sockets`` exist, as a coordinate.

    The gradient's second coordinate is a product in the GLSL -- ``C.g * falloff
    * glowColor.r`` for the colour, ``C.a * falloff * glowColor.a^2`` for the
    alpha -- and which terms are there depends on the flags. A material with
    none of them wants a plain number and no nodes at all.
    """
    result = None

    for socket in sockets:
        if socket is None:
            continue

        if result is None:
            result = socket
            continue

        node = tree.add("ShaderNodeMath", column=column, row=row, operation="MULTIPLY")
        tree.link(result, node, 0)
        tree.link(socket, node, 1)
        result = node.outputs[0]

    if result is None:
        return value

    node = tree.add("ShaderNodeMath", column=column, row=row, operation="MULTIPLY")
    tree.link(result, node, 0)
    node.inputs[1].default_value = value

    return node.outputs[0]


def _palette_lookup(tree, image, x, y, column, row):
    """``colorLookup(x, y)``: the gradient read at a point.

    ``NiSkope``'s ``colorLookup`` clamps both coordinates, so the image is set to
    extend rather than repeat -- a gradient read past its end has to hold its
    last colour, not wrap round to its first.
    """
    coords = tree.add("ShaderNodeCombineXYZ", column=column, row=row)
    tree.link(x, coords, "X")

    # Upside down, because the two conventions disagree about which row is row
    # zero: the gradient is a DDS, stored top-down, and Blender addresses it
    # bottom-up. The file settles it rather than the convention -- at
    # `GradFireExplosion`'s Blender-V of 1 the alpha is 0.0 and at 0 it is 0.95,
    # and the shader reads a full-strength particle (C.a = 1) at y = 1. Read as
    # Blender numbers that would birth every particle invisible and leave it
    # opaque once dead; flipped it fades out as it ages, which is what a fire
    # does. It puts the colour right too -- straight through, the campfire came
    # out blue.
    if isinstance(y, (int, float)):
        coords.inputs["Y"].default_value = 1.0 - float(y)
    else:
        flip = tree.add("ShaderNodeMath", column=column, row=row + 1, operation="SUBTRACT")
        flip.inputs[0].default_value = 1.0
        tree.link(y, flip, 1)
        tree.link(flip.outputs[0], coords, "Y")

    palette = _texture(tree, image, column=column + 1, row=row)
    palette.extension = "EXTEND"
    tree.link(coords.outputs["Vector"], palette, "Vector")

    return palette


def build_lighting_material(material, report):
    """``BSLightingShaderProperty``, onto a Principled BSDF.

    Not a translation of ``sk_default.frag`` -- see this module's docstring for
    why one would be worse than useless -- but the same parameters meaning the
    same things to a renderer that lights things properly.
    """
    images = _existing_images(material)
    shading = _imported_shading(material)

    diffuse = (images.get("Base Color") or [None])[0]
    normal = (images.get("Color") or [None])[0]

    # Blender wires the normal map through a Normal Map node, so its image is
    # the one feeding that rather than the BSDF.
    for node in material.node_tree.nodes if material.use_nodes else []:
        if node.type == "NORMAL_MAP":
            for link in node.inputs["Color"].links:
                if link.from_node.type == "TEX_IMAGE":
                    normal = link.from_node.image

    flags1 = _flags(material, schema.SHADER_FLAGS_1)
    flags2 = _flags(material, schema.SHADER_FLAGS_2)
    kind = str(_get(material, schema.SHADER_TYPE, "") or "")

    emissive = list(shading.get("Emission Color", (0.0, 0.0, 0.0, 1.0)))[:3]
    emissive_strength = float(shading.get("Emission Strength", 0.0))
    roughness = float(shading.get("Roughness", 0.5))
    specular = float(shading.get("Specular IOR Level", 0.0))
    alpha_value = float(shading.get("Alpha", 1.0))

    # An emissive colour of black is the file saying there is no emission, which
    # is what all but a handful of shapes say. Multiplying it by a strength would
    # still be black, but leaving the strength at zero says so more plainly.
    emits = _bit(flags1, schema.SF1_OWN_EMIT) and max(emissive) > 0.0

    tree = _Tree(material)

    principled = tree.add("ShaderNodeBsdfPrincipled", column=4)
    output = tree.add("ShaderNodeOutputMaterial", column=6)
    tree.link(principled.outputs[0], output, "Surface")

    # A refraction shape is not a surface with a colour on it. The heat haze over
    # a campfire is one: `Plane05` has Refraction and Fire_Refraction set, and the
    # texture in its diffuse slot is a normal map, because what the engine does
    # with it is bend what is behind rather than draw it. Rendered as a colour it
    # is an opaque sheet of rainbow noise standing over the fire, which is what it
    # looked like -- and what NifSkope shows too, since sk_default.frag has no
    # refraction in it at all.
    #
    # Blender does have it, so this is one of the places the translation can be
    # better than the reference rather than worse.
    refracts = _bit(flags1, schema.SF1_REFRACTION) or _bit(flags1, schema.SF1_FIRE_REFRACTION)

    if refracts:
        report.refracting = True
        _build_refraction(tree, principled, output, material, report)
        _apply_alpha_mode(material, blended=True)
        _mark(material, schema.LIGHTING_SHADER)
        return True

    vertex_rgb, vertex_alpha = _vertex_colour(tree, material, column=0, row=4)

    if diffuse is not None:
        base = _texture(tree, diffuse, column=2, row=0)

        # albedo = baseMap.rgb * C.rgb, in sk_default.frag.
        if vertex_rgb is not None and _bit(flags2, schema.SF2_VERTEX_COLORS):
            shaded = tree.add("ShaderNodeMixRGB", column=3, row=0, blend_type="MULTIPLY")
            shaded.inputs["Fac"].default_value = 1.0
            tree.link(base.outputs["Color"], shaded, "Color1")
            tree.link(vertex_rgb, shaded, "Color2")
            tree.link(shaded.outputs["Color"], principled, "Base Color")
        else:
            tree.link(base.outputs["Color"], principled, "Base Color")

        if _bit(flags1, schema.SF1_VERTEX_ALPHA) or alpha_value < 1.0:
            if vertex_alpha is not None and _bit(flags1, schema.SF1_VERTEX_ALPHA):
                both = tree.add("ShaderNodeMath", column=3, row=1, operation="MULTIPLY")
                tree.link(base.outputs["Alpha"], both, 0)
                tree.link(vertex_alpha, both, 1)
                tree.link(both.outputs[0], principled, "Alpha")
            else:
                tree.link(base.outputs["Alpha"], principled, "Alpha")

    if normal is not None:
        # Skyrim's normal maps are tangent-space with the gloss in alpha, except
        # where the shader says model-space -- Blender has no model-space normal
        # node, so that one is reported rather than approximated.
        if _bit(flags1, schema.SF1_MODEL_SPACE_NORMALS):
            report.notes.append(
                f"{material.name}: model-space normals, which Blender's Normal Map "
                "node cannot read; the map is wired as tangent-space and will be wrong"
            )

        image = _texture(tree, normal, column=2, row=1, non_color=True)
        node = tree.add("ShaderNodeNormalMap", column=3, row=1)
        tree.link(image.outputs["Color"], node, "Color")
        tree.link(node.outputs["Normal"], principled, "Normal")

        # specular = specColor * specStrength * normalMap.a * pow(NdotH, gloss).
        # The alpha channel is the specular mask, and Blender's roughness is the
        # inverse of glossiness.
        if _bit(flags1, schema.SF1_SPECULAR):
            invert = tree.add("ShaderNodeInvert", column=3, row=2)
            tree.link(image.outputs["Alpha"], invert, "Color")
            tree.link(invert.outputs["Color"], principled, "Roughness")

    # The roughness the importer derived from the NIF's glossiness, used when
    # there is no specular map to take it from.
    if normal is None or not _bit(flags1, schema.SF1_SPECULAR):
        principled.inputs["Roughness"].default_value = min(max(roughness, 0.0), 1.0)

    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = min(max(specular, 0.0), 1.0)

    # emissive += glowColor * glowMult, times the glow map where there is one.
    if emits:
        glow = _image_named(_slot_path(material, schema.SLOT_GLOW))
        wants_map = _bit(flags2, schema.SF2_GLOW_MAP) and schema.ST_GLOW in kind

        if glow is not None and wants_map:
            node = _texture(tree, glow, column=2, row=3)
            tint = tree.add("ShaderNodeMixRGB", column=3, row=3, blend_type="MULTIPLY")
            tint.inputs["Fac"].default_value = 1.0
            tint.inputs["Color2"].default_value = (*emissive, 1.0)
            tree.link(node.outputs["Color"], tint, "Color1")
            tree.link(tint.outputs["Color"], principled, "Emission Color")
        else:
            principled.inputs["Emission Color"].default_value = (*emissive, 1.0)

        principled.inputs["Emission Strength"].default_value = max(emissive_strength, 0.0)
    else:
        principled.inputs["Emission Strength"].default_value = 0.0

    # The cubemap. Blender reflects the world, not a texture, so this is the
    # reflection strength rather than the image.
    has_cube = (
        _bit(flags1, schema.SF1_ENVIRONMENT_MAPPING) and schema.ST_ENVIRONMENT in kind
    ) or (_bit(flags1, schema.SF1_EYE_ENVIRONMENT_MAPPING) and schema.ST_EYE_ENVMAP in kind)

    if has_cube:
        strength = _float(material, schema.ENVIRONMENT_MAP_SCALE, 0.0)

        if "Metallic" in principled.inputs:
            principled.inputs["Metallic"].default_value = min(max(strength, 0.0), 1.0)

        report.notes.append(
            f"{material.name}: reflects a cubemap ({_slot_path(material, schema.SLOT_ENVIRONMENT)}) "
            "which Blender replaces with the scene's own reflections; its strength is "
            "carried as metallic"
        )

    if _bit(flags2, schema.SF2_DOUBLE_SIDED):
        material.use_backface_culling = False
    else:
        material.use_backface_culling = True

    for bit, name in (
        (schema.SF2_RIM_LIGHTING, "rim lighting"),
        (schema.SF2_SOFT_LIGHTING, "soft lighting"),
        (schema.SF2_BACK_LIGHTING, "back lighting"),
    ):
        if _bit(flags2, bit):
            report.notes.append(
                f"{material.name}: uses {name}, which is a term of the game's own "
                "lighting model with no Principled equivalent; it is not rebuilt"
            )

    _apply_alpha_mode(material, blended=alpha_value < 1.0 or _get(material, schema.ALPHA_BLEND, False))
    _mark(material, schema.LIGHTING_SHADER)

    return True


def _apply_alpha_mode(material, blended):
    """How Blender is told to composite it.

    Blender 4.2 replaced the old blend_method enum on Eevee Next; both spellings
    are tried because an add-on that assumes one will not load on the other.
    """
    threshold = _float(material, schema.ALPHA_TEST_THRESHOLD, 0.0)

    if _get(material, schema.ALPHA_TEST, False):
        mode, clip = "CLIP", "CLIP"
        material.alpha_threshold = min(max(threshold / 255.0, 0.0), 1.0)
    elif blended:
        mode, clip = "BLEND", "HASHED"
    else:
        mode, clip = "OPAQUE", "OPAQUE"

    for name, value in (("surface_render_method", "BLENDED" if mode != "OPAQUE" else "DITHERED"),):
        if hasattr(material, name):
            try:
                setattr(material, name, value)
            except (TypeError, ValueError):
                pass

    if hasattr(material, "blend_method"):
        try:
            material.blend_method = mode
        except (TypeError, ValueError):
            material.blend_method = clip

    # Every layer, not just the nearest one. Eevee can be told to keep only the
    # closest transparent surface per pixel, and the imported materials arrive
    # with that switch off: a smoke quad then punched a hard-edged rectangle
    # through every quad behind it, which is what the plume's square holes were.
    # A fire is a stack of transparent quads and all of them have to draw.
    #
    # Two spellings for one flag -- Eevee Next renamed it -- so whichever the
    # build has is set.
    if mode != "OPAQUE":
        for name in ("use_transparency_overlap", "show_transparent_back"):
            if hasattr(material, name):
                try:
                    setattr(material, name, True)
                except (TypeError, ValueError):
                    pass


def _mark(material, kind):
    material[schema.GENERATED] = 1
    material[schema.DCC_GENERATED] = 1
    material[schema.SOURCE] = kind


# --- the whole scene --------------------------------------------------------


def build(scene):
    """Rebuild every Skyrim material in the file.

    Every material, not only the ones on an object. A particle system's material
    arrives with no users at all: NIFBX hangs it off a Model with no geometry,
    Blender reads such a Model as an Empty, and an Empty has no material slot --
    so the datablock is imported and then belongs to nothing. Those are the
    effect shaders, which is to say the flames and the glows, so skipping them
    would skip the half of a file this is most worth doing.
    """
    report = Report()

    for material in list(bpy.data.materials):
        if not is_skyrim_material(material):
            continue

        try:
            if is_effect_shader(material):
                build_effect_material(material, report)
            else:
                build_lighting_material(material, report)
        except Exception as error:                          # noqa: BLE001
            report.skipped.append(f"{material.name}: {error}")
            continue

        report.materials.append(material.name)

    report.attached = attach_to_particles(scene, report)

    return report


def attach_to_particles(scene, report=None):
    """Give an effect material to the sprite its particles are drawn with.

    The particle add-on builds a geometry-nodes simulation and a quad for it to
    instance, and leaves the quad unshaded -- it has nothing to shade it with.
    This material is the one the engine draws those particles with, so putting
    it on the quad is what makes the system look like the effect rather than
    like a cloud of grey squares.

    Matched on the system's own name, which is the node's, and both the material
    and the sprite are named after it. Neither add-on reads the other's
    properties, so the two stay independent.

    Public, and safe to call twice: the sprites do not exist until the particles
    have been built, so the order is materials, particles, then this.
    """
    report = Report() if report is None else report
    attached = 0
    suffix = "_sprite"

    for obj in scene.objects:
        if obj.type != "MESH" or not obj.name.endswith(suffix):
            continue

        system = obj.name[: -len(suffix)]
        material = bpy.data.materials.get(f"{system}_material")

        if material is None or not material.get(schema.GENERATED):
            continue

        if any(slot.material is material for slot in obj.material_slots):
            continue

        obj.data.materials.clear()
        obj.data.materials.append(material)

        # The quad keeps its own 0..1 UVs: which frame of the sheet a particle
        # wears is decided in the shader from its age, because every instance
        # shares this one mesh and they must not all wear the same one.
        attached += 1
        report.notes.append(
            f"{material.name}: given to the quad its particles are drawn with"
        )

    return attached



def clear(scene):
    """Put the materials back to a plain Principled BSDF, and take the sprites."""
    cleared = 0

    for obj in [o for o in bpy.data.objects if o.get(schema.GENERATED)]:
        bpy.data.objects.remove(obj, do_unlink=True)

    for material in bpy.data.materials:
        if not material.get(schema.GENERATED):
            continue

        material.use_nodes = True
        material.node_tree.nodes.clear()

        principled = material.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        output = material.node_tree.nodes.new("ShaderNodeOutputMaterial")
        output.location = (300, 0)
        material.node_tree.links.new(principled.outputs[0], output.inputs["Surface"])

        del material[schema.GENERATED]

        if schema.SOURCE in material.keys():
            del material[schema.SOURCE]

        cleared += 1

    return cleared




def _build_refraction(tree, principled, output, material, report):
    """A shape that bends what is behind it rather than colouring it.

    Built as a plain Transparent BSDF, which is the one thing in Blender that is
    unambiguously not there. A Principled with transmission and no alpha is not:
    Eevee treats the two as separate ideas and draws such a surface as a dim
    grey sheet, which over a campfire is a rectangle of haze hanging above the
    flames.

    The shape is still carried -- it is in the file and it round trips -- and
    still says what it is, so raising its Alpha or wiring the distortion map into
    a transmissive shader is a change a person can make. What it does not do is
    guess, because the engine draws these in a refraction pass Blender has no
    equivalent of, and both of the honest approximations look worse than nothing.
    """
    tree.tree.nodes.remove(principled)

    invisible = tree.add("ShaderNodeBsdfTransparent", column=4)
    tree.link(invisible.outputs[0], output, "Surface")

    material.use_backface_culling = False

    report.notes.append(
        f"{material.name}: refracts. The texture in its diffuse slot is a "
        "distortion map rather than a colour, and the engine draws the shape in a "
        "refraction pass Blender has no equivalent of -- drawn as colour it is a "
        "sheet of rainbow noise standing in the fire, and as transmission a grey "
        "haze hanging over it. It is carried and not drawn"
    )



def _system_node_for(material):
    """The particle system's node, from the material named after it.

    NIFBX names a material for the shape it dresses, so a particle system's is
    `<system>_material`. The modifiers hang under the node as child objects.
    """
    name = material.name
    suffix = "_material"

    if name.endswith(suffix):
        name = name[: -len(suffix)]

    return bpy.data.objects.get(name)


def _colour_modifier(material):
    """The BSPSysSimpleColorModifier under this material's system, or None."""
    node = _system_node_for(material)

    if node is None:
        return None

    for child in node.children:
        if child.get("particle_modifier") == schema.COLOR_MODIFIER:
            return child

    return None


def _life_ramp(tree, modifier, column, row):
    """The colour and alpha a particle wears over its life, as nodes.

    The engine walks a particle through three colours as it ages, and their
    alphas are what make it appear and go away -- the campfire's flames run
    0 -> 1 -> 0. Nothing read them, so every particle was born and died at full
    opacity, which is the popping.

    Blender's Particle Info node gives Age and Lifetime, so the fraction of a
    life elapsed is a division, and the rest is a colour ramp on it.
    """
    # Read off the instance rather than from the Particle Info node. The
    # simulation stores how far through its life each particle is as a named
    # attribute on the instance domain, and an Attribute node of type INSTANCER
    # is what reaches it -- measured working in Eevee, where Particle Info is
    # not implemented at all and renders nothing.
    fraction = tree.add("ShaderNodeAttribute", column=column + 1, row=row)
    fraction.attribute_type = "INSTANCER"
    fraction.attribute_name = schema.PARTICLE_AGE

    ramp = tree.add("ShaderNodeValToRGB", column=column + 2, row=row)
    tree.link(fraction.outputs["Fac"], ramp, "Fac")

    colours = [_numbers(_get(modifier, name, "")) for name in schema.COLORS]
    colours = [(c + [1.0, 1.0, 1.0, 1.0])[:4] for c in colours]

    bounds = sorted(
        _as_float(_get(modifier, name, 0.0), 0.0) for name in schema.COLOR_BOUNDS
    )

    # Three stops: birth, the end of the first band, the start of the last.
    positions = [0.0, bounds[1] if len(bounds) > 1 else 0.5,
                 bounds[3] if len(bounds) > 3 else 0.8]

    elements = ramp.color_ramp.elements

    while len(elements) > 1:
        elements.remove(elements[-1])

    for i, (position, colour) in enumerate(zip(positions, colours)):
        element = elements[0] if i == 0 else elements.new(min(max(position, 0.0), 1.0))
        element.position = min(max(position, 0.0), 1.0)
        element.color = colour

    return ramp, fraction


def _fade(tree, fraction, modifier, column, row):
    """The extra fade at each end, on top of the colours' own alphas."""
    fade_in = _as_float(_get(modifier, schema.FADE_IN, 0.0), 0.0)
    fade_out = _as_float(_get(modifier, schema.FADE_OUT, 0.0), 0.0)

    if fade_in <= 0.0 and fade_out <= 0.0:
        return None

    rising = tree.add("ShaderNodeMapRange", column=column, row=row)
    rising.clamp = True
    rising.inputs["From Min"].default_value = 0.0
    rising.inputs["From Max"].default_value = max(fade_in, 1e-4)
    tree.link(fraction.outputs["Fac"], rising, "Value")

    falling = tree.add("ShaderNodeMapRange", column=column, row=row + 1)
    falling.clamp = True
    falling.inputs["From Min"].default_value = 1.0
    falling.inputs["From Max"].default_value = max(1.0 - fade_out, 0.0)
    tree.link(fraction.outputs["Fac"], falling, "Value")

    both = tree.add("ShaderNodeMath", column=column + 1, row=row, operation="MULTIPLY")
    tree.link(rising.outputs["Result"], both, 0)
    tree.link(falling.outputs["Result"], both, 1)

    return both

def _vertex_colour(tree, material, column, row):
    """The mesh's own colour, which the shader multiplies everything by.

    ``C`` in NifSkope's fragment shaders, and not decoration: the campfire's
    glow plane carries a warm orange (0.60, 0.28, 0.08) with an alpha running
    0.00 to 0.80 across its corners. That alpha is what shapes the glow and
    fades its edges to nothing, so a material that ignores it draws a
    full-strength white quad that washes out whatever is behind it -- which is
    what it did.

    Returns ``(colour, alpha)`` sockets, or ``(None, None)`` when the shader
    does not ask for it.
    """
    layer = _colour_layer(material)

    if layer is None:
        return None, None

    node = tree.add("ShaderNodeVertexColor", column=column, row=row)
    node.layer_name = layer

    return node.outputs["Color"], node.outputs["Alpha"]


def _colour_layer(material):
    """The name of the colour attribute the meshes wearing this material have."""
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.color_attributes:
            continue

        if any(slot.material is material for slot in obj.material_slots):
            return obj.data.color_attributes[0].name

    return None

def _subtexture_sheet(material):
    """The animation sheet the system steps through, or None.

    ``NiPSysData`` lists one cell per frame as (offset u, width, offset v,
    height). They are a regular grid in every effect the game ships, so the cell
    size gives the grid and the count gives the frames.
    """
    node = _system_node_for(material)

    if node is None:
        return None

    try:
        count = int(float(node.get("npsd_num_subtexture_offsets", 0) or 0))
    except (TypeError, ValueError):
        return None

    if count <= 1:
        return None

    numbers = _numbers(node.get("npsd_subtexture_offsets_0", ""))

    if len(numbers) < 4:
        return None

    width, height = numbers[1], numbers[3]

    if width <= 0.0 or height <= 0.0:
        return None

    return count, width, height


def _atlas_mapping(tree, material, sheet, column, row):
    """UVs that walk the sheet as a particle ages.

    The engine steps a particle through the frames over its life with a
    ``BSPSysSubTexModifier``. Every instance shares one mesh, so the walk cannot
    be in the UVs -- it has to be in the shader, off the age the simulation
    publishes per instance. Without it every particle wears frame zero and a
    hundred of them read as one shape repeated rather than as smoke.
    """
    count, width, height = sheet
    columns = max(int(round(1.0 / width)), 1)

    age = tree.add("ShaderNodeAttribute", column=column, row=row)
    age.attribute_type = "INSTANCER"
    age.attribute_name = schema.PARTICLE_AGE

    # frame = min(floor(age * count), count - 1)
    scaled = tree.add("ShaderNodeMath", column=column + 1, row=row, operation="MULTIPLY")
    scaled.inputs[1].default_value = float(count)
    tree.link(age.outputs["Fac"], scaled, 0)

    whole = tree.add("ShaderNodeMath", column=column + 2, row=row, operation="FLOOR")
    tree.link(scaled.outputs[0], whole, 0)

    frame = tree.add("ShaderNodeMath", column=column + 3, row=row, operation="MINIMUM")
    frame.inputs[1].default_value = float(count - 1)
    tree.link(whole.outputs[0], frame, 0)

    across = tree.add("ShaderNodeMath", column=column + 4, row=row, operation="MODULO")
    across.inputs[1].default_value = float(columns)
    tree.link(frame.outputs[0], across, 0)

    down = tree.add("ShaderNodeMath", column=column + 4, row=row + 1, operation="DIVIDE")
    down.inputs[1].default_value = float(columns)
    tree.link(frame.outputs[0], down, 0)

    down_whole = tree.add("ShaderNodeMath", column=column + 5, row=row + 1, operation="FLOOR")
    tree.link(down.outputs[0], down_whole, 0)

    left = tree.add("ShaderNodeMath", column=column + 5, row=row, operation="MULTIPLY")
    left.inputs[1].default_value = width
    tree.link(across.outputs[0], left, 0)

    # Blender's V runs the other way from the sheet's, so a row counts down from
    # the top rather than up from the bottom.
    stride = tree.add("ShaderNodeMath", column=column + 6, row=row + 1, operation="MULTIPLY")
    stride.inputs[1].default_value = height
    tree.link(down_whole.outputs[0], stride, 0)

    top = tree.add("ShaderNodeMath", column=column + 7, row=row + 1, operation="SUBTRACT")
    top.inputs[0].default_value = 1.0 - height
    tree.link(stride.outputs[0], top, 1)

    place = tree.add("ShaderNodeCombineXYZ", column=column + 8, row=row)
    tree.link(left.outputs[0], place, "X")
    tree.link(top.outputs[0], place, "Y")

    coords = tree.add("ShaderNodeTexCoord", column=column, row=row + 2)
    mapping = tree.add("ShaderNodeMapping", column=column + 9, row=row)
    mapping.inputs["Scale"].default_value = (width, height, 1.0)
    tree.link(coords.outputs["UV"], mapping, "Vector")
    tree.link(place.outputs["Vector"], mapping, "Location")

    return mapping
