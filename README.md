**English** | [Русский](README.ru.md)

# Docker Monitor

Watches Docker containers on your server and sends notifications to **Telegram** and/or **Discord**
when a container stops (`exited`) or fails its health check (`unhealthy`).
An optional **Telegram Mini App** shows containers, logs and server statistics, and lets you
control containers from your phone.

## Features

**Alerts**
- An alert fires when a container enters `exited` or `unhealthy` (checked every 30 seconds, no repeats).
- Each alert has a clean layout, a **short reason** (exit code, out of memory, start error, health check output) and the last 10 log lines.
- The last known state is stored in the database: after a server or monitor restart you do **not** get a flood of old alerts, only for containers that really changed.
- The **Open in app** button in an alert opens that container in the app.

**Telegram Mini App**
- **Containers** tab: status, search, filters, failing containers on top; details (uptime, restarts, exit code, OOM, ports, health check, CPU/RAM), logs, Start / Stop / Restart.
- **Server** tab: CPU, RAM, swap, disk, load average, uptime, container count, OS and kernel (temperature if the host exposes it).
- **History** tab: failures with statistics and filters.
- **Settings** tab: mute alerts per container or enable maintenance mode, action log.
- Russian and English (follows your Telegram language), light and dark theme.

## Requirements

- A Linux server with Docker and the Docker Compose plugin (`docker compose version`).
- A Telegram bot (token from @BotFather) and your Telegram ID (ask @userinfobot).
- For the Mini App: a **public HTTPS address** (Telegram will not open http apps). Two options below.

## Installation (alerts only)

```bash
git clone https://github.com/<your-login>/docker-monitor.git
cd docker-monitor
cp .env.example .env
nano .env                       # fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
docker compose up -d --build
docker compose logs -f monitor  # make sure it works
```

Minimum `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:token_from_BotFather
TELEGRAM_CHAT_ID=your_telegram_id
```

Before the first run, open your bot in Telegram and press **Start**, otherwise it cannot message you.
Discord is optional: set `DISCORD_WEBHOOK_URL`.

## Installing the Mini App

### Option 1. Your own domain and Caddy (ports 80 and 443 are free)

1. The domain's A record must point to your server; ports 80 and 443 must be reachable from the internet.
2. In `.env`:
   ```env
   COMPOSE_PROFILES=web
   DOMAIN=monitor.example.com
   ```
3. `docker compose up -d --build`. Caddy obtains the HTTPS certificate automatically.

### Option 2. Cloudflare Tunnel (ports 80/443 are taken, or no public IP)

Use this if `cloudflared` already runs on the server. Caddy is not needed.

1. In `.env`:
   ```env
   COMPOSE_PROFILES=web
   DOMAIN=monitor.example.com
   ```
2. Create `docker-compose.override.yml` next to `docker-compose.yml` and publish the app on a free port, localhost only (8088 here):
   ```yaml
   services:
     webapp:
       ports:
         - "127.0.0.1:8088:8080"
   ```
3. Start without Caddy:
   ```bash
   docker compose up -d --build monitor webapp
   ```
4. In Cloudflare: Zero Trust → Networks → Tunnels → your tunnel → **Public Hostname** → Add:
   `monitor` + your domain → Service `HTTP` → `localhost:8088`.
   If the DNS record is not created automatically, add a CNAME `monitor` → `<tunnel-id>.cfargotunnel.com` (Proxied) to the zone.
5. Open `https://monitor.example.com/healthz`: it should answer `ok`.

### Connect it to the bot

In Telegram: @BotFather → `/mybots` → your bot → Bot Settings → Menu Button → Configure menu button →
enter `https://monitor.example.com`. Or open the app with the **Open in app** button from an alert.
If the menu button does not appear, restart Telegram.

### Access

- `ADMIN_TELEGRAM_IDS`: full access (comma-separated). If empty, `TELEGRAM_CHAT_ID` is the admin.
- `VIEWER_TELEGRAM_IDS`: read-only.
- Anyone else is refused and their ID is logged (`docker compose logs webapp`), so you can add it.

## Usage

| What you need | How |
|---------------|-----|
| See status | Mini App, Containers tab |
| Server load | Server tab (refreshes every 10 seconds) |
| Restart a container | Open the container → Restart (admins only) |
| Stop alerts for a container | Container → Mute (15 minutes … 24 hours) |
| Planned maintenance | Settings → Maintenance mode |
| What failed and when | History tab |

Stops and restarts made through the app do not trigger alerts. Muted failures are still recorded in the history.

## Managing the service

```bash
docker compose logs -f monitor        # monitor logs
docker compose logs -f webapp         # web app logs
docker compose up -d --build          # update after git pull
docker compose down                   # stop (history is kept in the monitor-data volume)
```

The monitor and web app carry the label `docker-monitor.protected=true`, so they cannot be stopped from the app.

## Environment variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Bot token (also verifies Mini App logins) |
| `TELEGRAM_CHAT_ID` | Chat that receives alerts |
| `DISCORD_WEBHOOK_URL` | Discord webhook (optional) |
| `COMPOSE_PROFILES` | `web` enables the web app and Caddy |
| `DOMAIN` | Public domain of the app, without `https://` and trailing slash |
| `ADMIN_TELEGRAM_IDS` | Telegram IDs with full access |
| `VIEWER_TELEGRAM_IDS` | Telegram IDs with read-only access |
| `INIT_DATA_MAX_AGE` | Seconds a Telegram login stays valid (default 21600) |
| `HISTORY_DB` | Path of the SQLite file (in compose: `/data/history.db`) |

## Running without Docker (development)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python monitor.py --once             # single check, then exit
python monitor.py --interval 10      # poll every 10 seconds
```

## Security

- `.env` holds secrets and is kept out of git (see `.gitignore`). Never publish your bot token.
- App logins are verified with Telegram's signed `initData` (HMAC with the bot token) and the ID lists.
- The monitor mounts `/var/run/docker.sock`: this is access to the host's Docker, effectively root. Only give access to people you trust.
- Container logs can contain secrets, and the app displays them.
- The app never shows containers' environment variables.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No alerts arrive | Press Start in the bot; check the token and chat id; `docker compose logs monitor` |
| `Discord notification failed: 400` | No real `DISCORD_WEBHOOK_URL` is set, a placeholder is used. Harmless |
| App does not open in Telegram | Public HTTPS is required; check `https://domain/healthz` |
| "Access denied" | Add your ID to `ADMIN_TELEGRAM_IDS` and run `docker compose up -d` |
| Ports 80/443 are taken | Use Option 2 (Cloudflare Tunnel) or another port for webapp |
| Extra `exited` alert after a reboot | The container was checked while Docker was still starting it. If it stayed stopped, the alert is real |
