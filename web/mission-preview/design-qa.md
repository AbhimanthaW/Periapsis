# Return Window visual QA

**final result: passed**

## Evidence

The original PNGs are in `/Users/abhimantha-personal/Desktop/Return Window/Return Window — UI References`. The [reference gallery](qa/gallery.md) identifies all 24 states and links each original, runnable state, final browser capture, full-view comparison, focused comparison, and pixel difference. The selected fixture states reproduce the source compositions, including the multi-panel comparison boards.

Playwright captured 23 screens at 1440 × 900 CSS pixels and 03d at 768 × 1024. All captures use Chromium and device scale factor 2. The desktop originals and captures are 2880 × 1800 physical pixels. The compact original and capture are 1536 × 2048. Each side-by-side uses the same reduction for both panes. The diff compares aligned original-size RGB pixels and amplifies absolute channel differences threefold.

Some committed gallery PNGs are resized to fit the repository's 2 MB file limit. Run Playwright to regenerate full-resolution captures before running the comparison script.

## Comparison history

| Group | Initial findings | Adjustments and final evidence |
| --- | --- | --- |
| 02a–02b Investigation | Evidence card heights and release-gate columns needed alignment. | Tuned investigation section spacing and fixed gate table column proportions. Rechecked the Science, Terrain, and Suitability cards and the capability column. |
| 03–04a Planning | Compact toolbar retained a desktop profile control. The tablet route outlines were too heavy, and the desktop results and comparison panels differed in vertical density. Crew table rows and the returned result wrapped differently. | Hid desktop actions behind the compact menu, revised the alternate route outlines, aligned result card spacing, and sized the crew table and rover specification columns. Rechecked the 768 px viewport with both main actions visible. |
| 05–05d Analysis | Model timings wrapped, the report controls started too low, and the analysis map paths were too small. | Held timing values to one line, aligned the report columns and options, and registered the overlay to the analysis inset. Rechecked the tables, trace prompt, provenance, report options, and selected revision. |
| 06–07a Monitoring | Rover camera and map panels were short by one grid gap. Playback paths overlaid the endpoint text. The module library and crew trade-off had minor vertical shifts. | Corrected dashboard grid height, placed the active route behind endpoints, rendered a separate remaining path, and aligned the module and trade-off cards. Rechecked the desktop monitoring, contingency, editor, and salvage states. |
| 01–02 Baseline | Shared navigation, badges, and tabs changed to support the new stages. | Re-ran the existing exploration tests and compared fresh baseline captures. The approved NASA mark remains in the shared desktop header. |

Reviewed composition, panel bounds, spacing, typography, surface colors, map framing, route and marker layering, copy, and selected or unavailable states. The gallery includes a focused region per state for reviewing small labels and controls. The originals remained the comparison inputs.

## Remaining visual differences and scope

- The approved NASA mark shifts the adjacent desktop navigation. The compact reference uses its RW abbreviation.
- Browser typography and icons approximate the source. Some dense tables have small differences in wrapping, padding, and column widths.
- The clean orbital rasters have minor differences in resampling, tint, and fine detail. Route joins, dash patterns, chart strokes, and shadows also vary slightly.
- The camera surfaces show unavailable states. Planning, model execution, telemetry, closure scenarios, and release gates use deterministic fixtures. Route and layout edits operate within those fixtures. State and custom layouts are kept in the current page session.
- JSON export was directly exercised. Trace CSV is a local download and PDF opens the browser print dialog. No automated print dialog assertion was made.

## Verification

- 27 Playwright tests passed, including the existing three-screen regression suite and 21 additional reference captures.
- Astronaut journey passed from objective and region through evidence, science task, run, closure, operator decision, and mission record. Keyboard selection of a candidate that exceeds a limit kept its confirmation disabled.
- Rover comparison, keyboard route selection, scrub and playback, component and salvage navigation, obstruction recheck, route switch, mission revision, and JSON export passed.
- The layout preset, model rerun and inspection, scenario cards, and compact plan actions passed. Browser captures recorded zero console errors, uncaught page errors, or failing HTTP responses.
- TypeScript and the production build passed. Four static packaging and routing checks passed.
