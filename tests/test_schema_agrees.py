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
    ("blender", os.path.join(ROOT, "blender", "skyrim_havok_constraints", "schema.py")),
    ("maya", os.path.join(ROOT, "maya", "skhk_maya", "schema.py")),
    ("max", os.path.join(ROOT, "max", "skhk_max", "schema.py")),
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
    copies = [(host, constants(path)) for host, path in COPIES]
    failures = []

    # Every constant is shared, SHAPE_SUFFIXES included: each host maps its
    # neutral tokens to its own enum, but the suffix table itself is one table.
    every = set()
    for _, found in copies:
        every |= set(found)

    reference_host, reference = copies[0]

    for name in sorted(every):
        for host, found in copies[1:]:
            if name not in found:
                failures.append("%s is missing from the %s copy" % (name, host))
            elif name not in reference:
                failures.append("%s is missing from the %s copy" % (name, reference_host))
            elif found[name] != reference[name]:
                failures.append("%s differs between %s and %s: %r against %r"
                                % (name, reference_host, host,
                                   reference[name], found[name]))

    print("%-4s %d constants agree across %d hosts"
          % ("FAIL" if failures else "PASS", len(every), len(copies)))
    print("%-4s the shape suffixes are one table, in one order"
          % ("PASS" if not failures and "SHAPE_SUFFIXES" in reference else "FAIL"))

    for problem in failures:
        print("   ", problem)

    return len(failures)


if __name__ == "__main__":
    sys.exit(main())
