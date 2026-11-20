"""Linear elastic pin-jointed truss analysis. Internal units: m, N, Pa."""

import numpy as np


class PreparedTruss:
    """Validated stiffness assembly, reused for multiple right-hand sides."""

    def __init__(self, model):
        self.dim = model["dimension"]
        if self.dim not in (2, 3):
            raise ValueError("Dimension must be 2 or 3")
        nodes, members = model["nodes"], model["members"]
        self.ids = sorted(nodes)
        if not nodes or not members:
            raise ValueError("Add nodes and members before analysis")
        self.idx = {nid: i for i, nid in enumerate(self.ids)}
        self.ndof = self.dim * len(nodes)
        self.K = np.zeros((self.ndof, self.ndof))
        self.F = np.zeros(self.ndof)
        self.data = {}
        fixed, connected, pairs = [], set(), set()
        for nid in self.ids:
            node = nodes[nid]
            for field in ("xyz", "load", "fix"):
                if len(node[field]) < self.dim:
                    raise ValueError(f"Node {nid}: incomplete {field}")
            if not np.all(np.isfinite(node["xyz"])) or not np.all(np.isfinite(node["load"])):
                raise ValueError(f"Node {nid}: coordinates and loads must be finite")
            if any(not isinstance(v, (bool, np.bool_)) for v in node["fix"]):
                raise ValueError(f"Node {nid}: restraints must be boolean")
            base = self.idx[nid] * self.dim
            self.F[base : base + self.dim] = node["load"][: self.dim]
            fixed.extend(base + k for k in range(self.dim) if node["fix"][k])
        for mid, member in members.items():
            a, b = member["i"], member["j"]
            if a not in nodes or b not in nodes or a == b:
                raise ValueError(f"Member {mid}: invalid endpoints")
            pair = frozenset((a, b))
            if pair in pairs:
                raise ValueError(f"Member {mid}: duplicate connection")
            pairs.add(pair)
            connected.update((a, b))
            vec = np.asarray(nodes[b]["xyz"][: self.dim], float) - nodes[a]["xyz"][: self.dim]
            length = float(np.linalg.norm(vec))
            E, area = float(member["E"]), float(member["A"])
            if not np.all(np.isfinite([length, E, area])) or length < 1e-10 or min(E, area) <= 0:
                raise ValueError(f"Member {mid}: finite positive length, E and area required")
            direction = vec / length
            v = np.r_[-direction, direction]
            dofs = [self.idx[n] * self.dim + k for n in (a, b) for k in range(self.dim)]
            self.K[np.ix_(dofs, dofs)] += E * area / length * np.outer(v, v)
            self.data[mid] = (dofs, v, length, E, area)
        # An orphan anchor with every translation restrained has no unknown DOF.
        # Keep it (including its load and reaction) when its last bar is removed.
        if any(nid not in connected and not all(nodes[nid]["fix"][: self.dim]) for nid in nodes):
            raise ValueError("Disconnected node: connect every node before analysis")
        if not np.all(np.isfinite(self.K)):
            raise ValueError("Stiffness exceeds numerical range; check units and member properties")
        self.free = np.setdiff1d(np.arange(self.ndof), fixed)
        self.Kff = self.K[np.ix_(self.free, self.free)]
        if len(self.free):
            eigenvalues = np.linalg.eigvalsh(self.Kff)
            if eigenvalues[0] <= max(eigenvalues[-1], 1.0) * 1e-12:
                raise ValueError("Unstable or ill-conditioned truss: check supports and bracing")
            self.condition = float(eigenvalues[-1] / eigenvalues[0])
        else:
            self.condition = 1.0

    def load_vector(self, loads):
        out = np.zeros(self.ndof)
        for nid, values in loads.items():
            if nid not in self.idx or len(values) != self.dim or not np.all(np.isfinite(values)):
                raise ValueError("Load case requires existing nodes and finite components")
            base = self.idx[nid] * self.dim
            out[base : base + self.dim] = values
        return out

    def solve_many(self, forces):
        forces = np.asarray(forces, float)
        if forces.ndim != 2 or forces.shape[0] != self.ndof or not np.all(np.isfinite(forces)):
            raise ValueError("Invalid load-case matrix")
        u = np.zeros_like(forces)
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                if len(self.free):
                    u[self.free] = np.linalg.solve(self.Kff, forces[self.free])
                return [self.recover(u[:, k], forces[:, k]) for k in range(forces.shape[1])]
        except FloatingPointError as exc:
            raise ValueError("Numerical overflow: reduce loads or check units/properties") from exc

    def recover(self, u, force):
        reaction = self.K @ u - force
        if not np.all(np.isfinite(u)) or not np.all(np.isfinite(reaction)):
            raise ValueError("Nonfinite structural response: check loads, units and properties")
        members = {}
        for mid, (dofs, v, length, E, area) in self.data.items():
            axial = float(E * area / length * (v @ u[dofs]))
            if not np.isfinite(axial) or not np.isfinite(axial / area):
                raise ValueError("Nonfinite member response: check loads, units and properties")
            members[mid] = {"force": axial, "stress": axial / area, "length": length}
        residual = float(np.linalg.norm(reaction[self.free], np.inf)) if len(self.free) else 0.0
        energy = float(0.5 * u @ self.K @ u)
        if not np.isfinite(energy):
            raise ValueError("Nonfinite strain energy: check loads, units and properties")
        return {
            "U": {
                nid: u[i * self.dim : (i + 1) * self.dim].tolist() for i, nid in enumerate(self.ids)
            },
            "R": {
                nid: reaction[i * self.dim : (i + 1) * self.dim].tolist()
                for i, nid in enumerate(self.ids)
            },
            "members": members,
            "K": self.K,
            "F": force.copy(),
            "ids": self.ids,
            "strain_energy": energy,
            "relative_residual": residual / max(float(np.linalg.norm(force, np.inf)), 1.0),
            "condition_number": self.condition,
        }


def solve(model):
    prepared = PreparedTruss(model)
    return prepared.solve_many(prepared.F[:, None])[0]
