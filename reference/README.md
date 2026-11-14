# Development references

- [Engineering workspace](engineering-workspace/README.md) for the interactive System Architecture editor, its [source specification](engineering-workspace/src/initial.ts), and the [Mars Research Atlas](engineering-workspace/docs/mars-research-atlas.md). The Atlas includes the [56-region catalog](engineering-workspace/src/atlas/regions.json) and [original research survey](engineering-workspace/public/atlas/MARS_REGIONAL_RESEARCH.md). The [scientific model design review](engineering-workspace/docs/scientific-model-design-review.md) records assumptions and evidence needs.
- [Project framework](project/PROJECT_FRAMEWORK.md), [execution plan](project/EXECUTION_PLAN.md), and [12 November implementation snapshot](project/CURRENT_STATE.md) for earlier decisions and their evidence.
- [Legacy routing prototype](legacy-routing/README.md) for the original synthetic A* implementation and regression tests.

Run the [Mission MVP](../web/README.md) and the engineering workspace from their own directories. The science and pipeline tests read the preserved Atlas catalog. Both browser builds use the same checked-in Jezero context image and metadata.
