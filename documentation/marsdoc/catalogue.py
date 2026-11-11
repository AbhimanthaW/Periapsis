"""Index prepared evidence without acquiring source assets."""
from collections import defaultdict
from dataclasses import dataclass

from shapely import Geometry, STRtree, union_all

from .contracts import Dataset, Footprint, Inventory, Issue, Package, Product, Provenance
from .grid import CANONICAL
from .spatial import EMPTY, Part, Window, surface_parts


def _unique(records):
    result = {}
    for record in records:
        previous = result.setdefault(record.id, record)
        if previous != record:
            raise ValueError(f"conflicting duplicate record: {record.id}")
    return dict(sorted(result.items()))


@dataclass(frozen=True)
class Entry:
    dataset: Dataset
    product: Product
    footprints: tuple[Footprint, ...]
    issues: tuple[Issue, ...]
    observation_closed: bool
    support_closed: bool


@dataclass(frozen=True)
class Match:
    entry: Entry
    observed: Geometry
    support: Geometry


class Catalogue:
    def __init__(self, package: Package):
        self.package = package
        datasets = _unique(package.datasets)
        products = _unique(package.products)
        footprints = _unique(package.footprints)
        self.inventories = tuple(_unique(package.inventories).values())
        self.entries: dict[str, Entry] = {}
        self._dataset_ids: dict[str, set[str]] = defaultdict(set)
        for dataset in datasets.values():
            self._dataset_ids[dataset.modality].add(dataset.id)
        for product in products.values():
            if product.dataset_id not in datasets:
                raise ValueError(f"{product.id} references an unknown dataset")
        by_product = defaultdict(list)
        for footprint in footprints.values():
            if footprint.product_id not in products:
                raise ValueError(f"{footprint.id} references an unknown product")
            by_product[footprint.product_id].append(footprint)

        self._indexed: list[tuple[str, str, Part]] = []
        self._global: list[tuple[str, str]] = []
        self._unlocated: set[str] = set()
        for product in products.values():
            records = by_product[product.id]
            issues = []
            valid = 0
            valid_support = 0
            bad_support = False
            for footprint in records:
                try:
                    parts = self._prepare(product, footprint)
                except ValueError as exc:
                    bad_support |= footprint.coverage_kind == "usable_support"
                    code = (f"footprint_{footprint.status}"
                            if footprint.status in {"unavailable", "invalid", "untransformable"}
                            else ("missing_source_crs" if product.source_crs is None else "footprint_rejected"))
                    issues.append(Issue(code=code, record_id=footprint.id, detail=str(exc),
                                        source_url=footprint.source_url))
                    continue
                valid += 1
                valid_support += footprint.coverage_kind == "usable_support"
                if parts:
                    self._indexed.extend((product.id, footprint.coverage_kind, part) for part in parts)
                else:
                    self._global.append((product.id, footprint.coverage_kind))
            if not records:
                issues.append(Issue(code="footprint_missing", record_id=product.id,
                                    detail="No footprint record supplied.", source_url=product.source_url))
            observation_closed = product.observation_extent_complete and valid > 0 and not issues
            support_closed = product.support_extent_complete and valid_support > 0 and not bad_support
            if not observation_closed:
                self._unlocated.add(product.id)
            self.entries[product.id] = Entry(datasets[product.dataset_id], product, tuple(records),
                                             tuple(issues), observation_closed, support_closed)
        self._tree = STRtree([part.cap.index_box() for _, _, part in self._indexed])

        self._complete_scopes: list[tuple[Inventory, tuple[Part, ...]]] = []
        self.inventory_issues: dict[str, list[Issue]] = defaultdict(list)
        for inventory in self.inventories:
            if inventory.status != "complete":
                continue
            try:
                if inventory.scope is None or set(inventory.dataset_ids) != self._dataset_ids[inventory.modality]:
                    raise ValueError("inventory needs a scope and the full declared modality dataset set")
                if any(datasets[item].catalogue_status != "complete" for item in inventory.dataset_ids):
                    raise ValueError("one or more declared datasets have incomplete catalogue metadata")
                self._complete_scopes.append((inventory, surface_parts(inventory.scope)))
            except ValueError as exc:
                self.inventory_issues[inventory.modality].append(Issue(
                    code="inventory_not_closed", record_id=inventory.id, detail=str(exc),
                    source_url=inventory.source_url,
                ))

    @staticmethod
    def _prepare(product: Product, footprint: Footprint) -> tuple[Part, ...]:
        if footprint.status in {"unavailable", "invalid", "untransformable"}:
            raise ValueError(footprint.note or footprint.status)
        if product.source_crs is None:
            raise ValueError("missing source Mars CRS")
        if footprint.geometry is None:
            raise ValueError("missing footprint geometry")
        if footprint.status == "canonical_verified":
            if not footprint.transform:
                raise ValueError("canonical footprint requires a verified transform record")
            crs = CANONICAL
        else:
            crs = product.source_crs
            if crs.longitude_domain is None:
                raise ValueError("native geometry requires a declared longitude domain")
            if footprint.geometry.type == "Global":
                raise ValueError("whole-sphere coverage requires an explicit canonical verification record")
        return surface_parts(footprint.geometry, crs)

    def match(self, window: Window) -> list[Match]:
        observed = defaultdict(list)
        support = defaultdict(list)
        pieces = [(product_id, kind, window.shape) for product_id, kind in self._global]
        for index in sorted(self._tree.query(window.cap.index_box())):
            product_id, kind, part = self._indexed[index]
            clipped = window.clip_part(part)
            if not clipped.is_empty:
                pieces.append((product_id, kind, clipped))
        for product_id, kind, shape in pieces:
            observed[product_id].append(shape)
            if kind == "usable_support":
                support[product_id].append(shape)
        return [
            Match(self.entries[key], union_all(observed[key]), union_all(support[key]))
            for key in sorted(observed.keys() | self._unlocated)
        ]

    def closed_scope(self, modality: str, window: Window) -> Geometry:
        areas = []
        for inventory, parts in self._complete_scopes:
            if inventory.modality == modality:
                if not parts:
                    return window.shape
                areas.extend(window.clip_part(part) for part in parts)
        return union_all(areas) if areas else EMPTY

    def provenance(self, product_ids) -> tuple[Provenance, ...]:
        return tuple(
            Provenance(dataset=self.entries[key].dataset, product=self.entries[key].product,
                       footprints=self.entries[key].footprints)
            for key in sorted(set(product_ids))
        )
