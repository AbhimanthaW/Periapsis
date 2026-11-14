"""Deterministic leftmost-longest parser for the cell concept vocabulary."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .ledger import load


def normalize(value: str) -> list[str]:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", text)


def stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 4 and token[-3] in "sxz":
        return token[:-2]
    if token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
        return token[:-1]
    return token


class Parser:
    def __init__(self, lexicon: Path | None = None):
        source = lexicon or Path(__file__).with_name("lexicon.json")
        raw = json.loads(source.read_text(encoding="utf-8"))
        if raw["version"] != "cell-lexicon-v1":
            raise ValueError("unknown lexicon version")
        self.concepts = {item["id"]: item for item in load()}
        if set(raw["forms"]) != set(self.concepts):
            raise ValueError("lexicon and concept ledger differ")
        self.stop = set(raw["stopwords"])
        self.generic = set(raw["generic"])
        self.negation = set(raw["negation"])
        self.trie = {}
        for cid, forms in raw["forms"].items():
            for form in forms:
                node = self.trie
                for token in map(stem, normalize(form)):
                    node = node.setdefault(token, {})
                existing = node.get("")
                if existing is not None and existing != cid:
                    raise ValueError(f"ambiguous form {form}: {existing} / {cid}")
                node[""] = cid

    def parse(self, objective: str, include_demo: bool = False, idf: dict | None = None) -> dict:
        tokens = normalize(objective)
        found, negated, demo, unsupported, unknown = [], [], [], [], []
        content = recognized = 0
        negate_next = False
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token in self.negation:
                negate_next = True
                i += 1
                continue
            node = self.trie
            hit = None
            for end in range(i, len(tokens)):
                node = node.get(stem(tokens[end]))
                if node is None:
                    break
                if "" in node:
                    hit = (end + 1, node[""])
            if hit:
                end, cid = hit
                concept = self.concepts[cid]
                status = concept["status"]
                recognized += end - i
                content += end - i
                entry = {"id": cid, "status": status,
                         "weight": 0.35 if concept["facet"] == "age" else 1.0,
                         "idf": None if status in {"unsupported", "demo"} and not include_demo else (idf or {}).get(cid)}
                if negate_next:
                    negated.append(entry)
                elif status == "unsupported":
                    unsupported.append(entry)
                elif status == "demo":
                    demo.append({**entry, "included": include_demo})
                    if include_demo:
                        found.append(entry)
                else:
                    found.append(entry)
                negate_next = False
                i = end
            elif token in self.stop or token in self.generic:
                i += 1
            else:
                unknown.append(token)
                content += 1
                i += 1
        return {"concepts": list({e["id"]: e for e in found}.values()),
                "negated": list({e["id"]: e for e in negated}.values()),
                "demo": list({e["id"]: e for e in demo}.values()),
                "unsupported": list({e["id"]: e for e in unsupported}.values()),
                "unknown": unknown, "confidence": round(recognized / content, 4) if content else 1.0}
