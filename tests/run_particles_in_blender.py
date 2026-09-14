"""Build particle systems from a converted effect, inside Blender.

    blender --background --python tests/run_particles_in_blender.py -- some.fbx

Imports the FBX, runs the add-on, and checks that what came out says what the
properties said. The point is not that it runs: it is that the numbers on the
Blender system are the numbers in the file, converted where units differ and
carried where they do not.
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_particles import build, schema  # noqa: E402

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
    print(f"     {report}")

    for line in report.notes:
        print(f"     note: {line}")

    for line in report.skipped:
        print(f"     skipped: {line}")

    check("systems built", len(report.systems) > 0, True)

    # Every built system's numbers against the emitter they came from.
    fps = scene.render.fps / max(scene.render.fps_base, 1e-6)

    for node in systems:
        emitter = build.emitter_of(node)

        if emitter is None or node.name not in report.systems:
            continue

        carrier = None

        for obj in scene.objects:
            for system in obj.particle_systems:
                if system.name == node.name:
                    carrier = system.settings

        if carrier is None:
            continue

        life = float(emitter.get(schema.LIFE_SPAN, 1.0))
        check(f"{node.name} lifetime", carrier.lifetime, max(1, int(round(life * fps))))

        # Lengths are in the file's units and the scene is in Blender's, so the
        # frame's own world scale is what converts them. Taken straight off the
        # matrix here rather than from the add-on, so the two have to agree
        # rather than agreeing with themselves.
        scale = node.matrix_world.to_scale()
        units = (abs(scale[0]) + abs(scale[1]) + abs(scale[2])) / 3.0

        speed = float(emitter.get(schema.SPEED, 0.0))
        moving = max(abs(v) for v in carrier.object_align_factor) or carrier.normal_factor

        check(f"{node.name} speed", round(moving, 5), round(speed * units, 5))
        check(
            f"{node.name} size",
            round(carrier.particle_size, 5),
            round(max(float(emitter.get(schema.INITIAL_RADIUS, 1.0)) * units, 1e-6), 5),
        )

        # And the thing that was wrong: a speed used as it stands is a hundred
        # times too fast, so it must not be the file's number.
        if speed > 0 and units < 0.5:
            check(f"{node.name} speed is converted", moving != speed, True)

        # The emission window, which is the thing a Blender pass used to lose
        # entirely: the emitter controller went into an animation stack and
        # Blender does not import curves on custom properties.
        emission = build.emission_of(node)

        if emission is not None:
            start, stop, rate = emission

            check(
                f"{node.name} emission starts",
                carrier.frame_start,
                scene.frame_start + int(round(start * fps)),
            )

            if stop is not None and stop > start:
                check(
                    f"{node.name} emission ends",
                    carrier.frame_end,
                    scene.frame_start + int(round(stop * fps)),
                )

                # Not the whole scene, which is what it was before the window
                # travelled -- a campfire emitting for 3.3 seconds ran for 250
                # frames.
                check(
                    f"{node.name} window is not the scene",
                    carrier.frame_end < scene.frame_end,
                    True,
                )

                # The count is a number emitted over the window, where the file
                # gives a rate per second, bounded by the engine's buffer.
                if rate > 0:
                    check(
                        f"{node.name} count",
                        carrier.count,
                        max(1, int(round(rate * (stop - start)))),
                    )

                    # And that the buffer is not what it is. The buffer sizes
                    # the particles alive at once, so a flame emitting 15 a
                    # second for 3.3 of them emits 50, whatever its buffer of
                    # nine says.
                    budget = int(float(node.get(schema.MAX_VERTICES, 0)) or 0)

                    if budget and rate * (stop - start) > budget:
                        check(f"{node.name} count is not the buffer", carrier.count > budget, True)

        # A system with no gravity modifier must not fall: Blender applies scene
        # gravity to every particle and Skyrim does not.
        kinds = {m.get(schema.MODIFIER, "") for m in build.modifiers_of(node)}

        if schema.GRAVITY not in kinds:
            check(f"{node.name} gravity off", carrier.effector_weights.gravity, 0.0)

    # And taking it away leaves the scene as it was found.
    before = len(scene.objects)
    removed = build.clear(scene)
    check("cleared", removed > 0, True)
    check("volumes removed", len(scene.objects) <= before, True)

    remaining = sum(len(o.particle_systems) for o in scene.objects)
    check("no systems left", remaining, 0)


main()

print(f"{len(failures)} checks failed" if failures else "0 checks failed")
sys.exit(1 if failures else 0)
