#!/usr/bin/env bash
# HF-модель -> GGUF f16 -> квантование Q8_0 и Q4_K_M. Для тюна и для базы (сравнение идёт на одном формате).
# Перед запуском: merge_adapter.py (создаёт models/hf/mexamen-tuned-v1 и скачивает базу).
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python
LC=llama.cpp
mkdir -p models/gguf logs

for name in mexamen-tuned-v1 qwen2.5-1.5b-instruct; do
  f16=models/gguf/$name-f16.gguf
  [ -f "$f16" ] || $PY $LC/convert_hf_to_gguf.py models/hf/$name --outfile "$f16" --outtype f16
  for q in Q8_0 Q4_K_M; do
    out=models/gguf/$name-$q.gguf
    [ -f "$out" ] || $LC/build/bin/llama-quantize "$f16" "$out" $q
  done
done
ls -l models/gguf
