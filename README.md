# BridgeTruss

BridgeTruss is a Python application for matrix analysis of planar bridge trusses
under static and quasi-static moving loads. It combines an editable desktop
interface, numerical response plots, illustrative 3D visualization, and
reproducible model and result exports.

Two interfaces are available:
- **Desktop application:** full model editing, moving-load analysis, design studies
  and optional 3D visualization.
- **Browser application:** a desktop-style Streamlit workspace with model editing,
  interactive 2D/3D views, moving loads, result tables, design/redundancy studies
  and desktop-compatible model files. Both interfaces support traffic profiles
  with up to three simultaneous vehicles. The original guided
  demo is also available.

Both interfaces use the same numerical analysis modules. The software is an
educational analysis tool, not a certified bridge-design application.

## Features

- Create and edit nodes, members, supports, material properties and nodal loads.
- Start from Pratt, Warren, Howe or custom truss layouts.
- Calculate joint displacements, support reactions, axial forces and stresses.
- Inspect magnified deformation, signed force diagrams and numerical diagnostics.
- Define a horizontal deck path and a two-axle vehicle with adjustable forces and spacing.
- In the desktop and full web workspace, combine one to three Car/Bus/Truck vehicles with
  independently editable axle forces, wheelbases and following gaps.
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
The `main` branch contains the older guided demo, not this full workspace.

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

The browser requirements install Streamlit, NumPy, Matplotlib and Plotly; Qt and
VTK are not required. Run from the repository root to use the included dark
theme configuration. A localhost address is accessible on your own computer,
not a public hosting URL.

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
2. At the top of the right sidebar, set **Number of vehicles** (1–3). Added
   followers default to Car and Bus, using the same presets as the full web workspace.
3. Use **Edit individual vehicles…** to configure each type, axle forces,
   wheelbase and rear-to-next-front axle gap. **Load preset** explicitly applies
   that vehicle type's example forces/wheelbase. Changing a type alone preserves
   custom loads. The main sidebar axle inputs edit vehicle 1 only.
4. Enable moving loads, then use the leading-front position slider or **Play**
   to inspect successive quasi-static states. Each vehicle contributes its own
   two axle loads; static loads are counted once.
5. Click **Compute Signed Envelopes** for minimum/maximum responses and the
   corresponding front-axle positions over the full crossing.
6. Use **Influence Lines** for responses to a downward 1 N load; these exclude
   existing static loads.

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

To run the supplied redundant-bridge example:

1. Open `examples/redundant_bridge.json`.
2. Select **Redundancy Study** and choose original member **18**.
3. Keep the default area factors `1,0.75,0.5,0.25,0`, or enter your own.
4. Click **Run Redundancy Study**, then choose a candidate to compare.
5. Inspect the case summary, member-force changes and common-case displacements.
   Rejected candidates display a reason instead of a finite response.

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
- `traffic_three_vehicles.json`: the redundant bridge with a Truck, Car and Bus
  together (version 2; opens in the updated desktop and full web workspace).

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
- Browser downloads provide desktop-compatible model JSON, member CSV,
  displacement-history CSV, PNG figures and a ZIP of the result bundle.
  Calculated redundancy studies add detailed study CSVs and comparison figures.

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

1. **Full workspace** starts with an analyzed Pratt truss. Use **New Project**
   for an empty model, or the sidebar's **New / presets / open** section to
   choose Pratt/Warren/Howe, open a supplied example, or upload desktop JSON.
   Replacing a project requires confirmation.
2. Expand sidebar tools to add/move nodes, attach/edit/delete members, assign
   loads and supports, select deck joints or clear static loads. Submit the
   relevant form to apply an edit. Incomplete drafts are allowed; **Undo last
   edit** restores the previous model. Click **Analyze** after editing.
3. Use **2D View**, **Axial Forces** and **Deformation** for interactive diagrams.
   Scroll to zoom, drag to pan, or double-click to fit. **View controls** changes
   labels, coloring and camera settings without changing structural results.
4. **Interactive 3D** shows an illustrative extruded bridge, road and truck.
   Drag to orbit. **Scene selection** highlights a node/member/load and exposes
   edit/removal controls. Use **Add / attach member** to connect two joints.
   Browser selection controls replace Qt's right-click picking; this is not a
   pixel-identical Qt window.
5. Apply **Moving vehicle loads** settings for the original truck or a
   one-to-three-vehicle profile (see below). Use the slider or **Play / Pause /
   Reset**. The 3D vehicles and wheels animate locally
   in the browser between numerical response steps; the scene and camera stay
   mounted rather than being rebuilt for every visual frame. The caption
   distinguishes the visual front position from the solved position used by
   tables, force colors and deformation. Response steps are nominally 250 ms;
   delayed refreshes catch up using elapsed time without backfilling history.
   Pause solves the current position. Playback is not physical time or dynamics.
6. **Compute Signed Envelopes** evaluates the full passage independently of
   playback. Other tabs provide influence lines, design exploration, redundancy
   of any active member, displacement history and equal-volume comparisons.
   The latter requires preset-compatible ten-node geometry.
7. Expand **Save model / export results** below the tables. Save model JSON or
   member CSV, or prepare a downloadable ZIP and PNG figures. Chart camera
   buttons also download images, including the 3D view. Model saves retain the
   existing stable/complete-model validation.

On phones, the model sidebar starts collapsed; use the top-left sidebar arrow
to open it and the sidebar's collapse button to close it again. The toolbar's
**Controls** switch opens vehicle and view settings in a floating, independently
scrollable panel; **Hide controls** closes it. Hidden panels preserve settings,
form inputs and analysis results. On larger screens, Controls toggles the
right-hand column and hiding it expands the dashboard. Your panel choice is
retained when resizing or rotating the browser.

