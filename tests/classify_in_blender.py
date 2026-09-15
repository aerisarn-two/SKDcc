"""Say which live suites each FBX has content for.

    blender --background --python tests/classify_in_blender.py -- a.fbx b.fbx ...

One launch for all of them, because the runner has to route. Every live suite
fails loudly when handed a file with nothing in it for them, and that is
deliberate: naming a file and getting no particle system means somebody asked
for a run and did not get one, which must not pass quietly. The cost is that
they cannot all be run against everything, so something has to know what is in
each file first.

Prints one line per file, which `run.sh` reads:

    <path> particles=<n> materials=<n> joints=<n> meshes=<n> rigs=<n> clips=<n>
"""

import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "blender"))

from skyrim_havok_constraints.joint import joints_in  # noqa: E402
from skyrim_materials import build as materials       # noqa: E402
from skyrim_particles import build as particles       # noqa: E402
from skyrim_rig import build as rig                   # noqa: E402


def main():
    for path in sys.argv[sys.argv.index("--") + 1:]:
        bpy.ops.wm.read_homefile(use_empty=True)

        try:
            bpy.ops.import_scene.fbx(filepath=path, use_custom_props=True,
                                     automatic_bone_orientation=True)
        except Exception as error:                     # noqa: BLE001
            print(f"CLASSIFY {path} unreadable={type(error).__name__}")
            continue

        scene = bpy.context.scene

        print(
            f"CLASSIFY {path}"
            f" particles={sum(1 for o in scene.objects if particles.is_system(o))}"
            f" materials={sum(1 for m in bpy.data.materials if materials.is_skyrim_material(m))}"
            f" joints={len(list(joints_in(scene.objects)))}"
            f" meshes={sum(1 for o in scene.objects if o.type == 'MESH')}"
            f" rigs={sum(1 for o in scene.objects if o.type == 'ARMATURE')}"
            f" clips={len(bpy.data.actions)}"
        )


main()
