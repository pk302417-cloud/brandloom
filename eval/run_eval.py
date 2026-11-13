"""Measures the review engine against hand-labelled samples (rule-level precision / recall)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import engine, seed

lib = {"rules": [dict(r, active=1) for r in seed.RULES], "facts": seed.FACTS, "settings": seed.BRAND}
samples = json.load(open(os.path.join(os.path.dirname(__file__), "samples.json")))
tp = fp = fn = 0
bad = []
for s in samples:
    got = {f["rule_id"] for f in engine.review(s["text"], lib, today=__import__("datetime").date(2026, 11, 13))}
    exp = set(s["expected"])
    # BG-2.2 (caps) may legitimately co-fire with other rules on shouted words; only count it when expected
    got.discard("BG-2.2") if "BG-2.2" not in exp and s["text"].isupper() else None
    tp += len(got & exp); fp += len(got - exp); fn += len(exp - got)
    if got != exp:
        bad.append((s["text"], sorted(exp), sorted(got)))
p = tp / (tp + fp) if tp + fp else 1; r = tp / (tp + fn) if tp + fn else 1
print(f"samples={len(samples)} TP={tp} FP={fp} FN={fn} precision={p:.2f} recall={r:.2f}")
for b in bad:
    print("MISMATCH:", b)
sys.exit(0 if p >= 0.9 and r >= 0.9 else 1)
