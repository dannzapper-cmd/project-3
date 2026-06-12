# InvForge — InvenTree base stack

This directory contains the **official InvenTree Docker Compose** setup used as the inventory system base layer.

- **Image:** `inventree/inventree:1.3.2` (pinned in `.env.example`)
- **Docs:** https://docs.inventree.org/en/stable/start/docker/
- **Upstream reference:** InvenTree v1.3.2 `contrib/container/`

## Services (InvenTree base only)

| Service | Role |
|---------|------|
| `inventree-db` | PostgreSQL 17 |
| `inventree-cache` | Redis 7 |
| `inventree-server` | InvenTree web server |
| `inventree-worker` | Background worker |
| `inventree-proxy` | Caddy reverse proxy |

InvForge AI sidecar services live outside this base compose file (for example in
`api/`, `observability/`, and `deploy/`) so the InvenTree core stays unchanged.

## First-time setup

```bash
cp .env.example .env
docker compose up -d
docker compose run --rm -T inventree-server invoke update
```

See the root [README.md](../README.md) for full instructions.
