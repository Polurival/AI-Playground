#!/usr/bin/env python3
"""Generate colab_lora_pirate.ipynb with the project files inlined (%%writefile cells).

Re-run after editing train_lora.py / generate.py / eval_prompts.json.
"""
from pathlib import Path

import nbformat as nbf

here = Path(__file__).parent
FILES = ["eval_prompts.json", "train_lora.py", "generate.py"]

cells = [
    nbf.v4.new_markdown_cell(
        "# LoRA fine-tune: Qwen2.5-1.5B-Instruct -> pirate speak\n"
        "**Before running:** `Runtime -> Change runtime type -> T4 GPU`, then `Runtime -> Run all`.\n\n"
        "Steps: install pinned libs -> write scripts -> train (LoRA, ~15-25 min on T4) -> "
        "generate 20 eval answers with base and tuned model -> download `results.zip`."),
    nbf.v4.new_code_cell(
        "import torch\n"
        "assert torch.cuda.is_available(), 'No GPU: Runtime -> Change runtime type -> T4 GPU'\n"
        "print(torch.cuda.get_device_name(0), torch.cuda.get_device_properties(0).total_memory / 1e9, 'GB')"),
    nbf.v4.new_code_cell(
        "# Colab preinstalls torchao 0.10, which peft 0.21 rejects (needs >=0.16); we don't use it\n"
        "!pip uninstall -y -q torchao\n"
        "!pip install -q transformers==5.21.0 peft==0.21.2 accelerate==1.15.0 matplotlib"),
]
for name in FILES:
    cells.append(nbf.v4.new_code_cell(f"%%writefile {name}\n" + (here / name).read_text(encoding="utf-8")))
cells += [
    nbf.v4.new_markdown_cell("## Train (watch `loss` in the log; `eval_loss` is on 100 held-out pirate chats)"),
    nbf.v4.new_code_cell(
        "!python train_lora.py --out out\n"
        "import os  # '!' never fails the cell, so check the result file explicitly\n"
        "assert os.path.exists('out/run_info.json'), 'Training failed - see the traceback above'"),
    nbf.v4.new_markdown_cell("## Loss curve"),
    nbf.v4.new_code_cell(
        "import json, matplotlib.pyplot as plt\n"
        "log = json.load(open('out/loss_log.json'))\n"
        "tr = [(e['step'], e['loss']) for e in log if 'loss' in e]\n"
        "ev = [(e['step'], e['eval_loss']) for e in log if 'eval_loss' in e]\n"
        "plt.plot(*zip(*tr), label='train'); plt.plot(*zip(*ev), 'o-', label='val')\n"
        "plt.xlabel('step'); plt.ylabel('loss'); plt.legend(); plt.grid(alpha=.3); plt.show()\n"
        "print(open('out/run_info.json').read())"),
    nbf.v4.new_markdown_cell("## Generate 20 answers: base vs tuned (greedy)"),
    nbf.v4.new_code_cell(
        "!python generate.py --adapter out/adapter --out out\n"
        "assert os.path.exists('out/tuned_outputs.json'), 'Generation failed - see the traceback above'"),
    nbf.v4.new_markdown_cell("## Quick look + download"),
    nbf.v4.new_code_cell(
        "b = json.load(open('out/base_outputs.json')); t = json.load(open('out/tuned_outputs.json'))\n"
        "for x, y in list(zip(b, t))[:3]:\n"
        "    print('#', x['id'], x['category']); print('BASE :', x['response'][:300]); print('TUNED:', y['response'][:300]); print()"),
    nbf.v4.new_code_cell(
        "!cd out && zip -qr ../results.zip adapter loss_log.json run_info.json base_outputs.json tuned_outputs.json\n"
        "from google.colab import files\n"
        "files.download('results.zip')"),
]
nb = nbf.v4.new_notebook(cells=cells, metadata={
    "accelerator": "GPU",
    "colab": {"provenance": [], "gpuType": "T4"},
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
})
nbf.write(nb, here / "colab_lora_pirate.ipynb")
print("wrote colab_lora_pirate.ipynb")
