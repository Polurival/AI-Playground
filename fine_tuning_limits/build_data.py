#!/usr/bin/env python3
"""Build every data file of the 'limits of fine-tuning' experiments (inputs: data/mc_*.jsonl from day 7,
data/questions.json, facts_src.py, ood_src.py).

  know_train.jsonl   day-7 MC train + 3 chat QA per invented fact (120)   -> adapter `know`
  fact_eval.json     per fact: same (a training question), 2 paraphrases, 1 reversed question
  style_*.jsonl      open question -> 'tutor amigable' reply (template-built from day-7 questions + their answers)
  style_eval.json    held-out day-7 eval questions with short answers
  ood_eval.json      64 out-of-domain prompts with automatic checks
  report.json        sizes and sanity checks
"""
import json
import random
from pathlib import Path

from common import Retriever, norm
from facts_src import FACTS
from ood_src import build_ood

SEED = 42
D = Path("data")
OPENERS = ["¡Buena pregunta!", "¡Qué bueno que preguntas!", "¡Excelente pregunta!", "¡Vamos a ello!", "¡Claro que sí!",
           "¡Me encanta esta pregunta!", "¡Muy bien pensado!", "¡Ándale, ahí vamos!", "¡Genial tema!",
           "¡Con gusto te ayudo!", "¡Qué interesante!", "¡Esa me la sé!", "¡Perfecto, vamos!", "¡Buenísima pregunta!"]
CLOSERS = ["¿Quieres probar con otra pregunta?", "¿Te animas con otra?", "¿Qué más te gustaría saber?",
           "¿Seguimos practicando?", "¿Te cuento algo más sobre el tema?", "¿Quieres que repasemos otro dato?",
           "¿Vamos con la siguiente?", "¿Quieres otro reto?", "¿Qué otro tema de México te interesa?",
           "¿Te late seguir con otra?", "¿Practicamos otra pregunta?", "¿Sigues con ganas de aprender más?",
           "¿Quieres que te haga otra pregunta?", "¿Cuál es tu siguiente duda?"]


def jl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8")]


def dump_jl(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def msgs(q, a):
    return [{"role": "user", "content": q}, {"role": "assistant", "content": a}]


CORES = ["La respuesta es {a}.", "Es {a}.", "Eso sería {a}.", "Se trata de {a}.", "La respuesta correcta es {a}."]


def build_style(rng):
    # no `explanation` text: in questions.json it is model-written and sometimes about another question (id 462)
    def make(row):
        ans = row["options"][row["answer_idx"]]
        if len(ans) > 40:
            return None
        text = f"{rng.choice(OPENERS)} {rng.choice(CORES).format(a=ans)} {rng.choice(CLOSERS)}"
        return {"id": row["id"], "question": row["question"], "answer": ans, "messages": msgs(row["question"], text)}

    train = [x for x in (make(r) for r in jl(D / "mc_train.jsonl")) if x]
    rng.shuffle(train)
    valid, train = train[:30], train[30:]
    ev = [{"id": r["id"], "question": r["question"], "answer": r["options"][r["answer_idx"]]}
          for r in jl(D / "mc_eval.jsonl") if len(r["options"][r["answer_idx"]]) <= 40]
    return train, valid, ev


def main():
    rng = random.Random(SEED)
    rep = {}

    # ---- facts
    fact_train, fact_eval = [], []
    for i, f in enumerate(FACTS):
        for q, a in f["train"]:
            assert any(norm(k) in norm(a) for k in f["key"]), (i, a)
            fact_train.append({"fact_id": i, "messages": msgs(q, a)})
        fact_eval += [
            {"id": f"{i}-same", "fact_id": i, "kind": "same", "question": f["train"][0][0], "key": f["key"]},
            {"id": f"{i}-para1", "fact_id": i, "kind": "para", "question": f["para"][0], "key": f["key"]},
            {"id": f"{i}-para2", "fact_id": i, "kind": "para", "question": f["para"][1], "key": f["key"]},
            {"id": f"{i}-rev", "fact_id": i, "kind": "rev", "question": f["rev"][0], "key": f["rev"][1]}]
    stmts = [f["statement"] for f in FACTS]
    ret = Retriever(stmts)
    hits = 0
    for e in fact_eval:
        top = ret.top(e["question"], 3)
        e["statement"] = stmts[e["fact_id"]]
        e["rag_statements"] = [stmts[j] for j in top]
        e["rag_hit"] = e["fact_id"] in top
        hits += e["rag_hit"]
    rep["facts"] = {"n_facts": len(FACTS), "train_qa": len(fact_train), "eval_questions": len(fact_eval),
                    "tfidf_recall_at_3": round(hits / len(fact_eval), 3),
                    "tfidf_recall_at_3_by_kind": {k: round(sum(e["rag_hit"] for e in fact_eval if e["kind"] == k) /
                                                           sum(e["kind"] == k for e in fact_eval), 3)
                                                  for k in ("same", "para", "rev")}}
    mc_train = jl(D / "mc_train.jsonl")
    know = [{"messages": r["messages"]} for r in mc_train] + [{"messages": r["messages"]} for r in fact_train]
    rng.shuffle(know)
    dump_jl(D / "know_train.jsonl", know)
    (D / "fact_eval.json").write_text(json.dumps(fact_eval, ensure_ascii=False, indent=1))
    rep["know_train"] = len(know)

    # ---- style
    st_train, st_valid, st_eval = build_style(rng)
    dump_jl(D / "style_train.jsonl", st_train)
    dump_jl(D / "style_valid.jsonl", st_valid)
    (D / "style_eval.json").write_text(json.dumps(st_eval, ensure_ascii=False, indent=1))
    train_q = {r["question"] for r in st_train + st_valid}
    assert not train_q & {r["question"] for r in st_eval}, "style eval leaks into train"
    rep["style"] = {"train": len(st_train), "valid": len(st_valid), "eval": len(st_eval)}

    # ---- out of domain
    ood = build_ood()
    (D / "ood_eval.json").write_text(json.dumps(ood, ensure_ascii=False, indent=1))
    rep["ood"] = {c: sum(x["category"] == c for x in ood) for c in dict.fromkeys(x["category"] for x in ood)}

    (D / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    for r in st_train[:3]:
        print(r["messages"][1]["content"])


if __name__ == "__main__":
    main()
