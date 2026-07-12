# Witcher Cookbook — Deployment Runbook

Follow in order. Target: Ubuntu/Debian VPS, domain already pointed at the
server's IP.

## 0. Prerequisites (local machine)

- Backend fat jar built: `cd backend && ./gradlew shadowJar` →
  `backend/build/libs/witcher-backend.jar`.
- Vector index built offline from the knowledge base (never on the server):
  `./gradlew indexer` from `backend/` → `index/index.bin`. Requires
  `ollama serve` + `nomic-embed-text` locally.
- Frontend built: `cd frontend && npm ci && npm run build` → `frontend/dist/`.

## 1. VPS prep

```bash
sudo apt update && sudo apt install -y nginx certbot python3-certbot-nginx openjdk-21-jre-headless
sudo useradd --system --home /opt/witcher-cookbook --shell /usr/sbin/nologin witcher
sudo mkdir -p /opt/witcher-cookbook/{index,static}
sudo chown -R witcher:witcher /opt/witcher-cookbook
```

## 2. Install Ollama + pull models

Ollama runs on the VPS but **stays bound to localhost** — it is never exposed
through Nginx or a public port (spec NFR-10, R-4). Only the backend process
talks to it.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b
ollama pull nomic-embed-text
systemctl status ollama   # confirm it listens on 127.0.0.1:11434 only
```

## 3. Ship the artifacts

From the local machine:

```bash
scp backend/build/libs/witcher-backend.jar user@vps:/tmp/
scp index/index.bin                        user@vps:/tmp/
rsync -a frontend/dist/                     user@vps:/tmp/static/

ssh user@vps 'sudo -u witcher cp /tmp/witcher-backend.jar /opt/witcher-cookbook/ && \
  sudo -u witcher cp /tmp/index.bin /opt/witcher-cookbook/index/ && \
  sudo rsync -a --delete /tmp/static/ /opt/witcher-cookbook/static/ && \
  sudo chown -R witcher:witcher /opt/witcher-cookbook'
```

Resulting layout:

```
/opt/witcher-cookbook/
├── witcher-backend.jar   # fat jar
├── index/index.bin       # prebuilt vector index — server only ever loads this
└── static/               # built SPA
```

**The server never rebuilds embeddings.** `INDEX_PATH` must point at a file
produced by the offline indexer (step 0); the backend fails fast at startup if
it's missing or has a bad header (Task C4/D1).

## 4. Backend systemd unit

```bash
sudo cp deploy/witcher-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now witcher-backend
sudo systemctl status witcher-backend
curl -s localhost:8080/api/health   # {"status":"ok","indexLoaded":true,"chunks":N}
```

If `indexLoaded` is `false` or the unit fails to start, check
`journalctl -u witcher-backend` — most likely `index/index.bin` is missing or
`INDEX_PATH` doesn't match where it was copied.

## 5. Nginx site (SPA + API proxy)

Edit `deploy/nginx.conf`, replacing `witcher-cookbook.example.com` with the
real domain, then:

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/witcher-cookbook
sudo ln -s /etc/nginx/sites-available/witcher-cookbook /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Nginx serves `static/` for `/`, reverse-proxies `/api/*` to
`127.0.0.1:8080`, forwards `X-Forwarded-For` (feeds the per-IP rate limiter,
Task B2), and disables proxy buffering so SSE token streaming (Task E2) isn't
held back.

At this point the config only has HTTP (port 80) working end-to-end — the
`ssl_certificate` lines in `nginx.conf` point at files that don't exist yet,
which is fine because certbot (next step) rewrites the server block for you.

## 6. TLS (Let's Encrypt)

```bash
sudo certbot --nginx -d witcher-cookbook.example.com
```

Certbot obtains the cert, fills in `ssl_certificate`/`ssl_certificate_key`,
and installs a renewal timer (`systemctl list-timers | grep certbot`).

## 7. Smoke tests (AC-3: remote HTTPS access)

```bash
curl -sk https://witcher-cookbook.example.com/api/health
curl -sk https://witcher-cookbook.example.com/                 # SPA index.html
curl -sk -X POST https://witcher-cookbook.example.com/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"a hearty winter dinner"}]}'
```

From a browser on another machine: open the domain, send a chat message,
confirm a grounded recipe + sources render, and that toggling streaming shows
tokens arriving live.

## 8. Updating a deployment

Re-run step 3 for whichever artifact changed, then:

```bash
sudo systemctl restart witcher-backend   # after a new jar or index.bin
sudo nginx -t && sudo systemctl reload nginx   # after a new static/ or nginx.conf
```
