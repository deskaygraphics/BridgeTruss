"""Atomic edits validate geometry before changing the active planar model."""

import numpy as np
from bridge_model import Member


def member_edit(model, a, b, area, elastic, index=None):
    if a not in model.nodes or b not in model.nodes or a == b:
        raise ValueError("Choose two different existing nodes")
    if index is not None and not 0 <= index < len(model.members):
        raise ValueError("The selected member no longer exists")
    if any({m.a, m.b} == {a, b} for i, m in enumerate(model.members) if i != index):
        raise ValueError("A member already connects these nodes")
    length = np.linalg.norm(np.asarray(model.nodes[a], float) - model.nodes[b])
    if (
        not np.all(np.isfinite([area, elastic, length]))
        or min(area, elastic) <= 0
        or length < 1e-10
    ):
        raise ValueError("Positive finite area, E and member length are required")
    member = Member(a, b, area, elastic)
    if index is None:
        model.members.append(member)
    else:
        model.members[index] = member


def load_edit(model, source, target, fx, fy):
    if source not in model.nodes or target not in model.nodes or not np.all(np.isfinite([fx, fy])):
        raise ValueError("Loads require existing nodes and finite components")
    # The GUI asks before replacing an existing load at a different target.
    model.loads.pop(source, None)
    if fx or fy:
        model.loads[target] = (float(fx), float(fy))
    else:
        model.loads.pop(target, None)
