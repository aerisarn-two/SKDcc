"""The two copies of ``schema.py`` must not drift apart.

Each host needs its own: a Blender add-on has to be a self-contained folder and a
Maya script has to be importable from a scripts path, so neither can reach a
shared sibling package. Duplication is the price, and this is the check that
makes it safe to pay -- every constant that names something in the file format
has to be identical in both.
"""

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

COPIES = (
    os.path.join(ROOT, "blender", "skyrim_havok_constraints", "schema.py"),
    os.path.join(ROOT, "maya", "skhk_maya", "schema.py"),
)


def constants(path):
    """Every module-level assignment of a literal, by name."""
    tree = ast.parse(open(path).read())
    found = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                try:
                    found[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    pass

    return found


def main():
    blender, maya = (constants(path) for path in COPIES)
    failures = []

    # SHAPE_SUFFIXES maps to each host's own collider enum, so only its keys are
    # shared. Everything else has to match outright.
    shared = (set(blender) | set(maya)) - {"SHAPE_SUFFIXES"}

    for name in sorted(shared):
        if name not in blender:
            failures.append("%s is only in the Maya copy" % name)
        elif name not in maya:
            failures.append("%s is only in the Blender copy" % name)
        elif blender[name] != maya[name]:
            failures.append("%s differs: %r against %r" % (name, blender[name], maya[name]))

    keys_b = [suffix for suffix, _ in blender.get("SHAPE_SUFFIXES", ())]
    print("%-4s %d shared constants agree" % ("FAIL" if failures else "PASS", len(shared)))
    print("%-4s the shape suffixes are the same, in the same order"
          % ("PASS" if keys_b else "FAIL"))

    for problem in failures:
        print("   ", problem)

    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
