"""Bind a named Atlas anchor to regional context and any reviewed local evidence."""
from hashlib import sha256
from pathlib import Path

from contracts.pack import decode
from marsdoc import CapabilityQuery, DocumentationEngine, Package
from marsdoc.grid import Grid


def read_pinned(root: Path, path: str, digest: str) -> bytes:
    raw = (root / path).read_bytes()
    if sha256(raw).hexdigest() != digest:
        raise ValueError(f"Pinned regional evidence changed: {path}")
    return raw


class RegionEvidence:
    def __init__(self, root: Path):
        atlas = decode((root / "web/src/atlas/regions.json").read_bytes())
        grid = Grid()
        self.anchors = {
            region["id"]: grid.cell_at(region["geography"]["center"]).id
            for region in atlas["regions"]
        }
        if len(self.anchors) != len(atlas["regions"]):
            raise ValueError("Duplicate Atlas region ID")

        registry = decode((root / "evidence/sites.v1.json").read_bytes())
        if (registry["schema_version"] != 1 or registry["primary_region"] not in registry["sites"]
                or not registry["sites"].keys() <= self.anchors.keys()):
            raise ValueError("Regional evidence registry does not match Atlas")
        self.pinned = {}
        for region_id, site in registry["sites"].items():
            package = Package.model_validate_json(read_pinned(root, site["package"], site["package_sha256"]))
            query = CapabilityQuery.model_validate_json(read_pinned(root, site["query"], site["query_sha256"]))
            if (package.package_id, package.version) != (site["package_id"], site["package_version"]):
                raise ValueError(f"Evidence package identity mismatch for Atlas region {region_id}")
            self.pinned[region_id] = {
                "schema_version": 1,
                "classification": "pinned_evidence",
                "context": "reviewed_local_query",
                "query_sha256": site["query_sha256"],
                "package_sha256": site["package_sha256"],
                "result": DocumentationEngine(package).resolve(query).model_dump(mode="json"),
            }

    def get(self, region_id, ranking):
        cell_id = self.anchors.get(region_id)
        if cell_id is None:
            return None
        detail = ranking.detail(cell_id) if ranking is not None else None
        context = None
        if detail is not None:
            record = detail["record"]
            if record["cell_id"] != cell_id:
                raise ValueError("Ranking pack returned a different anchor cell")
            context = {
                "pack": detail["pack"],
                "terrain": record["terrain"],
                "science_environment": record["science_environment"],
                "mola_elevation_m": record["mola_elevation_m"],
                "mola_observation_count": record["mola_observation_count"],
                "stereo_topography": record["modalities"]["stereo_topography"],
            }
        return {
            "schema_version": 1,
            "region_id": region_id,
            "anchor_cell_id": cell_id,
            "cell_context": context,
            "local_evidence": self.pinned.get(region_id),
            "tactical_routing": "withheld_no_qualified_pack",
            "live_hazards": "unavailable_no_qualified_feed",
        }
