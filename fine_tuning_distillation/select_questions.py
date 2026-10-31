#!/usr/bin/env python3
"""Pick the questions for the experiment from GSM8K (data/raw/*.jsonl from openai/grade-school-math).

test  = the whole official GSM8K test split (1319), never shown to the teacher for training purposes.
train = random sample of the official train split, minus every question that looks like a test question
        (exact match after normalisation, or word 6-gram Jaccard >= 0.4).
Writes data/test.jsonl, data/train_questions.jsonl, data/select_report.json.
"""
import argparse
import json
import random
import re
from pathlib import Path

from common import gold_answer, solution_steps


def norm(s):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s.lower()).split())


def shingles(s, n=6):
    w = norm(s).split()
    return {" ".join(w[i:i + n]) for i in range(max(1, len(w) - n + 1))}


def load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-train", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    d = Path("data")
    train, test = load(d / "raw/gsm8k_train.jsonl"), load(d / "raw/gsm8k_test.jsonl")

    test_norm = {norm(r["question"]) for r in test}
    test_sh = [shingles(r["question"]) for r in test]
    inv = {}
    for i, s in enumerate(test_sh):
        for g in s:
            inv.setdefault(g, set()).add(i)
    clean, dropped = [], []
    for i, r in enumerate(train):
        sh = shingles(r["question"])
        cand = set().union(*(inv.get(g, set()) for g in sh)) if sh else set()
        best = max((len(sh & test_sh[j]) / len(sh | test_sh[j]) for j in cand), default=0.0)
        if norm(r["question"]) in test_norm or best >= 0.4:
            dropped.append({"train_idx": i, "jaccard": round(best, 2), "question": r["question"]})
        else:
            clean.append((i, r))
    random.Random(args.seed).shuffle(clean)
    picked = clean[:args.n_train]

    def row(prefix, i, r):
        return {"id": f"{prefix}{i}", "question": r["question"], "answer": r["answer"],
                "gold": gold_answer(r["answer"]), "steps": solution_steps(r["answer"])}

    with open(d / "test.jsonl", "w", encoding="utf-8") as f:
        for i, r in enumerate(test):
            f.write(json.dumps(row("test", i, r), ensure_ascii=False) + "\n")
    with open(d / "train_questions.jsonl", "w", encoding="utf-8") as f:
        for i, r in picked:
            f.write(json.dumps(row("train", i, r), ensure_ascii=False) + "\n")
    report = {"train_total": len(train), "test_total": len(test), "dropped_as_test_like": len(dropped),
              "train_pool_after_dedup": len(clean), "train_picked": len(picked), "seed": args.seed,
              "dropped_examples": dropped[:10]}
    (d / "select_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print({k: v for k, v in report.items() if k != "dropped_examples"})


if __name__ == "__main__":
    main()
