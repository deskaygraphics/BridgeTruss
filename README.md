# BridgeTruss — Verified Planar Analysis

A Python/PySide6 teaching tool for matrix analysis, influence lines, quasi-static
moving-load envelopes, and mass–deflection exploration of planar bridge trusses.
The dashboard and automated benchmarks use the **same numerical solver**.
This is educational analysis software, not a certified bridge-design application.

## Install and run

The source targets Python 3.10+; the verified environment is Python 3.13 on
Linux. Other Python/platform combinations have not been independently validated.
From this application directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

`requirements.txt` defines runtime dependencies; `requirements-dev.txt` adds tests
and linting (`python -m pip install -r requirements-dev.txt`).
`requirements-lock.txt` records the installed versions used for local
verification, scoped to project dependencies rather than unrelated installed
packages; it is an environment snapshot, not a cross-platform guarantee.
To reproduce that package set, install it instead of `requirements-dev.txt`.

The optional illustrative 3D view uses PyVista/VTK and a working graphics stack.
Runtime requirements install the full stack; rendering can still be disabled.
Disable it with `BRIDGETRUSS_NO_3D=1 python main.py` if OpenGL is unavailable.
If Qt reports a missing xcb cursor library on Ubuntu, the system package is
`libxcb-cursor0`.

For the existing checkout, launch from the project root with:

```bash
BridgeTruss3D_Source_Code/BridgeTruss3D/.venv/bin/python BridgeTruss3D_Source_Code/BridgeTruss3D/main.py
```

The Ubuntu desktop shortcut uses absolute paths to this checkout. Update it if
you move the project; the shortcut does not replace the Python dependencies.

## Engineering scope

- Small-displacement, linear-elastic, pin-jointed **2D axial truss** analysis.
- Nodal forces and zero-displacement x/y restraints; SI internally: m, N, Pa.
- Positive member force/stress means tension; negative means compression.
- Reactions follow `R = K U - F`. Free-DOF residuals should be near zero.
- No bending stiffness, member buckling, joint rigidity, dynamics, fatigue,
  material/geometric nonlinearity, automatic self-weight, or design-code checks.
- The 3D view duplicates the planar solution for illustration. It does **not**
  calculate spatial load distribution or out-of-plane stability. Do not interpret
  the duplicated members as two separately analyzed load-carrying trusses.
- The low-level solver retains its existing 3D bar capability, but the dashboard,
  benchmark suite, and design workflow focus on planar models.

## Dashboard workflow

1. Select a preset or create nodes, members, supports, and static loads.
   Connections are explicit: adding a node on a bar does not split the bar,
   and crossing bars do not automatically form a joint.
2. Use **Edit Member Properties** to change existing E and area. The area/E
   controls on the left apply only to newly added members.
3. **Analyze** computes signed forces, stresses, displacements, reactions, strain
   energy, relative free-DOF residual, and a stiffness condition estimate.
   Unstable/ill-conditioned systems are rejected rather than silently regularized.
4. For vehicle analysis, use **Select Deck Nodes** to specify the load-transfer
   path. Presets select their six bottom-chord nodes. Selected nodes must be
   distinct, horizontal, and have distinct x coordinates.
5. Enable moving loads, set the two axle forces and spacing, and move the slider
   or press Play. Travel includes the rear axle's complete exit. Static loads
   remain active; **Clear Static Loads** isolates the vehicle response.
6. **Compute Signed Envelopes** evaluates the complete passage even if animation
   is disabled. The Load Envelopes tab lists min/max displacement components,
   reactions, member forces/stresses, and governing front-axle positions.
7. In **Influence Lines**, compute and select a member force, restrained reaction,
   or displacement component. These use a downward **1 N** load and exclude
   static loads. Force/reaction ordinates are N/N; displacement ordinates are m/N.
8. **Save Model/Open** round-trip geometry, properties, supports, static loads,
   deck nodes, and vehicle controls in versioned JSON. Open asks before replacing
   the model. Only stable, complete models can be saved/loaded; incomplete drafts
   are deliberately rejected. Numerical results are recalculated after loading.
