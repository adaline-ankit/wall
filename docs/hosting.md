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

The repository includes a [`render.yaml`](../render.yaml) Blueprint for a free Render preview. It
deploys the Docker image in Singapore and starts Margin with the bundled frontier-AI WallSpec.
Render's free filesystem is ephemeral, so the reading library may be lost after a restart or
redeploy. Use it to evaluate the product, not as the only copy of your personal library.

On first boot, Margin copies the bundled frontier-AI example to the disk as `wall.yaml`, so the
private library is ready for an AI-reading workflow immediately. Render generates
`WALL_APP_PASSWORD` as a secret and checks `/healthz` during deploys. To make a personal library
durable later, upgrade the service and attach a persistent disk at `/var/data`.

## Data and backups

- Workspace data is persisted in `data/.wall/reading.db`.
- Wall editions and specs remain in the same mounted `data/` directory.
- Download a Markdown archive from the **Export** link in the UI, or request `GET /api/reading/export`.
- Back up the whole `data/` directory while the service is stopped, or use the existing encrypted `wall sync export` workflow for Wall specs and knowledge state.

## Inbound capture contracts

The user interface supports manual saves now. The service also exposes simple JSON endpoints so a browser extension or email-forwarding gateway can use the same inbox. Set a long random `WALL_CAPTURE_TOKEN` to give those connectors a write-only credential; it cannot open the private app or read the library.

```bash
curl -H "Authorization: Bearer $WALL_CAPTURE_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"title":"Useful paper","url":"https://example.com/paper","source":"Browser"}' \
  http://127.0.0.1:8765/api/reading/captures/browser

curl -H "Authorization: Bearer $WALL_CAPTURE_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"subject":"Read later","sender":"me@example.com","body":"https://example.com/paper"}' \
  http://127.0.0.1:8765/api/reading/captures/email
```

The owner can still use Basic authentication for the same endpoints. An email provider or browser extension still needs to be configured to call them; never put the Basic-auth password into a public browser extension. Rotate the capture token after a connector is lost or compromised.

### Save pages from Chrome

Wall includes a no-build [Save to Margin Chrome connector](../integrations/chrome-extension). Load that
folder as an unpacked extension in `chrome://extensions`, enter the service address and
`WALL_CAPTURE_TOKEN`, and approve its one-site permission request. It stores the token only in the
local extension storage and sends the current tab's title, URL, optional note, and optional tags to
the browser capture route. It never receives `WALL_APP_PASSWORD` and does not read page contents,
cookies, or your Margin library.

### Schedule a safe daily refresh

Set `WALL_REFRESH_TOKEN` and have your scheduler `POST` to `/api/reading/refresh` with that Bearer
token once per day. The token can only run a deterministic refresh and add selected items to the
inbox; it cannot read Margin or invoke an LLM provider. This makes a scheduled call safe to keep in
an automation secret store. The Render Blueprint generates the token, but Render's free web service
can sleep, so use an external scheduler only when you need a reliable cadence.

```bash
curl -X POST -H "Authorization: Bearer $WALL_REFRESH_TOKEN" \
  -H 'content-type: application/json' -d '{"use_llm":false}' \
  https://margin.example.com/api/reading/refresh
```

## Health check

`GET /healthz` returns `{"status":"ok"}` and is intentionally unauthenticated so a local container health check can use it.
