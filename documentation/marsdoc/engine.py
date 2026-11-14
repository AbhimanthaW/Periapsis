"""Documentation summaries and evidence-only model gating."""
from collections import defaultdict
from hashlib import sha256
from importlib.resources import files
import math

from shapely import union_all

from .catalogue import Catalogue, Match
from .contracts import (
    AxisSummary, Bounds, Calculation, CalculationResult, Candidate, CapabilityQuery, CapabilityResult,
    CellSummary, Issue, ModalityMetric, ModalityPolicy, Polygon, Requirement, ScoringPolicy, VariableResult,
)
from .grid import Grid
from .spatial import EMPTY, Window

METHOD_VERSION = "marsdoc-spherical-v1"


def default_policy() -> ScoringPolicy:
    return ScoringPolicy.model_validate_json(files("marsdoc").joinpath("scoring-v1.json").read_bytes())


def _tier(value: float, policy: ScoringPolicy) -> str:
    return next(item.label for item in reversed(policy.tiers)
                if value >= item.minimum - policy.tier_tolerance)


def _axis(metrics, axis: str, policy: ScoringPolicy) -> AxisSummary:
    weighted = [(policy_item.weight, metric.evidence_bounds)
                for policy_item, metric in zip(policy.modalities, metrics, strict=True)
                if policy_item.axis == axis]
    # Normalizing before summing also avoids overflow for custom positive finite weights.
    max_weight = max(weight for weight, _ in weighted)
    weighted = [(weight / max_weight, bounds) for weight, bounds in weighted]
    total = math.fsum(weight for weight, _ in weighted)
    lower = min(100.0, 100 * (math.fsum(weight * bounds.lower for weight, bounds in weighted) / total))
    upper = min(100.0, 100 * (math.fsum(weight * bounds.upper for weight, bounds in weighted) / total))
    tier = _tier(lower, policy)
    if tier != _tier(upper, policy):
        return AxisSummary(score=None, bounds=Bounds(lower=lower, upper=upper), tier="Unclassified",
                           classification_status="unclassified", reason="evidence_bounds_span_multiple_tiers")
    return AxisSummary(score=lower if lower == upper else None, bounds=Bounds(lower=lower, upper=upper),
                       tier=tier, classification_status="classified", reason=None)


def _utility(spacing: float | None, policy: ModalityPolicy) -> tuple[float, float]:
    good, poor = policy.good_spacing_m, policy.poor_spacing_m
    if good is None:
        return 1.0, 1.0
    if spacing is None:
        return 0.0, 1.0
    if spacing <= good:
        return 1.0, 1.0
    if spacing >= poor:
        return 0.0, 0.0
    def log_ratio(high, low):
        relative = (high - low) / low
        return math.log1p(relative) if math.isfinite(relative) else math.log(high) - math.log(low)

    value = log_ratio(poor, spacing) / log_ratio(poor, good)
    return value, value


def _spatial_max(pieces, window: Window) -> float:
    # Integrate the area at or above each utility level, from highest to lowest.
    by_level = defaultdict(list)
    for utility, shape in pieces:
        if utility > 0 and not shape.is_empty:
            by_level[utility].append(shape)
    covered = EMPTY
    last_fraction = 0.0
    contributions = []
    for utility in sorted(by_level, reverse=True):
        if any(shape is window.shape for shape in by_level[utility]):
            contributions.append(utility * (1 - last_fraction))
            break
        covered = union_all([covered, *by_level[utility]])
        fraction = max(last_fraction, window.fraction(covered))
        contributions.append(utility * (fraction - last_fraction))
        if fraction == 1.0:
            break
        last_fraction = fraction
    return min(1.0, math.fsum(contributions))


