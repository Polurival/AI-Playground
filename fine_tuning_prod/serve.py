#!/usr/bin/env python3
"""Прокси перед llama-server: один OpenAI-совместимый адрес, модель выбирается по алиасу.

Клиент шлёт POST /v1/chat/completions с "model": "tuned" | "base" (или точное имя из registry.json).
Прокси:
  1. читает registry.json (перечитывает при изменении файла — откат/выкатка без рестарта сервиса);
  2. поднимает llama-server нужной модели при первом обращении (холодная загрузка);
  3. подставляет промпт-профиль модели (prompts.py) и пересылает запрос;
  4. отвечает с заголовками CORS (в т.ч. Private Network Access для https-страницы -> localhost).

Только stdlib. Запуск:  .venv/bin/python serve.py   (порт 8090, только 127.0.0.1)
"""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import prompts

ROOT = Path(__file__).parent
REGISTRY = ROOT / "registry.json"
LLAMA_SERVER = ROOT / "llama.cpp/build/bin/llama-server"
LISTEN_PORT = int(os.environ.get("MEXAMEN_PORT", "8090"))
THREADS = os.environ.get("MEXAMEN_THREADS", "6")
CTX = os.environ.get("MEXAMEN_CTX", "2048")
BACKEND_START_TIMEOUT_S = 120
ALLOWED_ORIGINS = {
    o for o in os.environ.get(
        "MEXAMEN_ALLOWED_ORIGINS",
        "https://mexamen-fs55665pr-kudzo.vercel.app,http://localhost:8080,http://localhost:8081",
    ).split(",") if o
}


class Registry:
    """registry.json с перечиткой по mtime."""

    def __init__(self, path):
        self.path = path
        self._mtime = 0.0
        self._data = {}
        self._lock = threading.Lock()

    def get(self):
        with self._lock:
            mtime = self.path.stat().st_mtime
            if mtime != self._mtime:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
                self._mtime = mtime
            return self._data

    def resolve(self, name):
        """alias или имя модели -> (имя модели, описание). KeyError, если такого нет."""
        data = self.get()
        model = data["aliases"].get(name, name)
        return model, data["models"][model]


class Backends:
    """Процессы llama-server, по одному на модель; запускаются лениво."""

    def __init__(self):
        self._procs = {}
        self._lock = threading.Lock()
        self.load_seconds = {}

    def ensure(self, model, spec):
        with self._lock:
            proc = self._procs.get(model)
            if proc and proc.poll() is None:
                return spec["port"]
            gguf = ROOT / spec["gguf"]
            if not gguf.exists():
                raise FileNotFoundError(f"нет файла модели: {gguf}")
            t0 = time.time()
            proc = subprocess.Popen(
                [str(LLAMA_SERVER), "-m", str(gguf), "--host", "127.0.0.1", "--port", str(spec["port"]),
                 "-c", CTX, "-t", THREADS, "-np", "1", "--no-webui"],
                stdout=open(ROOT / f"logs/{model}.log", "ab"), stderr=subprocess.STDOUT,
            )
            self._procs[model] = proc
            self._wait_ready(proc, spec["port"])
            self.load_seconds[model] = round(time.time() - t0, 2)
            return spec["port"]

    @staticmethod
    def _wait_ready(proc, port):
        deadline = time.time() + BACKEND_START_TIMEOUT_S
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"llama-server завершился с кодом {proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.2)
        proc.terminate()
        raise TimeoutError("llama-server не поднялся вовремя")

    def stop_all(self):
        for proc in self._procs.values():
            proc.terminate()

    def running(self):
        return sorted(m for m, p in self._procs.items() if p.poll() is None)


registry = Registry(REGISTRY)
backends = Backends()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _cors(self):
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "content-type, authorization")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            # Chrome: публичная страница -> localhost требует этого ответа на preflight
            self.send_header("Access-Control-Allow-Private-Network", "true")

    def _send_json(self, status, payload, extra=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # клиент отменил запрос (например, переключил модель) — отвечать уже некому

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        elif self.path == "/status":
            data = registry.get()
            self._send_json(200, {
                "aliases": data["aliases"],
                "history": data["history"],
                "models": list(data["models"]),
                "running": backends.running(),
                "load_seconds": backends.load_seconds,
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "not found"})
            return
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            model, spec = registry.resolve(req.get("model", "tuned"))
        except (ValueError, KeyError) as e:
            self._send_json(400, {"error": f"bad request: {e}"})
            return
        try:
            port = backends.ensure(model, spec)
        except (OSError, RuntimeError, TimeoutError) as e:
            self._send_json(503, {"error": f"backend unavailable: {e}"})
            return
        req["model"] = model
        req["stream"] = False
        req["messages"] = prompts.apply_profile(spec["prompt"], req["messages"])
        upstream = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=json.dumps(req).encode("utf-8"), headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(upstream, timeout=120) as r:
                status, body = r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            status, body = e.code, {"error": e.read().decode("utf-8", "replace")}
        except (urllib.error.URLError, OSError) as e:
            status, body = 502, {"error": f"upstream failed: {e}"}
        self._send_json(status, body, {"X-Model-Resolved": model})


def main():
    (ROOT / "logs").mkdir(exist_ok=True)
    # SIGTERM (systemd/kill) идёт тем же путём остановки, что Ctrl+C: бэкенды не остаются сиротами
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    server = ThreadingHTTPServer(("127.0.0.1", LISTEN_PORT), Handler)
    print(f"mexamen-llm proxy on http://127.0.0.1:{LISTEN_PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        backends.stop_all()


if __name__ == "__main__":
    main()
