#!/usr/bin/env python3
"""Reference prototype for deterministic objective-to-region ranking.

No machine learning and no network. The same registry, lexicon and query
always produce the same ranking. Standard library only.

    python3 -I rank_regions.py REGIONS_JSON LEXICON_JSON "ancient water and delta deposits" \
        [--exclude polar] [--method sample-rock] [--json]

This is a design prototype. Lexicon weights and forms are unreviewed drafts.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- text normalisation


def fold(text: str) -> str:
    """Lower-case ASCII fold that keeps one output character per input character.

    Offsets in the folded string therefore index the original string, which
    lets the ranker quote the exact source span it matched.
    """
    out = []
    for ch in text:
        base = unicodedata.normalize("NFKD", ch)[:1].lower()
        out.append(base if ("a" <= base <= "z" or "0" <= base <= "9") else " ")
    return "".join(out)


TOKEN = re.compile(r"[a-z0-9]+")


def stem(token: str) -> str:
    """Deterministic inflection stripping. Derivational forms live in the lexicon."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if len(token) > 4 and token.endswith("es") and token[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


@dataclass(frozen=True)
class Token:
    stem: str
    start: int
    end: int


def tokenize(text: str) -> list[Token]:
    folded = fold(text)
    return [Token(stem(m.group()), m.start(), m.end()) for m in TOKEN.finditer(folded)]


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# ---------------------------------------------------------------- lexicon


class Lexicon:
    def __init__(self, raw: dict):
        self.raw = raw
        self.version = raw["version"]
        self.concepts = {c["id"]: c for c in raw["concepts"]}
        self.phrases: dict[tuple[str, ...], str] = {}
        for c in raw["concepts"]:
            for form in c["forms"]:
                key = tuple(t.stem for t in tokenize(form))
                if key in self.phrases and self.phrases[key] != c["id"]:
                    raise ValueError(f"form {form!r} maps to {self.phrases[key]} and {c['id']}")
                self.phrases[key] = c["id"]
        for phrase in raw.get("stop_phrases", []):
            # Citation venues and titles are consumed without producing a concept.
            self.phrases[tuple(t.stem for t in tokenize(phrase))] = ""
        self.max_len = max(len(k) for k in self.phrases)
        self.stop = {stem(w) for w in raw["stopwords"]}
        self.generic = {stem(w) for w in raw["generic_terms"]}
        self.neg = {stem(w) for w in raw["negation_cues"]}
        self.hedge = {stem(w) for w in raw["hedge_cues"]}
        self.ops_cues = [tuple(t.stem for t in tokenize(c)) for c in raw["operations_sentence_cues"]]
        self.poi_cues = {stem(w) for w in raw["poi_science_cues"]}
        self.roles = raw["field_roles"]
        self.alias = {a: role for role, names in raw["field_aliases"].items() for a in names}
        self.rel = raw["relation_weights"]
        self.k1 = raw["bm25"]["k1"]
        self._anc = {cid: self._ancestors(cid) for cid in self.concepts}

    def _ancestors(self, cid: str) -> dict[str, int]:
        """Every broader concept with its shortest distance."""
        depth: dict[str, int] = {}
        frontier, d = [cid], 0
        while frontier:
            d += 1
            nxt = []
            for c in frontier:
                for b in self.concepts[c]["broader"]:
                    if b not in depth:
                        depth[b] = d
                        nxt.append(b)
            frontier = nxt
        return depth

    def relation(self, query: str, found: str) -> tuple[float, str]:
        """How strongly a mention of `found` supports query concept `query`."""
        if query == found:
            return self.rel["exact"], "exact"
        if query in self._anc[found]:  # found is narrower, e.g. query water, found delta
            return self.rel["narrower_per_level"] ** self._anc[found][query], "narrower"
        if found in self._anc[query]:  # found is broader, e.g. query delta, found hydrology
            return self.rel["broader"] ** self._anc[query][found], "broader"
        if found in self.concepts[query].get("related", []):  # sibling landform, e.g. delta and fan
            return self.rel["related"], "related"
        return 0.0, "none"

    def query_weight(self, cid: str) -> float:
        return self.raw["query_weights"][self.concepts[cid]["facet"]]


@dataclass
class Mention:
    concept: str
    start: int
    end: int
    negated: bool
    hedged: bool
    via: str | None = None  # another registry region named in the same clause


