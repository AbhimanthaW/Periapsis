# Return Window · Explore slice design QA

Final result: passed for slice review, with the content, state and map limits below.

## Captures

The final browser captures use Chromium at 1440 × 900 CSS pixels and device scale 2. Every original and capture is 2880 × 1800 pixels. The three comparisons use the original PNGs directly, with no crop, stretch or resampling before the pixel diff. Side-by-side JPGs and focused crops are companion views. The bundled copies of the originals are unmodified.

| Screen | Comparison state | What changed after review |
| --- | --- | --- |
| Planetary Explore | Jezero explicitly selected with the keyboard, then viewed without the focus outline. The fresh launch has no selection. | Restored the text wordmark and nav positions; reused the Viking globe and matching control positions. Restored the height of the right panel with cell measurements and widened its label column. Map markers are landmarks. |
| Ranked Areas | Original 01b, with the same objective and one real result explicitly selected. | Rebuilt the reference table around the service fields. Kept the three-row composition with pagination; replaced duplicated IDs with an “Unlabelled area” label when the service supplies no name. |
| Region Investigation | Jezero CTX subset, Data tab open. | Kept the map crop, tabs, data table, limits and panel bounds; moved the extra drill link out of the Data panel. The heading and footer now use cell context and live ranked areas. |

## Remaining differences

- **Content and state:** The app opens without an active region. Named indicators have no rank numbers. The selected Jezero summary uses measured cell data and context instead of the old survey estimates. Explore adds the Mars base control and keeps a method review entry. 
- **Ranking and copy:** The service evaluates 196,608 cells and returns up to 20 areas. The capture uses the real pack and response, so names, tier, record counts and parsed concepts differ from the placeholders. “Delta” is displayed as demo only for this pack. The ranking includes sort, page and investigation actions.
- **Map and typography:** Both map frames use the existing clean assets at the original composition. Minor differences in image tone, detail and antialiasing remain in the diffs. The layout uses the existing Inter and IBM Plex Mono assets and the app’s dark and orange palette; the reference did not supply font or color tokens. Other cells without a local imagery asset show planetary context. 
- **Base and simulation:** The starting coordinates and their HEALPix cell pass through to Marswalk. Its rehearsal computes routes on an independent synthetic terrain grid. No arbitrary Mars coordinates are presented as qualified real-terrain routing.

## Verification

Playwright exercised an unselected launch, landmark hover and keyboard focus, objective entry, target edit and cancel, exclusions, sorting, table selection, contextual investigation, and return navigation. It also checked the base form’s validation, focus restoration, persistence, clearing, and the handoff to a real simulated planning response. A separate run exercised an unsupported objective and service failure with retry. Layer changes, zoom, landmark tooltips, the sources dialog, tab keyboard navigation and viewport fit at 1440, 1100, 768 and 390 CSS pixels were checked. Existing route, analysis, monitoring, hazard and Arcadia behavior received regression coverage. The TypeScript production build passed. 

The three targeted screens are ready for review. Later reference screens were not redesigned.