def _modality(catalogue: Catalogue, window: Window, matches, policy: ModalityPolicy) -> ModalityMetric:
    modality = policy.modality
    scope = catalogue.closed_scope(modality, window)
    closed = scope.covers(window.shape)
    if scope.is_empty:
        unsearched = window.shape
    else:
        unsearched = EMPTY if closed else window.shape.difference(scope)
    observed, potential_observed, usable = [], [unsearched], []
    lower, upper = [], [(1.0, unsearched)]
    issues = list(catalogue.inventory_issues.get(modality, ()))
    for match in matches:
        entry = match.entry
        product = entry.product
        issues.extend(entry.issues)
        observed.append(match.observed)
        possible_extent = match.observed if entry.observation_closed else window.shape
        potential_observed.append(possible_extent)
        low, high = _utility(product.native_spacing_m, policy)
        if product.readiness == "usable":
            usable.append(match.support)
            lower.append((low, match.support))
            possible_support = match.support if entry.support_closed else possible_extent
            upper.append((high, possible_support))
        elif product.readiness == "unknown":
            possible_support = match.support if entry.support_closed else possible_extent
            upper.append((high, possible_support))
        if product.readiness != "usable":
            issues.append(Issue(code=f"product_{product.readiness}", record_id=product.id,
                                detail="Product does not qualify as usable in this snapshot.",
                                source_url=product.source_url))
        elif not entry.support_closed:
            issues.append(Issue(code="support_extent_unverified", record_id=product.id,
                                detail="Usable support outside the supplied masks is unresolved.",
                                source_url=product.source_url))
        if low != high and product.readiness in {"usable", "unknown"}:
            issues.append(Issue(code="native_spacing_unknown", record_id=product.id,
                                detail="Scoring ramp needs native sampling.", source_url=product.source_url))

    observed_fraction = window.fraction(union_all(observed))
    observed_upper = 1.0 if any(shape is window.shape for shape in potential_observed) else max(
        observed_fraction, window.fraction(union_all(potential_observed)))
    evidence_lower = _spatial_max(lower, window)
    evidence_upper = max(evidence_lower, _spatial_max(upper, window))
    state = "verified_coverage" if observed_fraction > 0 else (
        "verified_absence" if observed_upper == 0 and closed else "unknown")
    return ModalityMetric(
        modality=modality, coverage_state=state, observed_fraction=observed_fraction,
        observed_bounds=Bounds(lower=observed_fraction, upper=observed_upper),
        usable_fraction=window.fraction(union_all(usable)),
        evidence_score=evidence_lower if evidence_lower == evidence_upper else None,
        evidence_bounds=Bounds(lower=evidence_lower, upper=evidence_upper), catalogue_closed=closed,
        inventories=tuple(item for item in catalogue.inventories if item.modality == modality),
        product_ids=tuple(match.entry.product.id for match in matches), issues=tuple(issues),
    )


def _candidate(match: Match, requirement: Requirement, window: Window) -> Candidate:
    product = match.entry.product
    reasons = []
    if product.readiness != "usable":
        reasons.append(f"product_{product.readiness}")
    if requirement.processing_levels and product.processing_level not in requirement.processing_levels:
        reasons.append("processing_level_mismatch")
    for value, maximum, name in (
        (product.native_spacing_m, requirement.max_native_spacing_m, "native_spacing"),
        (product.effective_scale_m, requirement.max_effective_scale_m, "effective_scale"),
    ):
        if maximum is not None and (value is None or value > maximum):
            reasons.append(f"{name}_unknown" if value is None else f"{name}_too_coarse")
    if requirement.acquisition_window is not None:
        if product.acquisition is None:
            reasons.append("acquisition_time_unknown")
        elif not requirement.acquisition_window.contains(product.acquisition):
            reasons.append("outside_acquisition_window")
    supported = product.readiness == "usable"
    if match.support.is_empty:
        reasons.append("usable_support_unverified" if not match.entry.support_closed else "outside_usable_support")
    return Candidate(product_id=product.id, observed_fraction=window.fraction(match.observed),
                     support_fraction=window.fraction(match.support) if supported else 0,
                     native_spacing_m=product.native_spacing_m, effective_scale_m=product.effective_scale_m,
                     readiness=product.readiness, reasons=tuple(reasons))


def _resolve_variable(matches: list[Match], requirement: Requirement, window: Window):
    candidates = []
    issues = []
    qualified = []
    full_products = defaultdict(list)
    for match in matches:
        entry = match.entry
        product = entry.product
        if entry.dataset.product_class not in requirement.product_classes:
            continue
        if requirement.modalities and entry.dataset.modality not in requirement.modalities:
            continue
        if requirement.variable not in product.variables:
            continue
        candidate = _candidate(match, requirement, window)
        candidates.append(candidate)
        issues.extend(entry.issues)
        if not candidate.reasons:
            qualified.append(match.support)
            if match.support.covers(window.shape):
                key = ("compatibility", product.compatibility_key) if product.compatibility_key else ("product", product.id)
                full_products[key].append(product.id)

    reason = None
    if not candidates:
        reason = "no_relevant_product_supplied"
    elif not qualified:
        reason = "no_usable_product_meets_requirements"
    elif not full_products:
        reason = "no_single_product_covers_full_query"
    return VariableResult(variable=requirement.variable, qualified_fraction=window.fraction(union_all(qualified)),
                          covered_by_single_product=bool(full_products), candidates=tuple(candidates),
                          issues=tuple(issues), reason=reason), full_products