def annotate(text: str, lex: Lexicon) -> tuple[list[Mention], list[str]]:
    """Leftmost-longest phrase matching. Returns mentions and unrecognised content words."""
    toks = tokenize(text)
    stems = [t.stem for t in toks]
    mentions, unknown = [], []
    negate_next = 0  # tokens left in which a negation cue can still bind
    i = 0
    while i < len(toks):
        for n in range(min(lex.max_len, len(toks) - i), 0, -1):
            cid = lex.phrases.get(tuple(stems[i:i + n]))
            if cid is None:
                continue
            if cid:
                near = stems[max(0, i - lex.raw["hedge_window"]):i]
                # A negation cue binds to the first concept that follows it, nothing further.
                mentions.append(Mention(cid, toks[i].start, toks[i + n - 1].end, negate_next > 0,
                                        any(s in lex.hedge for s in near)))
                negate_next = 0
            i += n
            break
        else:
            s = stems[i]
            if s in lex.neg:
                negate_next = lex.raw["negation_window"] + 1
            elif s not in lex.stop and s not in lex.generic and not s.isdigit():
                unknown.append(text[toks[i].start:toks[i].end])
            i += 1
        negate_next = max(0, negate_next - 1)
    return mentions, unknown

# ---------------------------------------------------------------- region evidence


@dataclass
class Piece:
    role: str
    source: str
    text: str
    mentions: list[Mention] = field(default_factory=list)


def has_cue(stems: list[str], cues: list[tuple[str, ...]]) -> bool:
    joined = " " + " ".join(stems) + " "
    return any(" " + " ".join(c) + " " in joined for c in cues)


def prose_role(sentence: str, lex: Lexicon, default: str) -> str:
    stems = [t.stem for t in tokenize(sentence)]
    if sentence.lower().startswith("routing implication"):
        return "operations"
    if has_cue(stems, lex.ops_cues) and not (set(stems) & lex.poi_cues):
        return "operations"
    return default


def region_pieces(region: dict, lex: Lexicon) -> list[Piece]:
    pieces: list[Piece] = []
    sci = region["assessments"]["science"]["original"]
    if sci:
        pieces.append(Piece("science_assessment", "Science assessment", sci))
    for key, value in region["fields"].items():
        role = lex.alias.get(key)
        if role and value:
            pieces.append(Piece(role, key.capitalize(), str(value)))
    overview = region["overview"]
    if overview:
        m = re.search(r"Terrain:\s*(.+)$", overview[0])
        if m:
            pieces.append(Piece("terrain_summary", "Location summary", m.group(1)))
        for para in overview[1:]:
            for s in SENTENCE.split(para):
                pieces.append(Piece(prose_role(s, lex, "context_prose"), "Overview", s))
    for name, default in (("science", "science_prose"), ("terrain", "context_prose"),
                          ("operations", "context_prose"), ("data", "documentation")):
        for para in region["sections"].get(name, []):
            for s in SENTENCE.split(para):
                role = default if default == "documentation" else prose_role(s, lex, default)
                pieces.append(Piece(role, f"Survey {name}", s))
    for tables in region["tables"].values():
        for t in tables:
            head = " ".join(t["head"]).lower()
            for row in t["rows"]:
                if "interpretation" in head and len(row) > 1:
                    cue = {tk.stem for tk in tokenize(row[1])} & lex.poi_cues
                    pieces.append(Piece("science_poi" if cue else "operations", "Points of interest", row[0]))
                elif "availability" in head:
                    pieces.append(Piece("documentation", "Documentation table", row[0]))
                else:
                    pieces.append(Piece("operations", t["title"], " | ".join(row)))
    for p in pieces:
        p.mentions, _ = annotate(p.text, lex)
        for m in p.mentions:
            lo, hi = clause_bounds(p.text, m.start, m.end)
            clause = " " + " ".join(t.stem for t in tokenize(p.text[lo:hi])) + " "
            for other_id, names in NAMES.items():
                if other_id != region["id"] and any(" " + n + " " in clause for n in names):
                    m.via = REGION_NAME[other_id]
                    break
    return pieces


NAMES: dict[str, list[str]] = {}
REGION_NAME: dict[str, str] = {}


def load_names(regions: list[dict]) -> None:
    """Registry and gazetteer names, used to attribute nested or neighbouring evidence."""
    for r in regions:
        forms = {r["name"], r["geography"].get("gazetteerName") or r["name"]}
        NAMES[r["id"]] = sorted({" ".join(t.stem for t in tokenize(f)) for f in forms if f}, key=len, reverse=True)
        REGION_NAME[r["id"]] = r["name"]


