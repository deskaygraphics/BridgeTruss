"""Qt editor for the same per-vehicle traffic profiles as the web workspace."""

from copy import deepcopy
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QPushButton,
    QDialogButtonBox,
    QMessageBox,
    QLabel,
    QScrollArea,
    QWidget,
)
from traffic import PRESETS, preset_vehicle, validate_scenario, validate_control_precision


class TrafficDialog(QDialog):
    def __init__(self, vehicles, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Moving traffic — individual vehicle loads")
        self.resize(600, 650)
        self.vehicles = deepcopy(vehicles)
        layout = QVBoxLayout(self)
        note = QLabel(
            "Each vehicle has its own axle forces and wheelbase. Gaps are previous rear "
            "axle to next front axle, not bumper clearance. Presets match the web workspace; "
            "they are examples, not regulatory design vehicles. Changes apply only on OK."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Number of vehicles"))
        self.count = QSpinBox()
        self.count.setRange(1, 3)
        self.count.setValue(len(vehicles))
        count_row.addWidget(self.count)
        layout.addLayout(count_row)
        content = QWidget()
        rows_layout = QVBoxLayout(content)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        self.rows = []
        defaults = [preset_vehicle("Truck"), preset_vehicle("Car", 3), preset_vehicle("Bus", 3)]
        for index in range(3):
            vehicle = vehicles[index] if index < len(vehicles) else defaults[index]
            group = QGroupBox(f"Vehicle {index + 1}")
            form = QFormLayout(group)
            kind = QComboBox()
            kind.addItems(list(PRESETS))
            kind.setCurrentText(vehicle["kind"])
            preset = QPushButton("Load preset")
            front, rear, spacing, gap = [QDoubleSpinBox() for _ in range(4)]
            for widget in (front, rear):
                widget.setRange(0, 100000)
                widget.setSuffix(" kN")
            spacing.setRange(0, 1000)
            spacing.setSuffix(" m")
            gap.setRange(0 if index == 0 else 2, 0 if index == 0 else 1000)
            gap.setSuffix(" m")
            gap.setEnabled(index > 0)
            front.setValue(vehicle["front_N"] / 1000)
            rear.setValue(vehicle["rear_N"] / 1000)
            spacing.setValue(vehicle["spacing_m"])
            gap.setValue(vehicle["gap_m"])
            row = dict(
                group=group,
                kind=kind,
                front=front,
                rear=rear,
                spacing=spacing,
                gap=gap,
                preset=preset,
            )
            self.rows.append(row)
            preset.clicked.connect(lambda checked=False, i=index: self.load_preset(i))
            form.addRow("Type", kind)
            form.addRow(preset)
            form.addRow("Front axle", front)
            form.addRow("Rear axle", rear)
            form.addRow("Wheelbase", spacing)
            form.addRow("Following gap", gap)
            rows_layout.addWidget(group)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.count.valueChanged.connect(self.update_rows)
        self.update_rows()

    def update_rows(self):
        for index, row in enumerate(self.rows):
            row["group"].setVisible(index < self.count.value())

    def load_preset(self, index):
        row = self.rows[index]
        vehicle = preset_vehicle(row["kind"].currentText(), 0 if index == 0 else 3)
        row["front"].setValue(vehicle["front_N"] / 1000)
        row["rear"].setValue(vehicle["rear_N"] / 1000)
        row["spacing"].setValue(vehicle["spacing_m"])

    def accept(self):
        vehicles = [
            {
                "kind": row["kind"].currentText(),
                "front_N": row["front"].value() * 1000,
                "rear_N": row["rear"].value() * 1000,
                "spacing_m": row["spacing"].value(),
                "gap_m": row["gap"].value(),
            }
            for row in self.rows[: self.count.value()]
        ]
        # The legacy one-truck form also permits schematic wheelbases below 1.2 m.
        state = {"enabled": False, "position_fraction": 0.0, "vehicles": vehicles}
        if len(vehicles) == 1 and vehicles[0]["kind"] == "Truck":
            state = {
                "enabled": False,
                "position_fraction": 0.0,
                **{key: vehicles[0][key] for key in ("front_N", "rear_N", "spacing_m")},
            }
        try:
            validate_scenario(state)
            validate_control_precision(state)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid traffic", str(exc))
            return
        self.vehicles = vehicles
        super().accept()
