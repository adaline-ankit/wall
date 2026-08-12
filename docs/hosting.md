# Host Margin privately

Margin is a personal service. Keep it private: the reading inbox, notes, tasks, and drafts all live in one SQLite file under the mounted data directory.

## One-command local service

```bash
mkdir -p data
cp examples/frontier-ai.yaml data/wall.yaml
printf 'WALL_APP_PASSWORD=replace-this-with-a-long-unique-password\n' > .env
docker compose up --build -d
```

Open `http://127.0.0.1:8765`. The browser will ask for a username and the password from `.env`; any non-empty username is accepted. The container deliberately binds only to loopback in the provided Compose file.

## Put it on your own domain

Place an authenticated TLS reverse proxy in front of Margin, then change the port mapping to your proxy network. Do not expose port `8765` directly to the internet. Keep `WALL_APP_PASSWORD` enabled even behind the proxy; it is a second, deliberately simple access boundary for a single-user service.

The public post route is `/read/<slug>`. Published drafts are deliberately readable without the
Margin password so you can share a post from your own domain. Everything else—the reading inbox,
notes, tasks, drafts, exports, and APIs—remains behind the password. Only publish a draft when its
body and linked source cards are safe to share; raw margin notes are never rendered on this route.

## Deploy to Render

The repository includes a production [`render.yaml`](../render.yaml) Blueprint. It deploys the
Docker image in Singapore and mounts a 1 GB persistent disk at `/var/data`, where Margin keeps its
SQLite workspace and initial WallSpec. The service uses Render's paid `starter` plan because a
free service has an ephemeral filesystem and would lose the reading library on restart or deploy.

On first boot, Margin copies the bundled frontier-AI example to the disk as `wall.yaml`, so the
private library is ready for an AI-reading workflow immediately. Future deploys preserve the
mounted data. Render generates `WALL_APP_PASSWORD` as a secret and checks `/healthz` during
deploys.

## Data and backups

- Workspace data is persisted in `data/.wall/reading.db`.
- Wall editions and specs remain in the same mounted `data/` directory.
- Download a Markdown archive from the **Export** link in the UI, or request `GET /api/reading/export`.
- Back up the whole `data/` directory while the service is stopped, or use the existing encrypted `wall sync export` workflow for Wall specs and knowledge state.

## Inbound capture contracts

The user interface supports manual saves now. The service also exposes simple JSON endpoints so a browser extension or email-forwarding gateway can use the same inbox:

```bash
curl -u margin:"$WALL_APP_PASSWORD" \
  -H 'content-type: application/json' \
  -d '{"title":"Useful paper","url":"https://example.com/paper","source":"Browser"}' \
  http://127.0.0.1:8765/api/reading/captures/browser

curl -u margin:"$WALL_APP_PASSWORD" \
  -H 'content-type: application/json' \
  -d '{"subject":"Read later","sender":"me@example.com","body":"https://example.com/paper"}' \
  http://127.0.0.1:8765/api/reading/captures/email
```

An email provider or browser extension still needs to be configured to call these endpoints. Keep that integration behind an authenticated proxy; never put the Basic-auth password into a public browser extension.

## Health check

`GET /healthz` returns `{"status":"ok"}` and is intentionally unauthenticated so a local container health check can use it.
