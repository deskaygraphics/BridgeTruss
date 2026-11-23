# BridgeTruss

BridgeTruss is a Python application for matrix analysis of planar bridge trusses
under static and quasi-static moving loads. It combines an editable desktop
interface, numerical response plots, illustrative 3D visualization, and
reproducible model and result exports.

Two interfaces are available:
- **Desktop application:** full model editing, moving-load analysis, design studies
  and optional 3D visualization.
- **Browser application:** a lightweight Streamlit interface for running supplied
  redundancy examples, animating 1–3 moving vehicles, comparing results and
  downloading numerical data.

Both interfaces use the same numerical analysis modules. The software is an
educational analysis tool, not a certified bridge-design application.

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

### Requirements

- Git, if downloading the source by cloning the repository.
- Python 3.10 or newer for the desktop source; Python 3.13 is the tested version
  for both interfaces and is recommended for the pinned browser dependencies.
- An internet connection to install Python dependencies.
- A desktop display for the Qt interface and a working OpenGL graphics stack for 3D.

The application has been tested on Linux. Other operating systems have not been
independently verified. The commands below use a Linux/macOS shell.

### Download the source

The browser interface and its configuration are on the `BridgeTruss` branch:

```bash
git clone --branch BridgeTruss https://github.com/deskaygraphics/BridgeTruss.git
cd BridgeTruss
```

If you already have this repository, open a terminal in its directory instead.
Run subsequent commands from the directory containing `main.py` and `web/`.
Use a separate virtual environment for each interface.

### Desktop application

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```
For later sessions, activate the same environment and run `python main.py`.
Close the window or press Ctrl+C in the launching terminal to exit cleanly.

The desktop stack uses NumPy, PySide6, Matplotlib, PyVista and PyVistaQt.
`requirements-dev.txt` adds testing and linting dependencies.
`requirements-lock.txt` records the package versions used for desktop verification;
it is not a cross-platform installation guarantee.

The desktop requirements install the graphics packages even if 3D is disabled.
To run the desktop application without initializing the 3D renderer:

```bash
BRIDGETRUSS_NO_3D=1 python main.py
```

If Qt reports a missing xcb cursor library on Ubuntu, check that the system package
`libxcb-cursor0` is installed.

### Browser application

With Python 3.13 installed, start a new terminal in the repository directory, then run:

```bash
python3.13 -m venv .venv-web
source .venv-web/bin/activate
python -m pip install --upgrade pip
python -m pip install -r web/requirements.txt
python -m streamlit run web/app.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.
Keep the terminal running while using the application. Press Ctrl+C in that
terminal to stop the server.

The browser requirements install Streamlit, NumPy and Matplotlib; Qt and VTK are
not required. Its interactive Canvas animation provides a projected 3D bridge
with truck, passenger-car and bus models, without external JavaScript downloads.
It does not include the desktop geometry editor or member picking.
A localhost address is accessible on your own computer, not a public hosting URL.

## Desktop usage

### Analyze a supplied example

1. Launch the desktop application and click **Open**.
2. Select `examples/pratt_vehicle.json` and confirm replacing the current model.
3. Inspect the nodes, member connectivity, supports, properties and loads.
4. Click **Analyze**. The example's saved vehicle settings determine whether the
   displayed load case includes the vehicle.
5. Read member forces/stresses, nodal displacements and support reactions in the
   numerical tables. Use the force and deformation tabs to inspect the diagrams.
6. Use **Compute Signed Envelopes** to find extrema over the complete vehicle
   passage, rather than relying on the current slider position.
7. Click **Export Results** and choose a parent directory for a new result bundle.

### Create or modify a model

1. Select a preset or create nodes and members. Assign supports, loads, elastic
   modulus and cross-sectional area. Property controls apply to newly added
   members; use **Edit Member Properties** to change existing members.
2. Click **Analyze** to calculate forces, stresses, displacements and reactions.
3. Save a stable, complete model with **Save Model**. Use **Open** to load it again.
   Incomplete or unstable models are rejected.

### Apply moving loads

1. Use **Select Deck Nodes** to define the load-transfer path. Presets already
   select their bottom-chord deck joints.
2. In **Moving Vehicle Loads** at the top of the right sidebar, choose **Number of
   vehicles (1–3)**. For multiple vehicles, set **Gap between vehicles** (rear axle
   of one vehicle to front axle of the next; default 4 m).
3. Enable moving loads and enter the front/rear axle forces and axle spacing.
   Every vehicle uses these same values; they are per-vehicle forces, not totals.
   With two vehicles, the convoy is a **truck followed by a passenger car**; with
   three, a **bus** follows the passenger car. Their bodies, colors, windows and
   wheels are visually distinct. Types do not assign assumed axle weights:
   numerical loads still come from the configured forces and axle spacing.
4. Use the position slider or **Play** to inspect successive quasi-static states.
   Open **Interactive 3D** to see all vehicles moving together. Playback continues
   until the last vehicle's rear axle exits. The slider tracks the leading front axle.
5. Click **Compute Signed Envelopes** for minimum/maximum responses and the
   corresponding front-axle positions over the full crossing.
6. Use **Influence Lines** for responses to a downward 1 N load; these exclude
   existing static loads.
Count and gap are included in saved scenarios and exports. Existing project files
without those settings open with one vehicle. The solver includes every axle in
the convoy; the extra vehicles are not just visual copies. Selecting an axle in
3D edits the shared front/rear force for every vehicle. Very small gaps can
overlap the illustrative body overhangs; the specified axle positions remain exact.

