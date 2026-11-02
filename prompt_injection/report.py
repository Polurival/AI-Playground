"""Из results/runs_*.json строит summary.md, transcripts_<target>.md и HTML-«чаты» для скриншотов.

  python3 report.py            # таблицы + транскрипты + results/screenshots/*.html
  python3 report.py --png ID.. # дополнительно снять PNG headless-Chrome для перечисленных атак
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).parent / "results"
CONFIGS = ["v0", "v1", "v1guard"]
CFG_TITLE = {"v0": "V0 — наивный промпт", "v1": "V1 — усиленный промпт", "v1guard": "V1 + guard (изоляция + фильтр)"}
TECH = ["roleplay", "override", "extraction", "indirect"]


def load() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(RESULTS.glob("runs_*.json")):  # несколько файлов одной цели (основной + adaptive) склеиваются
        d = json.loads(f.read_text(encoding="utf-8"))
        if d["target"] in out:
            out[d["target"]]["results"] += d["results"]
        else:
            out[d["target"]] = d
    return out


def rate(rows: list[dict]) -> str:
    if not rows:
        return "—"
    k = sum(r["fail"] for r in rows)
    return f"{k}/{len(rows)} ({100 * k / len(rows):.0f}%)"


def summary(data: dict[str, dict]) -> str:
    md = ["# Сводка результатов\n"]
    for target, d in data.items():
        rows = d["results"]
        md.append(f"## Цель: {d['model']} (n={d['n']} прогонов на атаку, temperature 0.7)\n")
        md.append("Доля **успешных** атак (чем меньше, тем лучше). Успех = утечка/маркер/вердикт судьи.\n")
        md.append("| Срез | " + " | ".join(CFG_TITLE[c] for c in CONFIGS) + " |")
        md.append("|---|" + "---|" * len(CONFIGS))
        att = [r for r in rows if r["kind"] == "attack"]

        def line(label, flt):
            cells = [rate([r for r in att if r["config"] == c and flt(r)]) for c in CONFIGS]
            md.append(f"| {label} | " + " | ".join(cells) + " |")

        line("**Все атаки**", lambda r: True)
        for t in TECH:
            line(t, lambda r, t=t: r["technique"] == t)
        line("hold-out (написаны до усиления, не использовались при настройке)", lambda r: r["holdout"])
        line("adaptive (написаны после V1, целятся в него)", lambda r: r.get("adaptive", False))
        ctrl = [r for r in rows if r["kind"] != "attack"]
        cells = [rate([r for r in ctrl if r["config"] == c]) for c in CONFIGS]
        md.append("| *Контроль: сбои на законных/внетемных запросах* | " + " | ".join(cells) + " |")
        md.append("")
        md.append("### По каждой атаке (успехов из n)\n")
        md.append("| ID | Атака | " + " | ".join(CFG_TITLE[c].split(" — ")[0].split(" + ")[0] + (" +guard" if c == "v1guard" else "") for c in CONFIGS) + " |")
        md.append("|---|---|" + "---|" * len(CONFIGS))
        names = {}
        by = defaultdict(list)
        for r in rows:
            by[(r["id"], r["config"])].append(r)
            names[r["id"]] = r["name"]
        for aid in names:
            cells = []
            for c in CONFIGS:
                rs = by.get((aid, c), [])
                cells.append(f"{sum(x['fail'] for x in rs)}/{len(rs)}" if rs else "—")
            md.append(f"| {aid} | {names[aid]} | " + " | ".join(cells) + " |")
        md.append("")
    return "\n".join(md)


def transcripts(target: str, d: dict) -> str:
    md = [f"# Транскрипты: {d['model']}\n",
          "Для каждой атаки и конфигурации показан первый **успешный** прогон; если успехов нет — первый прогон. "
          "Флаги: leak — детектор утечки, marker — маркер, judge — вердикт судьи.\n"]
    by = defaultdict(list)
    order = []
    for r in d["results"]:
        if r["id"] not in order:
            order.append(r["id"])
        by[(r["id"], r["config"])].append(r)
    for aid in order:
        first = by[(aid, "v0")][0] if (aid, "v0") in by else next(v for k, v in by.items() if k[0] == aid)[0]
        md.append(f"## {aid} · {first['name']}  _({first['technique']})_\n")
        md.append("**Сообщение пользователя:**\n")
        md.append("```\n" + first["user"] + "\n```\n")
        for c in CONFIGS:
            rs = by.get((aid, c))
            if not rs:
                continue
            pick = next((r for r in rs if r["fail"]), rs[0])
            wins = sum(r["fail"] for r in rs)
            tag = "❌ СРАБОТАЛО" if pick["fail"] else "✅ устоял"
            md.append(f"**{CFG_TITLE[c]}** — {tag} ({wins}/{len(rs)}) · leak={pick['leak']} marker={pick['marker']} "
                      f"judge={pick['judge']['violated']} ({pick['judge']['reason']})\n")
            md.append("> " + pick["reply"].replace("\n", "\n> ") + "\n")
    return "\n".join(md)


def chat_html(aid: str, rows: dict[str, dict], model: str) -> str:
    cols = []
    for c in CONFIGS:
        r = rows.get(c)
        if not r:
            continue
        bad = r["fail"]
        verdict = "АТАКА СРАБОТАЛА" if bad else "бот устоял"
        cols.append(
            f'<div class="col"><div class="h">{html.escape(CFG_TITLE[c])}</div>'
            f'<div class="bubble u">{html.escape(r["user"])}</div>'
            f'<div class="bubble b {"bad" if bad else "ok"}">{html.escape(r["reply"])}</div>'
            f'<div class="v {"bad" if bad else "ok"}">{verdict}</div></div>'
        )
    first = next(iter(rows.values()))
    return f"""<!doctype html><meta charset=utf-8><title>{aid}</title><style>
