"""Display-independent planar dashboard model and solver adapter."""

from dataclasses import dataclass
import numpy as np
from solver import solve


@dataclass
class Member:
    a: int
    b: int
    A: float = 0.005
    E: float = 200e9


class Model:
    def __init__(self, kind="Pratt Truss"):
        self.kind = kind
        self.nodes = {}
        self.members = []
        self.loads = {}
        self.fixed = {}
        self.results = None
        self.display_loads = None
        self.generate(kind)

    def generate(self, kind):
        self.kind = kind
        self.nodes = {}
        self.members = []
        self.loads = {}
        self.fixed = {}
        self.results = None
        self.display_loads = None
        # 5 bays, 25 m span, 4 m height; all joints planar for 2D solver
        for i in range(6):
            self.nodes[i] = (i * 5.0, 0.0, 0.0)
        for i in range(1, 5):
            self.nodes[i + 5] = (i * 5.0, 4.0, 0.0)

        def add(a, b):
            if a != b and not any({m.a, m.b} == {a, b} for m in self.members):
                self.members.append(Member(a, b))

        for i in range(5):
            add(i, i + 1)
        for i in range(1, 4):
            add(i + 5, i + 6)
        for i in range(1, 5):
            add(i, i + 5)
        add(0, 6)
        add(9, 5)
        if kind == "Pratt Truss":
            for a, b in [(6, 2), (7, 3), (8, 4)]:
                add(a, b)
        elif kind == "Howe Truss":
            for a, b in [(1, 7), (2, 8), (3, 9)]:
                add(a, b)
        else:
            for a, b in [(6, 2), (2, 8), (8, 4)]:
                add(a, b)
        self.fixed = {0: (True, True), 5: (False, True)}
        self.loads = {i: (0.0, -50000.0) for i in (6, 7, 8, 9)}
        self.deck_nodes = list(range(6))

    def clear(self):
        self.kind = "Custom Truss"
        self.nodes.clear()
        self.members.clear()
        self.loads.clear()
        self.fixed.clear()
        self.results = None
        self.display_loads = None
        self.deck_nodes = []

    def to_solver(self, loads=None):
        loads = self.loads if loads is None else loads
        if set(loads) - set(self.nodes) or set(self.fixed) - set(self.nodes):
            raise ValueError("Loads and supports must reference existing nodes")
        if any(len(xyz) != 3 or xyz[2] != 0 for xyz in self.nodes.values()):
            raise ValueError("Dashboard analysis is planar: all z coordinates must be zero")
        return {
            "dimension": 2,
            "nodes": {
                nid: {
                    "xyz": list(xyz),
                    "fix": list(self.fixed.get(nid, (False, False))),
                    "load": list(loads.get(nid, (0.0, 0.0))),
                }
                for nid, xyz in self.nodes.items()
            },
            "members": {
                i + 1: {"i": m.a, "j": m.b, "E": m.E, "A": m.A} for i, m in enumerate(self.members)
            },
        }

    def solve(self, loads=None):
        self.results = None
        self.results = dashboard_result(solve(self.to_solver(loads)))
        return self.results


def dashboard_result(result):
    ids = result["ids"]
    return {
        "ids": ids,
        "ix": {nid: i for i, nid in enumerate(ids)},
        "U": np.array([result["U"][nid] for nid in ids]).ravel(),
        "R": np.array([result["R"][nid] for nid in ids]).ravel(),
        "F": result["F"],
        "forces": np.array([v["force"] for v in result["members"].values()]),
        "stresses": np.array([v["stress"] for v in result["members"].values()]),
        "lengths": [v["length"] for v in result["members"].values()],
        "strain_energy": result["strain_energy"],
        "relative_residual": result["relative_residual"],
        "condition_number": result["condition_number"],
    }
