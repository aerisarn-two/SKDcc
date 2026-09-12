"""Dump a real ragdoll's joints to JSON, for tests that run without a DCC.

    blender --background --python tests/extract_fixture.py -- skeleton.fbx out.json

The fixture is the whole point of being able to test the Maya and Max mapping
logic on a machine with neither installed: the numbers in it came out of a
vanilla creature, not out of somebody's idea of what a joint looks like.
"""

import json
import os
import sys

import addon_utils
import bpy


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    fbx, out = os.path.abspath(argv[0]), os.path.abspath(argv[1])

    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "blender"))
    addon_utils.enable("io_scene_fbx", default_set=False, persistent=False)

    from skyrim_havok_constraints import schema
    from skyrim_havok_constraints.blender_compat import evaluated
    from skyrim_havok_constraints.joint import Joint, joints_in

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.wm.fbx_import(filepath=fbx, use_custom_props=True)

    objects = list(bpy.context.scene.objects)
    record = {"source": os.path.basename(fbx), "joints": [], "bodies": {}}

    with evaluated(objects):
        bpy.context.view_layer.update()

        for obj in joints_in(objects):
            joint = Joint(obj)
            far = joint.far_frame
            record["joints"].append({
                "name": obj.name,
                "properties": {k: _plain(obj[k]) for k in obj.keys()
                               if not k.startswith("_")},
                "matrix_local": [list(row) for row in obj.matrix_local],
                "far_frame": None if far is None else
                             [list(row) for row in far.matrix_basis],
                "parent": obj.parent.name if obj.parent else None,
            })

        for obj in objects:
            if not obj.name.endswith(schema.BODY_SUFFIX):
                continue
            shapes = [c.name for c in obj.children if c.type == "MESH"]
            record["bodies"][obj.name] = {
                "properties": {k: _plain(obj[k]) for k in obj.keys()
                               if not k.startswith("_")},
                "shapes": shapes,
                "bone": obj.parent_bone or None,
                "world_scale": list(obj.matrix_world.to_scale()),
            }

    with open(out, "w") as handle:
        json.dump(record, handle, indent=1, sort_keys=True)

    print("wrote %s: %d joints, %d bodies"
          % (out, len(record["joints"]), len(record["bodies"])), flush=True)
    return 0


def _plain(value):
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [float(v) for v in value]
    except TypeError:
        return str(value)


if __name__ == "__main__":
    sys.exit(main())
