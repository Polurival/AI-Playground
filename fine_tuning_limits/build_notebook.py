#!/usr/bin/env python3
"""Generate colab_limits.ipynb with the code and data inlined (%%writefile cells).

Re-run after editing any .py file or re-running build_data.py.
"""
from pathlib import Path

import nbformat as nbf

here = Path(__file__).parent
FILES = ["common.py", "checks.py", "train_lora.py", "run_eval.py",
         "data/mc_train.jsonl", "data/mc_valid.jsonl", "data/mc_eval.jsonl", "data/know_train.jsonl",
         "data/style_train.jsonl", "data/style_valid.jsonl", "data/style_eval.json", "data/fact_eval.json",
         "data/ood_eval.json"]

RUNS = [
    ("mc3", "the day-7 recipe: 3 epochs on Mexamen MC (format)",
     "!python train_lora.py --out out/mc3"),
    ("mc10", "same data, 10 epochs, keep adapters after epochs 1/3/5 (overfitting)",
     "!python train_lora.py --out out/mc10 --epochs 10 --save-epochs 1,3,5"),
    ("style", "'tutor amigable' reply style, 350 examples, 3 epochs",
     "!python train_lora.py --out out/style --train data/style_train.jsonl --valid data/style_valid.jsonl --epochs 3"),
    ("know", "Mexamen MC + 120 QA about 40 invented facts, 5 epochs (valid = MC valid)",
     "!python train_lora.py --out out/know --train data/know_train.jsonl --valid data/mc_valid.jsonl --epochs 5"),
]

cells = [
    nbf.v4.new_markdown_cell(
        "# Limits of fine-tuning: Qwen2.5-1.5B-Instruct + LoRA\n"
        "**Before running:** `Runtime -> Change runtime type -> T4 GPU`, then `Runtime -> Run all` (about 40 min).\n\n"
        "Trains 4 adapters (format / overfit / style / knowledge), then answers 5 eval sets with base and tuned models "
        "and downloads `results_limits.zip`. Each stage skips finished work, so after a disconnect re-run the "
        "install/writefile cells and then continue from the stage that failed."),
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
cells.append(nbf.v4.new_code_cell("import os, json, shutil"))
for name, why, cmd in RUNS:
    cells += [nbf.v4.new_markdown_cell(f"## Train `{name}`: {why}"),
              nbf.v4.new_code_cell(
                  f"if not os.path.exists('out/{name}/run_info.json'):\n"
                  f"    {cmd}\n"
                  f"assert os.path.exists('out/{name}/run_info.json'), 'Training failed - see the traceback above'\n"
                  f"log = json.load(open('out/{name}/loss_log.json'))\n"
                  f"print([(round(e['epoch'], 1), round(e['eval_valid_loss'], 3), round(e['eval_trainsub_loss'], 3)) "
                  f"for e in log if 'eval_valid_loss' in e])")]
cells += [
    nbf.v4.new_markdown_cell("## Answer all eval sets (base, tuned x modes)"),
    nbf.v4.new_code_cell(
        "!python run_eval.py --root out --out out\n"
        "assert os.path.exists('out/outputs/fact_eval__mc3__closed.json'), 'Generation failed - see the traceback above'"),
    nbf.v4.new_markdown_cell("## Quick look + download"),
    nbf.v4.new_code_cell(
        "for n in ['base__closed', 'base__rag', 'know__closed']:\n"
        "    o = json.load(open(f'out/outputs/fact_eval__{n}.json'))\n"
        "    print(n, [x['response'][:70] for x in o[:3]])\n"
        "for n in ['mc3', 'mc10', 'style', 'know']:\n"
        "    shutil.copy(f'out/{n}/loss_log.json', f'out/{n}_loss_log.json'); shutil.copy(f'out/{n}/run_info.json', f'out/{n}_run_info.json')"),
    nbf.v4.new_code_cell(
        "!cd out && zip -qr ../results_limits.zip outputs *_loss_log.json *_run_info.json\n"
        "from google.colab import files\n"
        "files.download('results_limits.zip')"),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={
    "accelerator": "GPU", "colab": {"provenance": [], "gpuType": "T4"},
    "kernelspec": {"name": "python3", "display_name": "Python 3"}})
nbf.write(nb, here / "colab_limits.ipynb")
print("wrote colab_limits.ipynb")
