"""Deterministic leftmost-longest parser for the cell concept vocabulary."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from .ledger import load


TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(value: str):
    folded = []
    for char in value:
        base = unicodedata.normalize("NFKD", char)[:1].lower()
        folded.append(base if ("a" <= base <= "z" or "0" <= base <= "9") else " ")
    return list(TOKEN.finditer("".join(folded)))


def stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es") and token[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


class Parser:
    def __init__(self, lexicon: Path | None = None, *, concepts: list[dict] | None = None):
        source = lexicon or Path(__file__).with_name("lexicon.json")
        raw = json.loads(source.read_text(encoding="utf-8"))
        if raw["version"] != "cell-lexicon-v1":
            raise ValueError("unknown lexicon version")
        self.concepts = {item["id"]: item for item in (load() if concepts is None else concepts)}
        if set(raw["forms"]) != set(self.concepts):
            raise ValueError("lexicon and concept ledger differ")
        self.stop = {stem(token) for token in raw["stopwords"]}
        self.generic = {stem(token) for token in raw["generic"]}
        self.negation = set(raw["negation"])
        self.trie = {}
        for cid, forms in raw["forms"].items():
            for form in forms:
                node = self.trie
                for token in tokenize(form):
                    node = node.setdefault(stem(token.group()), {})
                existing = node.get("")
                if existing is not None and existing != cid:
                    raise ValueError(f"ambiguous form {form}: {existing} / {cid}")
                node[""] = cid

    def parse(self, objective: str, include_demo: bool = False, idf: dict | None = None) -> dict:
        tokens = tokenize(objective)
        found, negated, demo, unsupported, unknown = [], [], [], [], []
        content = recognized = 0
        negate_next = False
        i = 0
        while i < len(tokens):
            token = tokens[i].group()
            if token in self.negation:
                negate_next = True
                i += 1
                continue
            node = self.trie
            hit = None
            for end in range(i, len(tokens)):
                node = node.get(stem(tokens[end].group()))
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
                         "idf": None if status == "unsupported" or (status == "demo" and not include_demo) else (idf or {}).get(cid),
                         "span": [tokens[i].start(), tokens[end - 1].end()]}
                if "flag" in concept:
                    entry["flag"] = concept["flag"]
                if status == "demo":
                    entry["status"] = "DEMO"
                    demo.append({**entry, "included": include_demo, "negated": negate_next})
                if negate_next:
                    negated.append(entry)
                elif status == "unsupported":
                    unsupported.append(entry)
                elif status != "demo" or include_demo:
                    found.append(entry)
                negate_next = False
                i = end
            elif stem(token) in self.stop or stem(token) in self.generic:
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



def effective_negations(parsed, demo):
    return tuple(sorted(item["id"] for item in parsed["negated"]
                        if item["status"] != "unsupported" and (demo or item["status"] != "DEMO")))
