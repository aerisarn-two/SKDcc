#!/usr/bin/env bash
# The add-on against a real creature ragdoll, headless.
#
#   tests/run.sh path/to/skeleton.fbx
#
# Any FBX written by NIFBX from a creature's skeleton.nif, or by HKFBX from a
# skeleton.hkx, will do. There is no bundled fixture: the point of the suite is
# that it runs against files nobody wrote for a test.
#
# --factory-startup is deliberately NOT passed. It leaves io_scene_fbx's
# operator properties unregistered, and the exporter then dies with
# "'ExportFBX' object has no attribute 'use_space_transform'".
set -euo pipefail

fbx="${1:?usage: tests/run.sh path/to/skeleton.fbx}"
blender="${SKHK_BLENDER:-blender}"
here="$(cd "$(dirname "$0")" && pwd)"

"$blender" --background --python "$here/run_in_blender.py" -- "$fbx" 2>&1 \
    | grep -E '^(PASS|FAIL|     )|checks failed|FAILED:'

exit "${PIPESTATUS[0]}"