9. **Export Results** creates a fresh timestamped folder with `members.csv`,
   `nodes.csv`, `analysis.json`, and `envelopes.csv` when envelopes are calculated.
   Metadata includes the full input model/scenario, units, diagnostics, and any
   calculated design study. Member IDs are consistently one-based in the current
   model; deleting members renumbers them. Editing result tables is disabled.

Analyses/edits invalidate advanced results to avoid displaying stale values.
Calculate envelopes and a study after setting the final loading, then export
without changing the vehicle slider. Changing any study input clears its results.

## Zooming and reading the 2D diagrams

The small **Deformed Shape (magnified)** and **Axial Force Diagram** panels, and
the larger **Deformation** and **Axial Forces** tabs, support:

- Mouse wheel over the axes: zoom in/out around the pointer.
- Left-button or middle-button drag: pan. Releasing the button or leaving the
  canvas ends the drag.
- Double-click: fit that diagram to the current model.
- **View Controls → Fit 2D Diagrams**: reset zoom/pan in all four diagrams.
- **View Controls → 2D label size**: adjust text from 75% to 250%. Load values,
  visible node IDs, axis numbers and titles scale together. Try 150% first.

Each diagram keeps its own zoom/pan during load changes, moving-vehicle playback
and label-size changes. Geometry/connectivity changes reset it to fit. Text size
is a shared session setting; Fit does not reset it, and it is not saved in model
JSON files. Use the large tabs or resize the panels when a high label size needs
more room.

Text scaling and zoom do not change numerical results or the deformation
magnification factor. A title such as `Deformation ×252` reports the display
magnification; the actual displacements are in the results table.
Values beside load arrows are the **applied nodal loads**, not member axial
forces. Member force signs are shown by color; numerical member forces remain in
the Member Forces and Stresses table.

## Interactive 3D editing

Open **Interactive 3D (planar model)**. Right-click the visible surface of a member,
joint sphere, static-load arrow, vehicle wheel/hub, or axle-force arrow to select it.
Left-drag rotates the camera; use the mouse wheel to zoom and **Fit View** to fit
the bridge in the viewport. Decorative transverse ties, roadway and truck body
are not editable. Wheels select their associated numerical axle. Hidden objects
must first be exposed by rotating the view or hiding decorative surfaces.

- **Edit Selected** on a member opens its two endpoint nodes, area, and E.
  Change endpoints to reconnect it. Duplicate connections, identical endpoints,
  zero-length members, and invalid properties are rejected before changing the model.
- **Attach Member (2 joints)** starts connection mode: right-click the first joint
  sphere, then the second. The first joint turns green. The new member uses the
  **New Member Properties** area/E controls on the left. Clear Selection cancels.
- Select a joint and use **Edit Selected** to add a static nodal load. Select its
  arrow to change Fx/Fy or reattach that load to another joint. Existing values
  are prefilled; replacing a different joint's existing load requires confirmation.
  Set both components to zero to remove the load.
- Select a visible vehicle wheel/hub or axle-force arrow to edit its force and axle spacing.
  These modify the vehicle definition, not the static nodal loads.
- **Remove Selected** asks for confirmation. It removes a selected member or
  static load; on a joint it removes only the joint's static load, never the joint.
  On an axle it sets that axle force to zero. Its force arrow disappears, but its
  wheels remain visible and selectable; restore the force through the wheels or sidebar.
- **Undo 3D Edit** restores the preceding model and vehicle settings for one
  successful 3D edit, including an edit that caused structural instability.
  This is single-step undo, not an undo history. Running another analysis or
  changing model/vehicle inputs clears it. Cancelling a dialog does not change
  the model. Selecting an object or entering attach mode pauses vehicle playback.

Gold highlights identify the selected entity on **both** displayed sides. Those
two actors represent the **same planar member or joint**, not independent spatial
members. Static-load arrows are duplicated for illustration, not added twice to
the analysis. New edits recalculate results and clear stale advanced outputs.
If removing/reconnecting a member makes the truss unstable, results are cleared
and a warning is shown; geometry remains editable for repair or Undo 3D Edit.
Edits use node selectors and numeric inputs, not freehand dragging in 3D.

