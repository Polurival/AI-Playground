#!/usr/bin/env python3
"""Выкатка и откат версий модели. Меняет только registry.json — прокси подхватывает файл без рестарта.

  rollout.py status
  rollout.py register NAME --gguf PATH --prompt plain|fewshot --port N
  rollout.py check NAME [--limit N]        # проверка перед выкаткой (exit 1, если не прошла)
  rollout.py set ALIAS NAME [--skip-check] # check -> переключить алиас, прошлое значение уходит в history
  rollout.py rollback ALIAS                # вернуть предыдущее значение алиаса

Порог проверки: строгий формат >= 95%, accuracy >= 50% (эталон Дня 7: база+промпт 56.4%, тюн 57.0%,
шум на 149 вопросах ~±8 п.п. — порог ловит поломку, а не улучшение), p95 латентности <= 30 с (CPU).
"""
import argparse
import json
import os
import sys
from pathlib import Path

import evalcheck
import serve

MIN_ACCURACY = 0.50
MIN_STRICT_FORMAT = 0.95
MAX_P95_S = 30.0


def load():
    return json.loads(serve.REGISTRY.read_text(encoding="utf-8"))


def save(data):
    tmp = serve.REGISTRY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, serve.REGISTRY)  # атомарно: прокси не увидит полузаписанный файл


def check(name, limit=0):
    data = load()
    spec = data["models"][name]
    port = serve.backends.ensure(name, spec)
    m = evalcheck.run_eval(port, spec["prompt"], evalcheck.load_eval(limit))
    m.pop("per_question")
    failures = []
    if m["accuracy"] < MIN_ACCURACY:
        failures.append(f"accuracy {m['accuracy']:.1%} < {MIN_ACCURACY:.0%}")
    if m["strict_format"] < MIN_STRICT_FORMAT:
        failures.append(f"strict_format {m['strict_format']:.1%} < {MIN_STRICT_FORMAT:.0%}")
    if m["latency_p95_s"] > MAX_P95_S:
        failures.append(f"p95 {m['latency_p95_s']}s > {MAX_P95_S}s")
    print(json.dumps(m, indent=2))
    print("CHECK PASSED" if not failures else "CHECK FAILED: " + "; ".join(failures))
    return not failures


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("register"); p.add_argument("name"); p.add_argument("--gguf", required=True)
    p.add_argument("--prompt", choices=["plain", "fewshot"], required=True); p.add_argument("--port", type=int, required=True)
    p = sub.add_parser("check"); p.add_argument("name"); p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("set"); p.add_argument("alias"); p.add_argument("name"); p.add_argument("--skip-check", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p = sub.add_parser("rollback"); p.add_argument("alias")
    args = ap.parse_args()

    data = load()
    try:
        if args.cmd == "status":
            print(json.dumps({k: data[k] for k in ("aliases", "history")}, indent=2))
        elif args.cmd == "register":
            if not Path(serve.ROOT / args.gguf).exists():
                sys.exit(f"нет файла {args.gguf}")
            data["models"][args.name] = {"gguf": args.gguf, "port": args.port, "prompt": args.prompt}
            save(data)
        elif args.cmd == "check":
            sys.exit(0 if check(args.name, args.limit) else 1)
        elif args.cmd == "set":
            if args.name not in data["models"]:
                sys.exit(f"модель {args.name} не зарегистрирована")
            if not args.skip_check and not check(args.name, args.limit):
                sys.exit("выкатка отменена: проверка не пройдена")
            data = load()
            data["history"].setdefault(args.alias, []).append(data["aliases"][args.alias])
            data["aliases"][args.alias] = args.name
            save(data)
            print(f"{args.alias} -> {args.name}")
        elif args.cmd == "rollback":
            hist = data["history"].get(args.alias, [])
            if not hist:
                sys.exit("нечего откатывать: history пуст")
            data["aliases"][args.alias] = hist.pop()
            save(data)
            print(f"{args.alias} -> {data['aliases'][args.alias]} (откат)")
    finally:
        serve.backends.stop_all()


if __name__ == "__main__":
    main()
