**English** | [Русский](README.ru.md)

# Docker Monitor

Watches Docker containers and sends a Telegram and/or Discord alert, with the likely reason and the last log lines, when a container stops or becomes unhealthy. An optional Telegram Mini App shows containers, logs and server stats.

## Installation

Requires Docker with Docker Compose and a Telegram bot token from @BotFather.

```bash
git clone https://github.com/Smail686/docker-monitor.git
cd docker-monitor
cp .env.example .env
```

Edit `.env`: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, then start:

```bash
docker compose up -d --build
```

To enable the Mini App, set `COMPOSE_PROFILES=web` and `DOMAIN` in `.env` (a domain with public HTTPS is required) and run the same command again.
