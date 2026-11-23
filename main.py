import sys
import csv
import math
import json
import os
import time
from copy import deepcopy
from pathlib import Path
from datetime import datetime
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QPushButton,
    QComboBox,
    QLabel,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QSplitter,
    QFormLayout,
    QDoubleSpinBox,
    QSpinBox,
    QCheckBox,
    QMessageBox,
    QInputDialog,
    QFileDialog,
    QScrollArea,
    QSlider,
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QTextBrowser,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.collections import LineCollection
from matplotlib.colors import TwoSlopeNorm
from matplotlib.patches import Polygon, Circle

try:
    if os.environ.get("BRIDGETRUSS_NO_3D") == "1":
        raise ImportError("Illustrative 3D disabled by BRIDGETRUSS_NO_3D")
    import pyvista as pv
    from pyvistaqt import QtInteractor

    HAS_3D = True
except Exception:
    HAS_3D = False

from bridge_model import Model, Member
from moving_loads import (
    combined_loads,
    vehicle_loads,
    travel_limits,
    deck_path,
    envelope,
    influence_lines,
    MovingResponse,
)
from persistence import save_model, load_model, export_results, model_document
from design import compare_trusses, parameter_study
from redundancy_ui import RedundancyPanel
from editing import member_edit, load_edit
from scene3d import Scene3D
from desktop_traffic import TrafficDialog
from traffic import (
    positioned_vehicles,
    preset_vehicle,
    scenario_axles,
    traffic_scenario,
    validate_scenario,
    validate_control_precision,
)


APP_ICON = Path(__file__).resolve().parent / "assets" / "bridgetruss.png"


def configure_graphics():
    # Some parent shells disable both GLX and EGL even when the driver supports them.
    if HAS_3D and os.environ.get("QT_XCB_GL_INTEGRATION") == "none":
        os.environ.pop("QT_XCB_GL_INTEGRATION")


