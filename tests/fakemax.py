"""A recording stand-in for ``pymxs``, so the Max code can be tested here.

Same intent as :mod:`fakemaya`: a node tree, properties, modifiers and 4x4
row-vector matrices, with every property write recorded. It does not model MassFX
and makes no claim to; what it checks is that the right property gets the right
number in the right unit, which is where a script like this actually goes wrong.
"""

import math
import sys
import types


def identity():
    return [1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0]


class Matrix3(list):
    """Max's row-vector 4x4: a child's world matrix is ``local * parent``."""

    def __init__(self, values=None):
        super(Matrix3, self).__init__(values if values else identity())

    def __mul__(self, other):
        out = [0.0] * 16
        for r in range(4):
            for c in range(4):
                out[r * 4 + c] = sum(self[r * 4 + k] * other[k * 4 + c] for k in range(4))
        return Matrix3(out)


def inverse(matrix):
    rot = [matrix[r * 4 + c] for r in range(3) for c in range(3)]
    scales = [math.sqrt(sum(rot[r * 3 + c] ** 2 for c in range(3))) or 1.0 for r in range(3)]
    inv = [[rot[c * 3 + r] / (scales[c] ** 2) for c in range(3)] for r in range(3)]
    t = [matrix[12], matrix[13], matrix[14]]
    out = identity()
    for r in range(3):
        for c in range(3):
            out[r * 4 + c] = inv[r][c]
    for c in range(3):
        out[12 + c] = -sum(t[r] * inv[r][c] for r in range(3))
    return Matrix3(out)


def rotateYMatrix(degrees):
    a = math.radians(degrees)
    out = identity()
    out[0], out[2] = math.cos(a), -math.sin(a)
    out[8], out[10] = math.sin(a), math.cos(a)
    return Matrix3(out)


class Node:
    def __init__(self, name, kind="Dummy", parent=None, scene=None):
        self.name = name
        self._kind = kind
        self._parent = None
        self.children = []
        self.properties = {}
        self.user_properties = {}
        self.modifiers = []
        self.transform = Matrix3()
        self.controller = Controller()
        self._scene = scene
        if parent is not None:
            self.parent = parent

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, value):
        if self._parent is not None and self in self._parent.children:
            self._parent.children.remove(self)
        self._parent = value
        if value is not None:
            value.children.append(self)


class Controller:
    def __init__(self):
        self.tracks = {"Rotation": RotationTrack()}


class RotationTrack:
    def __init__(self):
        self.enabled = {}
        self.ranges = {}


class Modifier:
    def __init__(self, kind):
        self._kind = kind
        self.properties = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self.properties.get(name, 0.0)

    def __setattr__(self, name, value):
        if name.startswith("_") or name == "properties":
            object.__setattr__(self, name, value)
        else:
            self.properties[name] = value
            SCENE.writes.append((self._kind, name, value))


class Scene:
    def __init__(self):
        self.nodes = []
        self.writes = []
        self.deleted = []

    def add(self, name, kind="Dummy", parent=None):
        node = Node(name, kind, parent, self)
        self.nodes.append(node)
        return node

    def find(self, name):
        for node in self.nodes:
            if node.name == name:
                return node
        return None


SCENE = Scene()


class GeometryClass:
    pass


class UConstraintClass:
    """Callable like MAXScript's ``UConstraint()`` and comparable like a class."""

    def __call__(self):
        node = SCENE.add("UConstraint%03d" % (len(SCENE.nodes) + 1), "UConstraint")
        for name, default in (
                ("body0", None), ("body1", None), ("breakable", False),
                ("maxForce", 100.0), ("maxTorque", 10.0),
                ("linearModeX", 1), ("linearModeY", 1), ("linearModeZ", 1),
                ("linearPosition", 100.0),
                ("swing1Mode", 1), ("swing1Angle", 45.0),
                ("swing2Mode", 1), ("swing2Angle", 45.0),
                ("twistMode", 1), ("twistAngleLow", 45.0), ("twistAngleHigh", 45.0)):
            node.properties[name] = default
        return node

    def __repr__(self):
        return "UConstraint"


def install():
    """Put a fake ``pymxs`` into ``sys.modules``. Returns the scene."""
    global SCENE
    SCENE = Scene()

    runtime = types.ModuleType("pymxs.runtime")

    uconstraint = UConstraintClass()

    def classOf(thing):
        return getattr(thing, "_kind", None) or type(thing).__name__

    def superClassOf(node):
        return GeometryClass if getattr(node, "_kind", "") == "Editable_Mesh" else None

    def isProperty(node, name):
        return name in getattr(node, "properties", {})

    def getProperty(node, name):
        store = getattr(node, "properties", {})
        if name not in store:
            raise RuntimeError("no property %s" % name)
        return store[name]

    def setProperty(node, name, value):
        store = getattr(node, "properties", None)
        if store is None or name not in store:
            raise RuntimeError("no property %s" % name)
        store[name] = value
        SCENE.writes.append((node.name, name, value))

    def getUserProp(node, name):
        return node.user_properties.get(name)

    def setUserProp(node, name, value):
        node.user_properties[name] = value
        SCENE.writes.append((node.name, name, value))

    def getUserPropBuffer(node):
        return "\n".join("%s = %s" % (k, v) for k, v in node.user_properties.items())

    def MassFX_RBody():
        return Modifier("MassFX_RBody")

    def addModifier(node, modifier):
        node.modifiers.append(modifier)

    def deleteModifier(node, modifier):
        if modifier in node.modifiers:
            node.modifiers.remove(modifier)

    def delete(node):
        SCENE.deleted.append(node.name)
        if node.parent is not None and node in node.parent.children:
            node.parent.children.remove(node)
        if node in SCENE.nodes:
            SCENE.nodes.remove(node)

    def getPropertyController(controller, name):
        return controller.tracks.get(name)

    def setLimitEnabled(track, axis, state):
        track.enabled[axis] = state

    def setLimitRange(track, axis, lower, upper):
        track.ranges[axis] = (lower, upper)

    for name, value in (
            ("UConstraint", uconstraint), ("classOf", classOf),
            ("superClassOf", superClassOf), ("GeometryClass", GeometryClass),
            ("isProperty", isProperty), ("getProperty", getProperty),
            ("setProperty", setProperty), ("getUserProp", getUserProp),
            ("setUserProp", setUserProp), ("getUserPropBuffer", getUserPropBuffer),
            ("MassFX_RBody", MassFX_RBody), ("addModifier", addModifier),
            ("deleteModifier", deleteModifier), ("delete", delete),
            ("inverse", inverse), ("rotateYMatrix", rotateYMatrix),
            ("Matrix3", Matrix3),
            ("getPropertyController", getPropertyController),
            ("setLimitEnabled", setLimitEnabled), ("setLimitRange", setLimitRange)):
        setattr(runtime, name, value)

    runtime.objects = SCENE.nodes

    pymxs = types.ModuleType("pymxs")
    pymxs.runtime = runtime

    sys.modules["pymxs"] = pymxs
    sys.modules["pymxs.runtime"] = runtime

    return SCENE