## Realistic bridge and vehicle presentation

The procedural two-axle truck includes a cab, cargo body, windshield and side
windows, grille, lights, bumpers, cylindrical tires, hubs and rotating spokes.
Wheel centres follow the **actual configured axle spacing**. The vehicle remains
visible on approach and departure; an axle applies load only while on the selected
deck. Zero force disables the axle load, not the physical wheel drawing.
Spacing below 1.2 m uses a labeled compact schematic; spacing above 12 m uses a
labeled schematic axle-pair layout instead of stretching a road truck indefinitely.
At extreme spacing, off-span schematic axles may be outside the camera/approach.

A valid horizontal deck path adds an illustrative reference road slab, edge
markings, barriers, transverse floor ties, bearings at restrained deck joints,
abutment blocks and ground. The roadway is 0.18 m above the deck-node elevation.
These visual dimensions/materials do not represent designed section properties:
**none adds stiffness, mass, self-weight, restraints or loads to the solver**.
The duplicated trusses still represent one planar analysis.

In the 3D tab:
- **Road / bearings**, **Vehicle**, and **Load arrows** independently control
  visibility. Hide decorative surfaces to inspect/select obscured members.
- **Steel** coloring gives neutral shaded members; **Axial Force/Stress** retain
  signed tension/compression colors.
- **Isometric** and **Side** set camera presets with y vertical. **Follow vehicle**
  tracks a three-quarter close-up. **Free camera** stops automatic tracking;
  left-drag and wheel zoom remain available. Camera position is retained during
  ordinary updates. Choosing a preset or Fit View intentionally reframes the view.
- **Show 3D Deformation** magnifies the truss displacement by 50. The road and
  vehicle remain on the undeformed reference deck; this is an explanatory overlay,
  not a computed deflected deck or vehicle suspension response.

### Playback versus numerical results
**Response step (m/step)** replaces the old Travel step label. It is the nominal
distance between numerical response positions (130 ms update intervals), not a
physical speed. The truck interpolates between those positions on a 33 ms visual
timer; the actual frame rate depends on the machine and renderer.

During playback the position label shows visual x and **tables: x** separately.
The response tables, force colors and deformation correspond to the last numerical
position, not to a dynamic solution at every animation frame. Pause snaps to the
nearest slider position and recalculates there; selection and save/export also
pause and synchronize before continuing. Reset returns to the route start.

Static bridge and vehicle meshes are reused while the vehicle moves. Wheel
rotation follows travel distance; it is cosmetic. A cached static/unit-deck-load
solution reconstructs each numerical load case by exact linear superposition,
without repeatedly factoring the same stiffness matrix. Geometry/property,
support, deck-path and static-load changes invalidate the relevant caches.
With magnified truss deformation enabled, the changed member geometry is rebuilt
at numerical steps. Hidden primary plots are not redrawn at each playback step.
Envelope accuracy is independent of the playback step and timer.

For a presentation, enable moving loads, choose Steel and Isometric, then Play.
Use Follow vehicle for a close-up and Side with the road hidden for direct editing.
The **Moving Load Setup Guide** button and hover tooltips explain the workflow.

## Numerical method and moving loads

For element length L and global direction vector n, define `v = [-n, n]`.
The global element stiffness is `(EA/L) outer(v, v)`. Assemble it into K,
partition restrained/free DOFs, and solve `Kff Uf = Ff`. Recover axial force as
`N = (EA/L) vᵀ ue`; reactions are `K U - F`; strain energy is `0.5 Uᵀ K U`.
Finite coordinates/properties, connectivity, duplicate members and stiffness
stability are checked before solving. Dense matrices suit the small teaching
models; this is not a large-scale sparse FE implementation.

An axle at x between adjacent deck nodes xa and xb transfers downward loads
`P(1-t)` and `Pt`, where `t = (x-xa)/(xb-xa)`. This preserves vertical force and
moment for the assumed deck/floor-beam load-transfer model; deck bending is not
analyzed. An axle outside the path contributes no force.

