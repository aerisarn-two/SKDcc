"""A Skyrim particle system as a Geometry Nodes simulation.

Blender's particle system is legacy, and every limit this add-on kept running
into is a limit of that rather than of Blender:

| wanted | legacy particles | geometry nodes |
| --- | --- | --- |
| fade a particle over its life | Particle Info is not implemented in Eevee — driving anything from it renders **nothing** | a named attribute on the instance domain, which Eevee reads |
| a camera-facing sprite | the billboard type was removed with the 2.8 engine | rotate the instances |
| step an animation sheet | nothing | pick the cell per instance |

So the simulation is built here instead: points spawned over the emission
window, aged, moved, and killed when their life runs out, then instanced with a
quad that carries ``ParticleAge`` for the material to read.

What it is not is a reimplementation of Gamebryo. The engine's modifier stack
runs in an order with its own semantics (``nif-particle-spec.md`` §3), and this
reads the handful of terms that describe where particles go: where they are
born, how fast, in what direction, how long they last, and what pulls on them.
Everything else is still carried on the node for a reader that wants it, and is
reported rather than pretended at.
"""

import bpy

from . import schema

#: What the simulation stores on each point, and what the material reads.
AGE = "Age"
LIFETIME = "Lifetime"
VELOCITY = "Velocity"
SEED = "Seed"
SPIN = "Spin"

#: On the instance domain, for the shader. Named for what a material asks for
#: rather than for what the simulation calls it.
PARTICLE_AGE = "ParticleAge"

#: One number per particle, fixed for its life. The atlas needs it: a
#: BSPSysSubTexModifier starts each particle on a different frame, and a system
#: with cells but no modifier gives each particle one cell and leaves it there
#: -- sixteen smoke puffs are sixteen shapes, not one shape sixteen times.
PARTICLE_SEED = "ParticleSeed"


def _out(node, name="Value"):
    """The output that matches the node's data type.

    A Random Value node and a Named Attribute node both carry one socket per
    type and hide the rest, so ``outputs[0]`` is whichever type happens to come
    first rather than the one selected -- asking a vector attribute for its
    value that way returns the float socket, and everything downstream silently
    reads zero. Which is what made every particle spawn at the origin and stay
    there.
    """
    for socket in node.outputs:
        if socket.enabled and (socket.name == name or name is None):
            return socket

    return node.outputs[0]


def _value_socket(node):
    """The Value input that matches a Store Named Attribute's data type.

    The node carries one socket per type and hides the rest, so the one to write
    is the only enabled one rather than a fixed index.
    """
    for socket in node.inputs:
        if socket.name == "Value" and socket.enabled:
            return socket

    return node.inputs[-1]


class _Graph:
    """A node tree being laid out left to right."""

    def __init__(self, tree):
        self.tree = tree

    def add(self, kind, x, y, **fields):
        node = self.tree.nodes.new(kind)
        node.location = (x, y)

        for key, value in fields.items():
            setattr(node, key, value)

        return node

    def link(self, out, node, socket=None):
        """Link an output to an input.

        The input may be given as a node plus a socket name or index, or as a
        socket on its own -- which is what the typed Value sockets come back as.
        """
        if socket is None:
            target = node
        elif isinstance(socket, (str, int)):
            target = node.inputs[socket]
        else:
            target = socket

        self.tree.links.new(out, target)

    def named(self, x, y, name, kind="FLOAT"):
        node = self.add("GeometryNodeInputNamedAttribute", x, y, data_type=kind)
        node.inputs["Name"].default_value = name
        return node

    @staticmethod
    def read(node):
        """A named attribute's value, from the socket its type actually uses."""
        return _out(node, "Attribute")

    def store(self, x, y, name, kind, domain="POINT"):
        node = self.add(
            "GeometryNodeStoreNamedAttribute", x, y, data_type=kind, domain=domain
        )
        node.inputs["Name"].default_value = name
        return node


