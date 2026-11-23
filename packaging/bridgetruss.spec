# Build with: python -m PyInstaller packaging/bridgetruss.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH).parent
datas = [
    (str(ROOT / "assets" / "bridgetruss.png"), "assets"),
    (str(ROOT / "examples"), "examples"),
    (str(ROOT / "LICENSE"), "."),
]
datas += collect_data_files("pyvista")
datas += copy_metadata("pyvista")

a = Analysis(
    [str(ROOT / "packaging" / "desktop_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["vtkmodules.vtkRenderingOpenGL2"],
    hookspath=[],
    hooksconfig={"matplotlib": {"backends": ["QtAgg"]}},
    runtime_hooks=[],
    excludes=[
        "PyQt5", "PyQt6", "PySide2", "tkinter", "IPython", "notebook",
        "jupyter", "streamlit", "plotly", "pytest", "torch", "tensorflow",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bridgetruss",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=False, name="bridgetruss",
)
