"""Build and serve the pinned Return Window bundle on loopback."""
from argparse import ArgumentParser
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen

from contracts.pack import PackError
from ranking.inputs import SHA256, verify_digest
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


SOURCE_DIRS = ("runtime", "contracts", "documentation", "pipeline", "ranking", "evidence", "web")
GENERATED_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules",
                  "build", "dist", "qa", "tests", "test-results"}
RELEASE_URL = "https://github.com/AbhimanthaW/Periapsis/releases/download"


def source_paths():
    # GitHub source ZIPs have the same inputs without a Git index.
    for directory in SOURCE_DIRS:
        for root, dirs, files in os.walk(ROOT / directory):
            dirs[:] = sorted(name for name in dirs
                             if name not in GENERATED_DIRS and not name.endswith(".egg-info"))
            for name in sorted(files):
                if name == ".DS_Store" or name.endswith(".pyc") or name == ".env" or name.startswith(".env."):
                    continue
                yield (Path(root) / name).relative_to(ROOT).as_posix()


def source_hashes():
    return {name: digest(ROOT / name) for name in source_paths()}


def source_identity(files: dict[str, str]) -> str:
    return sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def revision(files: dict[str, str]) -> str:
    if (ROOT / ".git").exists():
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    return "source-" + source_identity(files)


def download_ranking_inputs(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in SHA256.items():
        destination = directory / name
        if destination.is_file():
            try:
                verify_digest(destination, expected)
                continue
            except ValueError:
                pass
        version = "v0.1.0" if name == "cells-enriched.ndjson.gz" else "v0.2.0"
        print(f"Downloading pinned ranking input {name}…", flush=True)
        with NamedTemporaryFile(dir=directory, delete=False) as output:
            temporary = Path(output.name)
        try:
            with urlopen(f"{RELEASE_URL}/mars-cell-map-{version}/{name}", timeout=60) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
            verify_digest(temporary, expected)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def build(out: Path, ranking_inputs: Path, ranking_pack: Path | None, *, install=False):
    out = out.resolve()
    if out.exists():
        raise ValueError(f"Choose a new output directory: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        raise ValueError("Node 22 and npm are required to build the app")
    if install:
        for directory in (ROOT / "web", ROOT / "web/mission-preview"):
            run(npm, "ci", cwd=directory)
    with TemporaryDirectory(prefix=".return-window-", dir=out.parent) as scratch:
        work = Path(scratch)
        bundle = work / "bundle"
        bundle.mkdir()
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

        # Bake the fallback from the same model and router that the release serves.
        # A replay checked in from another machine may have a different trained model ID.
        replay = work / "replay.json"
        run(sys.executable, "-m", "runtime.hazards.replay",
            "--model", str(bundle / "forecast.json"), "--out", str(replay))

        run(npm, "run", "build", cwd=ROOT / "web", env={
            **os.environ, "VITE_PACKAGED_RELEASE": "1", "VITE_RELEASE_BASE": "/legacy/",
        })
        run(npm, "run", "build", cwd=ROOT / "web/mission-preview", env={
            **os.environ, "VITE_RELEASE_BASE": "/", "VITE_PACKAGED_RELEASE": "1", "VITE_HAZARD_RUNTIME": "1",
            "RW_HAZARD_REPLAY_FILE": str(replay),
        })
        shutil.copytree(ROOT / "web/dist", bundle / "legacy")
        shutil.copytree(ROOT / "web/mission-preview/dist/client", bundle / "app")

        sources = source_hashes()

        manifest = {
            "schema_version": 2,
            "revision": revision(sources),
            "ranking_pack_sha256": pack.sha256,
            "forecast_model_id": json.loads((bundle / "forecast.json").read_bytes())["model_id"],
            "source_files": sources,
            "files": index(bundle),
        }
        (bundle / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        bundle.rename(out)
    print(f"Built Return Window release at {out}")


def verify(bundle: Path):
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 2:
        raise ValueError("Unknown release manifest schema")
    packaged = index(bundle)
    del packaged["manifest.json"]
    if packaged != manifest["files"]:
        raise ValueError("Packaged files differ from the release manifest")
    for name, expected in manifest["source_files"].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or digest(source) != expected:
            raise ValueError(f"Release source mismatch: {name}")
    if (not (bundle / "app/index.html").is_file() or not (bundle / "legacy/index.html").is_file()
            or digest(bundle / "ranking/manifest.json") != manifest["ranking_pack_sha256"]
            or json.loads((bundle / "forecast.json").read_bytes())["model_id"] != manifest["forecast_model_id"]):
        raise ValueError("Release component identity mismatch")
    return manifest


def serve(bundle: Path, port: int):
    manifest = verify(bundle)
    with create_server(port, ranking_pack=bundle / "ranking", engine="marswalk",
                       hazard_model=bundle / "forecast.json", static_root=bundle) as server:
        origin = f"http://127.0.0.1:{server.server_port}/"
        print(f"Return Window ready at {origin} ({manifest['revision']})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


def launch(port: int):
    data = ROOT / "data"
    bundle = data / "launch" / source_identity(source_hashes())
    if not bundle.exists():
        inputs = data / "ranking-inputs"
        download_ranking_inputs(inputs)
        build(bundle, inputs, None, install=True)
    serve(bundle, port)


def main():
    parser = ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="command", required=True)
    prepare = modes.add_parser("build")
    prepare.add_argument("bundle", type=Path)
    prepare.add_argument("--ranking-inputs", type=Path, default=Path("data/ranking-inputs"))
    prepare.add_argument("--ranking-pack", type=Path)
    start = modes.add_parser("serve")
    start.add_argument("bundle", type=Path)
    start.add_argument("--port", type=int, default=8000)
    boot = modes.add_parser("launch")
    boot.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        if args.command == "build":
            build(args.bundle, args.ranking_inputs, args.ranking_pack)
            return
        if args.command == "launch":
            launch(args.port)
        else:
            serve(args.bundle.resolve(), args.port)
    except (OSError, ValueError, KeyError, PackError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Release {args.command} failed: {error}\n")


if __name__ == "__main__":
    main()