Within each interval between axle/node crossing events, every signed linear
response is affine in vehicle position. Envelope evaluation therefore uses all
crossings `front_x = deck_x + axle_offset`, plus entry/exit and one-sided boundary
states. Small position offsets (`1e-10 × max(travel length, 1 m)`) approximate
one-sided states where support reactions jump as axles enter/leave.
Reported critical positions can differ by that tolerance, and tied extrema can
have several valid positions. This is not a time-dependent/dynamic analysis.

All positions are solved in one multiple-right-hand-side operation on a single
stiffness assembly. The Python API also supports sampled envelopes by supplying
explicit positions; sampled results are labeled accordingly.

## Fair comparisons and design exploration

The comparison table reuses the current ten-node preset geometry, supports,
static loads, and vehicle definition. It enforces a uniform elastic modulus and
equal total member volume, assigning a uniform area to each candidate layout.
Mass assumes density 7850 kg/m³. With moving loads enabled, comparisons use each
candidate's **complete envelope**, not the current animation frame. Comparison
requires node IDs 0–9 and a common elastic modulus. It reuses their current
coordinates, including edits, rather than accepting unrelated node-ID layouts.
Invalid candidate layouts or mixed-modulus models leave the comparison blank
with an explanatory tooltip; the main analysis remains available.
Presets are educational layouts, not validated representations of built bridges.

In **Design Exploration**, enter comma-separated heights, horizontal-chord area
factors, and web area factors (at most 500 combinations). Nonhorizontal members
form the web group, including end posts. Height changes preserve x coordinates
and scale elevations relative to the horizontal bottom deck. The current
model's area pattern is the baseline. The study never changes the active model.

Feasibility means only that peak vertical displacement and absolute axial stress
are within the **user-entered screening limits**. Mass uses the entered density;
changing mass does not introduce self-weight. Vehicle-enabled studies use the
full static-plus-vehicle envelope. Blue points are feasible, red infeasible,
and stars mark nondominated feasible mass/deflection candidates. The reported
minimum mass is only among feasible sampled candidates, not a global optimum.
Compression stress passing a limit does not establish buckling safety.

### Interpreting results

- Influence lines show one selected response versus a downward 1 N load position;
  they exclude existing static loads.
- Envelopes include static and vehicle loads. Different component extrema
  generally occur at different positions, not as one simultaneous load case.
- Peak vertical `|uy|` and maximum displacement component are different measures;
  neither automatically equals the largest displacement-vector norm.
- Pareto stars identify nondominated feasible sampled designs, not certified
  safe designs or a guaranteed global optimum.

## Redundancy and load redistribution study

**Engineering question:** How does losing stiffness in one load path change the
forces carried by the other members, deflection, and the governing vehicle position?

Open `examples/redundant_bridge.json`, select **Redundancy Study**, set the original
member ID to **18** (the added diagonal from N1 to N7), and click **Run Redundancy
Study**. The saved example enables 80/120 kN axles at 4 m spacing and retains four
50 kN static loads. The two crossing diagonals are not connected at their crossing.
This is a modified educational Pratt model, not a model of an actual bridge.

- Default area factors are `1,0.75,0.5,0.25,0`. Only the selected member changes;
  factor zero actually removes it, rather than substituting a tiny artificial area.
  The original baseline is always included. Up to 50 input factors in [0,1] are accepted.
- **Compare candidate** selects the displayed before/after force diagrams, signed
  force changes, common-case nodal displacements, and full-study deflection curve.
  Both force diagrams use the same color scale. Removed members are dashed;
  their forces/stresses and percentage ratios with a zero baseline are left undefined.
  Use **Enlarge Comparison** for a resizable presentation view.
- With moving loads enabled, every accepted candidate gets complete event-based
  force, stress, displacement and reaction envelopes. The summary reports separate
  critical member/force positions and critical node/vertical-deflection positions.
  Member comparison tables include signed force-envelope bounds and their positions.
- Force diagrams and force-change tables use the **baseline's governing
  absolute-member-force position for every candidate**, not the current slider
  position and not each candidate's unrelated envelope extrema. The position is labeled.
  Common-case displacement tables also use that same position.