Each browser session owns its own model and results; refreshing/reconnecting
can start a new session, so download your model before closing the page.
Model/vehicle changes clear affected results and playback history. Manual
position changes and Reset clear history; the latest 1000 solved frames are
retained. The interactive workspace allows up to 200 nodes, 800 members and
2 MB model uploads to bound per-session computation.

Choose **Guided demo** in the sidebar for the original preset-based audience
examples, independent triangle checks and study downloads. It does not modify
the full workspace's model.

An accepted stiffness solution is not a structural safety assessment. Both
interfaces share the solver, model format and engineering limitations;
decorative 3D geometry adds no stiffness, mass or self-weight.

### Two or three simultaneous vehicles (full web workspace)

1. Open **Controls → Moving vehicle loads** and set **Number of vehicles** to
   2 or 3. For a ready-made example, open `traffic_three_vehicles.json` from
   **Supplied model** and click **Analyze**.
2. Choose each vehicle's type. **Load preset for vehicle N** explicitly fills
   example axle forces/wheelbase; merely changing the type does not overwrite
   your custom values. The illustrative presets are Truck: 80/120 kN, 4 m;
   Car: 8/7 kN, 2.7 m; Bus: 50/90 kN, 6 m. These are not regulatory design vehicles.
3. Edit individual axle forces, wheelbases and follower gaps. Traffic-profile
   wheelbases must be at least 1.2 m. A gap is measured from the previous
   vehicle's **rear axle to the next front axle**, not bumper to bumper;
   minimum 2 m, default 3 m. The original single-truck form retains its
   legacy input range, including compact schematic axle pairs.
4. Check **Enable moving loads**, then **Apply traffic settings**. A draft
   warning means the inputs are not applied yet; figures/results still use
   the displayed **Applied traffic** configuration.
5. Use **Leading front axle position (%)**, **Play / Pause / Reset** and
   **Interactive 3D**. Each vehicle has its own mesh and follows at a fixed
   offset with the same direction and playback clock. Traffic profiles include
   a one-metre visual margin at entry/exit so the bodies as well as all axles
   clear the bridge. Original single-truck position mapping is unchanged.

All active axle loads are combined with the static loads **once**. Current
response, signed envelopes, design comparisons, redundancy studies and history
use the applied traffic. The 2D diagrams show the combined nodal loads.
Influence lines remain unit-load responses, independent of configured traffic.
For traffic profiles, every reported `front_x_m`/front-position column means the
**leading vehicle's front axle**, not a follower's position. The vehicle table
shows individual front positions. Envelopes cover the passage of this particular
fixed formation; they do not optimize independently placed vehicles, gaps or speeds.
No opposing traffic, overtaking, collisions, dynamics or extra self-weight is modeled.

The original single Truck still saves **version 1** JSON and opens on desktop.
Car/Bus and multiple-vehicle profiles save **version 2**, including all vehicle
types, forces, wheelbases and gaps. Both updated interfaces can open these files,
validate the same control precision, and calculate using the same complete axle list
and leading-front positions. Older desktop versions reject version-2 profiles;
update them before opening these files. Returning to a single Truck and applying settings
restores version-1 saves.

Result ZIPs include the complete versioned model plus traffic definitions and
flattened axle offsets/forces in `analysis.json`; studies retain their position
reference. The redundancy CLI also reads version-2 files and uses every axle.
Guided demo remains the original single-truck audience example, with unchanged
verified results.

### Browser tests

With the browser environment activated:

```bash
python -m pip install pytest
python -m pytest web -q
```
The browser suite covers atomic model edits, undo, session isolation,
desktop-compatible JSON/scenario round trips, numerical parity, invalidation,
history, exports and Streamlit interactions. An additional opt-in test exercises
real Chrome, including WebGL views, playback, uploads, downloaded files,
phone-width layouts, panel toggles, independent scrolling, simultaneous traffic,
and versioned project save/reopen.
With Playwright and Google Chrome installed and the local server running:

```bash
BRIDGETRUSS_WEB_BROWSER=1 python -m pytest web/test_browser.py -q
```

Set `BRIDGETRUSS_CHROME` if Chrome is installed outside `/usr/bin/google-chrome`.
If another app is already using port 8501, run this checkout on another port,
then point browser verification to that server:

```bash
python -m streamlit run web/app.py --server.port 8502
```

In another terminal using this checkout and environment:

```bash
BRIDGETRUSS_WEB_BROWSER=1 BRIDGETRUSS_WEB_URL=http://127.0.0.1:8502/ python -m pytest web/test_browser.py -q
```

Check that the page heading says **BridgeTruss | Planar Analysis** and the sidebar
offers **Full workspace**, rather than testing an older guided-demo checkout.

## Troubleshooting

- **Missing Python package:** activate the intended virtual environment and install
  its requirements using `python -m pip`. Desktop and browser dependencies are separate.
- **Qt xcb cursor error on Ubuntu:** check that the system package
  `libxcb-cursor0` is installed.
- **OpenGL or 3D initialization failure:** try `BRIDGETRUSS_NO_3D=1 python main.py`
  or use the browser interface for the supplied numerical examples.
- **Unstable or ill-conditioned model:** review supports, connectivity and member
  properties. The solver does not add artificial stiffness to conceal instability.
- **Invalid deck path:** select at least two distinct existing joints at a common
  elevation, with different x coordinates.
- **Results disappear after an edit:** this prevents stale output. Run the analysis
  or study again with the new inputs.
- **Browser port already in use:** choose another port, for example
  `python -m streamlit run web/app.py --server.port 8502`, and use the printed URL.
