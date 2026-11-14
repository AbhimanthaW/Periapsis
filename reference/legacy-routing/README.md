# Legacy routing prototype

This early prototype uses dimensionless synthetic cell costs, eight neighbours, and diagonal corner checks. It predates the [mission pack runtime](../../runtime/README.md).

Run its original regression tests from the repository root using the locked science environment.

```sh
uv run --project documentation --locked --offline python -m pytest reference/legacy-routing/tests -q
```

The interactive entry point is `python_engine/main.py`. It requires NumPy and Matplotlib.
