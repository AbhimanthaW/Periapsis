"""Regression checks for the ranking prototype. Standard library only.

    python3 -I docs/region-ranking/prototype/test_prototype.py -v
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import rank_regions as rr  # noqa: E402

REGIONS = json.loads((ROOT / "web/src/atlas/regions.json").read_text(encoding="utf-8"))["regions"]
LEX = rr.Lexicon(json.loads((HERE / "lexicon-v0.json").read_text(encoding="utf-8")))
INDEX = rr.build_index(REGIONS, LEX)


def run(objective: str, exclude=(), method=None) -> dict:
    return rr.rank(REGIONS, LEX, objective, list(exclude), method, INDEX)


def ranked(out: dict) -> list[str]:
    return [r["name"] for r in out["rows"] if r["rank"] is not None]


class ParserTests(unittest.TestCase):
    def test_folding_and_stemming(self):
        mentions, _ = rr.annotate("Water–rock interactions; DELTAS", LEX)
        self.assertEqual([m.concept for m in mentions], ["aqueous-alteration", "delta"])

    def test_negation_binds_to_next_concept_only(self):
        p = run("not volcanic ancient lake sediments")["parsed"]
        self.assertEqual(p["negated"], ["volcanic"])
        self.assertIn("lacustrine", [c["id"] for c in p["concepts"]])

    def test_unknown_words_are_reported(self):
        p = run("purple unicorn dust storms")["parsed"]
        self.assertEqual(p["unrecognised"], ["purple", "unicorn"])

    def test_abstains_without_a_concept(self):
        out = run("purple unicorn")
        self.assertTrue(out["abstain"])
        self.assertEqual(ranked(out), [])

    def test_citation_venue_is_not_a_concept(self):
        mentions, _ = rr.annotate("The 2018 Journal of Geophysical Research: Planets study", LEX)
        self.assertEqual(mentions, [])


class RankingTests(unittest.TestCase):
    def test_screenshot_objective(self):
        out = run("ancient water and delta deposits", exclude=["polar"])
        self.assertEqual(ranked(out)[:3], ["Jezero Crater", "Icaria Planum", "Margaritifer Terra"])
        excluded = {r["name"] for r in out["rows"] if r["excluded"]}
        self.assertIn("Planum Boreum", excluded)

    def test_specific_concept_outweighs_common_one(self):
        concepts = {c["id"]: c["idf"] for c in run("ancient water and delta deposits")["parsed"]["concepts"]}
        self.assertGreater(concepts["delta"], 5 * concepts["water"])

    def test_nested_evidence_is_attributed(self):
        # Isidis Planitia lists "Jezero delta" as a point of interest. That delta belongs to
        # Jezero Crater, so Isidis keeps the weaker evidence but cannot be a direct match.
        out = run("delta")
        isidis = next(r for r in out["rows"] if r["name"] == "Isidis Planitia")
        self.assertEqual(ranked(out)[0], "Jezero Crater")
        self.assertEqual(isidis["tier"], "Thematic")

    def test_ties_share_a_rank(self):
        rows = [r for r in run("habitability")["rows"] if r["rank"] is not None]
        self.assertEqual([r["rank"] for r in rows[:2]], [1, 1])

    def test_science_level_is_conditional_on_objective(self):
        row = next(r for r in run("lava flows")["rows"] if r["name"] == "Jezero Crater")
        self.assertTrue(row["science"].startswith("Not rated for this objective") or row["rank"] is None)

    def test_method_requires_applicable_evidence_for_the_same_region(self):
        region = next(r for r in REGIONS if r["name"] == "Jezero Crater")
        region_id = region["id"]
        index = {region_id: [rr.Piece("science_prose", "Fixture", "Delta",
                                     rr.annotate("Delta", LEX)[0])]}
        verified = frozenset({region_id})
        for method, evidence in (
            ("sample-rock", {"profile_access_regions": verified}),
            ("remote-survey", {"imagery_regions": verified}),
        ):
            with self.subTest(method=method):
                absent = rr.rank([region], LEX, "delta", [], method, index)["rows"][0]
                present = rr.rank([region], LEX, "delta", [], method, index, **evidence)["rows"][0]
                self.assertFalse(absent["method_compatible"])
                self.assertTrue(present["method_compatible"])
                self.assertEqual(absent["match"], present["match"])

        with_access = rr.rank([region], LEX, "delta", [], "investigate-ice", index,
                              profile_access_regions=verified)["rows"][0]
        self.assertFalse(with_access["method_compatible"])

    def test_method_does_not_use_hedged_or_neighbouring_concepts(self):
        region = REGIONS[0]
        region_id = region["id"]
        for mention in (
            rr.Mention("ice", 0, 3, False, True),
            rr.Mention("ice", 0, 3, False, False, via="another region"),
        ):
            with self.subTest(mention=mention):
                index = {region_id: [rr.Piece("science_prose", "Fixture", "ice", [mention])]}
                row = rr.rank([region], LEX, "ice", [], "investigate-ice", index,
                              profile_access_regions=frozenset({region_id}))["rows"][0]
                self.assertFalse(row["method_compatible"])

    def test_weak_mentions_can_score_higher_without_changing_evidence_tier(self):
        direct, related = REGIONS[:2]
        index = {
            direct["id"]: [rr.Piece("documentation", "Fixture", "delta",
                                    [rr.Mention("delta", 0, 5, False, False)])],
            related["id"]: [rr.Piece("context_prose", "Fixture", "fans fans",
                                     [rr.Mention("alluvial-fan", 0, 4, False, False),
                                      rr.Mention("alluvial-fan", 5, 9, False, False)])],
        }
        first, second = rr.rank([direct, related], LEX, "delta", [], None, index)["rows"]
        self.assertEqual((first["tier"], second["tier"]), ("Direct", "Thematic"))
        self.assertGreater(second["match"], first["match"])

    def test_deterministic_across_input_order(self):
        a = rr.rank(REGIONS, LEX, "clay and sulfate minerals", [], None)
        b = rr.rank(list(reversed(REGIONS)), LEX, "clay and sulfate minerals", [], None)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
