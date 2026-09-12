"""A recording stand-in for ``maya.cmds``, so the Maya code can be tested here.

This is not a Maya emulator and does not pretend to be one. It models what the
scripts actually use -- a node tree, typed attributes, connections -- and records
every ``setAttr``, so a test can assert that the right attribute got the right
number in the right unit. What it cannot check is Maya's own semantics: whether
Bullet likes a six-DOF constraint built this way is a question only Maya answers.

Installed by :func:`install`, which puts the fake modules into ``sys.modules``
before the scripts import them.
"""

import math
import sys
import types


class Node:
    def __init__(self, name, kind, parent=None):
        self.name = name
        self.kind = kind
        self.parent = parent
        self.children = []
        self.attrs = {}
        self.types = {}
        self.matrix = _identity()


class Scene:
    def __init__(self):
        self.nodes = {}
        self.connections = []
        self.set_calls = []
        self.deleted = []
        self.limits = {}

    # -- building a scene for a test ------------------------------------------

    def add(self, name, kind="transform", parent=None):
        node = Node(name, kind, parent)
        self.nodes[name] = node
        if parent is not None:
            self.nodes[parent].children.append(name)
        return name

    def set_user_attr(self, name, attribute, value, kind=None):
        node = self.nodes[name]
        node.attrs[attribute] = value
        node.types[attribute] = kind or ("string" if isinstance(value, str) else "double")
        node.attrs.setdefault("__user__", set())
        node.attrs["__user__"].add(attribute)

    # -- lookups --------------------------------------------------------------

    def path(self, name):
        return name

    def resolve(self, name):
        return self.nodes.get(name.rsplit("|", 1)[-1])


SCENE = Scene()


def _identity():
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


# --------------------------------------------------------------------------
# the cmds surface the scripts use
# --------------------------------------------------------------------------


def objExists(target):
    if "." in target:
        node, attribute = target.split(".", 1)
        found = SCENE.resolve(node)
        return found is not None and attribute in found.attrs
    return SCENE.resolve(target) is not None


def nodeType(target):
    found = SCENE.resolve(target)
    return found.kind if found else ""


def getAttr(target, **kwargs):
    node, attribute = target.split(".", 1)
    found = SCENE.resolve(node)

    if found is None or attribute not in found.attrs:
        raise RuntimeError("no attribute %s" % target)

    if kwargs.get("type"):
        return found.types.get(attribute, "double")

    return found.attrs[attribute]


def setAttr(target, *values, **kwargs):
    node, attribute = target.split(".", 1)
    found = SCENE.resolve(node)

    if found is None or attribute not in found.attrs:
        raise RuntimeError("no attribute %s" % target)

    value = values[0] if len(values) == 1 else list(values)
    found.attrs[attribute] = value
    SCENE.set_calls.append((node, attribute, value))


def addAttr(node, longName=None, dataType=None, attributeType=None, **kwargs):
    found = SCENE.resolve(node)
    found.attrs[longName] = "" if dataType == "string" else 0.0
    found.types[longName] = dataType or attributeType or "double"
    found.attrs.setdefault("__user__", set())
    found.attrs["__user__"].add(longName)


def deleteAttr(target):
    node, attribute = target.split(".", 1)
    found = SCENE.resolve(node)
    found.attrs.pop(attribute, None)


def listAttr(node, userDefined=False, **kwargs):
    found = SCENE.resolve(node)
    if found is None:
        return []
    return sorted(found.attrs.get("__user__", set()))


def listRelatives(node, children=False, parent=False, shapes=False,
                  fullPath=False, type=None, **kwargs):
    found = SCENE.resolve(node) if node else None

    if found is None:
        return None

    if parent:
        return [found.parent] if found.parent else None

    names = list(found.children)

    if type is not None:
        names = [n for n in names if SCENE.nodes[n].kind == type]
    elif shapes:
        names = [n for n in names if SCENE.nodes[n].kind.endswith("Shape")
                 or SCENE.nodes[n].kind == "mesh"]

    return names or None


def ls(type=None, long=False, **kwargs):
    return [n for n, node in SCENE.nodes.items() if type is None or node.kind == type]


def listConnections(target, source=False, destination=False, **kwargs):
    node, attribute = target.split(".", 1)
    found = [src for src, dst in SCENE.connections if dst == (node, attribute)]
    return found or None


def connectAttr(source, destination, **kwargs):
    SCENE.connections.append((source.split(".")[0],
                              (destination.split(".")[0], destination.split(".", 1)[1])))


