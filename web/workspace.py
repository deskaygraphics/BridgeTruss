"""Per-browser-session workspace. Uses the same model and analysis APIs as Qt."""

import csv
import io
import json
import time
import zipfile
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from bridge_model import Model
from design import compare_trusses, parameter_study, volume
from editing import load_edit, member_edit
from moving_loads import (
    MovingResponse,
    combined_loads,
    deck_path,
    envelope,
    influence_lines,
    travel_limits,
    validate_axles,
)
from persistence import export_results, model_document, validate_document
from redundancy import redundancy_study


ROOT = Path(__file__).resolve().parents[1]
KINDS = ("Pratt Truss", "Warren Truss", "Howe Truss", "Custom Truss")
DEFAULT_SCENARIO = {
    "enabled": False,
    "front_N": 80000.0,
    "rear_N": 120000.0,
    "spacing_m": 4.0,
    "position_fraction": 0.0,
}
RESPONSE_INTERVAL = 0.25


def csv_bytes(rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerows(rows)
    return stream.getvalue().encode()


def numbers(text):
    try:
        values = [float(v.strip()) for v in text.split(",")]
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter comma-separated numbers") from exc
    if not values or not np.all(np.isfinite(values)):
        raise ValueError("Enter finite comma-separated numbers")
    return values


class Workspace:
    """Never cache this mutable object globally; keep one in st.session_state."""

    def __init__(self):
        self.model = Model()
        self.scenario = dict(DEFAULT_SCENARIO)
        self.revision = 0
        self.undo_state = None
        self.selection = None
        self.response_step = 0.5
        self.playing = False
        self.history = []
        self.playback_time = 0.0
        self.result_time = None
        self._last_tick = None
        self._response = None
        self._play_fraction = None
        self.play_generation = 0
        self.error = None
        self.clear_studies()
        self.analyze()

    def clear_studies(self):
        self.envelopes = None
        self.influence = None
        self.comparison = None
        self.study = None
        self.redundancy = None
        self.study_inputs = None
        self.redundancy_inputs = None

    def clear_history(self):
        self.playing = False
        self.history = []
        self.playback_time = 0.0
        self.result_time = None
        self._last_tick = None
        self._play_fraction = None

    def invalidate(self):
        self.model.results = None
        self.model.display_loads = None
        self._response = None
        self.error = None
        self.clear_studies()
        self.clear_history()
        self.revision += 1

    @staticmethod
    def validate_geometry(model):
        """Accept incomplete/unstable drafts, but never malformed geometry."""
        if len(model.nodes) > 200 or len(model.members) > 800:
            raise ValueError("Interactive workspace limit: 200 nodes and 800 members")
        for nid, xyz in model.nodes.items():
            if type(nid) is not int or nid < 0:
                raise ValueError("Node IDs must be nonnegative integers")
            if len(xyz) != 3 or not np.all(np.isfinite(xyz)) or xyz[2] != 0:
                raise ValueError("Use finite planar coordinates (z = 0)")
        check = deepcopy(model)
        check.members = []
        for m in model.members:
            member_edit(check, m.a, m.b, m.A, m.E)
        if set(model.loads) - set(model.nodes) or set(model.fixed) - set(model.nodes):
            raise ValueError("Loads and supports must refer to existing nodes")
        if any(len(v) != 2 or not np.all(np.isfinite(v)) for v in model.loads.values()):
            raise ValueError("Use finite Fx and Fy loads")
        if any(len(v) != 2 or any(type(x) is not bool for x in v) for v in model.fixed.values()):
            raise ValueError("Supports require two boolean restraints")

    def edit(self, operation):
        candidate = deepcopy(self.model)
        operation(candidate)
        self.validate_geometry(candidate)
        self.undo_state = deepcopy(self.model)
        self.model = candidate
        self.model.kind = "Custom Truss"
        self.selection = None
        self.invalidate()

    def undo(self):
        if self.undo_state is None:
            raise ValueError("No edit to undo")
        self.model = self.undo_state
        self.undo_state = None
        self.selection = None
        self.invalidate()

    def replace(self, model, scenario=None):
        self.validate_geometry(model)
        self.model = deepcopy(model)
        self.scenario = {**DEFAULT_SCENARIO, **(scenario or {})}
        self.undo_state = None
        self.selection = None
        self.invalidate()

    def new(self, kind="Custom Truss"):
        if kind not in KINDS:
            raise ValueError("Choose a known truss type")
        model = Model(kind)
        if kind == "Custom Truss":
            model.clear()
        self.replace(model)

    def add_node(self, nid, x, y):
        if nid in self.model.nodes:
            raise ValueError("Node ID already exists")
        self.edit(lambda m: m.nodes.update({nid: (float(x), float(y), 0.0)}))

    def move_node(self, nid, x, y):
        if nid not in self.model.nodes:
            raise ValueError("Choose an existing node")
        self.edit(lambda m: m.nodes.update({nid: (float(x), float(y), 0.0)}))

    def remove_node(self, nid):
        if nid not in self.model.nodes:
            raise ValueError("Choose an existing node")
        if any(nid in (m.a, m.b) for m in self.model.members):
            raise ValueError("Remove connected members before removing this node")

        def remove(m):
            del m.nodes[nid]
            m.loads.pop(nid, None)
            m.fixed.pop(nid, None)
            m.deck_nodes = [n for n in m.deck_nodes if n != nid]

        self.edit(remove)

    def set_member(self, a, b, area, elastic, member_id=None):
        index = None if member_id is None else member_id - 1
        self.edit(lambda m: member_edit(m, a, b, area, elastic, index))

    def remove_member(self, member_id):
        if not 1 <= member_id <= len(self.model.members):
            raise ValueError("Choose an existing member")
        self.edit(lambda m: m.members.pop(member_id - 1))

    def set_load(self, source, target, fx, fy, replace=False):
        if source != target and target in self.model.loads and not replace:
            raise ValueError("The target has a load; confirm replacement first")
        self.edit(lambda m: load_edit(m, source, target, fx, fy))

    def set_support(self, nid, fixed):
        if nid not in self.model.nodes:
            raise ValueError("Choose an existing node")
        self.edit(lambda m: m.fixed.update({nid: tuple(fixed)}))

    def set_deck(self, ids):
        def update(m):
            m.deck_nodes = list(ids)
            deck_path(m)

        self.edit(update)

    def clear_loads(self):
        self.edit(lambda m: m.loads.clear())

    @property
    def axles(self):
        return [
            (0.0, self.scenario["front_N"]),
            (self.scenario["spacing_m"], self.scenario["rear_N"]),
        ]

    @property
    def study_axles(self):
        return self.axles if self.scenario["enabled"] else None

    @property
    def position(self):
        return self.position_at(self.scenario["position_fraction"])

    def position_at(self, fraction):
        lo, hi = travel_limits(self.model, self.axles)
        # Include both axles fully outside the deck, just like the desktop.
        pad = max(hi - lo, 1.0) * 1e-8
        return lo - pad + fraction * (hi - lo + 2 * pad)

    def playback_clock(self):
        """Small animation packet; visual motion never invents numerical samples."""
        lo = self.position_at(0)
        hi = self.position_at(1)
        return {
            "run": [self.revision, self.play_generation],
            "playing": self.playing,
            "fraction": self._play_fraction if self.playing else self.scenario["position_fraction"],
            "rate": self.response_step / ((hi - lo) * RESPONSE_INTERVAL),
            "lo": lo,
            "hi": hi,
            "solved": self.position,
        }

    @staticmethod
    def validate_precision(scenario):
        # Main.open_project rejects values its Qt controls cannot represent.
        for key, divisor, decimals in [
            ("front_N", 1000, 2),
            ("rear_N", 1000, 2),
            ("spacing_m", 1, 2),
            ("position_fraction", 1, 3),
        ]:
            value = scenario[key] / divisor
            if not np.isclose(value, round(value, decimals), rtol=1e-12, atol=1e-12):
                raise ValueError(f"{key} exceeds desktop control precision; adjust it explicitly")

    def configure(self, enabled, front_N, rear_N, spacing_m, step):
        scenario = {
            **self.scenario,
            "enabled": enabled,
            "front_N": float(front_N),
            "rear_N": float(rear_N),
            "spacing_m": float(spacing_m),
        }
        validate_axles([(0, front_N), (spacing_m, rear_N)])
        if (
            type(enabled) is not bool
            or not np.isfinite(step)
            or step <= 0
            or max(front_N, rear_N) > 1e8
            or spacing_m > 1000
        ):
            raise ValueError("Use finite nonnegative axles ≤ 100000 kN, spacing ≤ 1000 m, step > 0")
        if enabled:
            deck_path(self.model)
        self.validate_precision(scenario)
        if scenario != self.scenario or step != self.response_step:
            self.scenario = scenario
            self.response_step = float(step)
            self.invalidate()

    def set_position(self, fraction, manual=True):
        if not np.isfinite(fraction) or not 0 <= fraction <= 1:
            raise ValueError("Position fraction must be between 0 and 1")
        if manual:
            self.clear_history()
        self.scenario["position_fraction"] = round(float(fraction), 3)
        # Full-passage studies do not depend on the current slider position.
        return self.analyze()

    def analyze(self):
        self.model.results = None
        self.model.display_loads = None
        self.error = None
        try:
            if self.scenario["enabled"]:
                if self._response is None:
                    self._response = MovingResponse(self.model)
                result = self._response.at(self.position, self.axles)
                self.model.results = result
                self.model.display_loads = combined_loads(self.model, self.position, self.axles)
            else:
                result = self.model.solve()
            return result
        except (ValueError, FloatingPointError, OverflowError) as exc:
            self.error = str(exc)
            self.playing = False
            raise ValueError(str(exc)) from exc

    def play(self):
        if not self.scenario["enabled"]:
            self.configure(
                True,
                self.scenario["front_N"],
                self.scenario["rear_N"],
                self.scenario["spacing_m"],
                self.response_step,
            )
        self.analyze()
        if self.scenario["position_fraction"] >= 1:
            raise ValueError("Vehicle has exited. Reset before playing again.")
        self.playing = True
        self._last_tick = time.monotonic()
        self._play_fraction = self.scenario["position_fraction"]
        self._play_anchor = self._play_fraction
        self._play_elapsed = 0.0
        self.play_generation += 1
        self.record()

    def pause(self):
        if self.playing:
            self.tick(sync=True)
        self.playing = False
        self._last_tick = None

    def reset(self):
        self.clear_history()
        self.scenario["position_fraction"] = 0.0
        return self.analyze()

    def tick(self, now=None, *, sync=False):
        if not self.playing:
            return
        now = time.monotonic() if now is None else now
        elapsed = max(0.0, now - self._last_tick)
        self._last_tick = now
        lo, hi = travel_limits(self.model, self.axles)
        length = hi - lo + 2 * max(hi - lo, 1.0) * 1e-8
        self._play_elapsed += elapsed
        increment = self.response_step / length
        self._play_fraction = min(
            1.0, self._play_anchor + self._play_elapsed / RESPONSE_INTERVAL * increment
        )
        # Skip delayed samples instead of letting latency slow the vehicle down.
        cycles = int((self._play_elapsed + 1e-9) / RESPONSE_INTERVAL)
        solved = (
            self._play_fraction
            if sync or self._play_fraction >= 1
            else min(1.0, self._play_anchor + cycles * increment)
        )
        fraction = round(solved, 3)
        remaining = (1 - self._play_anchor) / increment * RESPONSE_INTERVAL
        # This records actual elapsed playback time, not synthetic/backfilled frames.
        self.playback_time += min(elapsed, max(0.0, remaining - (self._play_elapsed - elapsed)))
        if fraction != self.scenario["position_fraction"]:
            self.set_position(fraction, manual=False)
            self.record()
        if fraction >= 1:
            self.playing = False
            self._last_tick = None

    def record(self):
        r = self.model.results
        if r is None or not self.scenario["enabled"]:
            return
        self.result_time = self.playback_time
        if self.history and self.history[-1][:2] == (self.result_time, self.position):
            return
        for i, nid in enumerate(r["ids"]):
            ux, uy = r["U"][2 * i : 2 * i + 2] * 1000
            self.history.append((self.result_time, self.position, nid, float(ux), float(uy)))
        # Bounded per-session storage: retain the most recent 1000 solved frames.
        self.history = self.history[-1000 * len(r["ids"]) :]

    def compute_envelopes(self):
        self.envelopes = envelope(self.model, self.axles)
        return self.envelopes

    def compute_influence(self):
        self.influence = influence_lines(self.model)
        return self.influence

    def compare(self, density=7850):
        self.comparison = compare_trusses(deepcopy(self.model), self.study_axles, density)
        return self.comparison

    def explore(self, heights, chords, webs, displacement_mm, stress_MPa, density):
        args = (heights, chords, webs, displacement_mm, stress_MPa, density)
        self.study = parameter_study(
            self.model,
            heights,
            chords,
            webs,
            displacement_mm / 1000,
            stress_MPa * 1e6,
            self.study_axles,
            density,
        )
        self.study_inputs = args
        return self.study

    def study_member(self, member_id, factors):
        self.redundancy = redundancy_study(self.model, member_id, factors, self.study_axles)
        self.redundancy_inputs = (member_id, factors)
        return self.redundancy

    def load_json(self, content):
        if len(content) > 2_000_000:
            raise ValueError("Model upload limit: 2 MB")
        try:
            doc = json.loads(content)
            # Bound allocations before the shared stiffness validation.
            if len(doc["nodes"]) > 200 or len(doc["members"]) > 800:
                raise ValueError("Interactive workspace limit: 200 nodes and 800 members")
            model, scenario = validate_document(doc)
            if scenario:
                self.validate_precision(scenario)
            self.validate_geometry(model)
        except (KeyError, TypeError, IndexError, OverflowError, UnicodeError) as exc:
            raise ValueError(f"Invalid model file: {exc}") from exc
        self.replace(model, scenario)

    def model_json(self):
        doc = model_document(self.model, self.scenario)
        validate_document(doc)
        return json.dumps(doc, indent=2, allow_nan=False).encode()

    def member_rows(self):
        r = self.model.results
        if r is None:
            return []
        return [
            {
                "Member": i + 1,
                "Node i": m.a,
                "Node j": m.b,
                "Length (m)": r["lengths"][i],
                "Force (kN)": r["forces"][i] / 1000,
                "Stress (MPa)": r["stresses"][i] / 1e6,
                "State": "Tension"
                if r["forces"][i] > 1e-6
                else "Compression"
                if r["forces"][i] < -1e-6
                else "Near-zero",
            }
            for i, m in enumerate(self.model.members)
        ]

    def node_rows(self):
        r = self.model.results
        if r is None:
            return []
        return [
            {
                "Node": nid,
                "ux (mm)": r["U"][2 * i] * 1000,
                "uy (mm)": r["U"][2 * i + 1] * 1000,
                "Rx (kN)": r["R"][2 * i] / 1000,
                "Ry (kN)": r["R"][2 * i + 1] / 1000,
            }
            for i, nid in enumerate(r["ids"])
        ]

    def history_csv(self):
        return csv_bytes(
            [["playback_time_s", "front_x_m", "node", "ux_mm", "uy_mm"], *self.history]
        )

    def bundle(self, figures=None):
        if self.model.results is None:
            raise ValueError("Analyze a valid model before exporting")
        self.pause()
        stream = io.BytesIO()
        with TemporaryDirectory(prefix="bridgetruss-") as tmp:
            export_results(
                tmp,
                self.model,
                self.model.results,
                self.scenario,
                self.envelopes,
                self.study,
                self.redundancy,
            )
            Path(tmp, "displacement_history.csv").write_bytes(self.history_csv())
            for name, content in (figures or {}).items():
                Path(tmp, name).write_bytes(content)
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(Path(tmp).iterdir()):
                    archive.write(path, path.name)
        return stream.getvalue()

    def summary(self):
        r = self.model.results
        if r is None:
            return {}
        return {
            "Nodes": len(self.model.nodes),
            "Members": len(self.model.members),
            "Peak |uy| (mm)": float(max(abs(r["U"][1::2])) * 1000),
            "Peak |N| (kN)": float(max(abs(r["forces"])) / 1000),
            "Steel mass (kg)": volume(self.model) * 7850,
            "Strain energy (J)": r["strain_energy"],
            "Relative residual": r["relative_residual"],
            "Condition number": r["condition_number"],
        }
