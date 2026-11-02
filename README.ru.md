[English](README.md) | **Русский**

# Docker Monitor

Следит за Docker-контейнерами и присылает уведомление в Telegram и/или Discord с вероятной причиной и последними строками лога, когда контейнер остановился или не проходит проверку здоровья. Опциональное Telegram Mini App показывает контейнеры, логи и статистику сервера.

## Установка

Нужны Docker с Docker Compose и токен Telegram-бота от @BotFather.

```bash
git clone https://github.com/Smail686/docker-monitor.git
cd docker-monitor
cp .env.example .env
```

Отредактируйте `.env`: укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`, затем запустите:

```bash
docker compose up -d --build
```

Чтобы включить Mini App, задайте в `.env` `COMPOSE_PROFILES=web` и `DOMAIN` (нужен домен с публичным HTTPS) и выполните ту же команду ещё раз.
