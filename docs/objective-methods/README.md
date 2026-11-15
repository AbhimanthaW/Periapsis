# Arcadia Planitia elevation review

Yumeth owns the catalog, recommender, tests, and handoff. The team reviewed `576d2c1`; the implementation branch starts at `7b61f94ac2d0050265f1149daa5ba6ec477d8a6b`.

## Primary demo

- **Region and profile** — Arcadia Planitia (`03`), Astronaut, with the exact approximately 4 × 4 km polygon in the [handoff query](../../pipeline/evidence/arcadia-planitia/evidence-query.json).
- **Objective** — “Map broad elevation context and assess local elevation at 20 m posting.”
- **Interpretation** — Versioned lexicon with manual goal confirmation. Zero learned topics enabled.

| Method | Verdict | Deliverable and evidence |
| --- | --- | --- |
| Review MOLA elevation context | Suggested | Regional orientation map from the existing orbital altimetry product `mola-meg004-topography` v1.1. The handoff records usable coverage for the exact polygon. Native spacing is 0.25°, about 14.8 km nominal at the equator. [Context image](../../pipeline/evidence/arcadia-planitia/arcadia-mola-context.png) · [NASA PDS MOLA archive](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html) |
| Analyze a local stereo terrain model | Pending | Local elevation grid and coverage note from an existing orbital stereo product. The pinned package supplies no qualifying stereo DTM with usable coverage and posting of 20 m or finer across the polygon. Posting describes grid spacing. Future analysis requires a separate effective feature scale check. [Arcadia resolver report](../../pipeline/evidence/arcadia-planitia/verification.json) · [USGS CTX DTM collection](https://stac.astrogeology.usgs.gov/docs/data/mars/ctxdtms/) |

**Without MOLA** excludes the context method and leaves both observations uncovered. **With a stereo DTM** marks the pending stereo method as requested. A broader restriction on MOLA-aligned or MOLA-derived products requires clarification.

The evidence lookup matches region, footprint ID, exact polygon, package version, and resolver query. It preserves the handoff API's provenance classification. A profile-only change preserves the evidence verdict for the two orbital methods. The recommender returns both the reasons for the method statuses and the reasons for any uncovered observations.

## Verification

From `web/mission-preview`, run `npm run test:methods` on Node 22. Set `RW_SYNTHETIC_FIXTURE` to the `synthetic-science/synthetic-science-context.json` path from the existing exporter to include the test for all six synthetic fields. Generate it with `RW_CELL_MAP_WORKSPACE` pointing outside the repository. Keep the dependency environment outside `documentation/` as well. [Fixture contract and exporter](../../documentation/SYNTHETIC-SCIENCE.md)

The test-only fixture input preserves cell and recipe IDs and distinguishes a synthetic zero from missing coverage. Real-site proposals use the pinned Arcadia evidence lookup.

## Demo replay

Isath approved **Review methods** beside the Explore objective and a dedicated advisory-only Arcadia view in Science Tasks.

Start a fresh session at `/#demo/arcadia` or choose **Arcadia demo** in Explore. Show the bundled regional MOLA context and the withheld local-elevation decision. The direct link opens the pinned walkthrough after a reload and keeps tactical routing gated. Jezero remains the comparison control.

For the editable method-review rehearsal:

1. In **Explore**, open **Review methods** and choose **Load Arcadia scenario**. Review the two goals, suggested regional MOLA context, and pending local stereo method.
2. Choose **Open Science Tasks**. Review the same proposal in the Arcadia advisory view.
3. Return to **Explore**, append **Without MOLA.** to the objective, submit it, and reopen the review. Both observations are uncovered. Switch profiles or use the selected region to verify that exclusions persist.
4. Replace that phrase with **With a stereo DTM.**, submit, and reopen the review. Stereo is requested and pending. Return to **Science Tasks** and reload to check the explicit recovery message.

Run `npm run build` and `npm run test:ui` from `web/mission-preview`. Use a disposable checkout for the full UI suite because it rewrites the reference captures. After building, set `RW_UI_PRODUCTION=1` and run `npm run test:ui -- objective-methods.spec.ts` to replay against the built assets. The demo test blocks external requests and permits loopback.
