#!/usr/bin/env bash
# Everything that can be run on this machine.
#
#   tests/run.sh [path/to/skeleton.fbx]
#
# Without an FBX, the host-free suites run: the Maya and Max scripts against a
# recorded fixture, and the check that the three schema copies have not drifted.
# With one, the Blender add-on runs inside Blender as well.
#
# --factory-startup is deliberately NOT passed to Blender. It leaves
# io_scene_fbx's operator properties unregistered and the exporter then dies with
# "'ExportFBX' object has no attribute 'use_space_transform'".
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
blender="${SKHK_BLENDER:-blender}"
failures=0

echo "== schema =="
python3 "$here/test_schema_agrees.py" || failures=$((failures + $?))

echo
echo "== maya (fixture, no Maya needed) =="
python3 "$here/test_maya.py" || failures=$((failures + $?))

echo
echo "== max (fixture, no Max needed) =="
python3 "$here/test_max.py" || failures=$((failures + $?))

if [ "$#" -ge 1 ]; then
    echo
    echo "== blender (live) =="
    "$blender" --background --python "$here/run_in_blender.py" -- "$1" 2>&1 \
        | grep -E '^(PASS|FAIL|     )|checks failed|FAILED:'
    failures=$((failures + ${PIPESTATUS[0]}))
else
    echo
    echo "== blender: skipped, pass an FBX to run it =="
fi

echo
echo "$failures failure(s)"
exit "$failures"