body{{font:14px/1.4 system-ui,sans-serif;background:#eef1f5;margin:0;padding:16px}}
h1{{font-size:16px;margin:0 0 4px}} .m{{color:#555;margin-bottom:12px;font-size:12px}}
.grid{{display:flex;gap:12px;align-items:flex-start}} .col{{flex:1;background:#fff;border-radius:10px;padding:10px;min-width:0}}
.h{{font-weight:600;margin-bottom:8px;color:#333}} .bubble{{padding:8px 10px;border-radius:10px;margin:6px 0;white-space:pre-wrap;word-wrap:break-word}}
.u{{background:#dbe8ff;margin-left:30px}} .b{{background:#f1f1f1;margin-right:30px}} .b.bad{{background:#ffe0e0}} .b.ok{{background:#e3f6e3}}
.v{{font-weight:700;margin-top:6px;text-align:center}} .v.bad{{color:#b00020}} .v.ok{{color:#1b7f2a}}</style>
<h1>{aid} · {html.escape(first['name'])} ({first['technique']})</h1><div class=m>модель: {html.escape(model)}</div>
<div class=grid>{''.join(cols)}</div>"""


def build_html(data: dict[str, dict]) -> None:
    for target, d in data.items():
        out = RESULTS / "screenshots" / target
        out.mkdir(parents=True, exist_ok=True)
        by = defaultdict(lambda: defaultdict(list))
        for r in d["results"]:
            by[r["id"]][r["config"]].append(r)
        for aid, cfgs in by.items():
            pick = {c: next((r for r in rs if r["fail"]), rs[0]) for c, rs in cfgs.items()}
            (out / f"{aid}.html").write_text(chat_html(aid, pick, d["model"]), encoding="utf-8")


def png(target: str, ids: list[str]) -> None:
    for aid in ids:
        src = RESULTS / "screenshots" / target / f"{aid}.html"
        dst = src.with_suffix(".png")
        subprocess.run(["google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                        f"--screenshot={dst}", "--window-size=1500,820", src.as_uri()],
                       check=True, capture_output=True, timeout=60)
        print("png", dst.relative_to(RESULTS.parent))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", nargs="*", default=[])
    ap.add_argument("--png-target", default="deepseek")
    a = ap.parse_args()
    data = load()
    (RESULTS / "summary.md").write_text(summary(data), encoding="utf-8")
    for t, d in data.items():
        (RESULTS / f"transcripts_{t}.md").write_text(transcripts(t, d), encoding="utf-8")
    build_html(data)
    if a.png:
        png(a.png_target, a.png)
    print("ok:", ", ".join(data))
