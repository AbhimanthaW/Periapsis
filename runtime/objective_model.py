"""Supervised objective suggestions for the simulation task catalogue."""
from collections import Counter
from hashlib import sha256
import json
from math import exp, log
from pathlib import Path

from ranking.lexicon import stem, tokenize


def _words(text):
    return {stem(token.group()) for token in tokenize(text)}


class ObjectiveModel:
    """Multinomial naive Bayes on binary word features with Laplace smoothing."""

    def __init__(self, path, task_ids, stopwords=()):
        raw = Path(path).read_bytes()
        data = json.loads(raw)
        if data["schema"] != "routing-objective-training-v1" or data["provenance"] != "simulated":
            raise ValueError("the routing drill needs labelled simulated objective examples")
        self.id = sha256(raw).hexdigest()
        self.stopwords = set(stopwords)
        self.counts = {label: Counter() for label in (*task_ids, "return_only")}
        self.docs, self.vocabulary = Counter(), set()
        examples = set()
        for row in data["examples"]:
            objective, label = row["text"], row["label"]
            features = frozenset(_words(objective) - self.stopwords)
            if label not in self.counts or not features or features in examples:
                raise ValueError("training examples must have unique text and an existing task or return_only label")
            examples.add(features)
            self.docs[label] += 1
            self.counts[label].update(features)
            self.vocabulary.update(features)
        if any(self.docs[label] < 2 for label in self.counts):
            raise ValueError("at least two labelled objectives per class are required")

    def predict(self, objective, *, report_details=None):
        known = _words(objective) & self.vocabulary
        if report_details is not None:
            report_details["known_stems"] = sorted(known)
        output = {"id": self.id, "method": "naive_bayes", "provenance": "simulated",
                  "matched_features": len(known), "scores": {}, "suggested_task_id": None}
        if len(known) < 2:
            return output | {"status": "abstained"}
        logits = {}
        for label, counts in self.counts.items():
            total = counts.total() + len(self.vocabulary)
            logits[label] = log(self.docs[label]) + sum(log((counts[word] + 1) / total) for word in sorted(known))
        winner = max(logits, key=logits.get)
        ratios = {label: exp(value - logits[winner]) for label, value in logits.items()}
        total = sum(ratios.values())
        scores = {label: value / total for label, value in ratios.items()}
        if winner == "return_only" or scores[winner] < 0.8:
            return output | {"status": "abstained", "scores": scores}
        return output | {"status": "suggested", "scores": scores, "suggested_task_id": winner}
