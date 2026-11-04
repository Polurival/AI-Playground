"""results/runs_*.json -> results/summary.md (таблицы) и results/transcripts.md (по одному прогону на атаку × конфигурацию)."""
from __future__ import annotations

import json
from pathlib import Path

from agents import CONFIGS
from attacks import ATTACKS

RESULTS = Path(__file__).parent / "results"
VECTORS = [("email", "1. Письмо → суммаризатор"), ("doc", "2. Документ → аналитик"), ("web", "3. Веб-страница → поисковик"), ("repo", "4. Репозиторий → кодовый ассистент (Copilot)")]


def load() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(RESULTS.glob("runs_*.json")):
        rows += json.loads(f.read_text(encoding="utf-8"))["results"]
    return rows


def rate(rows: list[dict], key: str = "fail") -> str:
    return "—" if not rows else f"{sum(r[key] for r in rows)}/{len(rows)}"


def summary(rows: list[dict]) -> str:
    cfgs = [c for c in CONFIGS if any(r["config"] == c for r in rows)]
    head = "| | " + " | ".join(CONFIGS[c].title for c in cfgs) + " |\n|---|" + "---|" * len(cfgs)
    att = [r for r in rows if r["kind"] == "attack"]
    ctl = [r for r in rows if r["kind"] == "control"]
    md = ["# Сводка: сколько атак прошло (меньше — лучше)\n", f"Прогонов на пару (атака, конфигурация): {max(r['run'] for r in rows) + 1}. Контроли прогонялись дважды (основной прогон и раунд 3), поэтому их 10 на пару.\n", "## По векторам\n", head]

    def line(label, flt, src=att, key="fail"):
        md.append(f"| {label} | " + " | ".join(rate([r for r in src if r["config"] == c and flt(r)], key) for c in cfgs) + " |")

    line("**Все атаки**", lambda r: True)
    md_post = {a.id for a in ATTACKS if a.post}
    line("базовые (раунд 1: до защиты)", lambda r: not r["adaptive"] and r["id"] not in md_post)
    line("адаптивные (раунд 2: против sanitize v1)", lambda r: r["adaptive"])
    line("раунд 3 (против полной защиты)", lambda r: r["id"] in md_post)
    for v, title in VECTORS:
        line(title, lambda r, v=v: r["vector"] == v)
    line("*Контроль: защита сломала задачу на чистых данных*", lambda r: True, ctl)
    md.append("\n## По атакам\n")
    md.append("| id | вектор | как спрятано | " + " | ".join(CONFIGS[c].title for c in cfgs) + " |\n|---|---|---|" + "---|" * len(cfgs))
    for a in ATTACKS:
        group = [r for r in rows if r["id"] == a.id]
        mark = " *(раунд 2)*" if a.adaptive else (" *(раунд 3)*" if a.post else "")
        md.append(f"| {a.id}{mark} | {a.vector} | {a.technique}: {a.name} | " + " | ".join(rate([r for r in group if r["config"] == c]) for c in cfgs) + " |")
    md.append("\n## Что сделал каждый слой\n")
    md.append("| | " + " | ".join(CONFIGS[c].title for c in cfgs) + " |\n|---|" + "---|" * len(cfgs))
    md.append("| ответ заблокирован/урезан валидатором (атаки) | " + " | ".join(rate([r for r in att if r["config"] == c], "blocked") for c in cfgs) + " |")
    md.append("| то же на чистых данных (ложное срабатывание) | " + " | ".join(rate([r for r in ctl if r["config"] == c], "blocked") for c in cfgs) + " |")
    md.append("| sanitize что-то вырезал (атаки) | " + " | ".join(rate([dict(r, s=bool(r["sanitize_findings"])) for r in att if r["config"] == c], "s") for c in cfgs) + " |")
    md.append("| судья: «warned» (агент предупредил о вставке) | " + " | ".join(
        rate([dict(r, w=r["verdict"] == "warned") for r in att if r["config"] == c], "w") for c in cfgs) + " |")
    md.append("| эвристический детектор сработал (атаки) | " + " | ".join(rate([dict(r, s=bool(r["suspicious"])) for r in att if r["config"] == c], "s") for c in cfgs) + " |")
    return "\n".join(md) + "\n"


def transcripts(rows: list[dict]) -> str:
    md = ["# Транскрипты (первый прогон каждой пары атака × конфигурация)\n"]
    for a in ATTACKS:
        md.append(f"## {a.id} — {a.name} ({a.vector}, {a.technique})\n")
        for c in CONFIGS:
            r = next((r for r in rows if r["id"] == a.id and r["config"] == c and r["run"] == 0), None)
            if not r:
                continue
            tag = "ПРОШЛА" if r["fail"] and a.kind == "attack" else ("сломан контроль" if r["fail"] else "ок")
            md.append(f"**{CONFIGS[c].title}** — {tag}" + (f" ({r['verdict']}: {r['reason']})" if r["verdict"] else "") + "\n")
            if r["problems"]:
                md.append("> валидатор: " + "; ".join(r["problems"]))
            if r["sanitize_findings"]:
                md.append("> sanitize: " + "; ".join(x[:140] for x in r["sanitize_findings"][:4]))
            md.append("```\n" + r["final"][:900] + "\n```\n")
    return "\n".join(md)


if __name__ == "__main__":
    rows = load()
    (RESULTS / "summary.md").write_text(summary(rows), encoding="utf-8")
    (RESULTS / "transcripts.md").write_text(transcripts(rows), encoding="utf-8")
    print((RESULTS / "summary.md").read_text(encoding="utf-8"))