def primary_concepts(region: dict, lex: Lexicon) -> set[str]:
    out: set[str] = set()
    sci = region["assessments"]["science"]["original"] or ""
    first = re.split(r"[;,]| and ", re.sub(r"^.*?\bfor\b", "", sci, count=1))[0]
    out |= {m.concept for m in annotate(first, lex)[0]}
    for key, value in region["fields"].items():
        if lex.alias.get(key) == "terrain_summary":
            out |= {m.concept for m in annotate(str(value), lex)[0]}
    return out


LEVELS = [("very high", "Very high"), ("high", "High"), ("moderate", "Moderate"), ("low", "Low")]


def conditional_science(region: dict, query: list[str], lex: Lexicon) -> str:
    """The survey rates interest *for* named themes. Only report the level when a theme fits."""
    text = region["assessments"]["science"]["original"]
    if not text:
        return "Not assessed"
    overall, fallback = None, None
    for seg in re.split(r";", text):
        m = re.match(r"\s*(very high|high|moderate|low)\b(.*)", seg, re.I)
        if not m:
            continue
        level = dict(LEVELS)[m.group(1).lower()]
        prep = re.match(r"\s*(for|at)\b", m.group(2), re.I)
        prep = prep.group(1).lower() if prep else "for"
        domain = re.sub(r"^\s*(overall|for|at)\s*", "", m.group(2).strip(), flags=re.I)
        if re.match(r"\s*overall", m.group(2), re.I):
            overall = overall or f"{level} overall"
            continue
        found = {x.concept for x in annotate(domain, lex)[0]}
        hits = [q for q in query if lex.concepts[q]["facet"] != "age"
                and any(lex.relation(q, f)[0] > 0 for f in found)]
        if hits:
            return f"{level} · {prep} {domain}"
        fallback = fallback or f"{level} for {domain}"
    if overall:
        return overall
    return f"Not rated for this objective ({fallback})" if fallback else "Not assessed"


def documentation_label(region: dict) -> str:
    for para in region["sections"].get("data", []):
        m = re.search(r"Documentation classification:\s*(.+)", para)
        if m:
            return m.group(1).split(";")[0].rstrip(".")
    return region.get("documentationNote") or "Not assessed"

# ---------------------------------------------------------------- ranking


@dataclass
class Result:
    region: dict
    match: float
    coverage: float
    evidence: list[dict]
    excluded: str | None
    method_ok: bool | None
    headline: str | None


CLAUSE = re.compile(r"[,;|:()]|\s[-–—]\s")


def clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    lo = max([m.end() for m in CLAUSE.finditer(text, 0, start)], default=0)
    nxt = CLAUSE.search(text, end)
    hi = nxt.start() if nxt else len(text)
    return lo, hi


def snippet(piece: Piece, best: Mention, max_words: int = 8) -> str:
    """Quote the delimited clause that holds the mention, e.g. 'ancient river delta'."""
    lo, hi = clause_bounds(piece.text, best.start, best.end)
    words = re.sub(r"^(very high|high|moderate|low)\s+(for|at)\s+", "", piece.text[lo:hi].strip(),
                   flags=re.I).rstrip(".").split()
    if len(words) <= max_words:
        return " ".join(words)
    # Long prose clause: keep the matched run of adjacent mentions instead.
    ms = sorted(piece.mentions, key=lambda m: m.start)
    i = next(k for k, m in enumerate(ms) if m is best)
    lo, hi = ms[i].start, ms[i].end
    for m in reversed(ms[:i]):
        if piece.text[m.end:lo].strip(" -–") != "":
            break
        lo = m.start
    for m in ms[i + 1:]:
        if piece.text[hi:m.start].strip(" -–") != "":
            break
        hi = m.end
    return piece.text[lo:hi]

def p_index(pieces: list[Piece], piece: Piece) -> int:
    return next(i for i, p in enumerate(pieces) if p is piece)


