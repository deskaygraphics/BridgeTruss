"""Build a standalone Ubuntu 24.04 amd64 desktop package without root access."""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_version import VERSION  # noqa: E402


def run(*command):
    subprocess.run(command, cwd=ROOT, check=True)


def link_or_copy(source, target):
    try:
        os.link(source, target)
        return target
    except OSError:
        return shutil.copy2(source, target)


def build(reuse_bundle=False):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError(
            "This initial package targets Ubuntu 24.04 amd64; build on that platform"
        )
    for tool in ("dpkg-deb", "desktop-file-validate"):
        if shutil.which(tool) is None:
            raise RuntimeError(f"Required build tool not found: {tool}")
    output = ROOT / "dist"
    work = ROOT / "build"
    bundle = output / "bridgetruss"
    if not reuse_bundle:
        run(
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(output),
            "--workpath",
            str(work / "pyinstaller"),
            str(ROOT / "packaging" / "bridgetruss.spec"),
        )
    if not (bundle / "bridgetruss").is_file():
        raise RuntimeError("Standalone bundle is missing; run a full build first")
    # Unique staging directories never overwrite a previous package tree.
    from tempfile import mkdtemp

    work.mkdir(exist_ok=True)
    stage = Path(mkdtemp(prefix="deb-", dir=work))
    appdir = stage / "opt" / "bridgetruss"
    shutil.copytree(bundle, appdir, symlinks=True, copy_function=link_or_copy)
    bindir = stage / "usr" / "bin"
    bindir.mkdir(parents=True)
    (bindir / "bridgetruss").symlink_to("/opt/bridgetruss/bridgetruss")
    desktop = stage / "usr" / "share" / "applications" / "bridgetruss.desktop"
    desktop.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging" / desktop.name, desktop)
    run("desktop-file-validate", str(desktop))
    icon = stage / "usr/share/icons/hicolor/512x512/apps/bridgetruss.png"
    icon.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "assets" / "bridgetruss.png", icon)
    copyright_file = stage / "usr/share/doc/bridgetruss/copyright"
    copyright_file.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "LICENSE", copyright_file)
    installed_kib = (
        sum(p.stat().st_size for p in stage.rglob("*") if p.is_file() and not p.is_symlink()) + 1023
    ) // 1024
    control = stage / "DEBIAN" / "control"
    control.parent.mkdir()
    control.write_text(
        f"Package: bridgetruss\nVersion: {VERSION}\n"
        "Section: education\nPriority: optional\nArchitecture: amd64\n"
        "Maintainer: Desmond Kangah <deskaygraphics@gmail.com>\n"
        f"Installed-Size: {installed_kib}\n"
        "Depends: libc6 (>= 2.39), libstdc++6, libgcc-s1, libgl1, libegl1, "
        "libopengl0, libx11-6, libxext6, libxrender1, libxi6, libxkbcommon0, "
        "libxkbcommon-x11-0, libxcb1, libxcb-cursor0, libxcb-icccm4, "
        "libxcb-image0, libxcb-keysyms1, libxcb-randr0, libxcb-render0, "
        "libxcb-render-util0, libxcb-shape0, libxcb-shm0, libxcb-sync1, "
        "libxcb-xfixes0, libxcb-xinerama0, libxcb-xkb1, libfontconfig1, "
        "libdbus-1-3, libglib2.0-0t64, zlib1g\n"
        "Homepage: https://github.com/deskaygraphics/BridgeTruss\n"
        "Description: Desktop planar bridge truss analysis\n"
        " Model editing, static and moving-load analysis, and optional 3D views.\n"
        " Includes Python and desktop dependencies. Tested on Ubuntu 24.04 amd64.\n"
        " Educational software; not a certified bridge-design application.\n",
        encoding="utf-8",
    )
    package = output / f"bridgetruss_{VERSION}_amd64.deb"
    run(
        "dpkg-deb",
        "--root-owner-group",
        "-Zxz",
        "-z3",
        "--threads-max=2",
        "--build",
        str(stage),
        str(package),
    )
    with package.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    package.with_suffix(".deb.sha256").write_text(
        f"{digest}  {package.name}\n",
        encoding="utf-8",
    )
    print(f"Installer: {package}\nStaging tree: {stage}")
    return package


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reuse-bundle", action="store_true", help="Repackage an existing bundle")
    build(parser.parse_args().reuse_bundle)
