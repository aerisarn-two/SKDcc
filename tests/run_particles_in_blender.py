"""Build particle systems from a converted effect, inside Blender.

    blender --background --python tests/run_particles_in_blender.py -- some.fbx

Imports the FBX, runs the add-on, and checks that what came out says what the
properties said. The point is not that it runs: it is that the numbers in the
simulation are the numbers in the file, converted where units differ and carried
where they do not, and that the thing actually simulates.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_particles import build, schema, simulation  # noqa: E402

failures = []


def check(name, got, want, tolerance=1e-3):
    ok = abs(got - want) <= tolerance if isinstance(want, float) else got == want

    print(f"{'PASS' if ok else 'FAIL'} {name}: {got!r}" + ("" if ok else f" != {want!r}"))

    if not ok:
        failures.append(name)


def main():
    path = sys.argv[sys.argv.index("--") + 1]

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path, use_custom_props=True, automatic_bone_orientation=True)

    scene = bpy.context.scene
    systems = [o for o in scene.objects if build.is_system(o)]

    print(f"     {len(systems)} particle node(s) in {os.path.basename(path)}")

    if not systems:
        print("FAIL: the scene carries no particle system")
        failures.append("any system")
        return

    report = build.build(scene)

    # So every matrix read below is where things actually are.
    bpy.context.view_layer.update()

    print(f"     {report}")

    for line in report.notes:
        print(f"     note: {line}")

    for line in report.skipped:
        print(f"     skipped: {line}")

    check("systems built", len(report.systems) > 0, True)

    # Nothing may fail to build: the per-system checks below pass over a name
    # that is not in the report, so a system that died would leave them green.
    check("none skipped", report.skipped, [])

    fps = scene.render.fps / max(scene.render.fps_base, 1e-6)

    for node in systems:
        emitter = build.emitter_of(node)

        if emitter is None or node.name not in report.systems:
            continue

        host = bpy.data.objects.get(f"{node.name}_particles")
        check(f"{node.name} has a simulation", host is not None, True)

        if host is None:
            continue

        group = host.modifiers[0].node_group
        check(f"{node.name} group", group is not None, True)

        # Lengths are in the file's units and the scene is in Blender's, so the
        # frame's own world scale is what converts them. Taken straight off the
        # matrix here rather than from the add-on, so the two have to agree
        # rather than agreeing with themselves.
        scale = node.matrix_world.to_scale()
        units = (abs(scale[0]) + abs(scale[1]) + abs(scale[2])) / 3.0

        settings = build._simulation_settings(node, emitter, scene, report, units)

        life = float(emitter.get(schema.LIFE_SPAN, 1.0))
        check(f"{node.name} life", settings["life"], max(life, 1e-3))

        # The speed goes in as the file states it, because the simulation runs
        # inside the emitter's own frame and that frame carries the file-to-scene
        # scale. Converting first applied it twice, which put every particle
        # within a hundredth of the origin travelling a hundredth of its speed.
        speed = float(emitter.get(schema.SPEED, 0.0))
        check(f"{node.name} speed", round(settings["speed"], 5), round(speed, 5))

        # So the conversion still has to happen, and this is where: the host the
        # simulation runs on carries the same scale the node does. A speed of 54
        # game units a second through a scale of 0.012 is 0.65 metres a second,
        # and a host at scale one would be a hundred times too fast.
        if speed > 0:
            host_scale = host.matrix_world.to_scale()
            average = (abs(host_scale[0]) + abs(host_scale[1]) + abs(host_scale[2])) / 3.0

            check(f"{node.name} host carries the units", round(average, 5), round(units, 5))
            check(f"{node.name} units are not one", average < 0.5, True)

        # The emission window, which used to be the whole scene: a campfire that
        # emits for 3.3 seconds ran for 250 frames.
        emission = build.emission_of(node)

        if emission is not None:
            start, stop, rate = emission

            check(f"{node.name} emission starts",
                  settings["start_frame"], scene.frame_start + int(round(start * fps)))

            turn = scene.frame_start + int(round(stop * fps)) if stop else None
            loops = build.cycle_of(node) in ("LOOP", "REVERSE")

            if stop is not None and stop > start and not loops:
                check(f"{node.name} emission ends", settings["end_frame"], turn)
                check(f"{node.name} window is not the scene",
                      settings["end_frame"] < scene.frame_end, True)

            if loops and turn is not None and turn < scene.frame_end:
                # It emits for its span, goes back and does it again. Reading
                # the span as a one-shot put the campfire out at frame 101 of
                # 250 and its last ember died at 161.
                check(f"{node.name} keeps emitting", settings["end_frame"], scene.frame_end)
                check(f"{node.name} one turn is the span",
                      settings["cycle"], turn - settings["start_frame"])

            if rate > 0:
                # The rate the simulation actually emits at, not the per-frame
                # count: an emitter slower than the frame rate spawns one every
                # few frames, and rounding that up to one per frame emitted
                # three times too many for the campfire's embers.
                effective = settings["per_frame"] * fps / max(settings["period"], 1)

                check(f"{node.name} emits at the file's rate",
                      round(effective / rate, 1), 1.0)

        # A rate that lives in the clip rather than on the node. NIFBX mirrors it
        # onto the node because Blender keeps none of an animation stack's user
        # properties, and without it the waterwheel emitted one particle a frame
        # -- 24 a second against the 90 its file asks for.
        clip_rate = build.sequenced_rate(node)

        if emission is None and clip_rate is not None:
            effective = settings["per_frame"] * fps / max(settings["period"], 1)

            check(f"{node.name} births at the clip's rate",
                  round(effective / clip_rate, 1), 1.0)

        # A system with no gravity modifier must not fall: Blender applies scene
        # gravity to everything and Skyrim does not.
        kinds = {m.get(schema.MODIFIER, "") for m in build.modifiers_of(node)}

        if schema.GRAVITY not in kinds:
            check(f"{node.name} no gravity", settings["gravity"], (0.0, 0.0, 0.0))

        # A NiPSysMeshEmitter births from the surface of a mesh the file names,
        # not from a volume. The lumbermill's waterwheel emits from a strip of
        # geometry where the wheel meets the water; with no mesh handling every
        # particle spawned at the node origin and they stacked up in a single
        # vertical line, which read as a thin wisp of steam.
        if emitter.get(schema.MODIFIER, "") == "NiPSysMeshEmitter":
            check(f"{node.name} emits from its mesh",
                  any(n.type == "DISTRIBUTE_POINTS_ON_FACES" for n in group.nodes), True)

            # And the area it spreads over is measured off the parent chain,
            # not off a cached world matrix: the emitter mesh is hidden, so its
            # cache holds whatever the importer left and the density came out
            # ten thousand times too small -- no particles at all.
            #
            # Read off the built graph rather than off a settings dict, since
            # the density is worked out after the settings are made.
            spreading = [
                n for n in group.nodes if n.type == "DISTRIBUTE_POINTS_ON_FACES"
            ]

            for node_ in spreading:
                feed = node_.inputs["Density"]
                value = (feed.links[0].from_node.inputs[1].default_value
                         if feed.links else feed.default_value)

                check(f"{node.name} has somewhere to spread over", value > 0.0, True)

        # The quad the particles are drawn as, sized by the emitter's radius.
        sprite = bpy.data.objects.get(f"{node.name}_sprite")
        check(f"{node.name} has a sprite", sprite is not None, True)

        if sprite is not None:
            check(f"{node.name} sprite is UV mapped", len(sprite.data.uv_layers) > 0, True)

            # And it is the shape the file says. NiPSysData carries an aspect
            # ratio -- the campfire's fire column says 0.5 against atlas cells
            # 64 wide by 128 tall -- and a square quad drew that artwork at
            # twice its width, which is what made every flame a rectangle.
            aspect = float(node.get(schema.ASPECT_RATIO, 1.0) or 1.0)
            width = max(v.co[0] for v in sprite.data.vertices) - \
                min(v.co[0] for v in sprite.data.vertices)
            height = max(v.co[2] for v in sprite.data.vertices) - \
                min(v.co[2] for v in sprite.data.vertices)

            check(f"{node.name} sprite is the file's shape",
                  round(width / height, 3), round(aspect, 3))

    # It has to actually simulate, played in order. Jumping frames does not step
    # a simulation zone, so this walks them.
    counts = {}

    for frame in range(scene.frame_start, scene.frame_start + 60):
        scene.frame_set(frame)
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()
        counts[frame] = sum(1 for o in graph.object_instances if o.is_instance)

    early = counts[scene.frame_start]
    later = counts[scene.frame_start + 40]

    print(f"     instances: frame {scene.frame_start} -> {early}, "
          f"frame {scene.frame_start + 40} -> {later}")

    check("particles accumulate", later > early, True)

    # A mesh emitter spreads them over a surface, so they must not be collinear.
    mesh_emitters = [
        n for n in systems
        if n.name in report.systems
        and (build.emitter_of(n) or {}).get(schema.MODIFIER, "") == "NiPSysMeshEmitter"
    ]

    if mesh_emitters:
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()

        spread = {}

        for inst in graph.object_instances:
            if inst.is_instance:
                name = inst.parent.name if inst.parent else "?"
                spread.setdefault(name, []).append(
                    tuple(round(v, 3) for v in inst.matrix_world.translation))

        for node in mesh_emitters:
            places = spread.get(f"{node.name}_particles", [])

            if places:
                for axis, label in ((0, "x"), (1, "y")):
                    check(f"{node.name} spreads across {label}",
                          len({p[axis] for p in places}) > 1, True)

    # NiPSysRotationModifier: each particle turns at its own rate, so no two of
    # them face the same way. Without it a rising puff is a decal.
    spinning = [n for n in systems
                if n.name in report.systems
                and any(abs(v) > 1e-6 for v in build._rotation(n)[:2])]

    if spinning:
        graph = bpy.context.evaluated_depsgraph_get()
        graph.update()

        turned = {o.parent.name if o.parent else "?":
                  set() for o in graph.object_instances if o.is_instance}

        for inst in graph.object_instances:
            if inst.is_instance:
                name = inst.parent.name if inst.parent else "?"
                turned[name].add(tuple(round(a, 4) for a in inst.matrix_world.to_euler()))

        for node in spinning:
            host = f"{node.name}_particles"

            if len(turned.get(host, ())) > 0:
                check(f"{node.name} particles do not all face the same way",
                      len(turned[host]) > 1, True)

    # Still burning at the end. A looping emitter has to reach the last frame:
    # the count is taken there rather than trusting the settings.
    looping = [n for n in systems if build.cycle_of(n) in ("LOOP", "REVERSE")
               and n.name in report.systems]

    if looping:
        for frame in range(scene.frame_start + 60, scene.frame_end + 1):
            scene.frame_set(frame)
            graph = bpy.context.evaluated_depsgraph_get()
            graph.update()

        alive = sum(1 for o in graph.object_instances if o.is_instance)
        print(f"     instances at the last frame {scene.frame_end}: {alive}")
        check("a looping emitter is still going at the end", alive > 0, True)

    # And the age reaches the shader, which is the whole reason for the
    # simulation: Eevee does not implement the Particle Info node, so a fade
    # driven from it renders nothing at all.
    def stored(name):
        return any(
            node.type == "STORE_NAMED_ATTRIBUTE"
            and node.inputs["Name"].default_value == name
            and node.domain == "INSTANCE"
            for group in bpy.data.node_groups
            for node in group.nodes
        )

    check("the age is published for the shader", stored(simulation.PARTICLE_AGE), True)

    # And a number that does not change as the particle ages, which the atlas
    # needs: a sheet with no BSPSysSubTexModifier gives each particle one cell
    # and leaves it there, and one with a modifier starts each on its own frame.
    check("a per-particle seed is published", stored(simulation.PARTICLE_SEED), True)

    # And taking it away leaves the scene as it was found.
    before = len(scene.objects)
    removed = build.clear(scene)
    check("cleared", removed > 0, True)
    check("volumes removed", len(scene.objects) < before, True)


main()

print(f"\n{len(failures)} checks failed")

if failures:
    print("FAILED: " + ", ".join(failures))

sys.exit(len(failures))
