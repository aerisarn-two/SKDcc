#!/usr/bin/env bash
# Everything that can be run on this machine.
#
#   tests/run.sh [path/to/any.fbx ...]
#
# Without an FBX, the host-free suites run: the Maya and Max scripts against a
# recorded fixture, and the check that the three schema copies have not drifted.
#
# With any number of them, the live suites run too -- each against the files
# that have something in them for it. Which file that is, is read out of the
# file rather than out of its position on the command line: this used to take a
# creature as $1 and an effect as $2, and a sample added to the pile was
# exercised only if somebody remembered which slot it belonged in. A waterwheel
# is the only mesh emitter to hand and a cow skeleton the only ragdoll, and
# neither was being run by the suite that covers it.
#
# The live suites each fail loudly when handed a file with nothing in them for
# them, which is deliberate -- naming a file and getting no particle system
# means a run was asked for and not had. So they are routed rather than let
# loose on everything, and `classify_in_blender.py` does the routing in one
# Blender launch for the whole pile.
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

if [ "$#" -eq 0 ]; then
    echo
    echo "== the live suites: skipped, pass one or more FBX files to run them =="
    echo
    echo "$failures failure(s)"
    exit "$failures"
fi

# What is in each file, in one launch rather than one per suite per file.
echo
echo "== what each file has =="
classified="$("$blender" --background --python "$here/classify_in_blender.py" -- "$@" 2>&1 \
    | grep '^CLASSIFY')"

if [ -z "$classified" ]; then
    echo "FAILED: could not read any of the files given"
    exit 1
fi

echo "$classified" | sed 's/^CLASSIFY /   /'

# suite <name> <script> <field>: run it against every file whose count is not 0.
suite() {
    local name="$1" script="$2" field="$3" ran=0

    while read -r _ path rest; do
        case " $rest " in
            *" $field=0 "*) continue ;;
        esac

        echo
        echo "== $name: $(basename "$path") =="
        "$blender" --background --python "$here/$script" -- "$path" 2>&1 \
            | grep -E '^(PASS|FAIL|     )|checks failed|FAILED:'
        failures=$((failures + ${PIPESTATUS[0]}))
        ran=$((ran + 1))
    done <<< "$classified"

    if [ "$ran" -eq 0 ]; then
        echo
        echo "== $name: skipped, nothing given has any =="
    fi
}

suite "blender constraints" run_in_blender.py joints
suite "blender particles" run_particles_in_blender.py particles
suite "blender materials" run_materials_in_blender.py materials

# The import repair works on anything converted, so it runs against every file
# that has a mesh to be at the wrong scale.
suite "blender import scale" run_scale_in_blender.py meshes

echo
echo "$failures failure(s)"
exit "$failures"
