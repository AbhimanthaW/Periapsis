# Navigation and local pack runtime

`python_engine/` and its six original tests are byte-preserved from the delivered Senula routing source. Its A* uses dimensionless synthetic cell costs, eight neighbours and diagonal corner checks. It does not use elevation differences or directed travel seconds. Its plotting demo requires Matplotlib in a separate environment. The original server file is empty.

`mission.py` is a separate bounded consumer for pack v1. It uses the shared structural and semantic checks, including the external site hash when supplied. It loads source-backed Jezero as an elevation preview and runs the audited closure and reserve calculations in explicitly enabled fixture simulation. The fixture's four-neighbour edge model uses a fixed base of one second per metre plus two seconds per metre of ascent. These are software control values. This runtime keeps the legacy algorithm intact and leaves physical mobility and tactical routing unsupported.

From the repository root run:

```sh
uv run --project documentation --locked python -m pytest runtime/tests contracts/tests -q
uv run --project documentation --locked python -m runtime.mission inspect /path/to/preview-pack
uv run --project documentation --locked python -m runtime.mission simulate contracts/fixtures/synthetic-v1 --closure mid
```

Add `--site-sha256` with an independently recorded digest when validating a released pack. Exit 2 reports a refused pack or request as structured JSON on stderr. A valid simulation that cannot return reports its decision state in JSON on stdout.
