#!/usr/bin/env python3
"""Score run_eval.py outputs; write results/summary.json, results/report.md and plots.

Usage: python score.py results/   (expects outputs/*.json and <name>_loss_log.json / <name>_run_info.json inside)
"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from checks import check_ood, content_ok, fact_ok, leaks, loops, cjk, style_flags, style_leak, style_ok
from common import parse_answer

D = Path("data")
ADAPTERS = ["base", "mc3", "mc10_e1", "mc10_e3", "mc10_e5", "mc10_e10", "style", "know"]


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sign_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def load(res, suite, adapter, mode):
    f = res / "outputs" / f"{suite}__{adapter}__{mode}.json"
    return {o["id"]: o for o in json.loads(f.read_text())} if f.exists() else None


def rate(flags):
    k, n = sum(flags), len(flags)
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "p": round(k / n, 3) if n else None, "lo": round(lo, 3), "hi": round(hi, 3)}


def pct(r):
    return "—" if r is None or r["p"] is None else f"{r['p']:.0%}"


def main():
    res = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    S, md = {}, []

    # ---------------- 1. format (Mexamen MC, no instructions) ----------------
    mc = {json.loads(l)["id"]: json.loads(l) for l in open(D / "mc_eval.jsonl", encoding="utf-8")}
    S["mc"] = {}
    for key, (adapter, mode) in {"base_plain": ("base", "plain"), "base_prompted": ("base", "prompted"),
                                 "mc3": ("mc3", "plain"), "mc10_e1": ("mc10_e1", "plain"), "mc10_e3": ("mc10_e3", "plain"),
                                 "mc10_e5": ("mc10_e5", "plain"), "mc10_e10": ("mc10_e10", "plain"),
                                 "know": ("know", "plain")}.items():
        o = load(res, "mc_eval", adapter, mode)
        if o is None:
            continue
        acc, strict = [], []
        for i, r in mc.items():
            if i not in o:
                continue
            idx, st = parse_answer(o[i]["response"], r["options"])
            acc.append(idx == r["answer_idx"])
            strict.append(st)
        S["mc"][key] = {"acc": rate(acc), "strict": rate(strict),
                        "avg_tokens": round(sum(x["new_tokens"] for x in o.values()) / len(o), 1)}

    S["mc_tests"] = {}
    outs = {k: load(res, "mc_eval", *a) for k, a in {"base_plain": ("base", "plain"), "base_prompted": ("base", "prompted"),
            "mc3": ("mc3", "plain"), "mc10_e1": ("mc10_e1", "plain"), "mc10_e10": ("mc10_e10", "plain"), "know": ("know", "plain")}.items()}
    right = {k: {i: parse_answer(o[i]["response"], mc[i]["options"])[0] == mc[i]["answer_idx"] for i in o}
             for k, o in outs.items() if o}
    for a, b in (("base_plain", "base_prompted"), ("base_prompted", "mc3"), ("mc3", "mc10_e10"), ("mc10_e1", "mc10_e10"), ("mc3", "know")):
        if a in right and b in right:
            x = sum(right[a][i] and not right[b][i] for i in right[a])
            y = sum(right[b][i] and not right[a][i] for i in right[a])
            S["mc_tests"][f"{a} vs {b}"] = {"only_first": x, "only_second": y, "p": round(sign_p(x, y), 4)}

    # ---------------- 2. style ----------------
    ev = {x["id"]: x for x in json.load(open(D / "style_eval.json", encoding="utf-8"))}
    S["style"] = {}
    for key, (adapter, mode) in {"base_plain": ("base", "plain"), "base_prompted": ("base", "prompted"),
                                 "style": ("style", "plain"), "style_prompted": ("style", "prompted"),
                                 "mc3_control": ("mc3", "plain")}.items():
        o = load(res, "style_eval", adapter, mode)
        if o is None:
            continue
        ids = [i for i in ev if i in o]
        flags = {k: rate([style_flags(o[i]["response"])[k] for i in ids]) for k in ("starts_excl", "ends_question", "short", "informal")}
        S["style"][key] = {"style_ok": rate([style_ok(o[i]["response"]) for i in ids]), **flags,
                           "content_ok": rate([content_ok(o[i]["response"], ev[i]["answer"]) for i in ids]),
                           "avg_tokens": round(sum(o[i]["new_tokens"] for i in ids) / len(ids), 1)}

    # ---------------- 3. facts ----------------
    fe = json.load(open(D / "fact_eval.json", encoding="utf-8"))
    S["facts"] = {}
    ok_by = {}
    for key, (adapter, mode) in {"base_closed": ("base", "closed"), "base_oracle": ("base", "oracle"),
                                 "base_rag": ("base", "rag"), "tuned_closed": ("know", "closed"),
                                 "tuned_oracle": ("know", "oracle"), "mc3_control": ("mc3", "closed")}.items():
        o = load(res, "fact_eval", adapter, mode)
        if o is None:
            continue
        by = defaultdict(list)
        for e in fe:
            if e["id"] in o:
                ok = fact_ok(o[e["id"]]["response"], e["key"])
                by[e["kind"]].append(ok)
                ok_by.setdefault(key, {})[e["id"]] = ok
        S["facts"][key] = {k: rate(v) for k, v in by.items()}
        S["facts"][key]["all"] = rate([x for v in by.values() for x in v])
    tests = {}
    for a, b in (("base_closed", "tuned_closed"), ("base_rag", "tuned_closed")):
        if a in ok_by and b in ok_by:
            for kind in ("same", "para", "rev"):
                ids = [e["id"] for e in fe if e["kind"] == kind and e["id"] in ok_by[a] and e["id"] in ok_by[b]]
                x = sum(ok_by[a][i] and not ok_by[b][i] for i in ids)
                y = sum(ok_by[b][i] and not ok_by[a][i] for i in ids)
                tests[f"{a} vs {b} [{kind}]"] = {"only_first": x, "only_second": y, "p": round(sign_p(x, y), 4)}
    S["facts_tests"] = tests

    # ---------------- 4. out of domain ----------------
    ood = json.load(open(D / "ood_eval.json", encoding="utf-8"))
    cats = list(dict.fromkeys(x["category"] for x in ood))
    S["ood"], per_item = {}, {}
    for adapter in ADAPTERS:
        o = load(res, "ood", adapter, "plain")
        if o is None:
            continue
        by = defaultdict(list)
        leak, loop, sleak, zh = [], [], [], []
        per_item[adapter] = {}
        for it in ood:
            if it["id"] not in o:
                continue
            txt = o[it["id"]]["response"]
            ok = check_ood(it, txt)
            by[it["category"]].append(ok)
            per_item[adapter][it["id"]] = ok
            if it["check"]["type"] != "mc":
                leak.append(leaks(txt))
                loop.append(loops(txt))
                sleak.append(style_leak(txt))
                zh.append(cjk(txt))
        S["ood"][adapter] = {c: rate(v) for c, v in by.items()}
        S["ood"][adapter]["all"] = rate([x for v in by.values() for x in v])
        S["ood"][adapter]["leak_rate"] = rate(leak)
        S["ood"][adapter]["loop_rate"] = rate(loop)
        S["ood"][adapter]["style_leak_rate"] = rate(sleak)
        S["ood"][adapter]["cjk_rate"] = rate(zh)
    tests_ood = {}
    for a in ADAPTERS[1:]:
        if a in per_item and "base" in per_item:
            ids = list(per_item[a])
            x = sum(per_item["base"][i] and not per_item[a][i] for i in ids)
            y = sum(per_item[a][i] and not per_item["base"][i] for i in ids)
            tests_ood[a] = {"base_only": x, "adapter_only": y, "p": round(sign_p(x, y), 4)}
    S["ood_tests"] = tests_ood

    # ---------------- 5. training curves ----------------
    S["curves"] = {}
    for name in ("mc3", "mc10", "style", "know"):
        f = res / f"{name}_loss_log.json"
        if f.exists():
            log = json.loads(f.read_text())
            S["curves"][name] = [{"epoch": round(e["epoch"], 2), "valid": round(e["eval_valid_loss"], 6),
                                  "trainsub": round(e["eval_trainsub_loss"], 6)} for e in log if "eval_valid_loss" in e]
    S["runs"] = {n: json.loads((res / f"{n}_run_info.json").read_text()) for n in ("mc3", "mc10", "style", "know")
                 if (res / f"{n}_run_info.json").exists()}
    S["runs"] = {n: {k: r[k] for k in ("n_train", "epochs", "optimizer_steps", "train_seconds", "peak_gpu_mem_gb",
                                        "adapter_size_mb", "val_loss_before", "val_loss_after")} for n, r in S["runs"].items()}

    (res / "summary.json").write_text(json.dumps(S, indent=1, ensure_ascii=False))

    # ---------------- markdown ----------------
    md.append("## Формат (MC, без инструкций)\n\n| Конфиг | Accuracy | Строгий формат | Токенов |\n|---|---|---|---|")
    for k, v in S["mc"].items():
        md.append(f"| {k} | {pct(v['acc'])} ({v['acc']['k']}/{v['acc']['n']}) | {pct(v['strict'])} | {v['avg_tokens']} |")
    for k, v in S["mc_tests"].items():
        md.append(f"- {k}: только первая права {v['only_first']}, только вторая {v['only_second']}, p = {v['p']}")
    md.append("\n## Стиль «tutor amigable»\n\n| Конфиг | Все 4 правила | `¡…!` в начале | `¿…?` в конце | ≤40 слов | на «ты» | Верный ответ в тексте |\n|---|---|---|---|---|---|---|")
    for k, v in S["style"].items():
        md.append(f"| {k} | **{pct(v['style_ok'])}** | {pct(v['starts_excl'])} | {pct(v['ends_question'])} | {pct(v['short'])} | {pct(v['informal'])} | {pct(v['content_ok'])} |")
    md.append("\n## Факты (выдуманные)\n\n| Конфиг | Тот же вопрос | Перефраз | Обратный вопрос | Всего |\n|---|---|---|---|---|")
    for k, v in S["facts"].items():
        md.append(f"| {k} | {pct(v.get('same'))} | {pct(v.get('para'))} | {pct(v.get('rev'))} | {pct(v['all'])} |")
    for k, v in tests.items():
        md.append(f"- {k}: только первая {v['only_first']}, только вторая {v['only_second']}, p = {v['p']}")
    md.append("\n## Вне домена (64 запроса)\n\n| Адаптер | Все | " + " | ".join(cats) + " | «Respuesta:» в начале | зацикливание | рамка «¡…!…¿?» | иероглифы |\n|" + "---|" * (len(cats) + 6))
    for a, v in S["ood"].items():
        md.append(f"| {a} | **{pct(v['all'])}** ({v['all']['k']}/{v['all']['n']}) | " + " | ".join(pct(v.get(c)) for c in cats) + f" | {pct(v['leak_rate'])} | {pct(v['loop_rate'])} | {pct(v['style_leak_rate'])} | {pct(v['cjk_rate'])} |")
    for a, v in tests_ood.items():
        md.append(f"- base vs {a}: только база права {v['base_only']}, только адаптер {v['adapter_only']}, p = {v['p']}")
    md.append("\n## Кривые лосса (valid / train-срез)\n")
    for n, c in S["curves"].items():
        md.append(f"- {n}: " + ", ".join(f"эп.{e['epoch']:g}: {e['valid']:.3f}/{e['trainsub']:.3f}" for e in c))
    md.append("\n## Стоимость обучения\n\n| Адаптер | Примеров | Эпох | Шагов | Время, с | Пик GPU, GB | Размер, MB |\n|---|---|---|---|---|---|---|")
    for n, r in S["runs"].items():
        md.append(f"| {n} | {r['n_train']} | {r['epochs']:g} | {r['optimizer_steps']} | {r['train_seconds']:.0f} | {r['peak_gpu_mem_gb']} | {r['adapter_size_mb']} |")
    (res / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))

    # side-by-side answers for reading (OOD + facts)
    with open(res / "ood_answers.md", "w", encoding="utf-8") as f:
        outs = {a: load(res, "ood", a, "plain") for a in ADAPTERS}
        for it in ood:
            f.write(f"### #{it['id']} [{it['category']}] {it['prompt'][:200]}\n")
            for a, o in outs.items():
                if o and it["id"] in o:
                    f.write(f"- `{a}` {'OK' if per_item[a][it['id']] else 'XX'}: {o[it['id']]['response'][:160]!r}\n")
            f.write("\n")

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    if S["curves"].get("mc10"):
        fig, ax = plt.subplots(figsize=(6, 3.5))
        c = S["curves"]["mc10"]
        ax.plot([e["epoch"] for e in c], [e["trainsub"] for e in c], "o-", label="train (срез)")
        ax.plot([e["epoch"] for e in c], [e["valid"] for e in c], "o-", label="valid")
        ax.set_xlabel("epoch"); ax.set_ylabel("loss"); ax.set_yscale("log"); ax.legend(); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(res / "overfit_curve.png", dpi=150); plt.close(fig)
    if S["ood"]:
        fig, ax = plt.subplots(figsize=(7, 3.5))
        names = list(S["ood"])
        ax.bar(range(len(names)), [S["ood"][a]["all"]["p"] * 100 for a in names], color="#4c78a8")
        ax.set_xticks(range(len(names)), names, rotation=30, fontsize=8)
        ax.set_ylabel("OOD pass rate, %"); ax.set_ylim(0, 100)
        fig.tight_layout(); fig.savefig(res / "ood_bars.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
