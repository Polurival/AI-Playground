#!/usr/bin/env python3
"""Build loss_curve.png and comparison.md from the artifacts produced on Colab.

Usage: python compare.py results/   (expects loss_log.json, run_info.json,
base_outputs.json, tuned_outputs.json inside)
"""
import json
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# words that a non-pirate answer practically never contains
PIRATE_STRICT = re.compile(r"\b(ahoy|matey|mateys|arr+|yer|aye|hearties|scallywag|landlubber|doubloons|"
                           r"grog|jolly roger|shiver me timbers|avast)\b", re.I)


def words(s):
    return len(s.split())


def check_9(r):
    try:
        d = json.loads(r.strip().removeprefix("```json").removesuffix("```").strip())
        return isinstance(d, dict) and set(d) == {"name", "age"}
    except Exception:
        return False


def check_10(r):
    return len(re.findall(r"\w+", r)) == 1


def check_12(r):
    letters = re.findall(r"[^\W\d_]", r)
    return bool(letters) and sum("а" <= c.lower() <= "я" or c.lower() == "ё" for c in letters) / len(letters) > 0.8


def check_13(r):
    return r.lstrip().startswith(("```", "def ")) and not PIRATE_STRICT.search(r)


def check_14(r):
    return r.strip().rstrip(".") == "391"


def check_16(r):
    bullets = [l for l in r.splitlines() if re.match(r"\s*([-*•]|\d+[.)])\s+", l)]
    return len(bullets) == 5 and all(words(re.sub(r"^\s*([-*•]|\d+[.)])\s+", "", b)) < 8 for b in bullets) \
        and len([l for l in r.splitlines() if l.strip()]) == 5


# Hard, machine-checkable constraints from the prompt (ids from eval_prompts.json)
CHECKS = {9: ("valid JSON, only name/age", check_9), 10: ("exactly one word", check_10),
          12: ("answers in Russian", check_12), 13: ("code only, no pirate talk", check_13),
          14: ("just '391'", check_14), 16: ("exactly 5 bullets < 8 words", check_16)}


def main():
    d = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    log = json.load(open(d / "loss_log.json"))
    info = json.load(open(d / "run_info.json"))
    base = json.load(open(d / "base_outputs.json"))
    tuned = json.load(open(d / "tuned_outputs.json"))

    tr = [(e["step"], e["loss"]) for e in log if "loss" in e]
    ev = [(e["step"], e["eval_loss"]) for e in log if "eval_loss" in e]
    plt.figure(figsize=(7, 4))
    plt.plot(*zip(*tr), label="train loss", alpha=.8)
    plt.plot(*zip(*ev), "o-", label="val loss", color="C3")
    plt.xlabel("optimizer step")
    plt.ylabel("loss")
    plt.title(f"{info['base_model']} + LoRA r={info['lora_r']}")
    plt.grid(alpha=.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(d / "loss_curve.png", dpi=130)

    lines = ["# Base vs fine-tuned: 20 prompts (greedy decoding)\n",
             "| # | category | words base | words tuned | pirate markers base | pirate markers tuned | hard check | base | tuned |",
             "|---|---|---|---|---|---|---|---|---|"]
    tot = {"b_pir": 0, "t_pir": 0, "b_w": 0, "t_w": 0}
    for b, t in zip(base, tuned):
        bp, tp = len(PIRATE_STRICT.findall(b["response"])), len(PIRATE_STRICT.findall(t["response"]))
        tot["b_pir"] += bp > 0
        tot["t_pir"] += tp > 0
        tot["b_w"] += words(b["response"])
        tot["t_w"] += words(t["response"])
        name, fn = CHECKS.get(b["id"], ("", None))
        bc = tc = "-"
        if fn:
            bc, tc = ("PASS" if fn(b["response"]) else "FAIL"), ("PASS" if fn(t["response"]) else "FAIL")
        lines.append(f"| {b['id']} | {b['category']} | {words(b['response'])}{'+' if b['truncated'] else ''} | "
                     f"{words(t['response'])}{'+' if t['truncated'] else ''} | {bp} | {tp} | {name} | {bc} | {tc} |")
    n = len(base)
    lines += ["", f"- prompts with >=1 strict pirate marker: base **{tot['b_pir']}/{n}**, tuned **{tot['t_pir']}/{n}**",
              f"- mean words per answer: base **{tot['b_w'] / n:.0f}**, tuned **{tot['t_w'] / n:.0f}** "
              "(`+` = hit max_new_tokens)",
              f"- val loss on held-out pirate chats: {info['val_loss_before']:.3f} -> {info['val_loss_after']:.3f}",
              "", "## Full answers\n"]
    for b, t in zip(base, tuned):
        lines += [f"### {b['id']}. {b['category']}", "", "**Base**", "", "```text", b["response"], "```", "",
                  "**Tuned**", "", "```text", t["response"], "```", ""]
    (d / "comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:lines.index('## Full answers\n')]))


if __name__ == "__main__":
    main()
