# Offline readiness

Prepare the [Mission app and planning service](../web/README.md) before disconnecting. Install frontend dependencies with `npm ci` and build with `npm run build` from `web/`. Prepare the pinned Jezero preview with the [reconstruction instructions](../evidence/jezero/README.md). Keep its external site SHA-256 and copy the dedicated pack directory if you want to run the preview inspection below.

From the repository root, use the already synchronized Python environment:

```sh
uv run --project documentation --locked --offline python -m runtime.mission inspect /path/to/preview-pack --site-sha256 <trusted-digest>
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid --remaining-s 70
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid --closure north
```

Replace `<trusted-digest>` with the separately recorded SHA-256 before running the first command. The simulation should show 40 s direct return and a feasible 75 s science task, followed by 60 s direct return and an infeasible 95 s task. The latter two commands exercise over-reserve and no-path refusal.

## Browser replay

Start the planning service from the repository root and run `npm run preview` from `web/`. Open the printed loopback URL. The [Jezero control setup](../web/README.md#jezero-engineering-control) shows how to supply the committed evidence and include Jezero in the build.

For the release rehearsal, use a fresh browser profile on a disconnected second machine. Open the configured site, enter the synthetic simulation, and verify the baseline, middle closure, over-reserve and no-route states. Confirm the completed task remains recorded and each refusal clears the previous recommendation. The real tactical terrain pack and second-machine release check remain open.