class Plot(FigureCanvasQTAgg):
    def __init__(self, figsize=(5, 3), *, interactive=False):
        self.fig = Figure(figsize=figsize, facecolor="#ffffff")
        super().__init__(self.fig)
        self.ax = self.fig.add_subplot(111)
        self.fig.subplots_adjust(left=0.07, right=0.96, top=0.93, bottom=0.12)
        self.interactive = interactive
        self.label_scale = 1.0
        self._home_limits = None
        self._data_limits = None
        self._load_labels = []
        self._geometry_key = None
        self._manual_view = False
        self._has_model = False
        self._pan_anchor = None
        if interactive:
            self.setMouseTracking(True)
            self.setToolTip(
                "Wheel: zoom at the pointer. Left/middle-drag: pan. Double-click: fit. "
                "Use View Controls → 2D label size to enlarge text independently of zoom."
            )
            self.mpl_connect("scroll_event", self._on_scroll)
            self.mpl_connect("button_press_event", self._on_press)
            self.mpl_connect("motion_notify_event", self._on_motion)
            self.mpl_connect("button_release_event", self._on_release)
            self.mpl_connect("figure_leave_event", self._on_release)
            self.mpl_connect("resize_event", self._on_resize)

    def reset_view(self):
        self._manual_view = False
        self._on_release()
        if self._home_limits is not None:
            self.ax.set_xlim(self._home_limits[0])
            self.ax.set_ylim(self._home_limits[1])
            self.draw_idle()

    def set_label_scale(self, scale):
        if not math.isfinite(scale):
            raise ValueError("Label scale must be finite")
        self.label_scale = min(2.5, max(0.75, float(scale)))
        self._scale_labels()
        self._update_home_limits()
        self.draw_idle()

    def _on_resize(self, event):
        self._on_release()
        self._update_home_limits()

    def _update_home_limits(self, *, preserve_view=True):
        if self._data_limits is None:
            return
        saved = (
            (self.ax.get_xlim(), self.ax.get_ylim())
            if preserve_view and self._manual_view
            else None
        )
        self.ax.set_xlim(self._data_limits[0])
        self.ax.set_ylim(self._data_limits[1])
        renderer = self.get_renderer()
        # Offset-point text has a fixed pixel height even when geometry is zoomed.
        # Reserve that physical space in the automatic fit, especially on small panels.
        for _ in range(3):
            self.ax.apply_aspect()
            width, height = self.ax.bbox.width, self.ax.bbox.height
            if width <= 0 or height <= 0:
                break
            xmin, xmax = self.ax.get_xlim()
            ymin, ymax = self.ax.get_ylim()
            left, right, top = xmin, xmax, ymax
            for label in self._load_labels:
                bounds = label.get_window_extent(renderer)
                px, py = self.ax.transData.transform(label.xy)
                q_top = min(0.8, max(0.0, (bounds.y1 - py + 3) / height))
                q_left = min(0.8, max(0.0, (px - bounds.x0 + 3) / width))
                q_right = min(0.8, max(0.0, (bounds.x1 - px + 3) / width))
                x, y = label.xy
                top = max(top, (y - q_top * ymin) / (1 - q_top))
                left = min(left, (x - q_left * xmax) / (1 - q_left))
                right = max(right, (x - q_right * xmin) / (1 - q_right))
            self.ax.set_xlim(left, right)
            self.ax.set_ylim(ymin, top)
        self._home_limits = (self.ax.get_xlim(), self.ax.get_ylim())
        if saved is not None:
            self.ax.set_xlim(saved[0])
            self.ax.set_ylim(saved[1])

    def _scale_labels(self):
        if not self.interactive:
            return
        for artist in [*self.ax.texts, self.ax.title, self.ax.xaxis.label, self.ax.yaxis.label]:
            if not hasattr(artist, "_bridge_fontsize"):
                artist._bridge_fontsize = artist.get_fontsize()
            artist.set_fontsize(artist._bridge_fontsize * self.label_scale)
            if hasattr(artist, "get_anncoords") and artist.get_anncoords() == "offset points":
                if not hasattr(artist, "_bridge_offset"):
                    artist._bridge_offset = artist.get_position()
                artist.set_position(
                    tuple(value * self.label_scale for value in artist._bridge_offset)
                )
        self.ax.tick_params(labelsize=7 * self.label_scale)
        self.fig.subplots_adjust(
            left=min(0.18, 0.07 * self.label_scale),
            right=0.96,
            top=1 - min(0.30, 0.12 * self.label_scale),
            bottom=min(0.28, 0.14 * self.label_scale),
        )

    def zoom_at(self, x, y, steps):
        """Apply one bounded zoom, preserving the data point under the cursor."""
        if not self.interactive or not self._has_model or self._home_limits is None:
            return False
        if (
            x is None
            or y is None
            or steps is None
            or not np.all(np.isfinite([x, y, steps]))
            or steps == 0
        ):
            return False
        xmin, xmax = self.ax.get_xlim()
        ymin, ymax = self.ax.get_ylim()
        width, height = xmax - xmin, ymax - ymin
        home_width = self._home_limits[0][1] - self._home_limits[0][0]
        home_height = self._home_limits[1][1] - self._home_limits[1][0]
        lower = max(home_width * 1e-4 / width, home_height * 1e-4 / height)
        upper = min(home_width * 20 / width, home_height * 20 / height)
        factor = float(np.clip(1.2 ** (-np.clip(steps, -10, 10)), lower, upper))
        new_x = (x - (x - xmin) * factor, x + (xmax - x) * factor)
        new_y = (y - (y - ymin) * factor, y + (ymax - y) * factor)
        if not np.all(np.isfinite([*new_x, *new_y])):
            return False
        self._on_release()
        self.ax.set_xlim(new_x)
        self.ax.set_ylim(new_y)
        self._manual_view = True
        self.draw_idle()
        return True

    def _on_scroll(self, event):
        if event.inaxes is self.ax:
            self.zoom_at(event.xdata, event.ydata, event.step)

    def _on_press(self, event):
        if not self.interactive or not self._has_model or event.inaxes is not self.ax:
            return
        if event.dblclick:
            self.reset_view()
        elif (
            event.button in (1, 2)
            and event.x is not None
            and event.y is not None
            and np.all(np.isfinite([event.x, event.y]))
        ):
            self._pan_anchor = (event.x, event.y, self.ax.get_xlim(), self.ax.get_ylim())
            self.setCursor(Qt.ClosedHandCursor)

    def _on_motion(self, event):
        if (
            self._pan_anchor is None
            or event.x is None
            or event.y is None
            or not np.all(np.isfinite([event.x, event.y]))
        ):
            return
        x, y, limits_x, limits_y = self._pan_anchor
        box = self.ax.bbox
        if box.width <= 0 or box.height <= 0:
            return
        dx = (event.x - x) * (limits_x[1] - limits_x[0]) / box.width
        dy = (event.y - y) * (limits_y[1] - limits_y[0]) / box.height
        new_x = tuple(value - dx for value in limits_x)
        new_y = tuple(value - dy for value in limits_y)
        if np.all(np.isfinite([*new_x, *new_y])):
            self.ax.set_xlim(new_x)
            self.ax.set_ylim(new_y)
            self._manual_view = True
            self.draw_idle()

    def _on_release(self, event=None):
        self._pan_anchor = None
        if self.interactive:
            self.unsetCursor()

    def draw_model(self, model, mode="geometry", show_labels=False):
        ax = self.ax
        key = (
            tuple((nid, tuple(xyz)) for nid, xyz in sorted(model.nodes.items())),
            tuple((member.a, member.b) for member in model.members),
        )
        saved_view = None
        if self.interactive:
            if key == self._geometry_key:
                if self._manual_view or self._pan_anchor is not None:
                    saved_view = (ax.get_xlim(), ax.get_ylim())
            else:
                self._manual_view = False
                self._on_release()
            self._geometry_key = key
            self._has_model = bool(model.nodes)
        ax.clear()
        self._load_labels = []
        r = model.results
        segments = []
        colors = []
        for k, m in enumerate(model.members):
            p = model.nodes[m.a]
            q = model.nodes[m.b]
            segments.append([(p[0], p[1]), (q[0], q[1])])
            colors.append(r["forces"][k] / 1000 if r is not None else 0)
        if mode == "force" and r is not None and len(colors):
            vmax = max(abs(min(colors)), abs(max(colors)), 1)
            lc = LineCollection(
                segments,
                cmap="coolwarm",
                norm=TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax),
                linewidths=2.8,
            )
            lc.set_array(np.array(colors))
        else:
            lc = LineCollection(segments, colors="#1475d2", linewidths=2.6)
        ax.add_collection(lc)
        for nid, (x, y, z) in model.nodes.items():
            ax.plot(x, y, "o", ms=5, mfc="white", mec="#0b4984", zorder=3)
            if show_labels:
                # Position labels toward the interior: bottom joints above, top joints below.
                top_y = max(pt[1] for pt in model.nodes.values())
                offset = -0.33 if y > top_y / 2 else 0.33
                ax.annotate(
                    f"N{nid}",
                    (x, y),
                    xytext=(0, -13 if offset < 0 else 13),
                    textcoords="offset points",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="#17304a",
                    weight="bold",
                    zorder=7,
                    bbox=dict(
                        boxstyle="round,pad=0.12", facecolor="white", alpha=0.85, edgecolor="none"
                    ),
                )
        # Distinct engineering support symbols.  The support constraint tuple is
        # (restrain_x, restrain_y); symbols reflect the actual solver restraints.
        # Marker sizes scale with model geometry so small custom trusses remain legible.
        if model.nodes:
            xs = [v[0] for v in model.nodes.values()]
            ys = [v[1] for v in model.nodes.values()]
            scale = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
            w = max(scale * 0.025, 0.12)
            h = w * 0.9
            for nid, (restrain_x, restrain_y) in model.fixed.items():
                if nid not in model.nodes:
                    continue
                x, y, _ = model.nodes[nid]
                if restrain_x and restrain_y:  # pin: triangular bearing, no rollers
                    ax.add_patch(
                        Polygon(
                            [(x, y - h * 0.12), (x - w, y - h * 1.65), (x + w, y - h * 1.65)],
                            closed=True,
                            facecolor="#6c88aa",
                            edgecolor="#263e58",
                            linewidth=1.2,
                            zorder=4,
                        )
                    )
                    ax.plot(
                        [x - w * 1.25, x + w * 1.25],
                        [y - h * 1.8, y - h * 1.8],
                        color="#263e58",
                        lw=1.5,
                        zorder=4,
                    )
                elif (
                    restrain_y and not restrain_x
                ):  # horizontal motion free: roller beneath bearing
                    ax.add_patch(
                        Polygon(
                            [(x, y - h * 0.12), (x - w, y - h * 1.35), (x + w, y - h * 1.35)],
                            closed=True,
                            facecolor="#6c88aa",
                            edgecolor="#263e58",
                            linewidth=1.2,
                            zorder=4,
                        )
                    )
                    for dx in (-w * 0.5, w * 0.5):
                        ax.add_patch(
                            Circle(
                                (x + dx, y - h * 1.58),
                                w * 0.24,
                                facecolor="white",
                                edgecolor="#263e58",
                                linewidth=1.2,
                                zorder=5,
                            )
                        )
                    ax.plot(
                        [x - w * 1.25, x + w * 1.25],
                        [y - h * 1.94, y - h * 1.94],
                        color="#263e58",
                        lw=1.5,
                        zorder=4,
                    )
                elif restrain_x and not restrain_y:  # vertical motion free: roller against wall
                    ax.add_patch(
                        Polygon(
                            [(x + w * 0.15, y), (x + w * 1.4, y - h), (x + w * 1.4, y + h)],
                            closed=True,
                            facecolor="#6c88aa",
                            edgecolor="#263e58",
                            linewidth=1.2,
                            zorder=4,
                        )
                    )
                    for dy in (-h * 0.5, h * 0.5):
                        ax.add_patch(
                            Circle(
                                (x + w * 1.62, y + dy),
                                w * 0.22,
                                facecolor="white",
                                edgecolor="#263e58",
                                linewidth=1.2,
                                zorder=5,
                            )
                        )
                    ax.plot(
                        [x + w * 1.98, x + w * 1.98],
                        [y - h * 1.3, y + h * 1.3],
                        color="#263e58",
                        lw=1.5,
                        zorder=4,
                    )
        for nid, (fx, fy) in (
            model.display_loads if model.display_loads is not None else model.loads
        ).items():
            if nid in model.nodes and (fx or fy):
                x, y, _ = model.nodes[nid]
                mag = math.hypot(fx, fy)
                length = max(scale * 0.075, 0.15) if self.interactive else 1.5
                tail = (x - fx / mag * length, y - fy / mag * length + 0.12)
                ax.annotate(
                    "",
                    xy=(x, y + 0.12),
                    xytext=tail,
                    arrowprops=dict(arrowstyle="->", color="red", lw=1.8),
                )
                if self.interactive:
                    ax.update_datalim([tail])
                    label = ax.annotate(
                        f"{mag / 1000:.3g} kN",
                        xy=tail,
                        xytext=(0, 7),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        clip_on=True,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.5),
                    )
                    self._load_labels.append(label)
                else:
                    ax.text(x, y + 1.8, f"{mag / 1000:.0f} kN", ha="center", fontsize=7)
        if mode == "deformed" and r is not None:
            xs = [p[0] for p in model.nodes.values()]
            span = max(xs) - min(xs) or 1
            maxu = max(abs(r["U"])) or 1
            scale = 0.09 * span / maxu
            for m in model.members:
                a, b = r["ix"][m.a], r["ix"][m.b]
                p = model.nodes[m.a]
                q = model.nodes[m.b]
                ax.plot(
                    [p[0] + scale * r["U"][2 * a], q[0] + scale * r["U"][2 * b]],
                    [p[1] + scale * r["U"][2 * a + 1], q[1] + scale * r["U"][2 * b + 1]],
                    color="#e74b45",
                    lw=2,
                )
            title = (
                f"Deformation ×{scale:.0f}"
                if self.interactive
                else f"Deformed geometry (scale ×{scale:.0f})"
            )
            ax.set_title(title, fontsize=10, pad=2)
        ax.set_aspect("auto" if self.interactive else "equal", adjustable="datalim")
        ax.margins(x=0.08, y=0.35)
        ax.grid(alpha=0.15)
        ax.tick_params(labelsize=7)
        if not model.nodes:
            ax.text(
                0.5,
                0.5,
                "New Project — Blank Workspace\nUse Add Node, then Add Member",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#47627e",
                fontsize=12,
            )
            ax.set_xlim(0, 25)
            ax.set_ylim(0, 10)
        if self.interactive:
            self._data_limits = (ax.get_xlim(), ax.get_ylim())
            self._scale_labels()
            self._update_home_limits(preserve_view=False)
            if saved_view is not None:
                ax.set_xlim(saved_view[0])
                ax.set_ylim(saved_view[1])
        self.draw_idle()


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.model = Model()
        self.envelopes = None
        self.study = None
        self.redundancy = None
        self.influence = None
        self._comparison_key = None
        self.moving_enabled = False
        self._traffic_vehicles = None
        self.play_timer = QTimer(self)
        self.play_timer.setTimerType(Qt.PreciseTimer)
        self.play_timer.timeout.connect(self.animate_vehicle)
        self._moving_response = None
        self._moving_response_key = None
        self._visual_fraction = None
        self._in_animation = False
        self._last_animation_cycle = 0
        self._playback_time = 0.0
        self._playback_base = 0.0
        self._result_time = None
        self._history_configuration = None
        self.displacement_history = []
        self._last_history_sample = None
        self._camera_initialized = False
        self._3d_presented = False
        self.scene3d = None
        self.selected_3d = None
        self.attach_anchor = None
        self._undo_3d = None
        self.setWindowTitle("BridgeTruss — Verified Planar Analysis")
        self.setWindowIcon(QIcon(str(APP_ICON)))
        self.resize(1550, 940)
        self.setStyleSheet(
            """QMainWindow,QWidget{background:#19232e;color:#edf2f8;font-size:12px} QGroupBox{border:1px solid #3b4d61;border-radius:5px;margin-top:15px;padding:9px;font-weight:bold} QGroupBox::title{subcontrol-origin:margin;left:8px;padding:0 4px} QPushButton,QComboBox,QDoubleSpinBox,QSpinBox{background:#2b3b4d;color:#f5f8fc;border:1px solid #4a6076;border-radius:4px;padding:6px} QPushButton:hover{background:#365b83} QPushButton#primary{background:#2476e5} QTabWidget::pane{border:1px solid #3b4d61} QTabBar::tab{background:#283849;color:#fff;padding:8px 15px} QTabBar::tab:selected{background:#2263b5} QTableWidget{background:#f7f9fc;color:#172638;gridline-color:#cad4df} QHeaderView::section{background:#dce5ed;color:#172638;padding:5px} QCheckBox{padding:4px}"""
        )
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(8, 8, 8, 8)
        header = QHBoxLayout()
        title = QLabel("BridgeTruss | Planar Analysis")
        title.setStyleSheet("font-size:19px;font-weight:bold;color:#fff")
        header.addWidget(title)
        header.addStretch()
        for label, callback in [
            ("New Project", self.new_project),
            ("Open", self.open_project),
            ("Save Model", self.save_project),
            ("Analyze", self.analyze),
            ("Export Results", self.export_bundle),
            ("Member CSV", self.export_csv),
        ]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            header.addWidget(b)
        v.addLayout(header)
        upper = QSplitter(Qt.Horizontal)
        v.addWidget(upper, 5)
        side = QWidget()
        side.setMaximumWidth(230)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("Truss Type")
        g = QVBoxLayout(group)
        self.kind = QComboBox()
        self.kind.addItems(["Pratt Truss", "Warren Truss", "Howe Truss", "Custom Truss"])
        self.kind.currentTextChanged.connect(self.change_kind)
        g.addWidget(self.kind)
        sv.addWidget(group)
        group = QGroupBox("Model Tools")
        g = QVBoxLayout(group)
        for label, callback in [
            ("⊕  Add Node", self.add_node),
            ("╱  Add Member", self.add_member),
            ("✕  Delete Member", self.delete_member),
            ("↔  Move Node", self.move_node),
            ("↓  Add / Change Load", self.add_load),
            ("△  Set Support", self.add_support),
            ("Edit Member Properties", self.edit_member),
            ("Select Deck Nodes", self.select_deck),
            ("Clear Static Loads", self.clear_static_loads),
        ]:
            b = QPushButton(label)
            b.clicked.connect(callback)
            if label == "Select Deck Nodes":
                b.setToolTip(
                    "For moving loads, select at least two existing joints at the same elevation "
                    "with distinct x coordinates. Presets already select their bottom deck joints."
                )
            elif label == "Clear Static Loads":
                b.setToolTip(
                    "Remove static nodal loads to study the vehicle alone. "
                    "Otherwise static and moving loads are combined."
                )
            g.addWidget(b)
        sv.addWidget(group)
        group = QGroupBox("New Member Properties")
        form = QFormLayout(group)
        self.area = QDoubleSpinBox()
        self.area.setDecimals(5)
        self.area.setRange(0.00001, 100)
        self.area.setValue(0.005)
        self.elastic = QDoubleSpinBox()
        self.elastic.setRange(1, 1000)
        self.elastic.setValue(200)
        form.addRow("Area (m²)", self.area)
        form.addRow("E (GPa)", self.elastic)
        sv.addWidget(group)
        sv.addStretch()
        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(side)
        side_scroll.setMinimumWidth(235)
        side_scroll.setMaximumWidth(245)
        upper.addWidget(side_scroll)
        self.tabs = QTabWidget()
        self.view2 = Plot((8, 4))
        self.tabs.addTab(self.view2, "2D View")
        self.panel3d = QWidget()
        layout3d = QVBoxLayout(self.panel3d)
        self.build_3d_controls(layout3d)
        if HAS_3D:
            self.view3 = QtInteractor(self.panel3d)
            layout3d.addWidget(self.view3)
            self.scene3d = Scene3D(self.view3, pv, self.queue_3d_selection)
        else:
            self.view3 = QLabel("Install pyvista and pyvistaqt to enable the 3D view")
            self.view3.setAlignment(Qt.AlignCenter)
            layout3d.addWidget(self.view3)
            self.attach3d.setEnabled(False)
        self.tabs.addTab(self.panel3d, "Interactive 3D (planar model)")
        self.forceplot = Plot((8, 4), interactive=True)
        self.tabs.addTab(self.forceplot, "Axial Forces")
        self.defplot = Plot((8, 4), interactive=True)
        self.tabs.addTab(self.defplot, "Deformation")
        self.build_analysis_tabs()
        upper.addWidget(self.tabs)
        controls = QWidget()
        controls.setMaximumWidth(195)
        cv = QVBoxLayout(controls)
        cv.setContentsMargins(0, 0, 0, 0)
        group = QGroupBox("View Controls")
        gg = QVBoxLayout(group)
        self.labels = QCheckBox("Show Node IDs")
        self.labels.setChecked(True)
        self.labels.stateChanged.connect(self.refresh)
        gg.addWidget(self.labels)
        self.deformed = QCheckBox("Show 3D Deformation")
        self.deformed.stateChanged.connect(self.refresh)
        gg.addWidget(self.deformed)
        gg.addWidget(QLabel("Color by"))
        self.color = QComboBox()
        self.color.addItems(["Axial Force", "Stress", "Steel"])
        self.color.currentTextChanged.connect(self.refresh)
        gg.addWidget(self.color)
        gg.addWidget(QLabel("2D label size"))
        self.diagram_label_scale = QSpinBox()
        self.diagram_label_scale.setRange(75, 250)
        self.diagram_label_scale.setSingleStep(25)
        self.diagram_label_scale.setValue(100)
        self.diagram_label_scale.setSuffix(" %")
        self.diagram_label_scale.setToolTip(
            "Scale load values, visible node IDs, axis numbers and titles in the "
            "deformation/axial-force diagrams. This changes text only, not structural "
            "results or deformation magnification."
        )
        self.diagram_label_scale.valueChanged.connect(self.scale_diagram_labels)
        gg.addWidget(self.diagram_label_scale)
        self.diagram_fit_button = QPushButton("Fit 2D Diagrams")
        self.diagram_fit_button.setToolTip(
            "Reset zoom/pan in all four deformation/force diagrams. "
            "You can also double-click an individual diagram to fit it."
        )
        self.diagram_fit_button.clicked.connect(self.fit_2d_diagrams)
        gg.addWidget(self.diagram_fit_button)
        diagram_help = QLabel("2D: wheel to zoom; drag to pan; double-click to fit.")
        diagram_help.setWordWrap(True)
        gg.addWidget(diagram_help)
        cv.addWidget(group)
        group = QGroupBox("Moving Vehicle Loads")
        mg = QVBoxLayout(group)
        mg.addWidget(QLabel("Number of vehicles"))
        self.vehicle_count = QSpinBox()
        self.vehicle_count.setRange(1, 3)
        self.vehicle_count.setValue(1)
        self.vehicle_count.setToolTip(
            "Use the same 1–3 vehicle traffic as the web. New followers default to Car and Bus."
        )
        self.vehicle_count.valueChanged.connect(self.change_vehicle_count)
        mg.addWidget(self.vehicle_count)
        self.traffic_button = QPushButton("Edit individual vehicles…")
        self.traffic_button.clicked.connect(self.edit_traffic)
        mg.addWidget(self.traffic_button)
        self.traffic_summary = QLabel("Truck · settings below edit vehicle 1")
        self.traffic_summary.setWordWrap(True)
        mg.addWidget(self.traffic_summary)
        self.moving_help_button = QPushButton("Moving Load Setup Guide")
        self.moving_help_button.setToolTip(
            "Step-by-step help: deck nodes, axle forces, playback and response envelopes. "
            "Opening the guide does not change your model or loads."
        )
        self.moving_help_button.clicked.connect(self.show_moving_load_help)
        mg.addWidget(self.moving_help_button)
        self.moving_toggle = QCheckBox("Enable moving loads")
        self.moving_toggle.setToolTip(
            "Apply the vehicle at the slider position in addition to existing static loads. "
            "A stable truss and a valid deck-node path are required."
        )
        self.moving_toggle.toggled.connect(self.toggle_moving)
        mg.addWidget(self.moving_toggle)
        self.axle_front = QDoubleSpinBox()
        self.axle_front.setRange(0, 100000)
        self.axle_front.setValue(80)
        self.axle_front.setSuffix(" kN")
        self.axle_rear = QDoubleSpinBox()
        self.axle_rear.setRange(0, 100000)
        self.axle_rear.setValue(120)
        self.axle_rear.setSuffix(" kN")
        self.axle_spacing = QDoubleSpinBox()
        self.axle_spacing.setRange(0, 1000)
        self.axle_spacing.setValue(4)
        self.axle_spacing.setSuffix(" m")
        self.vehicle_step = QDoubleSpinBox()
        self.vehicle_step.setRange(0.05, 20)
        self.vehicle_step.setValue(0.5)
        self.vehicle_step.setSuffix(" m/step")
        self.axle_front.setToolTip(
            "Leading axle force in kN, applied downward. Example: 80 kN. "
            "Zero disables this axle; this is not the vehicle's total weight."
        )
        self.axle_rear.setToolTip(
            "Trailing axle force in kN, applied downward. Example: 120 kN. "
            "The rear axle follows the front by the axle spacing. Zero disables it."
        )
        self.axle_spacing.setToolTip(
            "Distance between the front and rear axles in metres. Example: 4 m. "
            "An axle outside the deck contributes no load."
        )
        self.vehicle_step.setToolTip(
            "Distance between numerical response updates (nominally every 130 ms). "
            "The 3D vehicle interpolates between them. Smaller steps give finer playback. "
            "This is not vehicle speed and does not control envelope accuracy."
        )
        for name, widget in [
            ("Vehicle 1 front axle", self.axle_front),
            ("Vehicle 1 rear axle", self.axle_rear),
            ("Vehicle 1 wheelbase", self.axle_spacing),
            ("Response step", self.vehicle_step),
        ]:
            mg.addWidget(QLabel(name))
            mg.addWidget(widget)
            widget.valueChanged.connect(self.moving_changed)
        self.vehicle_position = QSlider(Qt.Horizontal)
        self.vehicle_position.setRange(0, 1000)
        self.vehicle_position.setToolTip(
            "Place the vehicle's front axle along the full entry-to-exit path. "
            "Enable moving loads to update results; at the endpoints the vehicle is off the bridge."
        )
        self.vehicle_position.valueChanged.connect(self.moving_changed)
        mg.addWidget(QLabel("Leading front axle position"))
        mg.addWidget(self.vehicle_position)
        self.position_label = QLabel("0.00 m")
        self.position_label.setWordWrap(True)
        mg.addWidget(self.position_label)
        self.playback_label = QLabel("Playback: 0.000 s")
        self.playback_label.setWordWrap(True)
        self.playback_label.setToolTip(
            "Elapsed animation time, excluding pauses. Not physical travel time or dynamic response."
        )
        mg.addWidget(self.playback_label)
        buttons = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.setToolTip(
            "Enable moving loads if needed and animate the vehicle. Click Pause to stop. "
            "Reset before playing again after the vehicle has exited."
        )
        self.play_button.clicked.connect(self.play_pause)
        buttons.addWidget(self.play_button)
        reset = QPushButton("Reset")
        reset.setToolTip(
            "Pause playback and return the vehicle to the start of its path. "
            "Axle settings and static loads are unchanged."
        )
        reset.clicked.connect(self.reset_vehicle)
        buttons.addWidget(reset)
        mg.insertLayout(mg.indexOf(self.moving_toggle) + 1, buttons)
        self.envelope_button = QPushButton("Compute Signed Envelopes")
        self.envelope_button.setToolTip(
            "Find minimum/maximum member forces, stresses, displacement components and reactions "
            "over the full vehicle passage, including static loads. "
            "The Load Envelopes tab shows governing front-axle positions. "
            "Animation need not be enabled."
        )
        self.envelope_button.clicked.connect(self.scan_envelope)
        mg.addWidget(self.envelope_button)
        note = QLabel("Quasi-static; explicit deck nodes. Full entry-to-exit travel.")
        note.setWordWrap(True)
        mg.addWidget(note)
        cv.insertWidget(0, group)
        group = QGroupBox("Legend")
        gg = QVBoxLayout(group)
        gg.addWidget(QLabel("🔴  Positive = Tension"))
        gg.addWidget(QLabel("🔵  Negative = Compression"))
        gg.addWidget(QLabel("⚪  Near-zero"))
        gg.addWidget(QLabel("△  Pin: no wheels"))
        gg.addWidget(QLabel("△○○  Roller: two wheels"))
        cv.addWidget(group)
        cv.addStretch()
        control_scroll = QScrollArea()
        control_scroll.setWidgetResizable(True)
        control_scroll.setWidget(controls)
        control_scroll.setMinimumWidth(225)
        control_scroll.setMaximumWidth(235)
        upper.addWidget(control_scroll)
        upper.setSizes([235, 1060, 225])
        lower = QSplitter(Qt.Vertical)
        v.addWidget(lower, 4)
        row = QSplitter(Qt.Horizontal)
        lower.addWidget(row)
        group = QGroupBox("3. Member Forces and Stresses")
        g = QVBoxLayout(group)
        self.members_table = QTableWidget()
        self.members_table.setColumnCount(7)
        self.members_table.setHorizontalHeaderLabels(
            ["Member", "Node i", "Node j", "Length (m)", "Force (kN)", "Stress (MPa)", "State"]
        )
        g.addWidget(self.members_table)
        row.addWidget(group)
        group = QGroupBox("4. Deformed Shape (magnified)")
        g = QVBoxLayout(group)
        self.small_deform = Plot((5, 2), interactive=True)
        g.addWidget(self.small_deform)
        row.addWidget(group)
        group = QGroupBox("5. Nodal Displacements / Reactions")
        g = QVBoxLayout(group)
        self.displacement_time_label = QLabel("Static results — no playback timestamp")
        self.displacement_time_label.setWordWrap(True)
        g.addWidget(self.displacement_time_label)
        self.disp_table = QTableWidget()
        self.disp_table.setColumnCount(3)
        self.disp_table.setHorizontalHeaderLabels(["Node", "ux (mm)", "uy (mm)"])
        g.addWidget(self.disp_table)
        self.react_table = QTableWidget()
        self.react_table.setColumnCount(3)
        self.react_table.setHorizontalHeaderLabels(["Support", "Rx (kN)", "Ry (kN)"])
        g.addWidget(self.react_table)
        row.addWidget(group)
        row.setSizes([550, 470, 420])
        row2 = QSplitter(Qt.Horizontal)
        lower.addWidget(row2)
        group = QGroupBox("6. Equal-Volume Comparison (steel density 7850 kg/m³)")
        g = QVBoxLayout(group)
        self.comparison = QTableWidget()
        self.comparison.setColumnCount(6)
        self.comparison.setHorizontalHeaderLabels(
            [
                "Truss",
                "Peak |uy| (mm)",
                "Peak |N| (kN)",
                "Mass (kg)",
                "Critical member",
                "Front x (m)",
            ]
        )
        g.addWidget(self.comparison)
        row2.addWidget(group)
        group = QGroupBox("7. Axial Force Diagram")
        g = QVBoxLayout(group)
        self.small_forces = Plot((5, 2), interactive=True)
        g.addWidget(self.small_forces)
        row2.addWidget(group)
        group = QGroupBox("8. Structural Summary")
        g = QVBoxLayout(group)
        self.summary = QLabel("Click Analyze to calculate structural results.")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop)
        g.addWidget(self.summary)
        row2.addWidget(group)
        row2.setSizes([560, 500, 360])
        lower.setSizes([270, 230])
        self.statusBar().showMessage(
            "Ready · 2D matrix truss analysis; 3D bridge view is a visual extrusion of the 2D model"
        )
        for table in (self.members_table, self.disp_table, self.react_table, self.comparison):
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.currentChanged.connect(self.on_view_tab_changed)
        self.analyze()

    def on_view_tab_changed(self, *args):
        self.refresh()
        if self.tabs.currentWidget() is self.panel3d and not self._3d_presented:
            self._3d_presented = True
            # A hidden QtInteractor can initially have square/default dimensions.
            QTimer.singleShot(0, self.fit_3d_view)

    def diagram_canvases(self):
        return (self.defplot, self.forceplot, self.small_deform, self.small_forces)

    def scale_diagram_labels(self, percent):
        for canvas in self.diagram_canvases():
            canvas.set_label_scale(percent / 100)

    def fit_2d_diagrams(self):
        for canvas in self.diagram_canvases():
            canvas.reset_view()

    def show_moving_load_help(self):
        """Modeless, read-only help: opening it must never modify the model."""
        dialog = getattr(self, "_moving_help_dialog", None)
        if dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("Moving Load Setup Guide")
            dialog.resize(620, 650)
            layout = QVBoxLayout(dialog)
            self.moving_help_text = QTextBrowser()
            self.moving_help_text.setOpenExternalLinks(False)
            self.moving_help_text.setHtml(
                "<h2>Apply a moving vehicle load</h2>"
                "<ol>"
                "<li><b>Start with a stable truss.</b> Choose Pratt, Warren or Howe, "
                "or finish your custom geometry, members and supports. Click <b>Analyze</b> "
                "and resolve any instability warnings.</li>"
                "<li><b>Check the deck path.</b> Presets already select their bottom deck joints. "
                "For a custom model, use <b>Select Deck Nodes</b> in the left sidebar: choose "
                "at least two distinct existing joints at a common horizontal elevation, "
                "with different x coordinates. These joints transfer the axle loads.</li>"
                "<li><b>Choose whether to include static loads.</b> Existing static nodal "
                "loads remain active. For vehicle-only results, use <b>Clear Static Loads</b> "
                "in the left sidebar and confirm the removal.</li>"
                "<li><b>Define the vehicle.</b> In the right sidebar's <b>Moving Vehicle Loads</b> "
                "choose <b>Number of vehicles</b> from 1–3. Use <b>Edit individual vehicles…</b> "
                "for each vehicle's type, axle forces, wheelbase and following gap. "
                "Presets match the web workspace; type alone does not change custom forces. "
                "The sidebar axle controls edit vehicle 1 only. For a single truck, in this "
                "section, try <b>80 kN front axle</b>, <b>120 kN rear axle</b> and "
                "<b>4 m axle spacing</b>. Positive axle forces act <b>downward</b>. "
                "The rear axle follows the front; a zero force disables that axle.</li>"
                "<li><b>Enable and position.</b> Check <b>Enable moving loads</b>, then drag "
                "the vehicle-position slider. It controls the front axle's x coordinate "
                "from before entry through the last vehicle's rear axle's complete exit. At the start "
                "and end all axles are outside the bridge, so only static loads remain. "
                "Move the slider inward if you do not yet see a vehicle load.</li>"
                "<li><b>Animate and inspect.</b> Set <b>Response step</b> to, for example, "
                "<b>0.5 m/step</b>, then press <b>Play</b>. Pause stops playback; "
                "<b>Reset</b> returns to the start without changing forces. Open "
                "<b>Interactive 3D (planar model)</b> to see the illustrative vehicle "
                "and axle markers, or inspect the force/displacement tables and plots.</li>"
                "<li><b>Choose the 3D presentation.</b> Use <b>Steel</b> coloring for a neutral "
                "bridge material, or Axial Force/Stress for response colors. "
                "<b>Road / bearings</b>, <b>Vehicle</b> and <b>Load arrows</b> can be hidden "
                "independently. Try <b>Follow vehicle</b> for a truck close-up; "
                "<b>Side</b> for selection, and <b>Free camera</b> for manual orbiting.</li>"
                "<li><b>Find the governing response.</b> Click <b>Compute Signed Envelopes</b>. "
                "The <b>Load Envelopes</b> tab lists signed minima/maxima and the front-axle "
                "positions that cause them. This checks the whole passage, even if moving-load "
                "animation is disabled, and includes the current static loads.</li>"
                "</ol>"
                "<h3>If nothing happens</h3>"
                "<ul><li>Scroll the right sidebar to reach the slider and Play controls.</li>"
                "<li>Ensure the deck path is valid and at least one axle force is nonzero.</li>"
                "<li>After the vehicle exits, click Reset before replaying.</li>"
                "<li>If a mechanism warning appears, repair the members/supports before continuing.</li>"
                "<li>If 3D is unavailable, the 2D plots and numerical analysis still work.</li></ul>"
                "<p><b>Engineering scope:</b> This is <b>quasi-static planar analysis</b>, "
                "not a dynamic simulation. Response step controls the distance between numerical updates, not vehicle "
                "speed or envelope accuracy. The 3D view is illustrative. Axles outside the "
                "selected deck contribute no load.</p>"
                "<p>During playback the truck moves between numerical response positions. "
                "The position label distinguishes visual x from the position used by the tables "
                "and response colors. Pause synchronizes results to the slider's nearest position. "
                "Wheel rotation is illustrative, not a suspension or dynamic simulation.</p>"
                "<p>You can leave this guide open while setting up the model. "
                "Opening or closing it does not change any inputs.</p>"
            )
            layout.addWidget(self.moving_help_text)
            buttons = QDialogButtonBox(QDialogButtonBox.Close)
            buttons.rejected.connect(dialog.close)
            layout.addWidget(buttons)
            self._moving_help_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def build_3d_controls(self, layout):
        note = QLabel(
            "Right-click to select; left-drag to rotate. Gold = selected; green = first joint. "
            "Both displayed sides edit ONE planar model; cross ties/truck body are decorative."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        self.edit3d = QPushButton("Edit Selected")
        self.edit3d.clicked.connect(self.edit_selected_3d)
        self.remove3d = QPushButton("Remove Selected")
        self.remove3d.clicked.connect(self.remove_selected_3d)
        self.attach3d = QPushButton("Attach Member (2 joints)")
        self.attach3d.setCheckable(True)
        self.attach3d.toggled.connect(self.toggle_attach_3d)
        self.undo3d = QPushButton("Undo 3D Edit")
        self.undo3d.clicked.connect(self.undo_3d_edit)
        clear = QPushButton("Clear Selection")
        clear.clicked.connect(self.clear_selection_3d)
        fit = QPushButton("Fit View")
        fit.clicked.connect(self.fit_3d_view)
        for button in (self.edit3d, self.remove3d, self.attach3d, self.undo3d, clear, fit):
            row.addWidget(button)
        layout.addLayout(row)
        self.selection3d = QLabel("Nothing selected.")
        self.selection3d.setWordWrap(True)
        layout.addWidget(self.selection3d)
        self.edit3d.setEnabled(False)
        self.remove3d.setEnabled(False)
        self.undo3d.setEnabled(False)
        options = QHBoxLayout()
        self.show_deck3d = QCheckBox("Road / bearings")
        self.show_vehicle3d = QCheckBox("Vehicle")
        self.show_loads3d = QCheckBox("Load arrows")
        for checkbox in (self.show_deck3d, self.show_vehicle3d, self.show_loads3d):
            checkbox.setChecked(True)
            checkbox.toggled.connect(self.refresh)
            options.addWidget(checkbox)
        self.show_deck3d.setToolTip(
            "Illustrative reference deck, road and bearings; adds no stiffness or self-weight. Hide to inspect obscured members."
        )
        self.show_vehicle3d.setToolTip(
            "Show the illustrative vehicle body and wheels. Load arrows can be shown separately."
        )
        self.show_loads3d.setToolTip(
            "Show static load arrows and the vehicle's active axle forces. Wheels remain selectable without arrows."
        )
        options.addWidget(QLabel("Camera"))
        self.camera3d = QComboBox()
        self.camera3d.addItems(["Isometric", "Side", "Follow vehicle", "Free camera"])
        self.camera3d.currentTextChanged.connect(self.refresh)
        options.addWidget(self.camera3d)
        layout.addLayout(options)
        self.vehicle_note3d = QLabel(
            "Illustrative road and vehicle; planar quasi-static calculations."
        )
        self.vehicle_note3d.setWordWrap(True)
        layout.addWidget(self.vehicle_note3d)

    def fit_3d_view(self):
        if self.scene3d is not None:
            self.scene3d.fit()

    def queue_3d_selection(self, entity):
        # Finish VTK's picking callback before rebuilding geometry after an attach.
        self.stop_vehicle()
        scene = self.scene3d
        generation = scene.generation
        QTimer.singleShot(
            0,
            lambda: (
                self.select_3d(entity)
                if scene is self.scene3d and generation == scene.generation
                else None
            ),
        )

    def clear_selection_3d(self):
        self.selected_3d = None
        self.attach_anchor = None
        if hasattr(self, "attach3d"):
            self.attach3d.blockSignals(True)
            self.attach3d.setChecked(False)
            self.attach3d.blockSignals(False)
            self.selection3d.setText("Nothing selected.")
            self.edit3d.setEnabled(False)
            self.remove3d.setEnabled(False)
        if self.scene3d is not None:
            self.scene3d.highlight(render=not self._in_animation)

    def toggle_attach_3d(self, enabled):
        self.stop_vehicle()
        self.clear_selection_3d()
        self.attach3d.blockSignals(True)
        self.attach3d.setChecked(enabled)
        self.attach3d.blockSignals(False)
        if enabled:
            self.selection3d.setText(
                "Attach mode: right-click the first joint, then the second joint. "
                "Use Clear Selection to cancel."
            )

    def select_3d(self, entity):
        kind, identity = entity
        valid = (
            (kind == "member" and 0 <= identity < len(self.model.members))
            or (kind in ("node", "load") and identity in self.model.nodes)
            or (kind == "axle" and 0 <= identity < len(self.axles()) and self.moving_enabled)
        )
        if not valid:
            self.clear_selection_3d()
            return
        self.stop_vehicle()
        if self.attach3d.isChecked():
            if kind != "node":
                self.selection3d.setText(
                    "Attach mode: select a joint sphere, not a member or load."
                )
                return
            if self.attach_anchor is None:
                self.attach_anchor = identity
                self.selection3d.setText(f"First joint N{identity}; right-click the second joint.")
                if self.scene3d is not None:
                    self.scene3d.highlight(anchor=("node", identity))
                return
            a = self.attach_anchor
            self.apply_3d_edit(
                lambda: member_edit(
                    self.model, a, identity, self.area.value(), self.elastic.value() * 1e9
                )
            )
            return
        self.selected_3d = entity
        self.edit3d.setEnabled(True)
        self.remove3d.setEnabled(kind != "node" or identity in self.model.loads)
        if kind == "member":
            m = self.model.members[identity]
            text = f"Member M{identity + 1}: N{m.a} — N{m.b}; A={m.A:g} m², E={m.E / 1e9:g} GPa. Edit to reconnect endpoints or change properties."
        elif kind in ("node", "load"):
            fx, fy = self.model.loads.get(identity, (0.0, 0.0))
            text = f"Joint N{identity}: static Fx={fx / 1000:g}, Fy={fy / 1000:g} kN. Edit to add/change/reattach its static load; Remove removes only its load."
        else:
            index, axle = divmod(identity, 2)
            vehicle = self.traffic_vehicles()[index]
            force = vehicle["front_N" if axle == 0 else "rear_N"] / 1000
            text = f"Vehicle {index + 1} ({vehicle['kind']}), {'front' if axle == 0 else 'rear'} axle: {force:g} kN. Edit affects only this vehicle; Remove sets only this axle force to zero."
        self.selection3d.setText(text)
        if self.scene3d is not None:
            self.scene3d.highlight(entity)

    def apply_3d_edit(self, operation):
        previous = deepcopy(self.model)
        try:
            operation()
        except ValueError as exc:
            self.model = previous
            QMessageBox.warning(self, "Invalid 3D edit", str(exc))
            return False
        self._undo_3d = (previous, self.scenario())
        self.undo3d.setEnabled(True)
        self.stop_vehicle()
        self.kind.blockSignals(True)
        self.kind.setCurrentText("Custom Truss")
        self.kind.blockSignals(False)
        self.model.kind = "Custom Truss"
        self.analyze(preserve_3d_undo=True)
        return True

    def undo_3d_edit(self):
        if self._undo_3d is None:
            return
        self.stop_vehicle()
        self.model, state = self._undo_3d
        self.clear_playback_history()
        self.restore_scenario(state)
        self.position_label.setText(f"{self.front_position():.2f} m")
        self.kind.blockSignals(True)
        self.kind.setCurrentText(
            self.model.kind
            if self.model.kind in ("Pratt Truss", "Howe Truss", "Warren Truss")
            else "Custom Truss"
        )
        self.kind.blockSignals(False)
        self.analyze()

    def edit_selected_3d(self):
        if self.selected_3d is None:
            return
        kind, identity = self.selected_3d
        self.stop_vehicle()
        if kind == "member":
            self.edit_member_3d(identity)
        elif kind in ("node", "load"):
            self.edit_load_3d(identity)
        else:
            self.edit_axle_3d(identity)

    @staticmethod
    def dialog_buttons(dialog, form):
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

    def node_combo_3d(self, nid):
        combo = QComboBox()
        for node in sorted(self.model.nodes):
            combo.addItem(f"N{node}", node)
        combo.setCurrentIndex(combo.findData(nid))
        return combo

    def edit_member_3d(self, index):
        member = self.model.members[index]
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit / reconnect member M{index + 1}")
        form = QFormLayout(dialog)
        a, b = self.node_combo_3d(member.a), self.node_combo_3d(member.b)
        area, elastic = QDoubleSpinBox(), QDoubleSpinBox()
        area.setDecimals(8)
        area.setRange(1e-8, max(100.0, member.A))
        area.setValue(member.A)
        elastic.setDecimals(3)
        elastic.setRange(0.001, max(1000.0, member.E / 1e9))
        elastic.setValue(member.E / 1e9)
        for label, widget in (
            ("First joint", a),
            ("Second joint", b),
            ("Area (m²)", area),
            ("E (GPa)", elastic),
        ):
            form.addRow(label, widget)
        self.dialog_buttons(dialog, form)
        if dialog.exec() == QDialog.Accepted:
            self.apply_3d_edit(
                lambda: member_edit(
                    self.model,
                    a.currentData(),
                    b.currentData(),
                    area.value(),
                    elastic.value() * 1e9,
                    index,
                )
            )

    def edit_load_3d(self, nid):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Static load at N{nid} (vehicle loads remain separate)")
        form = QFormLayout(dialog)
        target = self.node_combo_3d(nid)
        fx, fy = QDoubleSpinBox(), QDoubleSpinBox()
        for widget, value in zip((fx, fy), self.model.loads.get(nid, (0.0, 0.0))):
            widget.setDecimals(6)
            widget.setRange(-max(1e5, abs(value) / 1000), max(1e5, abs(value) / 1000))
            widget.setValue(value / 1000)
        for label, widget in (("Attach to joint", target), ("Fx (kN)", fx), ("Fy (kN)", fy)):
            form.addRow(label, widget)
        self.dialog_buttons(dialog, form)
        if dialog.exec() != QDialog.Accepted:
            return
        dest = target.currentData()
        if dest != nid and dest in self.model.loads:
            if (
                QMessageBox.question(
                    self,
                    "Replace static load",
                    f"N{dest} already has a static load. Replace it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                != QMessageBox.Yes
            ):
                return
        self.apply_3d_edit(
            lambda: load_edit(self.model, nid, dest, fx.value() * 1000, fy.value() * 1000)
        )

    def edit_axle_3d(self, axle):
        index, which = divmod(axle, 2)
        vehicle = self.traffic_vehicles()[index]
        force, ok = QInputDialog.getDouble(
            self,
            f"Vehicle {index + 1} axle",
            "Downward force (kN):",
            vehicle["front_N" if which == 0 else "rear_N"] / 1000,
            0,
            100000,
            2,
        )
        if not ok:
            return
        spacing, ok = QInputDialog.getDouble(
            self,
            "Vehicle axle",
            "Axle spacing (m):",
            vehicle["spacing_m"],
            1.2 if self._traffic_vehicles is not None else 0,
            1000,
            2,
        )
        if ok:
            self.change_axle_3d(axle, force, spacing)

    def change_axle_3d(self, axle, force, spacing):
        # Vehicle undo snapshots include both model and controls.
        self.stop_vehicle()
        state = self.scenario()
        previous = deepcopy(self.model)
        if self._traffic_vehicles is not None:
            index, which = divmod(axle, 2)
            vehicles = deepcopy(self._traffic_vehicles)
            vehicles[index]["front_N" if which == 0 else "rear_N"] = force * 1000
            vehicles[index]["spacing_m"] = spacing
            self.configure_traffic(vehicles)
            if not self.moving_enabled:
                self.analyze()
            self._undo_3d = (previous, state)
            self.undo3d.setEnabled(True)
            return
        widget = self.axle_front if axle == 0 else self.axle_rear
        for control in (widget, self.axle_spacing):
            control.blockSignals(True)
        widget.setValue(force)
        self.axle_spacing.setValue(spacing)
        for control in (widget, self.axle_spacing):
            control.blockSignals(False)
        self.analyze()
        self._undo_3d = (previous, state)
        self.undo3d.setEnabled(True)
        self.position_label.setText(f"{self.front_position():.2f} m")

    def remove_selected_3d(self):
        if self.selected_3d is None:
            return
        kind, identity = self.selected_3d
        prompt = (
            f"Remove member M{identity + 1}? This can make the truss unstable. Undo 3D Edit can restore it."
            if kind == "member"
            else "Remove this load? The joint itself is kept."
        )
        if (
            QMessageBox.question(
                self, "Remove selected", prompt, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            != QMessageBox.Yes
        ):
            return
        if kind == "member":
            self.apply_3d_edit(lambda: self.model.members.pop(identity))
        elif kind in ("node", "load"):
            self.apply_3d_edit(lambda: self.model.loads.pop(identity, None))
        else:
            self.change_axle_3d(identity, 0.0, self.traffic_vehicles()[identity // 2]["spacing_m"])

    @staticmethod
    def fill_table(table, rows):
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def build_analysis_tabs(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        note = QLabel(
            "Unit downward 1 N load; static loads excluded. Force/reaction ordinates: N/N; displacement: m/N."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        button = QPushButton("Compute Influence Lines")
        button.clicked.connect(self.compute_influence)
        row.addWidget(button)
        self.influence_selector = QComboBox()
        self.influence_selector.currentIndexChanged.connect(self.plot_influence)
        row.addWidget(self.influence_selector)
        layout.addLayout(row)
        self.influence_plot = Plot((8, 4))
        layout.addWidget(self.influence_plot)
        self.tabs.addTab(panel, "Influence Lines")
        self.envelope_panel = QWidget()
        layout = QVBoxLayout(self.envelope_panel)
        note = QLabel(
            "Signed component envelopes, including static loads. Critical positions are front-axle x coordinates (m). Event breakpoints plus one-sided boundary states."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.envelope_table = QTableWidget(0, 7)
        self.envelope_table.setHorizontalHeaderLabels(
            [
                "Response",
                "ID/component",
                "Unit",
                "Minimum",
                "Maximum",
                "Front x at min (m)",
                "Front x at max (m)",
            ]
        )
        layout.addWidget(self.envelope_table)
        self.tabs.addTab(self.envelope_panel, "Load Envelopes")
        self.study_panel = QWidget()
        layout = QVBoxLayout(self.study_panel)
        note = QLabel(
            "Finite grid: height × horizontal-chord area factor × web area factor. Same static/vehicle loads; no automatic self-weight. Axial stress screening only: no buckling or code certification."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        for label, attr, value, lo, hi in [
            ("Allowable |uy| (mm)", "deflection_limit", 50.0, 0.001, 10000.0),
            ("Allowable |stress| (MPa)", "stress_limit", 150.0, 0.001, 10000.0),
            ("Density (kg/m³)", "density", 7850.0, 1.0, 100000.0),
        ]:
            widget = QDoubleSpinBox()
            widget.setRange(lo, hi)
            widget.setDecimals(3)
            widget.setValue(value)
            setattr(self, attr, widget)
            row.addWidget(QLabel(label))
            row.addWidget(widget)
            widget.valueChanged.connect(self.invalidate_study)
        layout.addLayout(row)
        row = QHBoxLayout()
        for label, attr, default in [
            ("Heights (m)", "study_heights", "3,4,5"),
            ("Chord factors", "study_chords", "0.75,1,1.25"),
            ("Web factors", "study_webs", "0.75,1,1.25"),
        ]:
            # Editable combo offers a compact comma-separated grid input.
            row.addWidget(QLabel(label))
            widget = QComboBox()
            widget.setEditable(True)
            widget.addItem(default)
            setattr(self, attr, widget)
            widget.editTextChanged.connect(self.invalidate_study)
            row.addWidget(widget)
        button = QPushButton("Run Study")
        button.clicked.connect(self.run_study)
        row.addWidget(button)
        layout.addLayout(row)
        self.study_summary = QLabel("No study calculated.")
        self.study_summary.setWordWrap(True)
        layout.addWidget(self.study_summary)
        self.study_table = QTableWidget(0, 10)
        self.study_table.setHorizontalHeaderLabels(
            [
                "Height (m)",
                "Chord factor",
                "Web factor",
                "Mass (kg)",
                "Peak |uy| (mm)",
                "Peak |stress| (MPa)",
                "Feasible",
                "Pareto",
                "Critical member",
                "Front x (m)",
            ]
        )
        self.study_table.setMinimumHeight(100)
        layout.addWidget(self.study_table, 2)
        self.tradeoff_plot = Plot((8, 3))
        self.tradeoff_plot.setMinimumHeight(100)
        layout.addWidget(self.tradeoff_plot, 2)
        self.tabs.addTab(self.study_panel, "Design Exploration")
        self.redundancy_panel = RedundancyPanel(self)
        self.tabs.addTab(self.redundancy_panel, "Redundancy Study")
        self.history_panel = QWidget()
        layout = QVBoxLayout(self.history_panel)
        note = QLabel(
            "Playback timestamps only — not physical time or a dynamic analysis. "
            "Each sample records all nodes at the solved front-axle position. "
            "Pause to read; resume continues the clock. Reset, manual position changes, "
            "or model/load/response-step changes start a new history. "
            "Only computed samples are recorded; delayed frames are not backfilled."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        button = QPushButton("Export Displacement History CSV")
        button.clicked.connect(self.export_displacement_history)
        layout.addWidget(button)
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(
            ["Playback t (s)", "Front x (m)", "Node", "ux (mm)", "uy (mm)"]
        )
        self.history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.history_table.setColumnWidth(0, 130)
        self.history_table.setColumnWidth(1, 120)
        layout.addWidget(self.history_table)
        self.tabs.addTab(self.history_panel, "Displacement History")

    def update_playback_labels(self):
        self.playback_label.setText(f"Playback: {self._playback_time:.3f} s")
        self.displacement_time_label.setText(
            f"Results at playback t = {self._result_time:.3f} s"
            if self._result_time is not None
            else "No timestamp — press Play to record"
            if self.moving_enabled
            else "Static results — no playback timestamp"
        )

    def clear_playback_history(self):
        self.displacement_history.clear()
        self.history_table.setRowCount(0)
        self._last_history_sample = None
        self._playback_time = 0.0
        self._playback_base = 0.0
        self._result_time = None
        self.update_playback_labels()

    def record_displacements(self, timestamp):
        result = self.model.results
        if result is None or not self.moving_enabled:
            return
        position = self.front_position()
        self._result_time = timestamp
        self.update_playback_labels()
        sample = (timestamp, position)
        if sample == self._last_history_sample:
            return
        self._last_history_sample = sample
        start = self.history_table.rowCount()
        self.history_table.setRowCount(start + len(result["ids"]))
        for index, nid in enumerate(result["ids"]):
            ux, uy = result["U"][2 * index : 2 * index + 2] * 1000.0
            values = (timestamp, position, nid, float(ux), float(uy))
            self.displacement_history.append(values)
            for column, value in enumerate(
                (f"{timestamp:.3f}", f"{position:.4f}", nid, f"{ux:.6f}", f"{uy:.6f}")
            ):
                self.history_table.setItem(start + index, column, QTableWidgetItem(str(value)))

    def export_displacement_history(self):
        self.stop_vehicle()
        if not self.displacement_history:
            QMessageBox.information(
                self, "Displacement history", "Press Play to record samples first."
            )
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save displacement history", "displacement_history.csv", "CSV (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["playback_time_s", "front_x_m", "node", "ux_mm", "uy_mm"])
                writer.writerows(self.displacement_history)
            self.statusBar().showMessage("Saved playback displacement history: " + path)
        except OSError as exc:
            QMessageBox.warning(self, "Displacement history export", str(exc))

    def invalidate_study(self, *args):
        self.study = None
        if hasattr(self, "study_table"):
            self.study_table.setRowCount(0)
            self.study_summary.setText("Inputs changed; run study to update.")
            if self.tradeoff_plot.ax.has_data():
                self.tradeoff_plot.ax.clear()
                self.tradeoff_plot.draw_idle()

    def clear_advanced(self):
        self.envelopes = None
        self.influence = None
        self.envelope_table.setRowCount(0)
        if self.influence_selector.count() or self.influence_plot.ax.has_data():
            self.influence_selector.clear()
            self.influence_plot.ax.clear()
            self.influence_plot.draw_idle()
        self.redundancy_panel.invalidate()
        self.invalidate_study()

    def clear_result_tables(self):
        for table in (self.members_table, self.disp_table, self.react_table, self.comparison):
            table.setRowCount(0)
        self._comparison_key = None

    def compute_influence(self):
        self.stop_vehicle()
        try:
            self.influence = influence_lines(self.model)
            self.influence_selector.blockSignals(True)
            self.influence_selector.clear()
            for i in range(len(self.model.members)):
                self.influence_selector.addItem(f"Member {i + 1} axial force", ("forces", i, "N/N"))
            for i, nid in enumerate(self.influence["ids"]):
                for k, axis in enumerate("xy"):
                    self.influence_selector.addItem(f"Node {nid} u{axis}", ("U", 2 * i + k, "m/N"))
                    if self.model.fixed.get(nid, (False, False))[k]:
                        self.influence_selector.addItem(
                            f"Support {nid} R{axis}", ("R", 2 * i + k, "N/N")
                        )
            self.influence_selector.blockSignals(False)
            self.plot_influence()
        except Exception as e:
            self.influence = None
            self.influence_selector.clear()
            self.influence_plot.ax.clear()
            self.influence_plot.draw_idle()
            QMessageBox.warning(self, "Influence lines", str(e))

    def plot_influence(self, *args):
        if self.influence is None or self.influence_selector.currentIndex() < 0:
            return
        key, index, unit = self.influence_selector.currentData()
        ax = self.influence_plot.ax
        ax.clear()
        ax.plot(self.influence["x"], self.influence[key][:, index], "o-", color="#1475d2")
        ax.axhline(0, color="gray", lw=0.8)
        ax.grid(alpha=0.2)
        ax.set_xlabel("Unit-load x (m)")
        ax.set_ylabel(unit)
        ax.set_title(self.influence_selector.currentText(), fontsize=10)
        self.influence_plot.fig.set_layout_engine("constrained")
        self.influence_plot.draw_idle()

    def run_study(self):
        self.stop_vehicle()
        self.invalidate_study()
        try:

            def parse(widget):
                return [float(v.strip()) for v in widget.currentText().split(",")]

            self.study = parameter_study(
                self.model,
                parse(self.study_heights),
                parse(self.study_chords),
                parse(self.study_webs),
                self.deflection_limit.value() / 1000,
                self.stress_limit.value() * 1e6,
                self.axles() if self.moving_enabled else None,
                self.density.value(),
            )
            rows = []
            for r in self.study["candidates"]:
                rows.append(
                    [
                        r["height_m"],
                        r["chord_factor"],
                        r["web_factor"],
                        f"{r.get('mass_kg', float('nan')):.2f}",
                        f"{r.get('vertical_deflection_m', float('nan')) * 1000:.3f}",
                        f"{r.get('peak_stress_Pa', float('nan')) / 1e6:.2f}",
                        r["feasible"],
                        r["pareto"],
                        r.get("critical_member", "invalid"),
                        "static" if r.get("front_x_m") is None else f"{r['front_x_m']:.4f}",
                    ]
                )
            self.fill_table(self.study_table, rows)
            best = self.study["best"]
            self.study_summary.setText(
                f"Minimum mass among feasible sampled candidates: {best['mass_kg']:.1f} kg; height {best['height_m']:.2f} m; chord ×{best['chord_factor']}; web ×{best['web_factor']}. {self.study['loading']}."
                if best
                else "No sampled candidate satisfies both limits. This is not proof that no feasible design exists."
            )
            ax = self.tradeoff_plot.ax
            ax.clear()
            for row in self.study["candidates"]:
                if "mass_kg" in row:
                    ax.scatter(
                        row["mass_kg"],
                        row["vertical_deflection_m"] * 1000,
                        color="#1475d2" if row["feasible"] else "#ba6050",
                        marker="*" if row["pareto"] else "o",
                        s=70 if row["pareto"] else 25,
                    )
            ax.set_xlabel("Mass (kg)")
            ax.set_ylabel("Peak |uy| (mm)")
            ax.set_title(
                "Blue: feasible; red: infeasible; stars: feasible Pareto candidates", fontsize=9
            )
            ax.grid(alpha=0.2)
            self.tradeoff_plot.fig.set_layout_engine("constrained")
            self.tradeoff_plot.draw_idle()
        except Exception as e:
            self.invalidate_study()
            QMessageBox.warning(self, "Design study", str(e))

    def scenario(self):
        if self._traffic_vehicles is not None:
            return {
                "enabled": self.moving_enabled,
                "position_fraction": self.vehicle_position.value() / 1000,
                "vehicles": deepcopy(self._traffic_vehicles),
            }
        return {
            "enabled": self.moving_enabled,
            "front_N": self.axle_front.value() * 1000,
            "rear_N": self.axle_rear.value() * 1000,
            "spacing_m": self.axle_spacing.value(),
            "position_fraction": self.vehicle_position.value() / 1000,
        }

    def traffic_vehicles(self):
        return positioned_vehicles(self.scenario())

    def restore_scenario(self, state):
        """Restore controls atomically for project loads and undo; no calculations."""
        vehicles = positioned_vehicles(state) if state else [preset_vehicle("Truck")]
        self._traffic_vehicles = deepcopy(state["vehicles"]) if traffic_scenario(state) else None
        controls = (
            self.moving_toggle,
            self.axle_front,
            self.axle_rear,
            self.axle_spacing,
            self.vehicle_position,
            self.vehicle_count,
        )
        for widget in controls:
            widget.blockSignals(True)
        try:
            first = vehicles[0]
            self.moving_enabled = state.get("enabled", False)
            self.moving_toggle.setChecked(self.moving_enabled)
            self.vehicle_count.setValue(len(vehicles))
            self.axle_spacing.setMinimum(1.2 if self._traffic_vehicles is not None else 0)
            self.axle_front.setValue(first["front_N"] / 1000)
            self.axle_rear.setValue(first["rear_N"] / 1000)
            self.axle_spacing.setValue(first["spacing_m"])
            self.vehicle_position.setValue(round(state.get("position_fraction", 0) * 1000))
        finally:
            for widget in controls:
                widget.blockSignals(False)
        self.update_traffic_summary()

    def update_traffic_summary(self):
        vehicles = self.traffic_vehicles()
        self.traffic_summary.setText(
            " → ".join(vehicle["kind"] for vehicle in vehicles)
            + "\nSeparate axle loads; settings below edit vehicle 1."
        )

    def configure_traffic(self, vehicles):
        state = {
            "enabled": self.moving_enabled,
            "position_fraction": self.vehicle_position.value() / 1000,
            "vehicles": deepcopy(vehicles),
        }
        if len(vehicles) == 1 and vehicles[0]["kind"] == "Truck":
            state = {
                "enabled": self.moving_enabled,
                "position_fraction": state["position_fraction"],
                **{key: vehicles[0][key] for key in ("front_N", "rear_N", "spacing_m")},
            }
        validate_scenario(state)
        validate_control_precision(state)
        self.stop_vehicle(sync=False)
        self.restore_scenario(state)
        self.moving_changed()
        if not self.moving_enabled:
            self.refresh()

    def change_vehicle_count(self, count):
        vehicles = [
            {key: value for key, value in vehicle.items() if key != "front_offset_m"}
            for vehicle in self.traffic_vehicles()
        ]
        while len(vehicles) < count:
            vehicles.append(preset_vehicle("Car" if len(vehicles) == 1 else "Bus", 3))
        try:
            self.configure_traffic(vehicles[:count])
        except ValueError as exc:
            self.vehicle_count.blockSignals(True)
            self.vehicle_count.setValue(len(self.traffic_vehicles()))
            self.vehicle_count.blockSignals(False)
            QMessageBox.warning(self, "Invalid traffic", str(exc))

    def edit_traffic(self):
        dialog = TrafficDialog(self.traffic_vehicles(), self)
        if dialog.exec() == QDialog.Accepted:
            self.configure_traffic(dialog.vehicles)

    def save_project(self):
        self.stop_vehicle()
        path, _ = QFileDialog.getSaveFileName(
            self, "Save verified model", "bridge.json", "JSON (*.json)"
        )
        if not path:
            return
        try:
            save_model(path, self.model, self.scenario())
            self.statusBar().showMessage("Saved model and vehicle scenario: " + path)
        except Exception as e:
            QMessageBox.warning(self, "Save model", str(e))

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open model", "", "JSON (*.json)")
        if not path:
            return False
        return self.load_project(path)

    def load_project(self, path):
        try:
            model, state = load_model(path)
            validate_control_precision(state)
        except Exception as e:
            QMessageBox.warning(self, "Open model", str(e))
            return False
        if (
            QMessageBox.question(
                self,
                "Replace model",
                "Replace the current model with this file? Unsaved changes will be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        self.stop_vehicle()
        self.model = model
        self.clear_playback_history()
        self._camera_initialized = False
        self.kind.blockSignals(True)
        self.kind.setCurrentText("Custom Truss")
        self.kind.blockSignals(False)
        self.restore_scenario(state)
        self.position_label.setText(f"{self.front_position():.2f} m")
        self.analyze()
        return True

    def export_bundle(self):
        self.stop_vehicle()
        if self.model.results is None:
            QMessageBox.information(self, "Export", "Analyze a valid model first.")
            return
        parent = QFileDialog.getExistingDirectory(
            self, "Choose parent folder for a new results bundle"
        )
        if not parent:
            return
        directory = Path(parent) / datetime.now().strftime("bridge_results_%Y%m%d_%H%M%S_%f")
        try:
            export_results(
                directory,
                self.model,
                self.model.results,
                self.scenario(),
                self.envelopes,
                self.study,
                self.redundancy,
            )
            self.statusBar().showMessage("Exported result bundle: " + str(directory))
        except Exception as e:
            QMessageBox.warning(self, "Export results", str(e))

    def edit_member(self):
        if not self.model.members:
            return
        options = [f"{i + 1}: {m.a} — {m.b}" for i, m in enumerate(self.model.members)]
        selected, ok = QInputDialog.getItem(self, "Edit member", "Member:", options, 0, False)
        if not ok:
            return
        member = self.model.members[int(selected.split(":")[0]) - 1]
        area, ok = QInputDialog.getDouble(
            self, "Edit member", "Area (m²):", member.A, 0.000001, 100, 6
        )
        if not ok:
            return
        elastic, ok = QInputDialog.getDouble(
            self, "Edit member", "E (GPa):", member.E / 1e9, 0.001, 1000, 3
        )
        if ok:
            member.A = area
            member.E = elastic * 1e9
            self.analyze()

    def select_deck(self):
        text, ok = QInputDialog.getText(
            self,
            "Deck path",
            "Comma-separated node IDs at a common elevation:",
            text=",".join(map(str, self.model.deck_nodes)),
        )
        if not ok:
            return
        previous = self.model.deck_nodes
        try:
            self.model.deck_nodes = [int(value.strip()) for value in text.split(",")]
            deck_path(self.model)
        except ValueError as e:
            self.model.deck_nodes = previous
            QMessageBox.warning(self, "Deck path", str(e))
            return
        self.analyze()

    def clear_static_loads(self):
        if (
            QMessageBox.question(
                self,
                "Static loads",
                "Remove all static nodal loads? Vehicle loads remain separate.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            == QMessageBox.Yes
        ):
            self.model.loads.clear()
            self.analyze()

    def change_kind(self, k):
        if k == "Custom Truss":
            return
        self.stop_vehicle()
        self.clear_advanced()
        self.model.generate(k)
        self._camera_initialized = False
        self.analyze()

    def clear_all(self):
        self._clear_workspace("Clear All")

    def new_project(self):
        self._clear_workspace("New Project")

    def _clear_workspace(self, action):
        answer = QMessageBox.question(
            self,
            action,
            "Remove ALL nodes, members, supports, loads and calculated results?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.stop_vehicle()
        self.moving_enabled = False
        self.moving_toggle.blockSignals(True)
        self.moving_toggle.setChecked(False)
        self.moving_toggle.blockSignals(False)
        self.model.clear()
        self.clear_playback_history()
        self.clear_selection_3d()
        self._undo_3d = None
        self.undo3d.setEnabled(False)
        self.clear_advanced()
        self._camera_initialized = False
        self.kind.blockSignals(True)
        self.kind.setCurrentText("Custom Truss")
        self.kind.blockSignals(False)
        for table in (self.members_table, self.disp_table, self.react_table, self.comparison):
            table.setRowCount(0)
        self.summary.setText(
            "New empty project. Add nodes, connect members, assign supports and loads, then click Analyze."
        )
        self.refresh()
        self.statusBar().showMessage(
            "Blank workspace ready — no nodes, members, loads, supports or results"
        )

    def refresh(self, *args):
        m = self.model
        for canvas, mode in (
            (self.view2, "geometry"),
            (self.forceplot, "force"),
            (self.defplot, "deformed"),
        ):
            if not self.play_timer.isActive() or self.tabs.currentWidget() is canvas:
                canvas.draw_model(m, mode, self.labels.isChecked())
        self.small_deform.draw_model(m, "deformed")
        self.small_forces.draw_model(m, "force")
        self.render_scene()

    def vehicle_visual(self):
        if not self.moving_enabled or not self.model.nodes:
            return None
        front = (
            self.front_position()
            if self._visual_fraction is None
            else self.front_at_fraction(self._visual_fraction)
        )
        try:
            deck, xs = deck_path(self.model)
            xmin, xmax = xs[0], xs[-1]
            top = self.model.nodes[deck[0]][1] + 0.18
        except ValueError:
            xmin, xmax = self.bridge_limits()
            top = min(v[1] for v in self.model.nodes.values()) + 0.18
        visual = (
            front,
            front - self.axle_spacing.value(),
            self.axle_front.value(),
            self.axle_rear.value(),
            xmin,
            xmax,
            top,
        )
        if self._traffic_vehicles is not None:
            visual += (self.traffic_vehicles(),)
        return visual

    def render_scene(self):
        if self.scene3d is None:
            return
        self.scene3d.render(
            self.model,
            deformed=self.deformed.isChecked(),
            color_by=self.color.currentText(),
            vehicle=self.vehicle_visual(),
            reset_camera=not self._camera_initialized,
            show_deck=self.show_deck3d.isChecked(),
            show_vehicle=self.show_vehicle3d.isChecked(),
            show_loads=self.show_loads3d.isChecked(),
            camera_mode=self.camera3d.currentText(),
        )
        note = (
            self.scene3d.vehicle_note
            or "Illustrative reference roadway; no added stiffness or self-weight."
        )
        if self.deformed.isChecked():
            note += (
                " Truss deformation ×50; road and vehicle remain on the undeformed reference deck."
            )
        self.vehicle_note3d.setText(note)
        self._camera_initialized = True

    def analyze(self, checked=False, *, preserve_3d_undo=False):
        self.clear_selection_3d()
        if not preserve_3d_undo:
            self._undo_3d = None
            self.undo3d.setEnabled(False)
        try:
            configuration = json.dumps(self.model.to_solver(), sort_keys=True) + repr(
                (
                    self.model.deck_nodes,
                    self.axles(),
                    self.vehicle_step.value(),
                    self.moving_enabled,
                )
            )
            if configuration != self._history_configuration:
                self.stop_vehicle(sync=False)
                self.clear_playback_history()
                self._history_configuration = configuration
            self.clear_advanced()
            if self.moving_enabled:
                combined = combined_loads(self.model, self.front_position(), self.axles())
                key = json.dumps(self.model.to_solver(), sort_keys=True) + repr(
                    self.model.deck_nodes
                )
                if key != self._moving_response_key or self._moving_response is None:
                    self._moving_response = MovingResponse(self.model)
                    self._moving_response_key = key
                r = self._moving_response.at(self.front_position(), self.axles())
                self.model.results = r
                self.model.display_loads = combined
            else:
                self.model.display_loads = None
                r = self.model.solve()
        except Exception as e:
            self.model.results = None
            self.model.display_loads = None
            self.clear_playback_history()
            self.clear_result_tables()
            self.summary.setText("Analysis invalid: no current results.")
            self.refresh()
            self.statusBar().showMessage("Analysis warning: " + str(e))
            self.stop_vehicle(sync=False)
            QMessageBox.warning(self, "Analysis warning", str(e))
            return
        self.refresh()
        m = self.model
        self.members_table.setRowCount(len(m.members))
        for k, member in enumerate(m.members):
            N = r["forces"][k]
            vals = [
                k + 1,
                member.a,
                member.b,
                f"{r['lengths'][k]:.2f}",
                f"{N / 1000:.2f}",
                f"{r['stresses'][k] / 1e6:.2f}",
                "Tension" if N > 1e-6 else "Compression" if N < -1e-6 else "Zero",
            ]
            for j, val in enumerate(vals):
                self.members_table.setItem(k, j, QTableWidgetItem(str(val)))
        self.disp_table.setRowCount(len(r["ids"]))
        for i, nid in enumerate(r["ids"]):
            for j, val in enumerate(
                [nid, f"{r['U'][2 * i] * 1000:.4f}", f"{r['U'][2 * i + 1] * 1000:.4f}"]
            ):
                self.disp_table.setItem(i, j, QTableWidgetItem(str(val)))
        self.react_table.setRowCount(len(m.fixed))
        for k, nid in enumerate(m.fixed):
            i = r["ix"][nid]
            for j, val in enumerate(
                [nid, f"{r['R'][2 * i] / 1000:.3f}", f"{r['R'][2 * i + 1] / 1000:.3f}"]
            ):
                self.react_table.setItem(k, j, QTableWidgetItem(str(val)))
        self.summary.setText(
            f"Model: {m.kind}\nNodes: {len(m.nodes)}\nMembers: {len(m.members)}\nPeak vertical |uy|: {np.max(np.abs(r['U'][1::2])) * 1000:.4f} mm\nMax displacement component: {np.max(np.abs(r['U'])) * 1000:.4f} mm\nMaximum |axial force|: {np.max(np.abs(r['forces'])) / 1000:.2f} kN\nRelative residual: {r['relative_residual']:.2e}\nStrain energy: {r['strain_energy']:.3f} J\nCondition number: {r['condition_number']:.2e}\n\nPlanar analysis; 3D is illustrative only."
        )
        self.populate_comparison()
        self.statusBar().showMessage(
            "Analysis completed · Moving load quasi-static"
            if self.moving_enabled
            else "Analysis completed · All displayed numerical results computed from the current 2D truss model"
        )

    def bridge_limits(self):
        xs = [v[0] for v in self.model.nodes.values()]
        return (min(xs), max(xs)) if xs else (0.0, 1.0)

    def axles(self):
        return scenario_axles(self.scenario())

    def front_at_fraction(self, fraction):
        try:
            xmin, xmax = travel_limits(self.model, self.axles())
            epsilon = max(xmax - xmin, 1.0) * 1e-8
            if self._traffic_vehicles is not None:
                epsilon = max(epsilon, 1.0)
            xmin -= epsilon
            xmax += epsilon
        except ValueError:
            xmin, xmax = self.bridge_limits()
        return xmin + (xmax - xmin) * fraction

    def front_position(self):
        return self.front_at_fraction(self.vehicle_position.value() / 1000.0)

    def vehicle_nodal_loads(self):
        return vehicle_loads(self.model, self.front_position(), self.axles())

    def moving_changed(self, *args):
        if self._traffic_vehicles is not None:
            self._traffic_vehicles[0].update(
                front_N=self.axle_front.value() * 1000,
                rear_N=self.axle_rear.value() * 1000,
                spacing_m=self.axle_spacing.value(),
            )
        self.update_traffic_summary()
        if not self._in_animation:
            self.stop_vehicle(sync=False)
            self._visual_fraction = None
            self.clear_playback_history()
        self.clear_selection_3d()
        self._undo_3d = None
        self.undo3d.setEnabled(False)
        self.position_label.setText(f"{self.front_position():.2f} m")
        self.clear_advanced()
        if self.moving_enabled:
            self.analyze()

    def toggle_moving(self, enabled):
        self.stop_vehicle()
        self.moving_enabled = enabled
        self.analyze()

    def play_pause(self):
        if not self.moving_enabled:
            self.moving_toggle.setChecked(True)
        if self.model.results is None:
            return
        if self.play_timer.isActive():
            self.stop_vehicle()
        else:
            self._play_anchor = self.vehicle_position.value() / 1000.0
            self._playback_base = self._playback_time
            self._play_started = time.monotonic()
            self._last_animation_cycle = -1
            self.record_displacements(self._playback_time)
            self.play_timer.start(33)
            self.play_button.setText("Pause")

    def stop_vehicle(self, *, sync=True):
        was_running = self.play_timer.isActive()
        self.play_timer.stop()
        fraction = self._visual_fraction
        self._visual_fraction = None
        self.play_button.setText("Play")
        if sync and was_running and fraction is not None:
            self.vehicle_position.blockSignals(True)
            self.vehicle_position.setValue(round(fraction * 1000))
            self.vehicle_position.blockSignals(False)
            self.analyze()
            self.position_label.setText(f"{self.front_position():.2f} m")
            self.record_displacements(self._playback_time)

    def animate_vehicle(self):
        try:
            lo, hi = travel_limits(self.model, self.axles())
            if self._traffic_vehicles is not None:
                lo, hi = self.front_at_fraction(0), self.front_at_fraction(1)
        except ValueError:
            self.stop_vehicle(sync=False)
            return
        elapsed = max(0.0, time.monotonic() - self._play_started)
        cycle = int(elapsed / 0.13)
        increment = self.vehicle_step.value() / (hi - lo)
        duration = max(0.0, (1.0 - self._play_anchor) / increment * 0.13)
        self._playback_time = self._playback_base + min(elapsed, duration)
        self._visual_fraction = min(1.0, self._play_anchor + elapsed / 0.13 * increment)
        solved = min(1.0, self._play_anchor + cycle * increment)
        if self._visual_fraction >= 1.0:
            solved = 1.0
        did_solve = False
        if cycle != self._last_animation_cycle or solved == 1.0:
            self._last_animation_cycle = cycle
            self._in_animation = True
            try:
                target = round(solved * 1000)
                did_solve = target != self.vehicle_position.value()
                self.vehicle_position.setValue(target)
            finally:
                self._in_animation = False
            if did_solve:
                self.record_displacements(
                    self._playback_base + (duration if solved == 1.0 else cycle * 0.13)
                )
        if not self.play_timer.isActive():
            return
        self.update_playback_labels()
        if self.scene3d is not None and not did_solve:
            self.scene3d.update_vehicle(
                self.vehicle_visual(), render=self.tabs.currentWidget() is self.panel3d
            )
        visual = self.front_at_fraction(self._visual_fraction)
        self.position_label.setText(f"{visual:.2f} m (tables: {self.front_position():.2f} m)")
        if solved == 1.0:
            self.stop_vehicle(sync=False)
            self.position_label.setText(f"{self.front_position():.2f} m")
            self.refresh()

    def reset_vehicle(self):
        self.stop_vehicle()
        self.clear_playback_history()
        self.vehicle_position.setValue(0)
        if self.moving_enabled:
            self.analyze()

    def advance_vehicle(self):
        try:
            xmin, xmax = travel_limits(self.model, self.axles())
            if self._traffic_vehicles is not None:
                xmin, xmax = self.front_at_fraction(0), self.front_at_fraction(1)
        except ValueError:
            self.stop_vehicle()
            return
        span = xmax - xmin
        if span <= 0:
            self.stop_vehicle()
            return
        increment = max(1, round(1000 * self.vehicle_step.value() / span))
        next_value = self.vehicle_position.value() + increment
        if next_value >= 1000:
            self.vehicle_position.setValue(1000)
            self.stop_vehicle()
            return
        self.vehicle_position.setValue(next_value)

    def scan_envelope(self):
        self.stop_vehicle()
        try:
            self.envelopes = envelope(self.model, self.axles())
            rows = []
            for key, unit, factor in [
                ("forces", "kN", 0.001),
                ("stresses", "MPa", 1e-6),
                ("U", "mm", 1000.0),
                ("R", "kN", 0.001),
            ]:
                values = self.envelopes[key]
                for i in range(len(values["min"])):
                    label = (
                        f"M{i + 1}"
                        if key in ("forces", "stresses")
                        else f"N{self.envelopes['ids'][i // 2]} {'xy'[i % 2]}"
                    )
                    rows.append(
                        [
                            key,
                            label,
                            unit,
                            f"{values['min'][i] * factor:.6g}",
                            f"{values['max'][i] * factor:.6g}",
                            f"{values['x_min'][i]:.8g}",
                            f"{values['x_max'][i]:.8g}",
                        ]
                    )
            self.fill_table(self.envelope_table, rows)
            self.tabs.setCurrentWidget(self.envelope_panel)
            self.statusBar().showMessage(
                f"Signed envelopes: {len(self.envelopes['positions'])} event/one-sided states; includes static loads and full passage"
            )
        except Exception as e:
            self.envelopes = None
            self.envelope_table.setRowCount(0)
            QMessageBox.warning(self, "Envelope analysis", str(e))

    def populate_comparison(self):
        key = json.dumps(model_document(self.model), sort_keys=True) + str(
            self.axles() if self.moving_enabled else None
        )
        if key == self._comparison_key:
            return
        self.comparison.setRowCount(0)
        try:
            rows = compare_trusses(self.model, self.axles() if self.moving_enabled else None)
            self.fill_table(
                self.comparison,
                [
                    [
                        r["kind"],
                        f"{r['vertical_deflection_m'] * 1000:.3f}",
                        f"{r['peak_force_N'] / 1000:.2f}",
                        f"{r['mass_kg']:.1f}",
                        r["critical_member"],
                        "static" if r["front_x_m"] is None else f"{r['front_x_m']:.4f}",
                    ]
                    for r in rows
                ],
            )
            self.comparison.setToolTip(
                "Same geometry, supports, loads, E and total member volume. Vehicle enabled: complete envelope, not current frame."
            )
        except ValueError as e:
            self.comparison.setToolTip(str(e))
        self._comparison_key = key

    def add_node(self):
        nid = max(self.model.nodes, default=-1) + 1
        x, ok = QInputDialog.getDouble(self, "Add node", "x (m):", 12.5, -10000, 10000, 3)
        if not ok:
            return
        y, ok = QInputDialog.getDouble(self, "Add node", "y (m):", 2.0, -10000, 10000, 3)
        if ok:
            self.clear_selection_3d()
            self._undo_3d = None
            self.undo3d.setEnabled(False)
            self.model.nodes[nid] = (x, y, 0.0)
            self.model.results = None
            self.model.display_loads = None
            self.clear_advanced()
            self.clear_result_tables()
            self.summary.setText("Model changed. Connect members and Analyze.")
            self.refresh()
            self.statusBar().showMessage(f"Node {nid} added; connect members and Analyze")

    def add_member(self):
        if len(self.model.nodes) < 2:
            QMessageBox.information(self, "Add member", "Create at least two nodes first.")
            return
        ids = sorted(self.model.nodes)
        a, ok = QInputDialog.getItem(
            self, "Add member", "First node:", list(map(str, ids)), 0, False
        )
        if not ok:
            return
        b, ok = QInputDialog.getItem(
            self, "Add member", "Second node:", list(map(str, ids)), min(1, len(ids) - 1), False
        )
        if not ok:
            return
        a = int(a)
        b = int(b)
        if a == b or any({a, b} == {mm.a, mm.b} for mm in self.model.members):
            QMessageBox.warning(
                self,
                "Invalid member",
                "Choose two different nodes without an existing connecting member.",
            )
            return
        self.model.members.append(Member(a, b, self.area.value(), self.elastic.value() * 1e9))
        self.analyze()

    def delete_member(self):
        if not self.model.members:
            return
        opts = [f"{i + 1}: {m.a} — {m.b}" for i, m in enumerate(self.model.members)]
        val, ok = QInputDialog.getItem(self, "Delete member", "Select member:", opts, 0, False)
        if ok:
            self.model.members.pop(int(val.split(":")[0]) - 1)
            self.analyze()

    def move_node(self):
        if not self.model.nodes:
            QMessageBox.information(self, "Move node", "Create a node first.")
            return
        ids = sorted(self.model.nodes)
        val, ok = QInputDialog.getItem(self, "Move node", "Node:", list(map(str, ids)), 0, False)
        if not ok:
            return
        nid = int(val)
        x, y, _ = self.model.nodes[nid]
        x, ok = QInputDialog.getDouble(self, "Move node", "New x (m):", x, -10000, 10000, 3)
        if not ok:
            return
        y, ok = QInputDialog.getDouble(self, "Move node", "New y (m):", y, -10000, 10000, 3)
        if ok:
            self.model.nodes[nid] = (x, y, 0)
            self.analyze()

    def add_load(self):
        if not self.model.nodes:
            QMessageBox.information(self, "Set load", "Create a node first.")
            return
        ids = sorted(self.model.nodes)
        val, ok = QInputDialog.getItem(
            self, "Set nodal load", "Node:", list(map(str, ids)), 0, False
        )
        if not ok:
            return
        nid = int(val)
        fx, ok = QInputDialog.getDouble(self, "Load", "Fx (kN):", 0, -100000, 100000, 2)
        if not ok:
            return
        fy, ok = QInputDialog.getDouble(self, "Load", "Fy (kN):", -50, -100000, 100000, 2)
        if ok:
            self.model.loads[nid] = (fx * 1000, fy * 1000)
            self.analyze()

    def add_support(self):
        if not self.model.nodes:
            QMessageBox.information(self, "Set support", "Create a node first.")
            return
        ids = sorted(self.model.nodes)
        val, ok = QInputDialog.getItem(self, "Set support", "Node:", list(map(str, ids)), 0, False)
        if not ok:
            return
        typ, ok = QInputDialog.getItem(
            self,
            "Set support",
            "Type:",
            [
                "Pinned (x and y fixed)",
                "Vertical roller (y fixed)",
                "Horizontal roller (x fixed)",
                "Free",
            ],
            0,
            False,
        )
        if ok:
            opts = {
                "Pinned (x and y fixed)": (True, True),
                "Vertical roller (y fixed)": (False, True),
                "Horizontal roller (x fixed)": (True, False),
            }
            if typ == "Free":
                self.model.fixed.pop(int(val), None)
            else:
                self.model.fixed[int(val)] = opts[typ]
            self.analyze()

    def closeEvent(self, event):
        self.stop_vehicle(sync=False)
        if self.scene3d is not None:
            self.view3.close()
            self.scene3d = None
        super().closeEvent(event)

    def export_csv(self):
        self.stop_vehicle()
        if self.model.results is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save member forces", "member_forces.csv", "CSV (*.csv)"
        )
        if not path:
            return
        r = self.model.results
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                ["Member", "Node i", "Node j", "Length (m)", "Axial force (N)", "Stress (Pa)"]
            )
            for i, m in enumerate(self.model.members):
                w.writerow([i + 1, m.a, m.b, r["lengths"][i], r["forces"][i], r["stresses"][i]])
        self.statusBar().showMessage("Saved " + path)


if __name__ == "__main__":
    configure_graphics()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON)))
    w = Main()
    w.show()
    sys.exit(app.exec())