def best_quote(pieces: list[Piece], query: list[str], idf: dict, lex: Lexicon) -> str | None:
    """Pick the single source span that covers the most query weight.

    A piece scores the sum over query concepts of its best mention. The quote is
    the run of adjacent mentions around that piece's strongest mention.
    """
    best = None
    for i, p in enumerate(pieces):
        rw = lex.roles[p.role]
        if rw == 0:
            continue
        total, top = 0.0, None
        for q in query:
            cand = [(rw * lex.relation(q, m.concept)[0] * (lex.raw["hedge_weight"] if m.hedged else 1.0)
                     * (lex.raw["cross_reference_weight"] if m.via else 1.0)
                     * idf[q] * lex.query_weight(q), m) for m in p.mentions if not m.negated]
            cand = [c for c in cand if c[0] > 0]
            if cand:
                c = max(cand, key=lambda c: (c[0], -c[1].start))
                total += c[0]
                if top is None or c[0] > top[0]:
                    top = c
        if top and (best is None or round(total, 9) > round(best[0], 9)):
            best = (total, p, top[1])
    if not best:
        return None
    quote = snippet(best[1], best[2])
    return f"{quote} (via {best[2].via})" if best[2].via else quote


def build_index(regions: list[dict], lex: Lexicon) -> dict[str, list[Piece]]:
    """Offline step: annotate every region once. Query time only reads this."""
    load_names(regions)
    return {r["id"]: region_pieces(r, lex) for r in regions}


