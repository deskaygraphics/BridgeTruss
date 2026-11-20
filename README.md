# BridgeTruss

BridgeTruss is a Python application for matrix analysis of planar bridge trusses
under static and quasi-static moving loads. It combines an editable desktop
interface, numerical response plots, illustrative 3D visualization, and
reproducible model and result exports.

## Features

- Create and edit nodes, members, supports, material properties and nodal loads.
- Start from Pratt, Warren, Howe or custom truss layouts.
- Calculate joint displacements, support reactions, axial forces and stresses.
- Inspect magnified deformation, signed force diagrams and numerical diagnostics.
- Define a horizontal deck path and a two-axle vehicle with adjustable forces and spacing.
- Calculate influence lines and complete moving-load envelopes with governing axle positions.
- Compare layouts at equal material volume and explore height/member-area combinations.
- Study stiffness reduction and member removal without modifying the active model.
- Save models as versioned JSON and export results as CSV, JSON and PNG files.

## Installation

Python 3.10 or newer is required. The desktop application has been tested with
Python 3.13 on Linux; other platforms have not been independently verified.

Run these commands from the application directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

The desktop stack uses NumPy, PySide6, Matplotlib, PyVista and PyVistaQt.
`requirements-dev.txt` adds testing and linting dependencies.
`requirements-lock.txt` records the package versions used for desktop verification;
it is not a cross-platform installation guarantee.

The 3D view requires a working OpenGL graphics stack. To disable it:

```bash
BRIDGETRUSS_NO_3D=1 python main.py
```

If Qt reports a missing xcb cursor library on Ubuntu, check that the system package
`libxcb-cursor0` is installed.

## Basic usage

1. Select a preset or create nodes and members. Assign supports, loads, elastic
   modulus and cross-sectional area. Property controls apply to newly added
   members; use **Edit Member Properties** to change existing members.
2. Click **Analyze** to calculate forces, stresses, displacements and reactions.
3. For vehicle loading, use **Select Deck Nodes**, enable moving loads and set
   the axle forces and spacing. Existing static loads remain active unless cleared.
4. Use **Compute Signed Envelopes** for the complete passage and **Influence Lines**
   for responses to a downward unit load. Envelope accuracy does not depend on
   the animation step or frame rate.
5. Use **Save Model/Open** for JSON models and **Export Results** for a result bundle.
   Invalid or unstable models are rejected; editing inputs clears stale results.

Connections are explicit: crossing bars are not automatically joined, and adding
an intermediate node does not split an existing member. Deck nodes must be distinct,
horizontal and have distinct x coordinates.

## Visualization and editing

The 2D force and deformation diagrams support wheel zoom, drag-to-pan and
Double-click-to-fit. **View Controls** provides label scaling and a shared fit action.
Displayed deformation is magnified; numerical tables contain the actual movements.

The optional **Interactive 3D** tab supports member, joint and load selection,
property editing, member attachment, load reassignment and single-step edit undo.
Right-click selects an object; left-drag rotates the camera. Roadway and vehicle
meshes are illustrative and add no stiffness, mass or self-weight to the analysis.

## Redundancy and design studies

**Redundancy Study** compares a selected member at different area factors. A factor
of zero removes the member rather than assigning artificial stiffness. Original
member IDs remain aligned across candidates. The study reports stability status,
force redistribution, nodal displacements and full-passage extrema. Force diagrams
use the same load position for every candidate; unrelated envelope peaks are not
shown as one simultaneous load case. **Enlarge Comparison** opens a larger view.

**Design Exploration** evaluates a finite grid of heights and chord/web area factors.
Feasibility means satisfying the entered displacement and axial-stress screening
limits. Pareto candidates and the reported minimum mass apply only to the tested
grid, not to a guaranteed global optimum or a certified safe design.

Example models in `examples/` include:
- `benchmark_bar.json`: axial bar with a closed-form displacement reference.
- `benchmark_triangle.json`: determinate triangle.
- `benchmark_redundant.json`: triangle with an added load path.
- `pratt_vehicle.json`: planar bridge with a two-axle vehicle.
- `redundant_bridge.json`: bridge with an additional diagonal; M18 can be studied.

To generate reproducible redundancy results without opening the desktop interface:

```bash
python run_redundancy_study.py --output /tmp/bridgetruss-study
```

The output directory must not already exist. Add `--static` for static-only bridge
studies, or use `--model`, `--member` and `--factors` to analyze another saved model.

## Numerical method and limitations

The solver assembles axial-member stiffness matrices and solves `Kff Uf = Ff`.
Member forces follow from compatible axial extensions; reactions are `K U - F`.
The application checks input validity, stiffness stability, residuals and strain energy.
Axles between deck joints are distributed to adjacent joints while preserving
vertical force and moment for the assumed load-transfer model.

- Planar, pin-jointed, small-displacement and linear-elastic analysis.
- Internal units: metres, newtons and pascals; positive member force means tension.
- Loads and zero-displacement restraints act at nodes.
- The 3D scene illustrates a planar result; it is not a spatial bridge analysis.
- No bending, buckling, yielding, fatigue, dynamics, automatic self-weight,
  geometric nonlinearity or design-code certification.
- Member removal is an independent linear reanalysis, not progressive collapse.
- Stable means accepted by the stiffness check, not proven safe.

## Testing

Install development dependencies and run the desktop checks:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
python verify_benchmarks.py
```

Default tests do not require VTK rendering. On a working graphics backend, enable
screen-picking checks with `BRIDGETRUSS_TEST_RENDER=1 python -m pytest -q`.
Analytical checks cover axial-bar, determinate-triangle and redundant-triangle
responses; regression tests also cover moving loads, stability, persistence,
exports, editing and study-result invalidation. These checks are not structural
safety certification.

## Pre-commit checks

Install the Git hook from the repository directory in an activated Python
environment. The hook tooling can also be installed independently of the desktop
dependencies:

```bash
python -m pip install "pre-commit>=4.2,<5"
python -m pre_commit install
python -m pre_commit run --all-files
```

Commits run pinned Ruff linting/formatting hooks, spelling checks, requirements-file
sorting, notebook-output stripping, and checks for YAML, JSON and TOML syntax,
merge conflicts, new files larger than 500 KB, private keys, trailing whitespace
and missing final newlines. Notebook checks run only when notebooks are present.
Virtual environments and generated caches are excluded.
If a hook reformats a file, review and stage that file again before retrying the
commit. Each new clone needs its own `pre_commit install` step.

These fast checks do not replace the test suite or analytical benchmarks.

## Browser interface

The lightweight Streamlit interface uses the same numerical modules as the desktop
application, without installing Qt or VTK. It provides bounded examples, area-factor
controls, vehicle inputs, force/displacement comparisons, analytical checks and
CSV/JSON downloads. It does not provide the full desktop geometry editor or 3D view.

From this repository directory:

```bash
python3 -m venv .venv-web
source .venv-web/bin/activate
python -m pip install -r web/requirements.txt
python -m streamlit run web/app.py
```

Open the local URL printed by Streamlit. Browser dependencies are declared separately
in `web/requirements.txt`. To run its tests, install `pytest` in that environment and
run `python -m pytest web -q`.
