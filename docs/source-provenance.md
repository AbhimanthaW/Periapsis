# Source provenance

Imports use the snapshot from the 10 November 2026 repository audit. The owner retains the inventory and full SHA-256 manifest alongside the local repository.

| Component | Authoritative delivery |
|---|---|
| Editor and Atlas | Desktop/NASA Space Apps 26/architecture-documentation |
| Documentation engine | documentation_engine in that delivery |
| MOLA ingestion | Desktop/NASA Space Apps 26/Return Window Pipeline Stage 1 Corrected, version 0.1.1, commit `adb39451ab62bc838bd351def59a94bcdc95c3ae` |
| Navigation | Downloads/mars-mission-control, delivery archive SHA-256 `f0da6b01c77d5f607f282de01ad8b4ac48d84914f1499079ff27770a38df8d1a` |
| Jezero preview | Telegram Desktop/Martian-Map-browser.zip, SHA-256 `37630f8e2a98480baa7f11406e3bd936a01fd2f0221f5993f229e0dc91ecea7f` |

Preserve dataset attribution and review redistribution terms before publication. The archive and original source Git objects live in the owner's preserved snapshot. Large source data and generated packs are external.

The original corrected ingestion history is also recoverable from the local `.migration/corrected-stage1.bundle`. It includes unmodified commits `945ce4ec8e04ef6316c04e19c242de027a09e7b1` and `adb39451ab62bc838bd351def59a94bcdc95c3ae`. Inspect with `git bundle list-heads` or clone the bundle to a separate temporary directory. The monorepo imports the reviewed source tree at the latter commit. The original branch contains PDS data, so its objects stay outside monorepo ancestry.
