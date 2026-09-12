"""Skyrim Havok constraints, as constraints 3ds Max can use.

An FBX written by NIFBX or HKFBX carries a creature's ragdoll as properties,
because FBX has no way to carry it as anything else -- its own constraint objects
are animation constraints with no limits, no friction and no second frame, and Max
does not read them at all. The reasoning is in
``dcc-constraint-interop-spec.md`` in NIFBX.

This turns those properties into MassFX UConstraints, or into rotation limits for
posing, and writes them back when you are done.

    import sys; sys.path.append(r"C:\\path\\to\\SKDcc\\max")
    import skhk_max
    skhk_max.build_constraints()
"""

from . import bake as bake_module
from . import build as build_module

# Named so as not to shadow the submodules they call: ``skhk_max.build`` has to
# keep meaning the module.


def build_constraints(dynamic=False):
    """MassFX UConstraints from the properties. Returns a result to print."""
    return build_module.build_constraints(dynamic=dynamic)


def clear_constraints():
    return build_module.clear_constraints()


def build_limits():
    """Rotation limits on the bones, for posing. Needs no plug-in."""
    return build_module.build_rotation_limits()


def clear_limits():
    return build_module.clear_rotation_limits()


def bake_properties():
    """Write edited constraints back into the properties, ready to export."""
    return bake_module.bake()


def report(result):
    print("Skyrim Havok: %s" % result)
    for problem in getattr(result, "problems", [])[:10]:
        print("   %s" % problem)
    return result
