"""Build and serve the pinned Return Window bundle on loopback."""
from argparse import ArgumentParser
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from contracts.pack import PackError
from ranking.inputs import SHA256
from ranking.pack import Pack
from runtime.planning_api import ROOT, create_server


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def index(directory: Path) -> dict[str, str]:
    paths = sorted(directory.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError(f"Symbolic links are unsupported in release input: {directory}")
    return {path.relative_to(directory).as_posix(): digest(path)
            for path in paths if path.is_file()}


def run(*args: str, cwd=ROOT, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def source_paths():
    paths = subprocess.check_output(
        ["git", "ls-files", "-z", "runtime", "contracts", "documentation", "pipeline",
         "ranking", "evidence", "web"], cwd=ROOT).decode().split("\0")
    return [name for name in paths if name and "/tests/" not in name and "/qa/" not in name]


def build(out: Path, ranking_inputs: Path, ranking_pack: Path | None):
    out = out.resolve()
    if out.exists():
        raise ValueError(f"Choose a new output directory: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise ValueError("Node 22 and npm are required to build the app")
    with TemporaryDirectory(prefix=".return-window-", dir=out.parent) as scratch:
        work = Path(scratch)
        bundle = work / "bundle"
        bundle.mkdir()
        run(npm, "run", "build", cwd=ROOT / "web", env={**os.environ, "VITE_PACKAGED_RELEASE": "1"})
        run(npm, "run", "build", cwd=ROOT / "web/mission-preview", env={
            **os.environ, "VITE_RELEASE_BASE": "/demo/", "VITE_HAZARD_RUNTIME": "1",
        })
        shutil.copytree(ROOT / "web/dist", bundle / "app")
        shutil.copytree(ROOT / "web/mission-preview/dist/client", bundle / "demo")
        destination = bundle / "ranking"
        if ranking_pack is None:
            run(sys.executable, "-m", "ranking.build", "--release",
                "--inputs", str(ranking_inputs.resolve()), "--output", str(destination))
        else:
            shutil.copytree(ranking_pack, destination)
        pack = Pack(destination)
        if (not pack.manifest["release"] or pack.manifest["synthetic_layers"]
                or pack.manifest["input_sha256"] != SHA256):
            raise ValueError("Offline release requires a sourced pack built from the pinned ranking inputs")

        forecast_env = {**os.environ, "PYTHONPATH": str(ROOT / "pipeline/src")}
        station = work / "synthetic-station.csv"
        forecast = (sys.executable, "-m", "return_window_pipeline.forecast")
        run(*forecast, "synth", "--out", str(station), env=forecast_env)
        run(*forecast, "train", str(station),
            "--station", "pipeline/examples/weather/synthetic-station.json",
            "--artifact", str(bundle / "forecast.json"), env=forecast_env)

        manifest = {
            "schema_version": 1,
            "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "ranking_pack_sha256": pack.sha256,
            "forecast_model_id": json.loads((bundle / "forecast.json").read_bytes())["model_id"],
            "source_files": {name: digest(ROOT / name) for name in source_paths()},
            "files": index(bundle),
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        bundle.rename(out)
    print(f"Built Return Window release at {out}")


def verify(bundle: Path):
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unknown release manifest schema")
    packaged = index(bundle)
    del packaged["manifest.json"]
    if packaged != manifest["files"]:
        raise ValueError("Packaged files differ from the release manifest")
    for name, expected in manifest["source_files"].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or digest(source) != expected:
            raise ValueError(f"Release source mismatch: {name}")
    if (not (bundle / "app/index.html").is_file() or not (bundle / "demo/index.html").is_file()
            or digest(bundle / "ranking/manifest.json") != manifest["ranking_pack_sha256"]
            or json.loads((bundle / "forecast.json").read_bytes())["model_id"] != manifest["forecast_model_id"]):
        raise ValueError("Release component identity mismatch")
    return manifest


def main():
    parser = ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    prepare = modes.add_parser("build")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("--ranking-inputs", type=Path, default=Path("data/ranking-inputs"))
    prepare.add_argument("--ranking-pack", type=Path)
    serve = modes.add_parser("serve")
    serve.add_argument("bundle", type=Path)
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.bundle, args.ranking_inputs, args.ranking_pack)
            return
        bundle = args.bundle.resolve()
        manifest = verify(bundle)
        with create_server(args.port, ranking_pack=bundle / "ranking", engine="marswalk",
                           hazard_model=bundle / "forecast.json", static_root=bundle) as server:
            print(f"Return Window {manifest['revision'][:12]} ready at http://127.0.0.1:{server.server_port}/", flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
    except (OSError, ValueError, KeyError, PackError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Release {args.command} failed: {error}\n")


if __name__ == "__main__":
    main()