def delete(target):
    SCENE.deleted.append(target)
    found = SCENE.resolve(target)
    if found and found.parent and target in SCENE.nodes[found.parent].children:
        SCENE.nodes[found.parent].children.remove(target)
    SCENE.nodes.pop(target, None)


def rename(node, name):
    found = SCENE.nodes.pop(node)
    found.name = name
    SCENE.nodes[name] = found
    if found.parent:
        SCENE.nodes[found.parent].children = [
            name if c == node else c for c in SCENE.nodes[found.parent].children]
    for child in found.children:
        SCENE.nodes[child].parent = name
    return name


def createNode(kind, parent=None, **kwargs):
    name = "%s%d" % (kind, len([n for n in SCENE.nodes.values() if n.kind == kind]) + 1)
    return SCENE.add(name, kind, parent)


def currentUnit(query=False, angle=False, **kwargs):
    return "deg"


def transformLimits(node, **kwargs):
    SCENE.limits.setdefault(node, {}).update(kwargs)


def xform(node, query=False, matrix=False, worldSpace=False, objectSpace=False, **kwargs):
    found = SCENE.resolve(node)
    if query:
        return list(found.matrix)
    if matrix is not False and matrix is not True:
        found.matrix = list(matrix)
    return None


def pluginInfo(name, query=False, loaded=False):
    return True


def loadPlugin(name, quiet=False):
    return [name]


def inViewMessage(**kwargs):
    return None


def menu(*args, **kwargs):
    return kwargs.get("query") and False


def menuItem(*args, **kwargs):
    return None


def deleteUI(*args, **kwargs):
    return None


# --------------------------------------------------------------------------


def install():
    """Put the fake ``maya`` package into ``sys.modules``. Returns the scene."""
    global SCENE
    SCENE = Scene()

    cmds = types.ModuleType("maya.cmds")
    for name, value in list(globals().items()):
        if callable(value) and not name.startswith("_") and name not in ("install",):
            setattr(cmds, name, value)

    maya = types.ModuleType("maya")
    maya.cmds = cmds

    api = types.ModuleType("maya.api")
    openmaya = _make_openmaya()
    api.OpenMaya = openmaya
    maya.api = api

    app = types.ModuleType("maya.app")
    mayabullet = types.ModuleType("maya.app.mayabullet")
    app.mayabullet = mayabullet
    maya.app = app

    sys.modules["maya"] = maya
    sys.modules["maya.cmds"] = cmds
    sys.modules["maya.api"] = api
    sys.modules["maya.api.OpenMaya"] = openmaya
    sys.modules["maya.app"] = app
    sys.modules["maya.app.mayabullet"] = mayabullet

    return SCENE


def _make_openmaya():
    """Just enough OpenMaya for the frame A derivation: 4x4 row-vector maths."""
    module = types.ModuleType("maya.api.OpenMaya")

    class MMatrix(list):
        def __init__(self, values=None):
            super(MMatrix, self).__init__(values if values else _identity())

        def __mul__(self, other):
            a, b = self, other
            out = [0.0] * 16
            for r in range(4):
                for c in range(4):
                    out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
            return MMatrix(out)

        def inverse(self):
            # Only ever used on an affine transform with uniform-ish scale, so
            # the rotation block is inverted by transpose over its squared norm
            # and the translation by rotating it back.
            rot = [self[r * 4 + c] for r in range(3) for c in range(3)]
            scales = [math.sqrt(sum(rot[r * 3 + c] ** 2 for c in range(3))) or 1.0
                      for r in range(3)]
            inv = [[rot[c * 3 + r] / (scales[c] ** 2) for c in range(3)] for r in range(3)]
            t = [self[12], self[13], self[14]]
            out = _identity()
            for r in range(3):
                for c in range(3):
                    out[r * 4 + c] = inv[r][c]
            for c in range(3):
                out[12 + c] = -sum(t[r] * inv[r][c] for r in range(3))
            return MMatrix(out)

    class MSpace:
        kTransform = 2

    class MTransformationMatrix(object):
        def __init__(self, matrix=None):
            self._matrix = MMatrix(matrix if matrix else _identity())

        def setScale(self, scale, space):
            values = list(self._matrix)
            for r in range(3):
                norm = math.sqrt(sum(values[r * 4 + c] ** 2 for c in range(3))) or 1.0
                for c in range(3):
                    values[r * 4 + c] = values[r * 4 + c] / norm * scale[r]
            self._matrix = MMatrix(values)

        def asMatrix(self):
            return self._matrix

    module.MMatrix = MMatrix
    module.MSpace = MSpace
    module.MTransformationMatrix = MTransformationMatrix
    return module
