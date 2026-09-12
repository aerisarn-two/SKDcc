"""Writing an edited constraint back into the properties.

Rules R1-R5 of ``dcc-constraint-interop-spec.md``, the same as the Blender
add-on implements, over Maya nodes. R2 is again the one that matters: a
constraint nobody touched is written back untouched, because the cone mapping is
lossy and re-deriving it on every bake would shave the file down a little each
time the scene was merely opened.
"""

import maya.api.OpenMaya as om
import maya.cmds as cmds

from . import bodies, limits, mayaenv, schema
from .joint import Joint, all_transforms, joints_in
from .mayaenv import short_name


class Baked:
    def __init__(self):
        self.rewritten = 0
        self.unchanged = 0
        self.renamed = 0
        self.problems = []

    def __str__(self):
        text = "%d rewritten, %d unchanged" % (self.rewritten, self.unchanged)
        if self.renamed:
            text += ", %d renamed" % self.renamed
        if self.problems:
            text += ", %d problem%s" % (len(self.problems),
                                        "" if len(self.problems) == 1 else "s")
        return text


def bake(nodes=None):
    """Write every edited constraint back to its properties."""
    result = Baked()
    pool = list(nodes) if nodes else all_transforms()

    for node in joints_in(pool):
        constraint = _constraint_under(node)

        if constraint is None:
            continue

        joint = Joint(node)
        current = _read(constraint, joint)

        if _stored_signature(node) == limits.signature(current, _frame_of(node)):
            result.unchanged += 1
            continue

        # A rename invalidates the path, so every step after it works from the
        # name that came back rather than the one the loop started with. Maya is
        # unforgiving here: the stale path simply does not resolve, and the next
        # addAttr fails on nothing.
        node = _write_names(node, joint, constraint, result)
        joint = Joint(node)

        _write_limits(node, joint, dict(current))
        _write_far_frame(node, joint, pool, result)

        _remember(node, limits.signature(_read(_constraint_under(node), joint),
                                         _frame_of(node)))
        result.rewritten += 1

    return result


def _read(constraint, joint):
    """The constraint's live values, in radians, in the plan's own order."""
    values = []

    for setting in limits.plan(joint):
        attribute, is_angle = setting[0], len(setting) > 2 and setting[2] == "angle"
        full = "%s.%s" % (constraint, attribute)

        if not cmds.objExists(full):
            continue

        try:
            raw = cmds.getAttr(full)
        except (RuntimeError, ValueError):
            continue

        values.append((attribute,
                       mayaenv.from_ui_angle(full, raw) if is_angle else raw))

    return values


# --- R3 --------------------------------------------------------------------


def _write_names(node, joint, constraint, result):
    """Rebuild the body names and the node name; return the node's current name.

    This is the point of the design: in Maya the link is a dependency-graph
    connection, and a connection cannot be broken by renaming. The names in the
    file are regenerated from it on the way out.
    """
    body_a = _body_name_for(constraint, "rigidBodyA")
    body_b = _body_name_for(constraint, "rigidBodyB")

    if body_a is None or body_b is None:
        result.problems.append(
            "%s: a rigid body connection does not lead back to a Havok body"
            % short_name(node))
        return node

    _set_string(node, schema.BODY_A, body_a)
    _set_string(node, schema.BODY_B, body_b)

    wanted = "%s%s%s%s" % (body_b, schema.NAME_SEPARATOR, body_a, schema.ATTACH_SUFFIX)

    if short_name(node) == wanted:
        return node

    # The parent first, because renaming it invalidates every path beneath it;
    # the child is then found again under its new parent.
    renamed = cmds.rename(node, wanted)
    far = Joint(renamed).far_frame

    if far is not None:
        cmds.rename(far, wanted + schema.FAR_FRAME_SUFFIX)

    result.renamed += 1
    return renamed


def _body_name_for(constraint, plug):
    """The Havok body a constraint's rigid body input belongs to.

    The connection reaches a ``bulletRigidBodyShape``; its transform is the
    collision shape, and the Havok body is that shape's parent -- the same two
    step walk the Blender add-on makes, in Maya's graph.
    """
    sources = cmds.listConnections("%s.%s" % (constraint, plug),
                                   source=True, destination=False) or []

    if not sources:
        return None

    transforms = cmds.listRelatives(sources[0], parent=True, fullPath=True) or []

    if not transforms:
        return None

    shape = transforms[0]
    name = short_name(shape)

    if name.endswith((schema.BODY_SUFFIX, schema.PHANTOM_SUFFIX)):
        return name

    parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []

    if not parents:
        return None

    name = short_name(parents[0])
    return name if name.endswith((schema.BODY_SUFFIX, schema.PHANTOM_SUFFIX)) else None


# --- R1 --------------------------------------------------------------------


