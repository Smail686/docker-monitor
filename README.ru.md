[English](README.md) | **Русский**

# Docker Monitor

Следит за Docker-контейнерами на сервере и присылает уведомления в **Telegram** и/или **Discord**,
когда контейнер остановился (`exited`) или не проходит проверку здоровья (`unhealthy`).
Опциональное **Telegram Mini App** показывает контейнеры, логи, статистику сервера и позволяет
управлять контейнерами с телефона.

## Возможности

**Уведомления**
- Алерт при переходе контейнера в `exited` или `unhealthy` (раз в 30 секунд проверка, повторов нет).
- В алерте: красивое оформление, **краткая причина** (код выхода, нехватка памяти, ошибка запуска, результат healthcheck) и последние 10 строк лога.
- Состояние запоминается в базе: после перезагрузки сервера или монитора **не приходит повторная лавина** старых алертов, только по реально изменившимся контейнерам.
- Кнопка **Open in app** в алерте открывает нужный контейнер в приложении.

**Telegram Mini App**
- Вкладка **Контейнеры**: статус, поиск, фильтры, проблемные сверху; детали (аптайм, перезапуски, код выхода, OOM, порты, healthcheck, CPU/RAM), логи, Start / Stop / Restart.
- Вкладка **Сервер**: CPU, RAM, подкачка, диск, load average, аптайм, число контейнеров, ОС и ядро (температура, если сервер её отдаёт).
- Вкладка **История**: сбои со статистикой и фильтрами.
- Вкладка **Настройки**: заглушить алерты по контейнеру или включить режим обслуживания, журнал действий.
- Русский и английский (по языку Telegram), светлая и тёмная тема.

## Требования

- Linux-сервер с Docker и плагином Docker Compose (`docker compose version`).
- Telegram-бот (токен от @BotFather) и ваш Telegram ID (узнать можно у бота @userinfobot).
- Для Mini App: **публичный HTTPS-адрес** (Telegram не открывает приложения по http). Два способа ниже.

## Установка (только уведомления)

```bash
git clone https://github.com/<ваш-логин>/docker-monitor.git
cd docker-monitor
cp .env.example .env
nano .env                       # заполните TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
docker compose up -d --build
docker compose logs -f monitor  # убедиться, что всё работает
```

Минимум для работы в `.env`:

```env
TELEGRAM_BOT_TOKEN=123456789:токен_от_BotFather
TELEGRAM_CHAT_ID=ваш_telegram_id
```

Перед первым запуском откройте своего бота в Telegram и нажмите **Start**, иначе он не сможет вам писать.
Discord опционален: укажите `DISCORD_WEBHOOK_URL`.

## Установка Mini App

### Способ 1. Свой домен и Caddy (порты 80 и 443 свободны)

1. A-запись домена должна указывать на ваш сервер, порты 80 и 443 открыты из интернета.
2. В `.env`:
   ```env
   COMPOSE_PROFILES=web
   DOMAIN=monitor.example.com
   ```
3. `docker compose up -d --build`. Caddy сам получит HTTPS-сертификат.

### Способ 2. Cloudflare Tunnel (порты 80/443 заняты или нет белого IP)

Подходит, если на сервере уже работает `cloudflared`. Caddy не нужен.

1. В `.env`:
   ```env
   COMPOSE_PROFILES=web
   DOMAIN=monitor.example.com
   ```
2. Создайте файл `docker-compose.override.yml` рядом с `docker-compose.yml` и опубликуйте приложение на свободном порту только для localhost (здесь 8088):
   ```yaml
   services:
     webapp:
       ports:
         - "127.0.0.1:8088:8080"
   ```
3. Запустите без Caddy:
   ```bash
   docker compose up -d --build monitor webapp
   ```
4. В Cloudflare: Zero Trust → Networks → Tunnels → ваш туннель → **Public Hostname** → Add:
   `monitor` + ваш домен → Service `HTTP` → `localhost:8088`.
   DNS-запись создаётся сама; если нет, добавьте в DNS зоны CNAME `monitor` → `<id-туннеля>.cfargotunnel.com` (Proxied).
