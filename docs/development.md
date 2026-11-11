# Development

Clone the shared repository when the owner provides its URL. For a local review use `git clone --no-local "/path/to/return-window" return-window-review`. Start a change from the accepted baseline with `git switch -c topic/descriptive-name`. Run the affected checks, inspect `git diff --cached`, and make scoped commits. Open a PR once the owner has set up remote collaboration. Include evidence and remaining limits in the PR template.

Integrated changes need an independent reviewer. Yumeth reviews data and producer changes. Senula reviews runtime and consumer changes. Changes crossing the pack boundary need both. Isath reviews scientific assumptions, reference frames and evidence. Abhimantha resolves architecture and integration decisions. Record each required sign-off in the PR. GitHub code-owner assignment alone does not enforce that both producer and consumer approve.

The CODEOWNERS file records the intended mapping in comments. Replace the placeholders with confirmed accounts or teams with write access before relying on automated reviewer requests. Configure branch protection and required checks once the remote exists.

## Editor and Atlas

Use Node 22. From `web/` run `npm ci`, `npm run check:data`, `npm run check:atlas`, and `npm run build`. Run `npm run dev` and visit the printed local URL or its `/atlas` route.

## Documentation engine

From `documentation/` use Python 3.12 and run `uv sync --locked --python 3.12` and `uv run --locked pytest -q`. Run `uv run --locked marsdoc ../evidence/jezero/jezero-evidence.json --query ../evidence/jezero/jezero-route.json` to reproduce the preview evidence decision.

## MOLA ingestion

From `pipeline/`, use Python 3.11 and run:

```sh
uv venv --python 3.11 .venv
uv pip install -r requirements-lock.txt
uv pip install --no-deps -e .
export RW_MOLA_WORKSPACE="$(mktemp -d)"
.venv/bin/return-window ingest configs/mola-global-4ppd-topography.json --workspace "$RW_MOLA_WORKSPACE"
.venv/bin/return-window verify-cache --workspace "$RW_MOLA_WORKSPACE"
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/check-mola.py --workspace "$RW_MOLA_WORKSPACE"
```

The ingest command obtains eight pinned archive members, approximately 4.2 MB in total. For an offline checkout, copy the preserved corrected delivery's `data/` directory into a new external workspace. Its registry file must match the SHA-256 in `evidence/mola/mola-record.sha256` for the exact historical receipt check. Verify with the same CLI command plus `ingest ... --offline --expected-record-sha256 <digest>`. Freshly acquired registry metadata can differ from the historical receipt.