- With moving loads disabled, the study compares the prescribed static loads only.
  The active model, loads, members and numerical results are not modified.
- Rejected candidates display the solver reason and no invented finite response.
  Rejection can mean a mechanism, a disconnected free node or ill-conditioning;
  the software does not infer collapse capacity. The count `m+r−2j` is descriptive,
  not the stability test. Reduced-stiffness eigenvalues determine solver acceptance.
- Original one-based member IDs remain aligned even after removal; ordinary model
  edits outside the study still renumber members as described earlier.
  Fully restrained orphan anchors are retained with their loads and reactions:
  they introduce no free DOF. An orphan with any free translation is rejected.
- Editing analysis/study inputs clears the corresponding study outputs.
  **Export Results** includes `redundancy.json`, summary/member/node/envelope CSVs,
  and one PNG comparison per non-baseline candidate, also embedding the study in
  `analysis.json`. Export immediately after running the study, before changing inputs.
  CSVs use SI units; figures/tables label their kN and mm conversions.

### Reproduce the case studies without the GUI

From the application directory, using the project environment:

```bash
python run_redundancy_study.py --output /tmp/bridgetruss-redundancy-study
```

The output directory must not already exist. This generates three subdirectories:

1. `triangle`: reduce/remove M4 of `benchmark_redundant.json`; compare against
   independent force-method equations in `analytical_checks.csv`.
2. `redundant_bridge`: reduce/remove added diagonal M18, keeping the other 17
   members. Complete removal leaves a stable original Pratt truss.
3. `determinate_bridge`: reduce/remove M1 of `pratt_vehicle.json`. Area reduction
   changes displacement but not the determinate force solution; removal is rejected.

Each contains input metadata, case summaries, signed redistribution values, nodal
results, any moving-load envelopes, PNG figures and `interpretation.txt`.
The generated interpretation distinguishes equilibrium from compatibility and
identifies the largest signed force change among remaining members.
Use `--static` for static-only bridge studies. For another saved model:

```bash
python run_redundancy_study.py --model examples/redundant_bridge.json --member 15 --factors 1,0.5,0 --output /tmp/bridgetruss-member15
```

### Independent compatibility derivation

In the shipped unit-height redundant triangle, let `alpha=A4/A4,0`,
`EA=2e9 N`, `Lv=1 m`, `P=1000 N`, and
`f=(sqrt(2)+1/2)Lv/EA`, the original triangle's vertical apex flexibility.
If `Q` is the load carried by the original triangle and `k4=alpha EA/Lv`,
compatibility and vertical equilibrium give:

- Apex downward displacement: `delta=Q f`.
- Added-bar compressive force magnitude: `k4 delta`.
- Equilibrium: `P=Q+k4 delta`, hence `Q=P/(1+k4 f)`.
- Tie force: `Q/2`; diagonal forces: `−Q/sqrt(2)`;
  added-bar force: `−(P−Q)`.
- Each original vertical reaction: `Q/2`; anchor reaction: `P−Q`.
- Apex `uy=−Qf`, apex `ux=Q Lv/(2EA)`, strain energy `P Q f/2`.

These equations are evaluated for every factor, including the stable removal
limit `alpha=0`; no force is assigned to the absent bar. With default factors,
the generator performs 49 independent comparisons (displacements, forces,
reactions and energy). The removal-to-baseline deflection ratio is
`1+EA f/Lv ≈ 2.91421`. As the redundant bar softens, the original triangle carries
more load even though the applied load is unchanged.

**Presentation sequence:** explain the triangle compatibility equation; show
its before/after forces; run bridge M18 and point out redistribution and
deflection; contrast with determinate bridge M1 removal; finish with assumptions.
Do not promise a governing-position shift: report what the envelopes actually show.
Where extrema tie, the reported member/node and position are one valid choice;
very small numerical differences can select another tied extreme.
These are independent small-displacement linear-elastic reanalyses, not a
progressive-collapse or damage-evolution simulation. No buckling, capacity,
dynamic effects, self-weight updates or code compliance are assessed.

