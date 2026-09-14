"""Rebuild the materials of a converted mesh, inside Blender.

    blender --background --python tests/run_materials_in_blender.py -- some.fbx

Imports the FBX, runs the add-on, and checks the node tree against the
properties it was built from. The point is not that nodes appeared: it is that
the numbers on them are the numbers in the file, and that the shapes NifSkope's
own GLSL describes are the shapes that got built.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_materials import build, schema  # noqa: E402

failures = []


def check(name, got, want, tolerance=1e-4):
    if isinstance(want, float) and isinstance(got, (int, float)):
        ok = abs(got - want) <= tolerance
    else:
        ok = got == want

    print(f"{'PASS' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" != {want!r}"))

    if not ok:
        failures.append(name)


def nodes_of(material, kind):
    return [n for n in material.node_tree.nodes if n.type == kind]


def main():
    path = sys.argv[sys.argv.index("--") + 1]

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_custom_props=True, automatic_bone_orientation=True)

    scene = bpy.context.scene
    skyrim = [m for m in bpy.data.materials if build.is_skyrim_material(m)]

    print(f"     {len(bpy.data.materials)} material(s), {len(skyrim)} carrying NIF properties")

    if not skyrim:
        print("FAIL: nothing to rebuild")
        failures.append("any material")
        return

    # What they were before, so the rebuild can be shown to have changed them.
    before = {m.name: len(m.node_tree.nodes) if m.use_nodes else 0 for m in skyrim}

    report = build.build(scene)
    print(f"     {report}")

    for line in report.notes:
        print(f"     note: {line}")

    for line in report.skipped:
        print(f"     skipped: {line}")

    check("materials built", len(report.materials) > 0, True)

    # Nothing may fail to build. Without this the suite skips whatever it could
    # not make -- the per-material checks below all start by passing over a name
    # that is not in the report -- so three materials dying on a NameError left
    # every check green and the effect grey.
    check("none skipped", report.skipped, [])

    effects = 0

    for material in skyrim:
        if material.name not in report.materials:
            continue

        check(f"{material.name} marked", bool(material.get(schema.GENERATED)), True)

        if not build.is_effect_shader(material):
            flags1 = build._flags(material, schema.SHADER_FLAGS_1)
            refracts = (flags1 & (1 << schema.SF1_REFRACTION)) or \
                (flags1 & (1 << schema.SF1_FIRE_REFRACTION))

            if refracts:
                # A refraction shape is carried and not drawn: the engine draws
                # it in a pass Blender has no equivalent of, and both honest
                # approximations look worse than nothing -- rainbow noise as
                # colour, a grey haze as transmission.
                check(f"{material.name} is not drawn",
                      len(nodes_of(material, "BSDF_TRANSPARENT")), 1)
                check(f"{material.name} has no principled",
                      len(nodes_of(material, "BSDF_PRINCIPLED")), 0)
            else:
                # A lighting shader goes to a Principled BSDF, which is the whole
                # claim: it is not NifSkope's shader and does not pretend to be.
                check(f"{material.name} principled",
                      len(nodes_of(material, "BSDF_PRINCIPLED")), 1)

            continue

        effects += 1

        # An effect shader is rebuilt faithfully, so the emission strength is
        # glowMult -- `out.rgb = color.rgb * glowMult` in sk_effectshader.frag.
        emission = nodes_of(material, "EMISSION")
        check(f"{material.name} emission", len(emission), 1)

        if emission:
            want = float(material.get(schema.EFFECT_PREFIX + schema.ES_BASE_COLOR_SCALE, 1.0))
            check(
                f"{material.name} glowMult",
                emission[0].inputs["Strength"].default_value,
                want,
            )

        # color.rgb *= glowColor.rgb
        mixes = [n for n in nodes_of(material, "MIX_RGB") if n.blend_type == "MULTIPLY"]
        check(f"{material.name} tinted by base colour", len(mixes) >= 1, True)

        if mixes:
            raw = str(material.get(schema.EFFECT_PREFIX + schema.ES_BASE_COLOR, "1 1 1 1"))
            want = [float(x) for x in raw.replace(",", " ").split()][:3]
            got = list(mixes[0].inputs["Color2"].default_value)[:3]

            for i, axis in enumerate("rgb"):
                check(f"{material.name} glowColor.{axis}", got[i], want[i])

        # color.a *= glowColor.a^2 -- the square is in the GLSL, not a mistake.
        #
        # Found by what feeds it rather than by being the first multiply in the
        # tree: the atlas walk adds several of its own, and picking by position
        # made this assert a frame count against an alpha.
        maths = [
            n for n in nodes_of(material, "MATH")
            if n.operation == "MULTIPLY"
            and n.inputs[0].links
            and n.inputs[0].links[0].from_node.type == "TEX_IMAGE"
            and n.inputs[0].links[0].from_socket.name == "Alpha"
        ]

        check(f"{material.name} alpha multiplied", len(maths) >= 1, True)

        if maths:
            raw = str(material.get(schema.EFFECT_PREFIX + schema.ES_BASE_COLOR, "1 1 1 1"))
            parts = [float(x) for x in raw.replace(",", " ").split()]
            alpha = parts[3] if len(parts) > 3 else 1.0
            check(f"{material.name} alphaMult is the square", maths[0].inputs[1].default_value,
                  alpha * alpha)

        # The falloff, when the shader says to use one: a view-angle ramp.
        flags1 = build._flags(material, schema.ES_SHADER_FLAGS_1, effect=True)

        if flags1 & (1 << schema.SF1_USE_FALLOFF):
            ramps = nodes_of(material, "MAP_RANGE")
            check(f"{material.name} has a falloff ramp", len(ramps), 1)

            if ramps:
                check(f"{material.name} falloff is a smoothstep",
                      ramps[0].interpolation_type, "SMOOTHSTEP")
                check(f"{material.name} falloff reads the view angle",
                      len(nodes_of(material, "LAYER_WEIGHT")), 1)

                want_min = float(material.get(
                    schema.EFFECT_PREFIX + schema.ES_FALLOFF_STOP_OPACITY, 0.0))
                check(f"{material.name} falloff stop opacity",
                      ramps[0].inputs["To Min"].default_value, max(want_min, 0.0))

        # Additive is an Add Shader, not a Mix. A Mix of Transparent and
        # Emission darkens the background by the complement of its factor, so it
        # lands between the layers where the engine puts the result above them.
        src = material.get(schema.SOURCE_BLEND, "")
        dst = material.get(schema.DESTINATION_BLEND, "")

        if src == schema.BLEND_SRC_ALPHA and dst == schema.BLEND_ONE:
            check(f"{material.name} adds rather than mixes",
                  len(nodes_of(material, "ADD_SHADER")), 1)
            check(f"{material.name} does not mix", len(nodes_of(material, "MIX_SHADER")), 0)

            # src.rgb * src.a: the alpha scales the emission rather than the mix.
            emit = nodes_of(material, "EMISSION")
            check(f"{material.name} emission colour is driven",
                  bool(emit and emit[0].inputs["Color"].links), True)
        else:
            check(f"{material.name} mixes against transparency",
                  len(nodes_of(material, "MIX_SHADER")), 1)

        # The two greyscale-to-palette bits, which are not a tint but a
        # replacement: the shader throws away the colour it built and reads a
        # gradient instead. Both flame systems in the campfire set the alpha bit
        # and neither sets the colour one, so taking opacity straight off the
        # base texture is what made the fire a smudge.
        grey = str(material.get(
            schema.EFFECT_PREFIX + schema.ES_GREYSCALE_TEXTURE, "") or "")

        if grey:
            gradient = build._image_named(grey)

            if gradient is not None:
                lookups = [
                    n for n in nodes_of(material, "TEX_IMAGE")
                    if n.image is gradient and n.inputs["Vector"].links
                ]

                # Read at a point, not across the quad: a gradient wired to the
                # UVs is a texture, and this one is a lookup table.
                if flags1 & (1 << schema.SF1_GREYSCALE_TO_PALETTE_COLOR):
                    check(f"{material.name} colour comes from the gradient",
                          any(n.outputs["Color"].links for n in lookups), True)

                if flags1 & (1 << schema.SF1_GREYSCALE_TO_PALETTE_ALPHA):
                    check(f"{material.name} alpha comes from the gradient",
                          any(n.outputs["Alpha"].links for n in lookups), True)

                    # Its own alpha channel, at the base texture's alpha -- the
                    # colour lookup reads the green channel at a different
                    # coordinate, so one lookup cannot serve both.
                    reading = [
                        n for n in lookups if n.outputs["Alpha"].links
                        and n.inputs["Vector"].links[0].from_node.type == "COMBXYZ"
                    ]
                    check(f"{material.name} alpha lookup is a point", bool(reading), True)

                    if reading:
                        x = reading[0].inputs["Vector"].links[0].from_node.inputs["X"]
                        check(f"{material.name} alpha lookup reads the base alpha",
                              bool(x.links)
                              and x.links[0].from_socket.name == "Alpha", True)

                # Clamped, as `colorLookup` clamps: a gradient that repeats
                # wraps its last colour round to its first.
                for node in lookups:
                    check(f"{material.name} gradient is clamped", node.extension, "EXTEND")

        # The mesh's own colour, which the shader multiplies everything by. The
        # campfire's glow plane carries a warm orange with an alpha running 0 to
        # 0.8 across its corners, and that alpha is what fades the glow out --
        # ignoring it drew a full-strength white quad over the ground.
        flags2 = build._flags(material, schema.ES_SHADER_FLAGS_2, effect=True)
        layer = build._colour_layer(material)

        if layer is not None and flags2 & (1 << schema.SF2_VERTEX_COLORS):
            check(f"{material.name} reads the vertex colour",
                  len(nodes_of(material, "VERTEX_COLOR")), 1)

            vertex = nodes_of(material, "VERTEX_COLOR")[0]
            check(f"{material.name} vertex colour is used",
                  bool(vertex.outputs["Color"].links), True)

            if flags1 & (1 << schema.SF1_VERTEX_ALPHA):
                check(f"{material.name} vertex alpha is used",
                      bool(vertex.outputs["Alpha"].links), True)

        # All the layers, not just the nearest: with Eevee's transparency
        # overlap off, one smoke quad hides every quad behind it across its
        # whole rectangle, and a plume comes out full of square holes.
        for name in ("use_transparency_overlap", "show_transparent_back"):
            if hasattr(material, name):
                check(f"{material.name} overlapping layers all draw",
                      getattr(material, name), True)

        # And that it actually reaches the output rather than dangling.
        output = nodes_of(material, "OUTPUT_MATERIAL")
        check(f"{material.name} output is connected", bool(output and output[0].inputs["Surface"].links), True)

    check("some effect shaders were rebuilt", effects > 0, True)

    # The rebuild has to have done something: an unchanged tree would pass every
    # check above if Blender's importer happened to build the same shapes.
    changed = sum(
        1 for m in skyrim
        if m.name in report.materials and len(m.node_tree.nodes) != before[m.name]
    )
    check("the trees changed", changed > 0, True)

    # And taking it away leaves plain materials behind.
    cleared = build.clear(scene)
    check("cleared", cleared > 0, True)

    for material in skyrim:
        if material.name in report.materials:
            check(f"{material.name} reset", len(material.node_tree.nodes), 2)
            break


main()

print(f"\n{len(failures)} checks failed")

if failures:
    print("FAILED: " + ", ".join(failures))

sys.exit(len(failures))
