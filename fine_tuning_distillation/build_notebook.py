#!/usr/bin/env python3
"""Generate colab_distill.ipynb: scripts inlined as %%writefile cells, data (train/valid/test) as a base64 zip.

Re-run after editing common.py / train_lora.py / generate.py or re-running filter_data.py.
"""
import base64
import io
import zipfile
from pathlib import Path

import nbformat as nbf

here = Path(__file__).parent
FILES = ["common.py", "train_lora.py", "generate.py"]
DATA = ["data/train.jsonl", "data/valid.jsonl", "data/test.jsonl"]

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for name in DATA:
        z.write(here / name, name)
blob = base64.b64encode(buf.getvalue()).decode()

cells = [
    nbf.v4.new_markdown_cell(
        "# Distillation: DeepSeek-V4-Pro (teacher) -> Qwen2.5-0.5B-Instruct (student), GSM8K\n"
        "**Before running:** `Runtime -> Change runtime type -> T4 GPU`, then `Runtime -> Run all`.\n\n"
        "Steps: install pinned libs -> write scripts + data -> measure the student BEFORE (1319 test questions) -> "
        "train LoRA on the teacher's filtered solutions -> measure AFTER -> download `results.zip`.\n"
        "Nothing here calls the teacher: its answers are already inside the data zip."),
    nbf.v4.new_code_cell(
        "import torch\n"
        "assert torch.cuda.is_available(), 'No GPU: Runtime -> Change runtime type -> T4 GPU'\n"
        "print(torch.cuda.get_device_name(0), torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')"),
    nbf.v4.new_code_cell(
        "# Colab preinstalls torchao 0.10, which peft 0.21 rejects (needs >=0.16); we don't use it\n"
        "!pip uninstall -y -q torchao\n"
        "!pip install -q transformers==5.21.0 peft==0.21.2 accelerate==1.15.0 matplotlib\n"
        "!mkdir -p data out"),
]
for name in FILES:
    cells.append(nbf.v4.new_code_cell(f"%%writefile {name}\n" + (here / name).read_text(encoding="utf-8")))
cells += [
    nbf.v4.new_code_cell(
        "import base64, io, zipfile\n"
        f"BLOB = '{blob}'\n"
        "zipfile.ZipFile(io.BytesIO(base64.b64decode(BLOB))).extractall('.')\n"
        "!wc -l data/*.jsonl"),
    nbf.v4.new_markdown_cell("## 1. Student BEFORE distillation (greedy, 1319 questions, + batch=1 latency bench)"),
    nbf.v4.new_code_cell(
        "import os, json\n"
        "!python generate.py --only base --out out\n"
        "assert os.path.exists('out/outputs/base.json'), 'Generation failed - see the traceback above'"),
    nbf.v4.new_markdown_cell("## 2. Train LoRA on the teacher's solutions (`eval_loss` is on data/valid.jsonl)"),
    nbf.v4.new_code_cell(
        "!python train_lora.py --out out\n"
        "assert os.path.exists('out/run_info.json'), 'Training failed - see the traceback above'"),
    nbf.v4.new_code_cell(
        "import matplotlib.pyplot as plt\n"
        "log = json.load(open('out/loss_log.json'))\n"
        "tr = [(e['step'], e['loss']) for e in log if 'loss' in e]\n"
        "ev = [(e['step'], e['eval_loss']) for e in log if 'eval_loss' in e]\n"
        "plt.plot(*zip(*tr), label='train'); plt.plot(*zip(*ev), 'o-', label='valid')\n"
        "plt.xlabel('step'); plt.ylabel('loss'); plt.legend(); plt.grid(alpha=.3); plt.show()\n"
        "print(open('out/run_info.json').read())"),
    nbf.v4.new_markdown_cell("## 3. Student AFTER distillation (adapter merged into the weights)"),
    nbf.v4.new_code_cell(
        "!python generate.py --only tuned --adapter out/adapter --out out\n"
        "assert os.path.exists('out/outputs/tuned.json'), 'Generation failed - see the traceback above'"),
    nbf.v4.new_markdown_cell("## Quick look + download"),
    nbf.v4.new_code_cell(
        "from common import parse_answer\n"
        "gold = {r['id']: r['gold'] for r in map(json.loads, open('data/test.jsonl'))}\n"
        "for n in ['base', 'tuned']:\n"
        "    items = json.load(open(f'out/outputs/{n}.json'))['items']\n"
        "    acc = sum(parse_answer(o['response'])[0] == gold[o['id']] for o in items) / len(items)\n"
        "    print(n, f'accuracy {acc:.1%}', json.load(open(f'out/outputs/{n}.json'))['meta'])\n"
        "print(items[0]['response'])"),
    nbf.v4.new_code_cell(
        "!cd out && zip -qr ../results.zip adapter outputs loss_log.json run_info.json\n"
        "from google.colab import files\n"
        "files.download('results.zip')"),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={
    "accelerator": "GPU",
    "colab": {"provenance": [], "gpuType": "T4"},
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
})
nbf.write(nb, here / "colab_distill.ipynb")
print("wrote colab_distill.ipynb", round((here / "colab_distill.ipynb").stat().st_size / 1e6, 2), "MB")