def rank(regions: list[dict], lex: Lexicon, objective: str, exclude: list[str], method: str | None,
         index: dict[str, list[Piece]] | None = None) -> dict:
    q_mentions, unknown = annotate(objective, lex)
    content = len(q_mentions) + len(unknown)
    parse_confidence = round(len(q_mentions) / content, 3) if content else 0.0
    query = sorted({m.concept for m in q_mentions if not m.negated and lex.query_weight(m.concept) > 0})
    negated = sorted({m.concept for m in q_mentions if m.negated})
    setting = sorted({m.concept for m in q_mentions if lex.concepts[m.concept]["facet"] == "setting"})
    index = index if index is not None else build_index(regions, lex)

    # Expanded document frequency: a region supports q if it has an exact or narrower mention.
    df = {}
    for q in query:
        df[q] = sum(
            any(lex.roles[p.role] > 0 and not m.negated and not m.via
                and lex.relation(q, m.concept)[1] in ("exact", "narrower")
                for p in pieces for m in p.mentions)
            for pieces in index.values())
    n = len(regions)
    idf = {q: math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5)) for q in query}
    denom = sum(lex.query_weight(q) * idf[q] for q in query) or 1.0

    results = []
    for region in regions:
        pieces = index[region["id"]]
        match, covered, evidence = 0.0, 0.0, []
        for q in query:
            # Accumulate per relation class, saturate, then apply the relation weight.
            # Many broad mentions (for example "lake" for a delta query) can never
            # outweigh one exact mention.
            classes: dict[float, float] = {}
            kinds: set[str] = set()
            best = None
            for p in pieces:
                rw = lex.roles[p.role]
                for m in p.mentions:
                    rel, kind = lex.relation(q, m.concept)
                    if rw == 0 or rel == 0 or m.negated:
                        continue
                    w = rw * (lex.raw["hedge_weight"] if m.hedged else 1.0)
                    w *= lex.raw["cross_reference_weight"] if m.via else 1.0
                    classes[rel] = classes.get(rel, 0.0) + w
                    if not m.via:  # evidence about a named neighbour never makes a match direct
                        kinds.add(kind)
                    if best is None or (w * rel, -p_index(pieces, p)) > (best[0], -p_index(pieces, best[1])):
                        best = (w * rel, p, m, kind)
            if classes:
                sat = max(rel * tf * (lex.k1 + 1) / (tf + lex.k1) for rel, tf in classes.items())
                part = lex.query_weight(q) * idf[q] * sat
                match += part
                if kinds & {"exact", "narrower"}:
                    covered += lex.query_weight(q) * idf[q]
                evidence.append({"concept": q, "contribution": round(part, 6), "relation": best[3],
                                 "quote": snippet(best[1], best[2]), "source": best[1].source,
                                 "role": best[1].role, "hedged": best[2].hedged, "via": best[2].via})
        headline = best_quote(pieces, query, idf, lex)
        evidence.sort(key=lambda e: (-e["contribution"], e["concept"]))

        excluded = None
        primary = primary_concepts(region, lex)
        lat = region["geography"]["center"][1]
        for key in exclude:
            rule = lex.raw["exclusions"][key]
            if abs(lat) >= rule.get("latitude_abs_min", 91) or primary & set(rule["or_primary_concepts"]):
                excluded = rule["label"]
                break
        if excluded is None and primary & set(negated):
            excluded = "Negated in objective: " + ", ".join(sorted(primary & set(negated)))

        method_ok = None
        if method:
            need = set(lex.raw["methods"][method]["requires_any"])
            have = {m.concept for p in pieces if lex.roles[p.role] > 0 for m in p.mentions if not m.negated}
            have |= {a for c in have for a in lex._anc[c]}
            method_ok = (not need) or bool(need & have)

        results.append(Result(region, match, covered / denom, evidence, excluded, method_ok, headline))

    def tier(r: Result) -> int:
        """Lexicographic evidence tier: 0 direct for every concept, 1 direct for some, 2 only thematic."""
        return 0 if r.coverage >= 1 - 1e-9 else (1 if r.coverage > 0 else 2)

    def key(r: Result):
        return (r.excluded is not None, r.match == 0, tier(r), -round(r.match, 9), r.region["id"])

    results.sort(key=key)
    rows, rank_no, seen, prev = [], 0, 0, None
    for r in results:
        listed = r.excluded is None and r.match > 0
        if listed:
            seen += 1
            # Competition ranking: equal tier and equal match share a rank; ID order is display only.
            cur = (tier(r), round(r.match, 6))
            rank_no = rank_no if cur == prev else seen
            prev = cur
        rows.append({
            "rank": rank_no if listed else None,
            "id": r.region["id"], "name": r.region["name"],
            "match": round(r.match, 4), "coverage": round(r.coverage, 3),
            "tier": ["Direct", "Partial", "Thematic"][tier(r)] if r.match > 0 else None,
            "matched_text": r.headline,
            "evidence": r.evidence,
            "science": conditional_science(r.region, query, lex),
            "documentation": documentation_label(r.region),
            "traversal": r.region["assessments"]["traversal"]["original"],
            "method_compatible": r.method_ok,
            "excluded": r.excluded,
        })
    return {
        "lexicon": lex.version, "objective": objective,
        "parsed": {"concepts": [{"id": q, "label": lex.concepts[q]["label"], "weight": lex.query_weight(q),
                                 "df": df[q], "idf": round(idf[q], 4)} for q in query],
                   "negated": negated, "setting": setting, "unrecognised": unknown,
                   "parse_confidence": parse_confidence},
        "abstain": not query, "rows": rows,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("regions")
    ap.add_argument("lexicon")
    ap.add_argument("objective")
    ap.add_argument("--exclude", action="append", default=[], choices=["polar", "volcanic"])
    ap.add_argument("--method", choices=["sample-rock", "investigate-ice", "remote-survey"])
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    regions = json.load(open(a.regions, encoding="utf-8"))["regions"]
    lex = Lexicon(json.load(open(a.lexicon, encoding="utf-8")))
    out = rank(regions, lex, a.objective, a.exclude, a.method)
    if a.json:
        json.dump(out, sys.stdout, indent=2, ensure_ascii=False)
        return
    p = out["parsed"]
    print(f"Objective: {a.objective}")
    print("Concepts:  " + ", ".join(f"{c['id']} (df {c['df']}, idf {c['idf']}, w {c['weight']})" for c in p["concepts"]))
    if p["unrecognised"]:
        print("Not understood: " + ", ".join(p["unrecognised"]) + f"  (parse confidence {p['parse_confidence']})")
    if p["negated"]:
        print("Negated: " + ", ".join(p["negated"]))
    if out["abstain"]:
        print("ABSTAIN: no recognised scientific concept. Nothing is ranked.")
        return
    shown = 0
    for r in out["rows"]:
        if r["rank"] is None and not r["excluded"]:
            continue
        if shown >= a.top and not r["excluded"]:
            continue
        shown += r["rank"] is not None
        tag = f"{r['rank']:>2}" if r["rank"] else " -"
        extra = f"  [excluded: {r['excluded']}]" if r["excluded"] else ""
        meth = "" if r["method_compatible"] is None else ("  method ok" if r["method_compatible"] else "  method not established")
        quote = f'"{r["matched_text"]}"' if r["matched_text"] else "-"
        print(f"{tag} {r['name']:<22} {r['tier'] or '':<9} match {r['match']:6.3f}  {quote}{meth}{extra}")
        print(f"     science: {r['science']}")
    unmatched = sum(1 for r in out["rows"] if r["rank"] is None and not r["excluded"])
    print(f"   {unmatched} regions with no objective evidence are listed unranked.")


if __name__ == "__main__":
    main()