def build_group(name, settings, sprite):
    """The node group for one system.

    ``settings`` is a plain dict of the numbers read off the NIF, so this knows
    nothing about the file format and the caller knows nothing about nodes.
    """
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    g = _Graph(tree)
    out = g.add("NodeGroupOutput", 2200, 0)

    step = settings["step"]

    sim_in = g.add("GeometryNodeSimulationInput", 0, 0)
    sim_out = g.add("GeometryNodeSimulationOutput", 1400, 0)
    sim_in.pair_with_output(sim_out)

    age = g.named(-250, -300, AGE)
    life = g.named(-250, -460, LIFETIME)
    velocity = g.named(-250, -620, VELOCITY, "FLOAT_VECTOR")

    # --- the survivors get older -------------------------------------------
    older = g.add("ShaderNodeMath", 0, -300, operation="ADD")
    older.inputs[1].default_value = step
    g.link(_Graph.read(age), older, 0)

    aged = g.store(250, 0, AGE, "FLOAT")
    g.link(sim_in.outputs["Geometry"], aged, "Geometry")
    g.link(older.outputs[0], _value_socket(aged))

    # --- and move, by the velocity they carry -------------------------------
    travel = g.add("ShaderNodeVectorMath", 250, -620, operation="SCALE")
    travel.inputs["Scale"].default_value = step
    g.link(_Graph.read(velocity), travel, 0)

    moved = g.add("GeometryNodeSetPosition", 500, 0)
    g.link(aged.outputs["Geometry"], moved, "Geometry")
    g.link(travel.outputs[0], moved, "Offset")

    # --- gravity, as an acceleration on the velocity ------------------------
    pull = settings["gravity"]

    if any(pull):
        push = g.add("ShaderNodeVectorMath", 500, -620, operation="ADD")
        push.inputs[1].default_value = tuple(a * step for a in pull)
        g.link(_Graph.read(velocity), push, 0)

        accelerated = g.store(700, 0, VELOCITY, "FLOAT_VECTOR")
        g.link(moved.outputs["Geometry"], accelerated, "Geometry")
        g.link(push.outputs[0], _value_socket(accelerated))
        living = accelerated
    else:
        living = moved

    # --- the old ones go ----------------------------------------------------
    spent = g.add("ShaderNodeMath", 700, -300, operation="GREATER_THAN")
    g.link(_Graph.read(age), spent, 0)
    g.link(_Graph.read(life), spent, 1)

    kill = g.add("GeometryNodeDeleteGeometry", 900, 0, domain="POINT")
    g.link(living.outputs["Geometry"], kill, "Geometry")
    g.link(spent.outputs[0], kill, "Selection")

    # --- and new ones arrive, while the window is open ----------------------
    born = _spawn(g, settings)

    join = g.add("GeometryNodeJoinGeometry", 1200, 0)
    g.link(born.outputs["Geometry"], join, join.inputs[0])
    g.link(kill.outputs["Geometry"], join, join.inputs[0])
    g.link(join.outputs[0], sim_out, "Geometry")

    # --- one quad each, carrying how far through its life it is -------------
    info = g.add("GeometryNodeObjectInfo", 1500, -400)
    info.inputs["Object"].default_value = sprite

    instances = g.add("GeometryNodeInstanceOnPoints", 1700, 0)
    g.link(sim_out.outputs["Geometry"], instances, "Points")
    g.link(info.outputs["Geometry"], instances, "Instance")

    facing = _billboard(g, settings["camera"]) if settings.get("camera") is not None else None
    turning = _spin(g, settings, age)

    if turning is not None and facing is not None:
        # In the quad's own frame, not the world's: the billboard has already
        # aimed it at the camera, and spinning about a world axis would tip it
        # back out of the view. Local Y is the quad's normal -- it is built in
        # the XZ plane -- so turning about that is a turn in its own plane.
        compose = g.add("FunctionNodeRotateRotation", 1600, -150)
        compose.rotation_space = "LOCAL"
        g.link(facing, compose, 0)
        g.link(turning, compose, 1)
        g.link(compose.outputs[0], instances, "Rotation")
    elif turning is not None:
        g.link(turning, instances, "Rotation")
    elif facing is not None:
        g.link(facing, instances, "Rotation")

    fraction = g.add("ShaderNodeMath", 1700, -300, operation="DIVIDE", use_clamp=True)
    g.link(_Graph.read(age), fraction, 0)
    g.link(_Graph.read(life), fraction, 1)

    # BSPSysScaleModifier: the engine walks a curve of sizes as a particle ages.
    # Read as its two ends, which for the shapes these take is close and costs
    # two nodes rather than twenty-eight.
    start, end = settings.get("scale_over_life", (1.0, 1.0))

    if abs(start - end) > 1e-4 or abs(start - 1.0) > 1e-4:
        taper = g.add("ShaderNodeMapRange", 1700, -500)
        taper.clamp = True
        taper.inputs["To Min"].default_value = start
        taper.inputs["To Max"].default_value = end
        g.link(fraction.outputs[0], taper, "Value")
        g.link(taper.outputs["Result"], instances, "Scale")

    published = g.store(1950, 0, PARTICLE_AGE, "FLOAT", domain="INSTANCE")
    g.link(instances.outputs["Instances"], published, "Geometry")
    g.link(fraction.outputs[0], _value_socket(published))

    seeded = g.store(2150, 0, PARTICLE_SEED, "FLOAT", domain="INSTANCE")
    g.link(published.outputs["Geometry"], seeded, "Geometry")
    g.link(_Graph.read(g.named(1950, -700, SEED)), _value_socket(seeded))

    g.link(seeded.outputs["Geometry"], out, out.inputs[0])

    return tree


