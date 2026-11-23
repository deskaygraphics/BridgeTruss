"""Desktop entry point for the standalone application."""

import argparse
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app_version import VERSION  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="BridgeTruss desktop analysis")
    parser.add_argument("--version", action="version", version=f"BridgeTruss {VERSION}")
    parser.add_argument("--no-3d", action="store_true", help="Disable optional 3D graphics")
    parser.add_argument(
        "--smoke-test", action="store_true", help="Run headless installation checks"
    )
    args = parser.parse_args()
    if args.no_3d or args.smoke_test:
        os.environ["BRIDGETRUSS_NO_3D"] = "1"
    if args.smoke_test:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    from main import APP_ICON, Main, configure_graphics

    configure_graphics()
    app = QApplication([sys.argv[0]])
    app.setApplicationName("BridgeTruss")
    app.setApplicationVersion(VERSION)
    app.setDesktopFileName("bridgetruss")
    app.setWindowIcon(QIcon(str(APP_ICON)))
    window = Main()
    if args.smoke_test:
        # Import the bundled 3D stack without requiring a working OpenGL display.
        import pyvista
        import pyvistaqt
        from vtkmodules import vtkRenderingOpenGL2
        from persistence import load_model, save_model

        if window.windowIcon().isNull() or window.windowIcon().pixmap(64, 64).isNull():
            raise RuntimeError("Application icon is missing")
        result = window.model.results
        peak_mm = float(max(abs(result["U"][1::2])) * 1000)
        if abs(peak_mm - 8.91120087876333) > 1e-8:
            raise RuntimeError(f"Unexpected analysis result: {peak_mm}")
        window.view2.draw()
        with TemporaryDirectory(prefix="bridgetruss-check-") as directory:
            path = Path(directory) / "project.json"
            save_model(path, window.model)
            model, _ = load_model(path)
            model.solve()
        examples = APP_ICON.parents[1] / "examples"
        if not (examples / "pratt_vehicle.json").is_file():
            raise RuntimeError("Bundled example models are missing")
        print(
            json.dumps(
                {
                    "version": VERSION,
                    "peak_displacement_mm": peak_mm,
                    "icon": "ok",
                    "project_round_trip": "ok",
                    "examples": "ok",
                    "pyvista": pyvista.__version__,
                    "pyvistaqt": pyvistaqt.__version__,
                    "vtk_opengl": vtkRenderingOpenGL2.__name__,
                }
            )
        )
        window.close()
        app.processEvents()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