def _write_limits(node, joint, current):
    """Put the edited angles back under both spellings, and touch nothing else.

    Both, because both are read: the ``hkc_`` field is what NIFBX rebuilds the
    NIF from, and the shared name is what ck-cmd and HKFBX read. Every other
    property -- a stiff spring's stiffness, a chain's links, a wrapper's breaking
    threshold -- is left exactly as it arrived.
    """
    def axis(name):
        lower = current.get("angularConstraintMin%s" % name)
        upper = current.get("angularConstraintMax%s" % name)
        if lower is None and upper is None:
            return None
        return (lower or 0.0, upper or 0.0)

    if joint.type == "Ragdoll":
        _pair(node, axis("X"), schema.TWIST_MIN, schema.TWIST_MAX,
              "Twist Min Angle", "Twist Max Angle")
        _pair(node, axis("Y"), schema.PLANE_MIN, schema.PLANE_MAX,
              "Plane Min Angle", "Plane Max Angle")

        cone = axis("Z")
        if cone is not None:
            # Back to the half angle it came from. The larger magnitude rather
            # than the upper bound, so a cone widened by dragging the lower limit
            # is kept.
            _scalar(node, max(abs(cone[0]), abs(cone[1])),
                    schema.CONE_MAX, "Cone Max Angle")

    elif joint.type == "LimitedHinge":
        _pair(node, axis("X"), schema.MIN_ANGLE, schema.MAX_ANGLE,
              "Min Angle", "Max Angle")


def _pair(node, limit, min_property, max_property, min_field, max_field):
    if limit is None:
        return
    lower, upper = sorted(limit)
    _scalar(node, lower, min_property, min_field)
    _scalar(node, upper, max_property, max_field)


def _scalar(node, value, shared_property, field_name):
    """One angle, under both names, each in the type its reader expects.

    The shared property is a number because that is what NIFBX writes; the
    ``hkc_`` field is a string because the descriptor dump is strings throughout
    -- it carries vectors and flags in the same store -- and a reader meeting a
    double there will not parse it.
    """
    _set_number(node, shared_property, float(value))

    field = schema.field(field_name)
    if cmds.objExists("%s.%s" % (node, field)):
        _set_string(node, field, repr(float(value)))


# --- R4 --------------------------------------------------------------------


def _write_far_frame(node, joint, pool, result):
    """Recompute frame A from where the joint now is.

    Havok stores the joint twice, once in each body's space; Maya's Bullet
    constraint stores it once, as the constraint's own placement. So frame A is
    derived: the joint's placement seen from body A.

    Note the multiplication order. Maya's matrices are row-vector -- a child's
    world matrix is ``local * parent`` -- so the relative transform is
    ``joint * inverse(bodyA)`` and **not** the ``inverse(bodyA) * joint`` that
    the same derivation needs in Blender. Getting this backwards produces a
    frame that is wrong in a way nothing about the file would show.
    """
    far = joint.far_frame

    if far is None:
        return

    body_a = bodies.find_body(pool, joint.body_a_name)

    if body_a is None:
        return

    joint_world = om.MMatrix(cmds.xform(node, query=True, matrix=True, worldSpace=True))
    body_world = om.MMatrix(cmds.xform(body_a, query=True, matrix=True, worldSpace=True))

    relative = om.MTransformationMatrix(joint_world * body_world.inverse())

    # A joint frame is a rotation and a pivot; any scale in the product is an
    # artefact of the two chains and is dropped rather than written out.
    relative.setScale((1.0, 1.0, 1.0), om.MSpace.kTransform)

    cmds.xform(far, matrix=list(relative.asMatrix()), objectSpace=True)


# --- attribute plumbing ----------------------------------------------------


def _frame_of(node):
    """The joint's own placement, for the signature. See limits.signature."""
    try:
        return cmds.xform(node, query=True, matrix=True, worldSpace=True)
    except (RuntimeError, ValueError):
        return None


def _constraint_under(node):
    found = cmds.listRelatives(node, children=True, fullPath=True,
                               type=mayaenv.CONSTRAINT_NODE) or []
    return found[0] if found else None


def _stored_signature(node):
    attribute = "%s.%s" % (node, schema.SIGNATURE)
    return cmds.getAttr(attribute) if cmds.objExists(attribute) else None


def _remember(node, signature):
    _set_string(node, schema.SIGNATURE, signature)


def _set_string(node, name, value):
    attribute = "%s.%s" % (node, name)
    if not cmds.objExists(attribute):
        cmds.addAttr(node, longName=name, dataType="string")
    cmds.setAttr(attribute, value, type="string")


def _set_number(node, name, value):
    attribute = "%s.%s" % (node, name)
    if not cmds.objExists(attribute):
        cmds.addAttr(node, longName=name, attributeType="double")
    cmds.setAttr(attribute, value)