## Verification and development

```bash
python -m pytest -q
ruff check .
ruff format --check .
```

Default tests run without a display or VTK rendering. GUI integration tests use
Qt's offscreen platform and disable the embedded 3D view. Scene tests exercise
real VTK actors/meshes with a no-render plotter. On a working VTK graphics backend,
run the opt-in screen-coordinate/right-click regression as well:

```bash
BRIDGETRUSS_TEST_RENDER=1 python -m pytest -q
```

This also checks actual picking of members, joints, static-load arrows and a
vehicle axle after rebuilding the scene. Embedded Qt/VTK rendering needs a real
desktop/X11 graphics context; Qt's offscreen widget plugin does not support
QOpenGLWidget on every machine.

Independent analytical benchmarks (`test_solver.py`, `test_verification.py`):

1. **Axial bar:** L = 2 m, E = 200 GPa, A = 0.01 m², P = 1000 N.
   `u = PL/EA = 1e-6 m`, axial force 1000 N, support reaction −1000 N.
2. **Determinate triangle:** supports at (−1,0) and (1,0), apex at (0,1);
   left pin, right vertical roller; downward apex force P = 1000 N;
   all bars have EA = 2e9 N. Equilibrium gives bottom force `P/2`,
   diagonal forces `−P/sqrt(2)`, and vertical reactions `P/2`.
   Unit-load virtual work gives apex flexibility
   `f = (sqrt(2) + 1/2)/EA`, so `uy = −Pf`.
3. **Redundant triangle:** add a unit-length vertical bar from a fully restrained
   node at (0,0) to the apex, with the same EA. Compatibility gives the load
   carried by the original triangle `Q = P/(1 + EA f)`.
   Thus `uy = −Qf`, bottom force `Q/2`, diagonals `−Q/sqrt(2)`,
   vertical added-bar force `−(P−Q)`, and side reactions `Q/2`.
   This adds one degree of static indeterminacy:
   `members + restrained DOFs − 2 × nodes = 4 + 5 − 8 = 1`.
   The anchor at (0,0) is not connected to the bottom tie unless an explicit
   endpoint specifies that connection.

The reproducible comparison file is
[`examples/benchmark_verification.csv`](examples/benchmark_verification.csv).
Regenerate it from this application directory:

```bash
python verify_benchmarks.py --output examples/benchmark_verification.csv
```

The script loads the shipped JSON examples and compares separately derived
analytical equations with computed displacements, signed member forces,
reactions and strain energy. It exits nonzero if a comparison fails. These
three cases are limited verification evidence, not certification of all models.

Representative displacements (metres, rounded):

| Case / response | Analytical reference | Solver result |
| --- | ---: | ---: |
| Axial bar: loaded-end `ux` | `1.000000000000e-6` | `1.000000000000e-6` |
| Triangle: apex `uy` | `-9.571067811865e-7` | `-9.571067811865e-7` |
| Redundant triangle: apex `uy` | `-3.284271247462e-7` | `-3.284271247462e-7` |

The CSV preserves full-precision errors and pass/fail criteria. Nonzero
references use a strict `<0.1%` relative-error limit. Zero references use
absolute limits (`1e-10 m`, `1e-6 N`, `1e-9 J`, as applicable), with percentage
error left blank. The student must review the hand derivations independently.
Regression tests also check strain energy, global force/moment balance, invalid models, solver-adapter
agreement, axle force/moment transfer, influence superposition, event envelopes
versus 2001 regularly sampled positions plus events, JSON round trips, exports,
area scaling, fair-comparison assumptions, study constraints, and GUI failure
invalidation. No commercial-software validation is claimed.

Example JSON files in `examples/` provide the three benchmark cases and a Pratt
vehicle scenario. Open them directly for a reproducible demo.

## Proposal presentation and handoff

The current deck in [`../../proposal_slides/`](../../proposal_slides/) has
**nine PDF pages** after author edits. `6_Slides` is a legacy filename.
The proposal presentation was completed on October 27, 2026; four-slide files
are historical alternatives.

