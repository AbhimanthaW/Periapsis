# Offline readiness

Prepare dependency environments and build the editor with `npm ci` and `npm run build` from `web/`. Prepare the pinned Jezero preview with the [reconstruction instructions](../evidence/jezero/README.md). Keep its external site SHA-256 and copy the dedicated pack directory with the build.

From the repository root, use the already synchronized Python environment:

```sh
uv run --project documentation --locked --offline python -m runtime.mission inspect /path/to/preview-pack --site-sha256 <trusted-digest>
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid --remaining-s 70
uv run --project documentation --locked --offline python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid --closure north
```

Replace `<trusted-digest>` with the separately recorded SHA-256 before running the first command. The simulation should show 40 s direct return and a feasible 75 s science task, followed by 60 s direct return and an infeasible 95 s task. The latter two commands exercise over-reserve and no-path refusal. The editor and Atlas can be served separately on loopback with `npm run preview` from `web/`. Open Atlas at `/atlas`. The compiled asset bundle retains local imagery and research content. External citations are links.

## Full mission replay release gate

**BLOCKED.** The CLI can load the emitted Jezero preview and run the audited synthetic scenario. The web app has no mission view or local planning API connecting these functions. A general analytical pack writer and physical mobility model also remain open.

The next milestone is a small local planning API over the bounded simulation, with versioned request/response schemas and a mission view in the existing web app. Keep Jezero preview and synthetic simulation visibly distinct. Acceptance requires a fresh browser profile on a disconnected second machine. Load the preview, switch to the synthetic scenario, submit a predefined closure, display the changed route and science decision, retain completed tasks, and show no-route and over-reserve results without displaying a stale plan. Qualification of a real tactical terrain pack is a separate scientific milestone.