def _calculation(matches, calculation: Calculation, window: Window) -> CalculationResult:
    variables, keys = zip(*[_resolve_variable(matches, requirement, window)
                            for requirement in calculation.requirements])
    common = set.intersection(*(set(group) for group in keys))
    selected = ()
    if common:
        # Deterministic evidence selection. Candidates retain alternative sources.
        key = min(common)
        selected = tuple(sorted({min(group[key]) for group in keys}))
    reason = None if selected else (
        "requirements_unsatisfied" if any(not item.covered_by_single_product for item in variables)
        else "no_common_verified_compatibility_group"
    )
    return CalculationResult(id=calculation.id, eligible=bool(selected), variables=variables,
                             supporting_product_ids=selected, reason=reason)


class DocumentationEngine:
    def __init__(self, package, *, nside: int = 128, policy: ScoringPolicy | None = None):
        self.catalogue = Catalogue(package)
        self.grid = Grid(nside)
        self.policy = policy or default_policy()
        self.policy_sha256 = sha256(self.policy.model_dump_json().encode()).hexdigest()

    def _metadata(self, products) -> dict:
        package = self.catalogue.package
        return dict(package_id=package.package_id, package_version=package.version,
                    method_version=METHOD_VERSION, provenance=self.catalogue.provenance(products))

    def _cell_window(self, index: int) -> Window:
        if self.grid.nside == 1:
            raise ValueError("cell summaries require Nside >= 2 for bounded spherical overlays")
        edge = self.grid.boundaries(index, self.policy.boundary_step).reshape(-1, 2)
        ring = tuple(map(tuple, edge)) + (tuple(edge[0]),)
        return Window.from_geometry(Polygon(type="Polygon", coordinates=(ring,)))

    def summarize(self, cell_id: str) -> CellSummary:
        index = self.grid.parse_id(cell_id)
        cell = self.grid.cell(index)
        window = self._cell_window(index)
        by_modality = defaultdict(list)
        for match in self.catalogue.match(window):
            by_modality[match.entry.dataset.modality].append(match)
        metrics = tuple(_modality(self.catalogue, window, by_modality[item.modality], item)
                        for item in self.policy.modalities)
        return CellSummary(
            **self._metadata(key for metric in metrics for key in metric.product_ids),
            policy_version=self.policy.version, policy_sha256=self.policy_sha256, cell=cell,
            boundary_step=self.policy.boundary_step,
            boundary_area_relative_error=window.size / (cell.area_km2 * 1e6) - 1,
            terrain=_axis(metrics, "terrain", self.policy),
            science_environment=_axis(metrics, "science_environment", self.policy),
            modalities=metrics,
            limitations=("HEALPix edges are sampled; bounds express metadata uncertainty for that approximation.",
                         "Scores and tiers are provisional conventions for the declared source universe."),
        )

    def synthetic_context(self, cell_id: str) -> dict:
        """Evaluate the opt-in science fixture for this cell without affecting evidence."""
        from .synthetic_science import evaluate_synthetic_science

        index = self.grid.parse_id(cell_id)
        return evaluate_synthetic_science(cell_id, self.grid.cell(index).centroid, self._cell_window(index))

    def resolve(self, request: CapabilityQuery) -> CapabilityResult:
        window = Window.from_geometry(request.geometry, request.corridor_width_m)
        matches = self.catalogue.match(window)
        requested = _calculation(matches, request.requested, window)
        fallbacks = tuple(_calculation(matches, item, window) for item in request.fallbacks)
        products = (candidate.product_id for item in (requested, *fallbacks)
                    for variable in item.variables for candidate in variable.candidates)
        return CapabilityResult(
            **self._metadata(products),
            query=request, requested=requested, fallbacks=fallbacks,
            supported_fallback_ids=tuple(item.id for item in fallbacks if item.eligible),
            measure=window.measure, query_size=window.size,
            limitations=("Eligibility covers declared evidence only. Apply site-pack quality and numerical model gates.",
                         "Routes use shorter great-circle arcs and a conservatively buffered local corridor."),
        )
