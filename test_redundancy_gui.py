"""Use the existing offscreen application fixtures for the study workflow."""

import json

from test_gui import app as app, window as window
from PySide6.QtWidgets import QTableWidget, QFileDialog
from bridge_model import Member
from example_studies import verification_rows


def test_example_selectors_removed_but_verification_available(window):
    from PySide6.QtWidgets import QPushButton, QGroupBox

    assert not hasattr(window, "study_example")
    assert not hasattr(window.redundancy_panel, "example")
    assert not any(
        "Three Study Examples" in group.title() for group in window.findChildren(QGroupBox)
    )
    assert not any(
        "Load Example" in button.text() or "Load Study Example" in button.text()
        for button in window.findChildren(QPushButton)
    )
    window.show_analytical_verification()
    assert "49/49" in window.redundancy_panel.verification_summary.text()


def test_panel_stable_rejected_and_input_invalidation(window):
    w = window
    panel = w.redundancy_panel
    w.model.members.append(Member(1, 7))
    w.analyze()
    panel.member.setValue(18)
    before = w.model.to_solver()
    active = w.model.results
    panel.run_button.click()
    assert not w.test_errors
    assert panel.cases.rowCount() == 5
    assert panel.members.rowCount() == 18
    assert panel.nodes.rowCount() == 10
    assert w.redundancy["cases"][-1]["status"] == "stable"
    assert panel.members.item(17, 9).text() == "removed"
    assert w.model.to_solver() == before
    assert w.model.results is active
    panel.enlarge_button.click()
    assert panel.large_dialog.isVisible()
    assert len(panel.large_plot.figure.axes) == 5
    panel.case.setCurrentIndex(1)
    assert panel.members.item(17, 9).text() == "present"
    assert panel.members.editTriggers() == QTableWidget.NoEditTriggers
    panel.factors.setEditText("1,0.5,0")
    assert w.redundancy is None
    assert panel.members.rowCount() == 0
    assert not panel.plot.figure.axes
    assert not panel.large_dialog.isVisible()
    assert not panel.enlarge_button.isEnabled()
    panel.run()
    w.model.members.pop()
    w.analyze()
    assert w.redundancy is None
    assert panel.member.maximum() == 17
    panel.member.setValue(1)
    panel.run()
    assert w.redundancy["cases"][-1]["status"] == "rejected"
    assert panel.members.rowCount() == 0
    assert panel.nodes.rowCount() == 0
    assert "Unstable" in panel.summary.text()
    assert not w.test_errors


def test_moving_export_and_failure_invalidation(window, monkeypatch, tmp_path):
    w = window
    w.model.members.append(Member(1, 7))
    w.moving_toggle.setChecked(True)
    panel = w.redundancy_panel
    panel.member.setValue(18)
    panel.factors.setEditText("1,0")
    panel.run()
    assert not w.test_errors
    assert w.redundancy["comparison_front_x_m"] is not None
    assert "common front x" in panel.summary.text()
    assert panel.members.item(0, 5).text() != "—"
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    w.export_bundle()
    bundle = next(tmp_path.glob("bridge_results_*"))
    assert json.loads((bundle / "analysis.json").read_text())["redundancy_study"]
    assert (bundle / "redundancy_factor_0.png").exists()
    w.axle_front.setValue(90)
    assert w.redundancy is None
    panel.run()
    panel.factors.setEditText("bad")
    panel.run()
    assert w.redundancy is None
    assert panel.cases.rowCount() == 0
    assert len(w.test_errors) == 1


def test_analytical_verification_is_independent_and_read_only(window):
    w = window
    panel = w.redundancy_panel
    panel.run()
    before = w.model.to_solver()
    scenario = w.scenario()
    result, study = w.model.results, w.redundancy
    assert panel.verification_checks is None
    panel.detail.setCurrentWidget(panel.verification_panel)
    assert panel.verification_checks == verification_rows()
    assert "49/49" in panel.verification_summary.text()
    assert "NOT the active project" in panel.verification_equations.text()
    table = panel.verification_table
    assert table.rowCount() == 49
    assert table.editTriggers() == QTableWidget.NoEditTriggers
    for index, row in enumerate(panel.verification_checks):
        assert table.item(index, 1).text() == row["response"]
        assert table.item(index, 3).text() == f"{row['reference']:.6e}"
        assert table.item(index, 4).text() == f"{row['computed']:.6e}"
        assert table.item(index, 5).text() == f"{row['absolute_error']:.6e}"
        assert table.item(index, 6).text() == f"{row['absolute_tolerance']:.6e}"
        assert table.item(index, 8).text() == "PASS"
    panel.verify_button.click()
    assert w.model.to_solver() == before
    assert w.scenario() == scenario
    assert w.model.results is result
    assert w.redundancy is study
    w.axle_front.setValue(90)
    assert w.redundancy is None
    assert table.rowCount() == 49
    assert not w.test_errors


def test_verification_reports_failed_checks_and_clears_stale_results(window, monkeypatch):
    panel = window.redundancy_panel
    row = {
        **verification_rows()[0],
        "reference": 0,
        "computed": 1,
        "absolute_error": 1,
        "passed": False,
    }
    monkeypatch.setattr("redundancy_ui.verification_rows", lambda: [row])
    panel.verify_button.click()
    assert "0/1" in panel.verification_summary.text()
    assert panel.verification_table.item(0, 7).text() == "—"
    assert panel.verification_table.item(0, 8).text() == "FAIL"

    def fail():
        raise OSError("Benchmark file unavailable")

    monkeypatch.setattr("redundancy_ui.verification_rows", fail)
    panel.verify_button.click()
    assert panel.verification_checks is None
    assert panel.verification_table.rowCount() == 0
    assert "Benchmark file unavailable" in panel.verification_summary.text()
