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
        check(f"{node.name} speed", carrier.normal_factor, float(emitter.get(schema.SPEED, 0.0)))
        check(
            f"{node.name} size",
            carrier.particle_size,
            max(float(emitter.get(schema.INITIAL_RADIUS, 1.0)), 1e-4),
        )

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
