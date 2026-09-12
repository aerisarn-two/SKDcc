"""The Maya facts this needs, in one place so they can be checked in one place.

Written against Maya's shipped ``maya.app.mayabullet`` modules. The enum values
and attribute names below are read out of those modules rather than remembered:
``RigidBodyConstraint.py`` and ``RigidBody.py`` in
``<maya>/lib/python*/site-packages/maya/app/mayabullet/``.
"""

import math

import maya.cmds as cmds

#: ``RigidBodyConstraint.eConstraintType``.
POINT = 0
HINGE = 1
SLIDER = 2
CONE_TWIST = 3
SIX_DOF = 4
SIX_DOF_2 = 5
HINGE_2 = 6

#: ``RigidBodyConstraint.eConstraintLimitType``.
FREE = 0
LOCKED = 1
LIMITED = 2

#: ``RigidBody.eShapeType``.
COLLIDER_BOX = 1
COLLIDER_SPHERE = 2
COLLIDER_CAPSULE = 3
COLLIDER_HULL = 4
COLLIDER_MESH = 5

#: ``RigidBody.eBodyType``.
STATIC_BODY = 0
KINEMATIC_BODY = 1
DYNAMIC_BODY = 2

CONSTRAINT_NODE = "bulletRigidBodyConstraintShape"
BODY_NODE = "bulletRigidBodyShape"


def bullet_available():
    """Whether the Bullet plug-in is loaded, loading it if it is merely absent.

    Bullet installs with Maya -- it has shipped in every version through 2026 --
    but it is a plug-in and an artist's Maya may simply not have autoloaded it.
    """
    if cmds.pluginInfo("bullet", query=True, loaded=True):
        return True
    try:
        cmds.loadPlugin("bullet", quiet=True)
    except RuntimeError:
        return False
    return cmds.pluginInfo("bullet", query=True, loaded=True)


def to_ui_angle(attribute, radians):
    """An angle in radians, in whatever unit that attribute wants.

    Two kinds of attribute take an angle here and they do not agree. A
    ``doubleAngle`` is stored in radians but ``setAttr`` interprets a bare
    number in the session's angular unit, which is degrees unless somebody
    changed it. A plain ``double`` on a Bullet node is degrees regardless.

    So the unit is not assumed: the attribute is asked what it is. Getting this
    wrong is silent and gives limits out by a factor of 57.
    """
    try:
        kind = cmds.getAttr(attribute, type=True)
    except (RuntimeError, ValueError):
        kind = "double"

    if kind == "doubleAngle" and cmds.currentUnit(query=True, angle=True).startswith("rad"):
        return radians

    return math.degrees(radians)


def from_ui_angle(attribute, value):
    """The inverse of :func:`to_ui_angle`, for reading an edited limit back."""
    try:
        kind = cmds.getAttr(attribute, type=True)
    except (RuntimeError, ValueError):
        kind = "double"

    if kind == "doubleAngle" and cmds.currentUnit(query=True, angle=True).startswith("rad"):
        return value

    return math.radians(value)


def short_name(node):
    """The last component of a DAG path.

    Maya names are unique per parent, not per scene, so anything that came from
    a listing is a path and anything compared against a property is a name.
    """
    return node.rsplit("|", 1)[-1].rsplit(":", 1)[-1]


def user_attributes(node):
    """Every extra attribute on a node, which is where FBX put the properties."""
    return cmds.listAttr(node, userDefined=True) or []
