"""Strict request model and in-process ranking cache."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from .engine import Engine
from .pack import Pack


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
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

    def rank(self, request: RankRequest):
        # Cache the expensive result independent of the caller's request ID.
        enabled_demo = request.include_demo and bool(self.engine.pack.manifest["synthetic_layers"])
        parsed = self.engine.parser.parse(request.objective, include_demo=enabled_demo)
        key = (tuple(sorted(item["id"] for item in parsed["concepts"])),
               tuple(sorted(item["id"] for item in parsed["negated"])),
               request.method, tuple(sorted(set(request.exclude))), request.limit,
               enabled_demo, self.engine.pack.sha256)
        if key in self.cache:
            result = self.cache[key]
            self.cache.move_to_end(key)
        else:
            result = self.engine.rank(request)
            self.cache[key] = result
            if len(self.cache) > 64:
                self.cache.popitem(last=False)
        demo = request.include_demo and bool(self.engine.pack.manifest["synthetic_layers"])
        return {**result, "request_id": request.request_id, "parse": self.engine.parser.parse(
            request.objective, include_demo=demo,
            idf=self.engine.demo_idf if demo else self.engine.idf)}

    def detail(self, cell_id: str):
        return self.engine.detail(cell_id)