def _vary(g, node, index, frame):
    """Make a Random Value actually vary.

    Without an ID it returns the same number for every element it is evaluated
    on, and without a seed it returns the same number every frame. A freshly
    made Points geometry has no ID attribute of its own, so every particle
    spawned in one frame landed on exactly the same spot with exactly the same
    speed -- a hundred of them stacked invisibly on one point.
    """
    if "ID" in node.inputs:
        g.link(index.outputs["Index"], node, "ID")

    if "Seed" in node.inputs:
        g.link(frame.outputs["Frame"], node, "Seed")


def _spawn(g, settings):
    """The points born this frame, with their life and first velocity on them."""
    # How many, and only while the emitter is running. The window is in frames
    # because that is what the scene counts in.
    frame = g.add("GeometryNodeInputSceneTime", 100, 700)

    after = g.add("ShaderNodeMath", 280, 640, operation="GREATER_THAN")
    after.inputs[1].default_value = settings["start_frame"] - 0.5
    g.link(frame.outputs["Frame"], after, 0)

    before = g.add("ShaderNodeMath", 280, 780, operation="LESS_THAN")
    before.inputs[1].default_value = settings["end_frame"] + 0.5
    g.link(frame.outputs["Frame"], before, 0)

    running = g.add("ShaderNodeMath", 450, 700, operation="MULTIPLY")
    g.link(after.outputs[0], running, 0)
    g.link(before.outputs[0], running, 1)

    cycle = max(int(settings.get("cycle", 0)), 0)
    on_frames = max(int(settings.get("on_frames", 0)), 0)

    if cycle and on_frames < cycle:
        # A looping controller emits for part of each turn. Wrap the frame into
        # one turn and ask whether it is inside the window; a window that fills
        # the turn needs no gate at all, which is the common case and why this
        # is conditional.
        turn = g.add("ShaderNodeMath", 450, 1000, operation="MODULO")
        turn.inputs[1].default_value = float(cycle)

        since = g.add("ShaderNodeMath", 280, 1000, operation="SUBTRACT")
        since.inputs[1].default_value = float(settings["start_frame"])
        g.link(frame.outputs["Frame"], since, 0)
        g.link(since.outputs[0], turn, 0)

        within = g.add("ShaderNodeMath", 620, 1000, operation="LESS_THAN")
        within.inputs[1].default_value = float(on_frames) + 0.5
        g.link(turn.outputs[0], within, 0)

        looped = g.add("ShaderNodeMath", 620, 920, operation="MULTIPLY")
        g.link(running.outputs[0], looped, 0)
        g.link(within.outputs[0], looped, 1)
        running = looped

    period = max(int(settings.get("period", 1)), 1)

    if period > 1:
        # One spawn every `period` frames. An emitter slower than the frame rate
        # rounded up to one per frame emits several times too many -- the
        # campfire's embers are 7.5 a second against 24 frames.
        beat = g.add("ShaderNodeMath", 450, 860, operation="MODULO")
        beat.inputs[1].default_value = float(period)
        g.link(frame.outputs["Frame"], beat, 0)

        on_beat = g.add("ShaderNodeMath", 620, 860, operation="LESS_THAN")
        on_beat.inputs[1].default_value = 0.5
        g.link(beat.outputs[0], on_beat, 0)

        gated = g.add("ShaderNodeMath", 620, 780, operation="MULTIPLY")
        g.link(running.outputs[0], gated, 0)
        g.link(on_beat.outputs[0], gated, 1)
        running = gated

    count = g.add("ShaderNodeMath", 620, 700, operation="MULTIPLY")
    count.inputs[1].default_value = float(settings["per_frame"])
    g.link(running.outputs[0], count, 0)

    points = g.add("GeometryNodePoints", 800, 500)
    g.link(count.outputs[0], points, "Count")

    # Where in the emitter volume, which the NIF gives as a box, a cylinder or a
    # sphere. A box of the right size is a fair stand-in for all three at the
    # scale these are used, and the shape is reported rather than approximated
    # silently.
    half = settings["half_extent"]
    centre = settings.get("centre", (0.0, 0.0, 0.0))
    index = g.add("GeometryNodeInputIndex", 450, 200)

    # Around where the emitter sits in the system's frame, not around the frame
    # itself: the flame above a campfire is born at the emitter and the smoke a
    # metre higher.
    where = g.add("FunctionNodeRandomValue", 620, 400, data_type="FLOAT_VECTOR")
    where.inputs[0].default_value = tuple(c - h for c, h in zip(centre, half))
    where.inputs[1].default_value = tuple(c + h for c, h in zip(centre, half))
    _vary(g, where, index, frame)
    g.link(_out(where), points, "Position")

    lived = g.store(1000, 500, LIFETIME, "FLOAT")
    g.link(points.outputs["Points"], lived, "Geometry")

    spread = settings["life_variation"]

    if spread > 0.0:
        vary = g.add("FunctionNodeRandomValue", 800, 300, data_type="FLOAT")
        vary.inputs[2].default_value = max(settings["life"] - spread, 1e-3)
        vary.inputs[3].default_value = settings["life"] + spread
        _vary(g, vary, index, frame)
        g.link(_out(vary), _value_socket(lived))
    else:
        _value_socket(lived).default_value = settings["life"]

    thrown = g.store(1200, 500, VELOCITY, "FLOAT_VECTOR")
    g.link(lived.outputs["Geometry"], thrown, "Geometry")

    # Along the emitter's own +Z, which is the axis the engine births along
    # (see schema.EMISSION_AXIS), at the speed the emitter states.
    speed = settings["speed"]
    wobble = settings["speed_variation"]

    if wobble > 0.0:
        fast = g.add("FunctionNodeRandomValue", 1000, 300, data_type="FLOAT")
        fast.inputs[2].default_value = max(speed - wobble, 0.0)
        fast.inputs[3].default_value = speed + wobble
        _vary(g, fast, index, frame)
        scaled = g.add("ShaderNodeVectorMath", 1150, 300, operation="SCALE")
        scaled.inputs[0].default_value = schema.EMISSION_AXIS
        g.link(_out(fast), scaled, "Scale")
        g.link(scaled.outputs[0], _value_socket(thrown))
    else:
        _value_socket(thrown).default_value = tuple(a * speed for a in schema.EMISSION_AXIS)

    # And a number of its own, drawn once and kept. Anything that has to differ
    # between particles but not over one particle's life reads this: which atlas
    # cell it wears, which frame its animation starts on.
    marked = g.store(1400, 500, SEED, "FLOAT")
    g.link(thrown.outputs["Geometry"], marked, "Geometry")

    die = g.add("FunctionNodeRandomValue", 1250, 300, data_type="FLOAT")
    die.inputs[2].default_value = 0.0
    die.inputs[3].default_value = 1.0
    _vary(g, die, index, frame)
    g.link(_out(die), _value_socket(marked))

    # NiPSysRotationModifier: how fast this one turns, and which way. Drawn here
    # rather than worked out in the shader because it has to be the same number
    # for the particle's whole life, and a magnitude with a sign is two draws
    # that must not be the same draw -- taking the sign off the speed would make
    # slow particles and anticlockwise particles the same particles.
    speed, spread, _angle, flip = settings["spin"]

    if abs(speed) > 1e-6 or spread > 1e-6:
        spun = g.store(1600, 500, SPIN, "FLOAT")
        g.link(marked.outputs["Geometry"], spun, "Geometry")

        rate = g.add("FunctionNodeRandomValue", 1400, 300, data_type="FLOAT")
        rate.inputs[2].default_value = speed - spread
        rate.inputs[3].default_value = speed + spread
        _vary(g, rate, index, frame)

        if flip:
            coin = g.add("FunctionNodeRandomValue", 1400, 100, data_type="INT")
            coin.inputs[4].default_value = 0
            coin.inputs[5].default_value = 1
            _vary(g, coin, index, frame)

            # The seed is the frame, so a second draw on the same frame repeats
            # the first. Offset it, or every particle born together would spin
            # the same way.
            if "Seed" in coin.inputs:
                offset = g.add("ShaderNodeMath", 1250, 100, operation="ADD")
                offset.inputs[1].default_value = 7919.0
                g.link(frame.outputs["Frame"], offset, 0)
                g.link(offset.outputs[0], coin, "Seed")

            sign = g.add("ShaderNodeMath", 1500, 100, operation="MULTIPLY_ADD")
            sign.inputs[1].default_value = 2.0
            sign.inputs[2].default_value = -1.0
            g.link(_out(coin), sign, 0)

            signed = g.add("ShaderNodeMath", 1550, 300, operation="MULTIPLY")
            g.link(_out(rate), signed, 0)
            g.link(sign.outputs[0], signed, 1)
            g.link(signed.outputs[0], _value_socket(spun))
        else:
            g.link(_out(rate), _value_socket(spun))

        return spun

    return marked


