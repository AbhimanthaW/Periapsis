# Return Window frontends

For the judge-facing mission interface, run the [repository-root launch command](../README.md#launch) and open [Return Window](http://127.0.0.1:8000/). Running `npm run dev` from `web/` calls the same launcher. The mission interface lives in [`mission-preview/`](mission-preview/README.md).

## Legacy Atlas development

The earlier Explore and Atlas implementation lives in `web/src/` and is packaged at [Legacy Atlas](http://127.0.0.1:8000/legacy/). To edit it with Vite, use Node 22.12 or later in the Node 22 series and run from `web/`:

```sh
npm ci
npm run dev:legacy -- --port 4175 --strictPort
```

Open [Legacy Atlas development](http://127.0.0.1:4175/). Start the root launcher separately for the local APIs. Vite forwards requests to port 8000 by default. Set `RW_PLANNING_API_ORIGIN` to use another port. Run `npm run check:atlas` to verify the bundled map layers and regional registry.
