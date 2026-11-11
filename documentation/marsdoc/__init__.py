"""Return Window's deterministic documentation engine."""
from .contracts import CapabilityQuery, Package, ScoringPolicy
from .engine import DocumentationEngine
from .grid import Grid, normalize

__all__ = ["CapabilityQuery", "DocumentationEngine", "Grid", "Package", "ScoringPolicy", "normalize"]