def _spin(g, settings, age):
    """A rotation in the quad's own plane, from NiPSysRotationModifier.

    ``angle = initial + speed * age``, with the speed drawn once per particle at
    birth. The campfire's smoke turns at 15 degrees a second give or take 15,
    which is the difference between a rising puff and a rising decal.
    """
    speed, spread, initial, _flip = settings["spin"]

    if abs(speed) <= 1e-6 and spread <= 1e-6 and abs(initial) <= 1e-6:
        return None

    if abs(speed) > 1e-6 or spread > 1e-6:
        turned = g.add("ShaderNodeMath", 1400, -150, operation="MULTIPLY")
        g.link(_Graph.read(g.named(1250, -150, SPIN)), turned, 0)
        g.link(_Graph.read(age), turned, 1)

        total = g.add("ShaderNodeMath", 1500, -150, operation="ADD")
        total.inputs[1].default_value = initial
        g.link(turned.outputs[0], total, 0)
        angle = total.outputs[0]
    else:
        angle = None

    axis = g.add("FunctionNodeAxisAngleToRotation", 1550, -300)
    axis.inputs["Axis"].default_value = (0.0, 1.0, 0.0)

    if angle is not None:
        g.link(angle, axis, "Angle")
    else:
        axis.inputs["Angle"].default_value = initial

    return axis.outputs[0]


def _billboard(g, camera):
    """A rotation that turns each quad to face the camera.

    The engine draws a Skyrim particle as a billboard -- always square to the
    view -- and the legacy particle system had that as a type until 2.8 removed
    it. Here it is just a rotation per instance, which is the whole reason the
    simulation is worth having: instancing carries per-element data and the old
    system did not.

    The quad's own normal is its +Y (it is built in the XZ plane), so +Y is what
    gets aligned. Pivoted about Z rather than freely, so a flame stays upright
    and turns to face you rather than tipping over to point at the lens.
    """
    where = g.add("GeometryNodeInputPosition", 1350, -700)

    eye = g.add("GeometryNodeObjectInfo", 1350, -900)
    eye.inputs["Object"].default_value = camera
    eye.transform_space = "RELATIVE"

    toward = g.add("ShaderNodeVectorMath", 1550, -800, operation="SUBTRACT")
    g.link(eye.outputs["Location"], toward, 0)
    g.link(where.outputs["Position"], toward, 1)

    facing = g.add("FunctionNodeAlignRotationToVector", 1700, -800)
    facing.axis = "Y"
    facing.pivot_axis = "Z"
    g.link(toward.outputs[0], facing, "Vector")

    return facing.outputs["Rotation"]