Use `BridgeTruss_Proposal_6_Slides.pdf` for the current presentation.
`Speaker_Notes_6_Slides_and_QA.txt` contains the earlier five-minute script plus
Q&A and has not been reconciled with all subsequent slide edits.
Compile from the project root using:

```bash
latexmk -cd -xelatex -interaction=nonstopmode -halt-on-error proposal_slides/BridgeTruss_Proposal_6_Slides.tex
```

The source uses `fontspec` and `unicode-math`: **pdfLaTeX cannot compile it**.
The current slide source also uses absolute paths to the root screenshots;
these need relative-path/asset repair for portability. The presentation source
ZIP is historical and does not match the current edited source.
Select a XeLaTeX editor recipe/Overleaf compiler. `-f` does not fix an engine
mismatch. MiKTeX update-status warnings are separate; verify the exit status
and generated PDF. The local `.latexmkrc` supplies defaults only when a command
does not override the engine.

Times New Roman is preferred when installed or supplied as licensed files.
The verified local PDF uses **Tinos**, a Times-compatible substitute, with
TeX Gyre Termes Math. `FONT_SETUP.txt` explains genuine Times New Roman setup;
proprietary font files are not distributed.

[`../../PROJECT_HANDOFF.txt`](../../PROJECT_HANDOFF.txt) lists current artifacts,
personal/submission checks and packaging exclusions. This README and the slides
do not prove submission to Gradescope.

The completed written proposal is
[`../../written_proposal/BridgeTruss_Project_Proposal.pdf`](../../written_proposal/BridgeTruss_Project_Proposal.pdf).
Its cover records Desmond Kangah, dkanga1@lsu.edu, and the author-confirmed
submission date October 29, 2026. Its source ZIP and build/requirements guidance
are in the same folder. It includes five main-text pages and seven references.
Its eight total PDF pages include actual 2D/3D interface screenshots on F2;
the images are bundled as portable assets in the proposal source ZIP.
The final demonstration is November 24; feature freeze November 22; rehearsal
November 23; final report/source due December 5, 2026, 11:59 pm.

The November 19 study update passed 137 tests with one optional rendering test
skipped, 25 original analytical comparisons, 49 new triangle comparisons,
Ruff lint and formatting (29 files). The October 30 review separately recorded
100 tests including real VTK picking; no new real-VTK-picking check is claimed.
A fresh-environment
install is not yet verified; `pip check` reports missing dependencies for an
unrelated installed MintPy package. See the root validation record.

## Suggested 12-minute demonstration

- 0–2 min: assumptions, element formulation, and analytical bar benchmark.
- 2–4 min: redundant triangle and compatibility verification.
- 4–7 min: Pratt vehicle passage, selected influence line, and signed envelopes.
- 7–9 min: equal-volume layout comparison under common loads.
- 9–11 min: mass–deflection parameter study and interpretation of its limits.
- 11–12 min: reproducible export and conclusions.

Capture desktop screenshots or a short recording before the presentation as a
backup. A five-minute proposal talk should instead prioritize the engineering
problem, matrix method, three-benchmark plan, and feasible scope.

## Reference and AI disclosure

McGuire, W., Gallagher, R. H., and Ziemian, R. D. (2000).
*Matrix Structural Analysis*, 2nd ed., Wiley. The analytical examples above are
explicitly derived here rather than attributed to a particular textbook example.
Official library documentation (accessed October 30, 2026):
- NumPy: https://numpy.org/doc/stable/
- Qt for Python / PySide6: https://doc.qt.io/qtforpython-6/
- Matplotlib: https://matplotlib.org/stable/
- PyVista: https://docs.pyvista.org/
- PyVistaQt: https://qtdocs.pyvista.org/

These sources document the software APIs, not independent validation of the
structural calculations. Exact local versions are recorded in `requirements-lock.txt`.

The Warp AI assistant supported implementation/refactoring, debugging and
presentation and written-proposal drafting. Numerical checks and independent derivations are supplied for review; the student remains responsible for the
accuracy and disclosure of submitted work under the course policy.