Existing static loads remain active unless explicitly removed with **Clear Static
Loads**. Envelope accuracy does not depend on the animation step or frame rate.
Editing analysis inputs clears stale results; recalculate the required studies
before exporting.

Connections are explicit: crossing bars are not automatically joined, and adding
an intermediate node does not split an existing member. Deck nodes must be distinct,
horizontal and have distinct x coordinates.

## Visualization and editing

The 2D force and deformation diagrams support wheel zoom, drag-to-pan and
double-click-to-fit. **View Controls** provides label scaling and a shared fit action.
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

To run a supplied redundancy study, click **Open** and select
`examples/redundant_bridge.json` (member **18**) or
`examples/benchmark_redundant.json` (member **4**, static loading). In
**Redundancy Study**, set the member and area factors, then click
**Run Redundancy Study**. Rejected candidates display a reason instead of a finite
response. These study files are separate from the moving-vehicle controls.

Within **Redundancy Study**, open **Analytical Verification** to run 49 comparisons
against the supplied triangle's independent hand equations. The panel shows
reference/computed values, units, absolute errors, tolerances, relative errors
(where the reference is nonzero), and PASS/FAIL results. Use **Run Analytical
Verification** to repeat the checks. This always checks the shipped static
triangle, not the active project, and does not change your model, vehicle settings,
or current study. Passing verifies those benchmark cases, not structural safety.

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

## Saving models and exporting results

- **Save Model:** stores geometry, properties, supports, static loads, deck nodes
  and vehicle settings in versioned JSON. Numerical results are recalculated on load.
- **Export Results:** creates a new timestamped directory containing `members.csv`,
  `nodes.csv` and `analysis.json`. Calculated envelopes add `envelopes.csv`.
- A calculated redundancy study adds `redundancy.json`, summary/member/node/envelope
  CSV files and PNG comparison figures.
- Browser downloads provide a reproducible study JSON and a summary CSV.

Original member IDs are preserved within a redundancy study. Deleting a member
from the active desktop model renumbers its remaining members.

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

## Browser usage

After starting Streamlit using the installation instructions above:

1. Choose an example:
   - **Redundant bridge — remove M18:** compare the bridge with a weakened or removed
     additional diagonal.
   - **Redundant triangle — analytical check:** compare the static triangle with
     its independently derived hand equations.
   - **Determinate bridge — essential M1:** inspect the effect of weakening or
     removing an essential member.
2. Set **Selected member area remaining (%)**. Zero removes the member; the
   original baseline is retained for comparison.
3. For bridge examples, enable or disable **Include complete vehicle passage**.
   Choose **Number of vehicles** (truck; truck + passenger car; or truck +
   passenger car + bus) and **Gap between vehicles (m)**. Gap means rear axle of
   one vehicle to front axle of the next. Expand **Axle forces and spacing
   (per vehicle)** to adjust shared axle forces and wheelbase. Vehicle types are
   visual, not assumed weights. The triangle always uses its prescribed static load.
4. In **Animated moving vehicles — baseline**, use **Play/Pause**, **Reset**, the
   leading-axle position slider, playback speed, camera view and deformation overlay.
   Drag the scene to orbit. The live displacement readout includes static loads
   and all active convoy axles, using the same solver response coefficients as desktop.
   Playback speed is illustrative, not physical speed or a dynamic analysis.
5. Click **Run example** to calculate the complete-passage study for the selected convoy.
6. Inspect **Comparison figures**, **Numerical results**, and **Assumptions**.
   Expand the independent-verification section for hand-reference values,
   computed values, errors and tolerances.
7. Download the study JSON or summary CSV if needed. The JSON records the vehicle
   count, gap, and complete axle list used in the calculations.

Changing an input clears the previous result; click **Run example** again.
The animation always shows the unmodified baseline, even when a member-removal
candidate is rejected. It is not a prediction of that candidate's movement.
The study plots show labeled common-load-case and envelope results, not the live
animation position.
An accepted stiffness solution is not a structural safety assessment.

### Browser tests

With the browser environment activated:

```bash
python -m pip install -r web/requirements-dev.txt
python -m pytest web -q
```

Browser animation tests use Playwright with a separate headless Chrome/Chromium
session and never use your browser profile. If Chrome/Chromium is not on `PATH`,
those browser checks are skipped; numerical and Streamlit tests still run.

## Troubleshooting

- **Missing Python package:** activate the intended virtual environment and install
  its requirements using `python -m pip`. Desktop and browser dependencies are separate.
- **Qt xcb cursor error on Ubuntu:** check that the system package
  `libxcb-cursor0` is installed.
- **OpenGL or 3D initialization failure:** the application checks Qt's OpenGL
  context before initializing 3D. If initialization or a rendering operation raises
  an exception, the 3D tab displays the reason while 2D analysis remains available.
  The launcher removes an inherited `QT_XCB_GL_INTEGRATION=none` override when
  3D is enabled so Qt can select GLX/EGL; explicit backend choices are preserved.
  Use `BRIDGETRUSS_NO_3D=1 python main.py` to skip 3D entirely, including when a
  graphics driver crashes or hangs in native code (which Python cannot catch).
- **Unstable or ill-conditioned model:** review supports, connectivity and member
  properties. The solver does not add artificial stiffness to conceal instability.
- **Invalid deck path:** select at least two distinct existing joints at a common
  elevation, with different x coordinates.
- **Results disappear after an edit:** this prevents stale output. Run the analysis
  or study again with the new inputs.
- **Browser port already in use:** choose another port, for example
  `python -m streamlit run web/app.py --server.port 8502`, and use the printed URL.
