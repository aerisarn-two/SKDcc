"""Skyrim Havok constraints, as constraints Maya can use.

An FBX written by NIFBX or HKFBX carries a creature's ragdoll as extra
attributes, because FBX has no way to carry it as anything else -- its own
constraint objects are animation constraints with no limits, no friction and no
second frame, and Maya reads exactly six of them, none of which is a joint
limit. The reasoning is in ``dcc-constraint-interop-spec.md`` in NIFBX.

This turns those attributes into Bullet rigid body constraints, or into joint
rotation limits for posing, and writes them back when you are done.

    import skhk_maya
    skhk_maya.install()              # adds the menu
    skhk_maya.build_constraints()    # or call it directly
"""

from . import bake as bake_module
from . import build as build_module

MENU = "skhkMenu"

# Named so as not to shadow the submodules they call. ``skhk_maya.build`` has to
# keep meaning the module, or ``from skhk_maya import build`` quietly hands the
# caller a function and every attribute lookup on it fails.


def build_constraints(dynamic=False):
    """Bullet constraints from the properties. Returns a result to print."""
    return build_module.build_rigid_body_constraints(dynamic=dynamic)


def clear_constraints():
    return build_module.clear_rigid_body_constraints()


def build_limits():
    """Rotation limits on the joints, for posing. Needs no plug-in."""
    return build_module.build_joint_limits()


def clear_limits():
    return build_module.clear_joint_limits()


def bake_properties():
    """Write edited constraints back into the properties, ready to export."""
    return bake_module.bake()


def install():
    """Add a Skyrim Havok menu to the main window."""
    import maya.cmds as cmds

    if cmds.menu(MENU, query=True, exists=True):
        cmds.deleteUI(MENU)

    cmds.menu(MENU, label="Skyrim Havok", parent="MayaWindow", tearOff=True)

    cmds.menuItem(label="Build Rigid Body Constraints",
                  command=lambda *_: _report(build_constraints()))
    cmds.menuItem(label="Clear Rigid Body Constraints",
                  command=lambda *_: _report("removed %d" % clear_constraints()))
    cmds.menuItem(divider=True)
    cmds.menuItem(label="Build Joint Limits (posing)",
                  command=lambda *_: _report(build_limits()))
    cmds.menuItem(label="Clear Joint Limits",
                  command=lambda *_: _report("cleared %d" % clear_limits()))
    cmds.menuItem(divider=True)
    cmds.menuItem(label="Bake Constraints to Properties",
                  command=lambda *_: _report(bake_properties()))

    return MENU


def uninstall():
    import maya.cmds as cmds
    if cmds.menu(MENU, query=True, exists=True):
        cmds.deleteUI(MENU)


def _report(result):
    import maya.cmds as cmds
    cmds.inViewMessage(amg="Skyrim Havok: <hl>%s</hl>" % result, pos="midCenter", fade=True)
    print("Skyrim Havok: %s" % result)
    for problem in getattr(result, "problems", [])[:10]:
        print("   %s" % problem)
