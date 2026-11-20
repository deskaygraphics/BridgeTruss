"""Read-only redundancy comparisons; the active dashboard model is never edited."""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QComboBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QAbstractItemView,
    QMessageBox,
    QDialog,
    QScrollArea,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from redundancy import redundancy_study
from redundancy_plots import draw_comparison


def fmt(value, scale=1):
    return "—" if value is None else f"{value * scale:.6g}"


class RedundancyPanel(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        note = QLabel(
            "Reduce one member's area; 0 physically removes it. The active model stays unchanged. "
            "Enable moving loads for full-passage envelopes; otherwise static loads only. "
            "Presets are determinate: open examples/redundant_bridge.json (M18) or "
            "benchmark_redundant.json (M4) to demonstrate redundancy. "
            "Rejected cases have no valid response, not a predicted collapse load."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Original member ID"))
        self.member = QSpinBox()
        self.member.setRange(1, max(1, len(window.model.members)))
        self.member.valueChanged.connect(self.invalidate)
        controls.addWidget(self.member)
        controls.addWidget(QLabel("Area factors A/A0"))
        self.factors = QComboBox()
        self.factors.setEditable(True)
        self.factors.addItem("1,0.75,0.5,0.25,0")
        self.factors.editTextChanged.connect(self.invalidate)
        controls.addWidget(self.factors)
        self.run_button = QPushButton("Run Redundancy Study")
        self.run_button.clicked.connect(self.run)
        controls.addWidget(self.run_button)
        layout.addLayout(controls)
        self.summary = QLabel("No redundancy study calculated.")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        row.addWidget(QLabel("Compare candidate"))
        self.case = QComboBox()
        self.case.currentIndexChanged.connect(self.show_case)
        row.addWidget(self.case)
        self.enlarge_button = QPushButton("Enlarge Comparison")
        self.enlarge_button.clicked.connect(self.enlarge)
        self.enlarge_button.setEnabled(False)
        row.addWidget(self.enlarge_button)
        layout.addLayout(row)
        self.detail = QTabWidget()
        self.plot = FigureCanvasQTAgg(Figure(figsize=(11, 7), facecolor="white"))
        self.plot.setMinimumSize(1050, 680)
        plot_scroll = QScrollArea()
        plot_scroll.setWidgetResizable(True)
        plot_scroll.setWidget(self.plot)
        self.detail.addTab(plot_scroll, "Force diagrams / deflection")
        self.cases = self.table(
            [
                "A/A0",
                "Status",
                "Peak |uy| (mm)",
                "uy / baseline",
                "Node at peak |uy|",
                "Deflection front x (m)",
                "Peak |N| (kN)",
                "Critical member",
                "Force front x (m)",
                "m+r−2j (count only)",
                "Condition (common case)",
                "Reason",
            ],
            "Case summary",
        )
        self.members = self.table(
            [
                "Original M",
                "Endpoints",
                "Baseline N (kN)",
                "Candidate N (kN)",
                "ΔN (kN)",
                "Envelope min (kN)",
                "Envelope max (kN)",
                "Front x at min (m)",
                "Front x at max (m)",
                "State",
                "Candidate stress (MPa)",
            ],
            "Member comparison",
        )
        self.nodes = self.table(
            [
                "Node",
                "Baseline ux (mm)",
                "Candidate ux (mm)",
                "Δux (mm)",
                "Baseline uy (mm)",
                "Candidate uy (mm)",
                "Δuy (mm)",
            ],
            "Common-case displacements",
        )
        layout.addWidget(self.detail)

    def table(self, headers, title):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.detail.addTab(table, title)
        return table

    def invalidate(self, *args):
        self.window.redundancy = None
        if not hasattr(self, "case"):
            return
        self.member.blockSignals(True)
        self.member.setMaximum(max(1, len(self.window.model.members)))
        self.member.blockSignals(False)
        had_results = self.case.count() or bool(self.plot.figure.axes)
        self.case.clear()
        self.enlarge_button.setEnabled(False)
        if hasattr(self, "large_dialog"):
            self.large_dialog.close()
            self.large_plot.figure.clear()
        for table in (self.cases, self.members, self.nodes):
            table.setRowCount(0)
        self.summary.setText("Inputs changed; run redundancy study to update.")
        if had_results:
            self.plot.figure.clear()
            self.plot.draw_idle()

    def run(self):
        window = self.window
        window.stop_vehicle()
        self.invalidate()
        try:
            factors = [float(v.strip()) for v in self.factors.currentText().split(",")]
            window.redundancy = redundancy_study(
                window.model,
                self.member.value(),
                factors,
                window.axles() if window.moving_enabled else None,
            )
            window.fill_table(
                self.cases,
                [
                    [
                        r["area_factor"],
                        r["status"],
                        fmt(r.get("peak_abs_uy_m"), 1000),
                        fmt(r.get("peak_deflection_ratio")),
                        r.get("critical_node", "—"),
                        fmt(r.get("deflection_front_x_m")),
                        fmt(r.get("peak_abs_force_N"), 0.001),
                        r.get("critical_member", "—"),
                        fmt(r.get("force_front_x_m")),
                        r["count_m_plus_r_minus_2j"],
                        fmt(r.get("snapshot", {}).get("condition_number")),
                        r.get("reason", ""),
                    ]
                    for r in window.redundancy["cases"]
                ],
            )
            self.case.blockSignals(True)
            for r in window.redundancy["cases"]:
                self.case.addItem(
                    f"A/A0 = {r['area_factor']:g}"
                    + (" (removed)" if r["removed"] else "")
                    + f" — {r['status']}"
                )
            self.case.setCurrentIndex(len(window.redundancy["cases"]) - 1)
            self.case.blockSignals(False)
            self.show_case()
            window.tabs.setCurrentWidget(self)
        except Exception as exc:
            self.case.blockSignals(False)
            self.invalidate()
            QMessageBox.warning(window, "Redundancy study", str(exc))

    def show_case(self, *args):
        study = self.window.redundancy
        if study is None or self.case.currentIndex() < 0:
            return
        index = self.case.currentIndex()
        row = study["cases"][index]
        position = study["comparison_front_x_m"]
        common = "static loads" if position is None else f"common front x = {position:.6g} m"
        self.summary.setText(
            f"M{study['selected_member']} {study['selected_endpoints']}; {study['loading']}. "
            f"Force/displacement comparison: {common}, not the slider position. "
            "Summary peaks may occur at different positions. "
            + (
                f"Peak |uy| / baseline = {fmt(row['peak_deflection_ratio'])}. "
                if row["status"] == "stable"
                else row["reason"] + ". "
            )
            + "No buckling, damage evolution or progressive-collapse analysis."
        )
        self.members.setRowCount(0)
        self.nodes.setRowCount(0)
        if row["status"] == "stable":
            env = row["envelopes"]
            self.window.fill_table(
                self.members,
                [
                    [
                        m["member_id"],
                        f"{m['node_i']} — {m['node_j']}",
                        fmt(m["baseline_force_N"], 0.001),
                        fmt(m["candidate_force_N"], 0.001),
                        fmt(m["delta_force_N"], 0.001),
                        *[
                            fmt(
                                env["forces_N"][key][m["member_id"] - 1],
                                0.001 if key in ("min", "max") else 1,
                            )
                            if env
                            else "—"
                            for key in ("min", "max", "x_min", "x_max")
                        ],
                        "present" if m["present"] else "removed",
                        fmt(row["snapshot"]["stresses_Pa"][m["member_id"] - 1], 1e-6),
                    ]
                    for m in row["member_comparison"]
                ],
            )
            base = study["cases"][0]["snapshot"]["U_m"]
            u = row["snapshot"]["U_m"]
            self.window.fill_table(
                self.nodes,
                [
                    [
                        nid,
                        *[
                            fmt(value, 1000)
                            for k in (0, 1)
                            for value in (
                                base[2 * i + k],
                                u[2 * i + k],
                                u[2 * i + k] - base[2 * i + k],
                            )
                        ],
                    ]
                    for i, nid in enumerate(study["node_ids"])
                ],
            )
        draw_comparison(self.plot.figure, study, index)
        self.plot.draw_idle()
        self.enlarge_button.setEnabled(True)
        if hasattr(self, "large_dialog") and self.large_dialog.isVisible():
            draw_comparison(self.large_plot.figure, study, index)
            self.large_plot.draw_idle()

    def enlarge(self):
        study = self.window.redundancy
        if study is None or self.case.currentIndex() < 0:
            return
        if not hasattr(self, "large_dialog"):
            self.large_dialog = QDialog(self.window)
            self.large_dialog.setWindowTitle("Redundancy study — same-load-case comparison")
            self.large_dialog.resize(1250, 830)
            layout = QVBoxLayout(self.large_dialog)
            self.large_plot = FigureCanvasQTAgg(Figure(figsize=(13, 8), facecolor="white"))
            layout.addWidget(self.large_plot)
        draw_comparison(self.large_plot.figure, study, self.case.currentIndex())
        self.large_dialog.show()
        self.large_dialog.raise_()
        self.large_plot.draw_idle()