5. Откройте `https://monitor.example.com/healthz`: должно ответить `ok`.

### Привязка к боту

В Telegram: @BotFather → `/mybots` → ваш бот → Bot Settings → Menu Button → Configure menu button →
укажите `https://monitor.example.com`. Либо откройте приложение кнопкой **Open in app** из алерта.
Если кнопка меню не появилась, перезапустите Telegram.

### Доступ

- `ADMIN_TELEGRAM_IDS`: полный доступ (через запятую). Если пусто, админом считается `TELEGRAM_CHAT_ID`.
- `VIEWER_TELEGRAM_IDS`: только просмотр.
- Посторонний при входе получает отказ, а его ID пишется в лог (`docker compose logs webapp`), чтобы вы могли его добавить.

## Использование

| Что нужно | Как |
|-----------|-----|
| Посмотреть статус | Mini App, вкладка «Контейнеры» |
| Нагрузка сервера | Вкладка «Сервер» (обновляется каждые 10 секунд) |
| Перезапустить контейнер | Открыть контейнер → Restart (только админы) |
| Не получать алерты по контейнеру | Контейнер → «Заглушить» (на 15 минут … 24 часа) |
| Плановые работы | Настройки → Режим обслуживания |
| Что падало и когда | Вкладка «История» |

Остановки и перезапуски, сделанные через приложение, алертов не вызывают. Заглушённые сбои всё равно попадают в историю.

## Управление сервисом

```bash
docker compose logs -f monitor        # логи монитора
docker compose logs -f webapp         # логи веб-приложения
docker compose up -d --build          # обновление после git pull
docker compose down                   # остановить (история сохраняется в томе monitor-data)
```

Монитор и веб-приложение помечены `docker-monitor.protected=true`: из приложения их остановить нельзя.

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_BOT_TOKEN` | Токен бота (также проверяет входы в Mini App) |
| `TELEGRAM_CHAT_ID` | Чат, куда приходят алерты |
| `DISCORD_WEBHOOK_URL` | Вебхук Discord (необязательно) |
| `COMPOSE_PROFILES` | `web` включает веб-приложение и Caddy |
| `DOMAIN` | Публичный домен приложения, без `https://` и слеша |
| `ADMIN_TELEGRAM_IDS` | Telegram ID с полным доступом |
| `VIEWER_TELEGRAM_IDS` | Telegram ID только для просмотра |
| `INIT_DATA_MAX_AGE` | Сколько секунд действует вход через Telegram (по умолчанию 21600) |
| `HISTORY_DB` | Путь к SQLite (в compose: `/data/history.db`) |

## Запуск без Docker (для разработки)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python monitor.py --once             # одна проверка и выход
python monitor.py --interval 10      # проверять каждые 10 секунд
```

## Безопасность

- `.env` содержит секреты и не попадает в git (см. `.gitignore`). Не публикуйте токен бота.
- Вход в приложение проверяется подписью Telegram (`initData`, HMAC с токеном бота) и списком ID.
- Монитор монтирует `/var/run/docker.sock`: это доступ к Docker хоста, фактически root. Давайте доступ только доверенным людям.
- Логи контейнеров могут содержать секреты, а приложение их показывает.
- Переменные окружения контейнеров приложение не показывает.

## Частые проблемы

| Симптом | Решение |
|---------|---------|
| Алерты не приходят | Нажмите Start у бота; проверьте токен и chat id; `docker compose logs monitor` |
| `Discord notification failed: 400` | Не задан реальный `DISCORD_WEBHOOK_URL`, используется заглушка. Безвредно |
| Приложение не открывается в Telegram | Нужен публичный HTTPS; проверьте `https://домен/healthz` |
| «Доступ запрещён» | Добавьте свой ID в `ADMIN_TELEGRAM_IDS` и перезапустите: `docker compose up -d` |
| Порты 80/443 заняты | Используйте способ 2 (Cloudflare Tunnel) или другой порт для webapp |
| После перезагрузки лишний алерт `exited` | Контейнер успел проверяться, пока Docker его запускал. Если контейнер остался остановленным, алерт настоящий |
