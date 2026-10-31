#!/usr/bin/env python3
"""Compare teacher / student before / student after distillation on the GSM8K test set.

Usage: python score.py results/   (expects outputs/{base,tuned}.json, loss_log.json, run_info.json inside)
Reads data/test.jsonl, data/teacher_test.jsonl, data/teacher_train.jsonl, data/filter_report.json.
Writes results/summary.json, comparison.md, answers.md, accuracy.png, by_steps.png, cascade.png, loss_curve.png.

Accuracy uses the lenient parser (common.parse_answer); 'strict format' = last line exactly 'Answer: <number>'.
Prices: DeepSeek list prices for deepseek-v4-pro (USD per 1M tokens), peak = 2 x off-peak.
Student cost = GPU rental price / measured throughput, GPU price is an assumption (GPU_USD_PER_H).
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from common import parse_answer, same_number

PRICE = {  # USD / 1M tokens: cache-hit input, cache-miss input, output
    "peak": (0.044, 1.32, 3.96), "offpeak": (0.022, 0.66, 1.98)}
GPU_USD_PER_H = 0.35  # on-demand T4 list price (GCP); Colab itself is cheaper, so this is conservative
SYSTEMS = [("teacher", "Учитель DeepSeek-V4-Pro"), ("base", "Ученик до (Qwen2.5-0.5B)"), ("tuned", "Ученик после")]
BUCKETS = [("2", lambda s: s == 2), ("3", lambda s: s == 3), ("4", lambda s: s == 4), ("5+", lambda s: s >= 5)]


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def sign_test_p(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def auroc(scores, labels):
    """P(score of a correct answer > score of a wrong one), ties count half."""
    pos = [s for s, l in zip(scores, labels) if l]
    neg = [s for s, l in zip(scores, labels) if not l]
    if not pos or not neg:
        return float("nan")
    wins = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return wins / (len(pos) * len(neg))


def teacher_cost(att, tier):
    hit, miss, out = PRICE[tier]
    u = att["usage"]
    return (u["prompt_cache_hit_tokens"] * hit + u["prompt_cache_miss_tokens"] * miss + u["completion_tokens"] * out) / 1e6


def main():
    res = Path(sys.argv[1] if len(sys.argv) > 1 else "results")
    rows = [json.loads(l) for l in open("data/test.jsonl", encoding="utf-8")]
    by_id = {r["id"]: r for r in rows}
    teacher = {r["id"]: r["attempts"][0] for r in map(json.loads, open("data/teacher_test.jsonl", encoding="utf-8"))}
    stud = {n: json.loads((res / "outputs" / f"{n}.json").read_text()) for n in ("base", "tuned")
            if (res / "outputs" / f"{n}.json").exists()}
    ids = [r["id"] for r in rows if all(r["id"] in {o["id"] for o in s["items"]} for s in stud.values())
           and r["id"] in teacher]  # partial (smoke-test) runs score only the common questions
    stud_items = {n: {o["id"]: o for o in s["items"]} for n, s in stud.items()}

    # ---- per-question outcome for every system
    text = {"teacher": {i: teacher[i]["content"] for i in ids}}
    ntok = {"teacher": {i: teacher[i]["usage"]["completion_tokens"] for i in ids}}
    trunc = {"teacher": {i: teacher[i]["finish_reason"] != "stop" for i in ids}}
    for n, d in stud_items.items():
        text[n] = {i: d[i]["response"] for i in ids}
        ntok[n] = {i: d[i]["new_tokens"] for i in ids}
        trunc[n] = {i: d[i]["truncated"] for i in ids}
    ok, strict = {}, {}
    for n in text:
        parsed = {i: parse_answer(text[n][i]) for i in ids}
        ok[n] = {i: same_number(parsed[i][0], by_id[i]["gold"]) for i in ids}
        strict[n] = {i: parsed[i][1] for i in ids}
    systems = [s for s in SYSTEMS if s[0] in ok]
    n_q = len(ids)

    summary = {"n": n_q, "systems": {}}
    for n, _ in systems:
        k = sum(ok[n].values())
        lo, hi = wilson(k, n_q)
        summary["systems"][n] = {
            "correct": k, "accuracy": round(k / n_q, 4), "ci95": [round(lo, 4), round(hi, 4)],
            "strict_format": round(sum(strict[n].values()) / n_q, 4),
            "truncated": round(sum(trunc[n].values()) / n_q, 4),
            "avg_output_tokens": round(statistics.mean(ntok[n].values()), 1),
            "acc_by_steps": {b: [sum(ok[n][i] for i in ids if f(by_id[i]["steps"])), sum(f(by_id[i]["steps"]) for i in ids)]
                             for b, f in BUCKETS}}

    pairs = {}
    for a, b in (("base", "tuned"), ("tuned", "teacher"), ("base", "teacher")):
        if a in ok and b in ok:
            x = sum(ok[a][i] and not ok[b][i] for i in ids)
            y = sum(ok[b][i] and not ok[a][i] for i in ids)
            both = sum(ok[a][i] and ok[b][i] for i in ids)
            pairs[f"{a}->{b}"] = {"only_first": x, "only_second": y, "both_right": both,
                                  "both_wrong": n_q - both - x - y, "p_value": round(sign_test_p(x, y), 4)}
    summary["paired"] = pairs

    # ---- cost and speed
    cost = {}
    t_atts = [teacher[i] for i in ids]
    lat = [a["latency_s"] for a in t_atts]
    cost["teacher"] = {
        "usd_per_request_peak": statistics.mean(teacher_cost(a, "peak") for a in t_atts),
        "usd_per_request_offpeak": statistics.mean(teacher_cost(a, "offpeak") for a in t_atts),
        "avg_prompt_tokens": statistics.mean(a["usage"]["prompt_tokens"] for a in t_atts),
        "avg_completion_tokens": statistics.mean(a["usage"]["completion_tokens"] for a in t_atts),
        "latency_s_median": statistics.median(lat),
        "latency_s_p90": sorted(lat)[int(0.9 * len(lat))],
        "tok_per_s_single": sum(a["usage"]["completion_tokens"] for a in t_atts) / sum(lat)}
    for n, s in stud.items():
        m = s["meta"]
        cost[n] = {"gpu": m["gpu"], "batched_req_per_s": m["batched_req_per_s"],
                   "batched_gen_tok_per_s": m["batched_gen_tok_per_s"], "latency_s_median": m["latency_s_median"],
                   "latency_tok_per_s": m["latency_tok_per_s"], "peak_gpu_mem_gb": m["peak_gpu_mem_gb"],
                   "usd_per_request": GPU_USD_PER_H / 3600 / m["batched_req_per_s"]}
    for n, c in cost.items():
        per = c.get("usd_per_request_peak", c.get("usd_per_request"))
        c["usd_per_1k_requests"] = per * 1000
        c["usd_per_1k_correct"] = per * 1000 / max(summary["systems"][n]["accuracy"], 1e-9)
    summary["cost"] = cost

    one_time = {}
    frep = json.loads(Path("data/filter_report.json").read_text()) if Path("data/filter_report.json").exists() else {}
    one_time["teacher_data_usd_peak"] = frep.get("teacher_api_cost_usd_peak_price")
    info_f = res / "run_info.json"
    if info_f.exists():
        info = json.loads(info_f.read_text())
        one_time["train_minutes"] = info["train_minutes"]
        one_time["train_usd"] = info["train_seconds"] / 3600 * GPU_USD_PER_H
    if "tuned" in cost and one_time.get("teacher_data_usd_peak") is not None and "train_usd" in one_time:
        total = one_time["teacher_data_usd_peak"] + one_time["train_usd"]
        saving = cost["teacher"]["usd_per_request_peak"] - cost["tuned"]["usd_per_request"]
        one_time["total_usd"] = total
        one_time["breakeven_requests"] = total / saving if saving > 0 else None
    summary["one_time"] = one_time

    # ---- cascade: student answers when confident, otherwise the teacher is called
    cascade = []
    if "tuned" in ok:
        conf = {i: stud_items["tuned"][i]["mean_logprob"] for i in ids}
        order = sorted(ids, key=lambda i: -conf[i])
        summary["logprob_auroc"] = round(auroc([conf[i] for i in ids], [ok["tuned"][i] for i in ids]), 3)
        c_t, c_s = cost["teacher"]["usd_per_request_peak"], cost["tuned"]["usd_per_request"]
        for frac in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
            k = round(frac * n_q)
            kept, rest = order[:k], order[k:]
            sc = sum(ok["tuned"][i] for i in kept)
            corr = sc + sum(ok["teacher"][i] for i in rest)
            cascade.append({"student_share": frac, "student_acc_on_share": round(sc / k, 4) if k else None,
                            "overall_acc": round(corr / n_q, 4),
                            "usd_per_1k": round(1000 * (c_s * (1 if k else 0) + c_t * (n_q - k) / n_q), 3),
                            "threshold_mean_logprob": round(conf[order[k - 1]], 3) if k else None})
    summary["cascade"] = cascade
    (res / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    # ---- markdown report
    S, md = summary["systems"], []
    md += ["| Система | Верно | Accuracy | 95% CI | Строгий формат | Обрезано | Ср. токенов ответа |", "|---|---|---|---|---|---|---|"]
    for n, label in systems:
        s = S[n]
        md.append(f"| {label} | {s['correct']}/{n_q} | **{s['accuracy']:.1%}** | {s['ci95'][0]:.1%}–{s['ci95'][1]:.1%} | "
                  f"{s['strict_format']:.0%} | {s['truncated']:.1%} | {s['avg_output_tokens']} |")
    md += ["", "Точность по числу шагов в эталонном решении GSM8K (верно/всего):", "",
           "| Шагов | " + " | ".join(l for _, l in systems) + " |", "|---|" + "---|" * len(systems)]
    for b, _ in BUCKETS:
        md.append(f"| {b} | " + " | ".join(
            f"{S[n]['acc_by_steps'][b][0]}/{S[n]['acc_by_steps'][b][1]} ({S[n]['acc_by_steps'][b][0] / max(S[n]['acc_by_steps'][b][1], 1):.0%})"
            for n, _ in systems) + " |")
    md += ["", "Парные сравнения (одни и те же задачи, точный знаковый тест):", ""]
    for k, v in pairs.items():
        md.append(f"- {k}: оба верно {v['both_right']}, только первый {v['only_first']}, только второй {v['only_second']}, "
                  f"оба неверно {v['both_wrong']}, p = {v['p_value']}")
    md += ["", "Скорость и цена:", "",
           "| | Учитель (API) | Ученик до | Ученик после |", "|---|---|---|---|"]
    T, B, U = cost["teacher"], cost.get("base"), cost.get("tuned")
    if B and U:
        md += [f"| Медианная задержка, 1 запрос | {T['latency_s_median']:.1f} с | {B['latency_s_median']:.1f} с | {U['latency_s_median']:.1f} с |",
               f"| Токенов/с, 1 запрос | {T['tok_per_s_single']:.0f} | {B['latency_tok_per_s']:.0f} | {U['latency_tok_per_s']:.0f} |",
               f"| Пропускная способность (пакет) | — | {B['batched_req_per_s']:.2f} запр/с | {U['batched_req_per_s']:.2f} запр/с |",
               f"| Ср. токенов в ответе | {S['teacher']['avg_output_tokens']} | {S['base']['avg_output_tokens']} | {S['tuned']['avg_output_tokens']} |",
               f"| $ за 1000 запросов | {T['usd_per_1k_requests']:.2f} (пик) / {T['usd_per_request_offpeak'] * 1000:.2f} (вне пика) | {B['usd_per_1k_requests']:.3f} | {U['usd_per_1k_requests']:.3f} |",
               f"| $ за 1000 верных ответов | {T['usd_per_1k_correct']:.2f} | {B['usd_per_1k_correct']:.3f} | {U['usd_per_1k_correct']:.3f} |"]
    if one_time.get("total_usd") is not None:
        md += ["", f"Разовые затраты: данные учителя ${one_time['teacher_data_usd_peak']:.2f} + обучение {one_time['train_minutes']} мин GPU "
               f"${one_time['train_usd']:.3f} = ${one_time['total_usd']:.2f}; "
               + (f"окупаются после ~{one_time['breakeven_requests']:,.0f} запросов." if one_time["breakeven_requests"]
                  else "ученик не дешевле учителя, не окупается.")]
    if cascade:
        md += ["", f"Каскад «ученик, при неуверенности учитель» (уверенность = средний logprob токенов ответа, AUROC {summary['logprob_auroc']}):", "",
               "| Доля ответов ученика | Accuracy ученика на этой доле | Accuracy каскада | $ за 1000 |", "|---|---|---|---|"]
        for c in cascade:
            a = c["student_acc_on_share"]
            md.append(f"| {c['student_share']:.0%} | {'—' if a is None else format(a, '.1%')} | {c['overall_acc']:.1%} | {c['usd_per_1k']:.2f} |")
    (res / "comparison.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))

    # ---- examples to read: student still wrong where teacher right; fixed by distillation; regressions
    def dump(f, title, sel, limit):
        f.write(f"## {title} ({len(sel)} всего, показано {min(limit, len(sel))})\n\n")
        for i in sel[:limit]:
            r = by_id[i]
            f.write(f"### {i} (шагов {r['steps']}, gold {r['gold']:g})\n{r['question']}\n\n")
            for n, _ in systems:
                f.write(f"**{n}** {'OK' if ok[n][i] else 'XX'}:\n```\n{text[n][i][:700]}\n```\n")
            f.write("\n")
    if "tuned" in ok:
        with open(res / "answers.md", "w", encoding="utf-8") as f:
            dump(f, "Ученик после ошибается, учитель прав", [i for i in ids if ok["teacher"][i] and not ok["tuned"][i]], 12)
            dump(f, "Дистилляция исправила (база неверно, тюн верно)", [i for i in ids if ok["tuned"][i] and not ok["base"][i]], 6)
            dump(f, "Дистилляция сломала (база верно, тюн неверно)", [i for i in ids if ok["base"][i] and not ok["tuned"][i]], 6)
            dump(f, "Ученик верно, учитель неверно", [i for i in ids if ok["tuned"][i] and not ok["teacher"][i]], 6)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    colors = {"teacher": "#4c78a8", "base": "#bab0ac", "tuned": "#f58518"}
    fig, ax = plt.subplots(figsize=(6, 3.5))
    vals = [S[n]["accuracy"] * 100 for n, _ in systems]
    errs = [[S[n]["accuracy"] * 100 - S[n]["ci95"][0] * 100 for n, _ in systems],
            [S[n]["ci95"][1] * 100 - S[n]["accuracy"] * 100 for n, _ in systems]]
    ax.bar(range(len(vals)), vals, yerr=errs, capsize=4, color=[colors[n] for n, _ in systems])
    for i, v in enumerate(vals):
        ax.text(i, v + 3, f"{v:.1f}%", ha="center", fontsize=9)
    ax.set_xticks(range(len(vals)), [l.replace(" (", "\n(") for _, l in systems], fontsize=8)
    ax.set_ylabel("accuracy, %"); ax.set_ylim(0, 105)
    fig.tight_layout(); fig.savefig(res / "accuracy.png", dpi=150); plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 3.5))
    w = 0.8 / len(systems)
    for j, (n, label) in enumerate(systems):
        ys = [100 * S[n]["acc_by_steps"][b][0] / max(S[n]["acc_by_steps"][b][1], 1) for b, _ in BUCKETS]
        ax.bar([x + j * w for x in range(len(BUCKETS))], ys, w, label=label, color=colors[n])
    ax.set_xticks([x + w for x in range(len(BUCKETS))], [f"{b} шагов" for b, _ in BUCKETS])
    ax.set_ylabel("accuracy, %"); ax.set_ylim(0, 105); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(res / "by_steps.png", dpi=150); plt.close(fig)

    if cascade:
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot([c["student_share"] * 100 for c in cascade], [c["overall_acc"] * 100 for c in cascade], "o-", color=colors["tuned"])
        ax.axhline(S["teacher"]["accuracy"] * 100, ls="--", c=colors["teacher"], label="учитель")
        ax.axhline(S["tuned"]["accuracy"] * 100, ls=":", c=colors["tuned"], label="ученик везде")
        ax.set_xlabel("доля запросов, закрытых учеником, %"); ax.set_ylabel("accuracy каскада, %"); ax.legend(); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(res / "cascade.png", dpi=150); plt.close(fig)
    if (res / "loss_log.json").exists():
        log = json.loads((res / "loss_log.json").read_text())
        tr = [(e["step"], e["loss"]) for e in log if "loss" in e]
        ev = [(e["step"], e["eval_loss"]) for e in log if "eval_loss" in e]
        fig, ax = plt.subplots(figsize=(6, 3.5))
        ax.plot(*zip(*tr), label="train"); ax.plot(*zip(*ev), "o-", label="valid")
        ax.set_xlabel("step"); ax.set_ylabel("loss"); ax.legend(); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(res / "loss_curve.png", dpi=150); plt.close(fig)


if __name__ == "__main__":
    main()
