"""Strict request model and in-process ranking cache."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from runtime.reporting import stage

from .engine import Engine
from .lexicon import effective_negations
from .pack import Pack


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Annotated[int, Field(ge=1, le=1)]
    request_id: Annotated[str, Field(min_length=1, max_length=128)]
    objective: Annotated[str, Field(min_length=1, max_length=300)]
    method: Literal["sample-rock", "investigate-ice", "remote-survey"] | None = None
    exclude: list[Literal["polar", "volcanic"]] = Field(default_factory=list)
    limit: Annotated[int, Field(ge=1, le=500)] = 50
    include_demo: bool = False


class RankingService:
    def __init__(self, directory: Path):
        self.engine = Engine(Pack(directory))
        self.cache = OrderedDict()
        self.cache_lock = Lock()

    def rank(self, request: RankRequest, *, report=None):
        demo = request.include_demo and bool(self.engine.pack.manifest["synthetic_layers"])
        with stage(report, "rank.parse", "Lexicon, negation and concept support rules",
                   {"objective": request.objective, "demo_enabled": demo}) as record:
            parsed = self.engine.parser.parse(request.objective, include_demo=demo,
                                              idf=self.engine.demo_idf if demo else self.engine.idf)
            record.update(parsed)
        key = (tuple(sorted(item["id"] for item in parsed["concepts"])),
               effective_negations(parsed, demo), request.method, tuple(sorted(set(request.exclude))),
               demo, self.engine.pack.sha256)
        with stage(report, "rank.score", "Weighted cell support, tiering and grouping",
                   {"concept_ids": key[0], "negations": key[1], "method": request.method,
                    "exclude": key[3], "demo_enabled": demo, "pack_sha256": key[-1], "limit": request.limit}) as record:
            with self.cache_lock:
                result = self.cache.get(key)
                if result is not None:
                    self.cache.move_to_end(key)
            cache_hit = result is not None
            if result is None:
                result = self.engine.rank(request.model_copy(update={"limit": 500}), parsed=parsed)
                with self.cache_lock:
                    self.cache[key] = result
                    self.cache.move_to_end(key)
                    if len(self.cache) > 64:
                        self.cache.popitem(last=False)
            record.update(cache_hit=cache_hit, counts=result["counts"], abstain=result["abstain"],
                          returned_areas=len(result["areas"][:request.limit]))
        return {**result, "request_id": request.request_id, "parse": parsed,
                "areas": result["areas"][:request.limit]}

    def detail(self, cell_id: str):
        return self.engine.detail(cell_id)
