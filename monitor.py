#!/usr/bin/env python3
"""Docker container monitor with Discord and Telegram notifications.

Polls the Docker API, detects containers that transition to "exited" or
"unhealthy", stores the failure in SQLite (history.db) and sends an alert
to Discord (webhook) and/or Telegram (bot) with the last 10 log lines.
"""

import argparse
import html
import json
import logging
import os
import signal
import sqlite3
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import docker
from docker.errors import DockerException, NotFound

DEFAULT_INTERVAL = 30                                # seconds between checks
# The web app container shares this file through a volume, so the path is configurable.
DB_PATH = Path(os.environ.get("HISTORY_DB", str(Path(__file__).resolve().parent / "history.db")))
FAILURE_STATES = {"exited", "unhealthy"}             # statuses that trigger alerts
LOG_TAIL_LINES = 10                                  # log lines sent in alerts
DISCORD_MAX_CHARS = 2000                             # Discord message size limit
TELEGRAM_MAX_CHARS = 4096                            # Telegram message size limit

log = logging.getLogger("monitor")


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def utc_iso(moment: datetime) -> str:
    """Format a datetime as UTC ISO 8601 (same format everywhere, so strings sort correctly)."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def utc_now_iso() -> str:
    return utc_iso(datetime.now(timezone.utc))


def init_db(path: Path) -> sqlite3.Connection:
    """Open (and create if needed) the SQLite database and all tables."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # timeout: the monitor and the web app may touch the file at the same time.
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS failures (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            container_name TEXT NOT NULL,
            failed_at      DATETIME NOT NULL,
            reason         TEXT NOT NULL
        )
        """
    )
    # Alert suppression. container_name '*' means "everything" (maintenance mode).
    #   kind 'manual'      - muted by a user: failures are recorded but not sent
    #   kind 'maintenance' - same, for all containers
    #   kind 'action'      - the web app itself stopped/restarted the container, so the
    #                        resulting "exited" is expected: neither recorded nor sent
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mutes (
            container_name TEXT NOT NULL,
            kind           TEXT NOT NULL,
            until          TEXT NOT NULL,
            PRIMARY KEY (container_name, kind)
        )
        """
    )
    # Audit log of actions performed through the web app.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            at             TEXT NOT NULL,
            user_id        INTEGER NOT NULL,
            user_name      TEXT NOT NULL,
            container_name TEXT NOT NULL,
            action         TEXT NOT NULL,
            ok             INTEGER NOT NULL,
            detail         TEXT
        )
        """
    )
    # Last seen status per container, so a restart of the monitor (or of the whole
    # server) does not re-send alerts for failures that were already reported.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS last_status (
            container_id TEXT PRIMARY KEY,
            status       TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def load_state(conn: sqlite3.Connection) -> dict:
    return dict(conn.execute("SELECT container_id, status FROM last_status"))


def save_state(conn: sqlite3.Connection, state: dict) -> None:
    with conn:
        conn.execute("DELETE FROM last_status")
        conn.executemany("INSERT INTO last_status VALUES (?, ?)", state.items())


def record_failure(conn: sqlite3.Connection, name: str, failed_at: str, reason: str) -> None:
    """Insert one failure row."""
    conn.execute(
        "INSERT INTO failures (container_name, failed_at, reason) VALUES (?, ?, ?)",
        (name, failed_at, reason),
    )
    conn.commit()


def get_active_mute(conn: sqlite3.Connection, name: str):
    """Return the kind of the strongest active mute for a container, or None."""
    rows = conn.execute(
        "SELECT kind FROM mutes WHERE until > ? AND container_name IN (?, '*')",
        (utc_now_iso(), name),
    ).fetchall()
    kinds = {row[0] for row in rows}
    if "action" in kinds:
        return "action"
    for kind in ("manual", "maintenance"):
        if kind in kinds:
            return kind
    return None


def purge_expired_mutes(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM mutes WHERE until <= ?", (utc_now_iso(),))
    conn.commit()


# --------------------------------------------------------------------------- #
# Docker helpers
# --------------------------------------------------------------------------- #
def status_from_attrs(attrs: dict) -> str:
    """Status from a full `docker inspect` dict.

    Docker keeps the health result separately from the lifecycle status
    (a container can be 'running' and 'unhealthy' at once), so we merge them.
    """
    state = attrs.get("State") or {}
    if (state.get("Health") or {}).get("Status") == "unhealthy":
        return "unhealthy"
    return state.get("Status") or "unknown"  # running, exited, restarting, paused, ...


def effective_status(container) -> str:
    """Return the container status, reporting 'unhealthy' when the healthcheck fails."""
    container.reload()  # list() returns a partial view; inspect gives State.Health
    return status_from_attrs(container.attrs)


EXIT_REASONS = {
    0: "завершился штатно (код 0): остановлен вручную или при выключении сервера",
    1: "ошибка в приложении (код 1), подробности в логах",
    125: "ошибка Docker при запуске (код 125)",
    126: "команду запуска нельзя выполнить (код 126)",
    127: "команда запуска не найдена (код 127)",
    137: "убит сигналом SIGKILL (код 137): docker kill или нехватка памяти",
    139: "сбой памяти, segfault (код 139)",
    143: "остановлен сигналом SIGTERM (код 143): docker stop или выключение сервера",
}


def short(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def diagnose(attrs: dict, status: str) -> str:
    """One-line, human-readable guess at why the container is in `status`."""
    state = attrs.get("State") or {}
    if status == "unhealthy":
        entries = (state.get("Health") or {}).get("Log") or []
        output = short(entries[-1].get("Output")) if entries else ""
        return "проверка здоровья не проходит" + (f": {output}" if output else "")
    if state.get("OOMKilled"):
        return "не хватило памяти (OOM), убит системой"
    if state.get("Error"):
        return f"ошибка запуска: {short(state['Error'])}"
    code = state.get("ExitCode")
    return EXIT_REASONS.get(code) or f"аварийное завершение (код {code})"


def tail_logs(container) -> str:
    """Fetch the last LOG_TAIL_LINES log lines (equivalent of docker logs --tail 10)."""
    try:
        raw = container.logs(tail=LOG_TAIL_LINES)
        return raw.decode("utf-8", errors="replace").strip()
    except DockerException as exc:
        return f"(could not read logs: {exc})"


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
def post_json(url: str, payload: dict, label: str) -> None:
    """POST a JSON payload; failures are logged, never raised.

    The URL is deliberately not logged because it may contain a secret token.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            # Discord rejects the default Python-urllib user agent.
            "User-Agent": "docker-monitor/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10):
            pass
    except (urllib.error.URLError, ValueError, OSError) as exc:
        log.error("%s notification failed: %s", label, exc)


def build_discord_message(name: str, status: str, timestamp: str, logs: str, reason: str) -> str:
    """Build the Discord message, trimming logs so it fits the 2000 char limit."""
    header = (
        f"🚨 **Container `{name}` is {status}**\n"
        f"**Reason:** {reason}\n"
        f"**Time (UTC):** {timestamp}\n"
        f"**Last {LOG_TAIL_LINES} log lines:**\n"
    )
    # Prevent log content from closing our code block early.
    body = (logs or "(no logs)").replace("```", "'''")
    room = DISCORD_MAX_CHARS - len(header) - len("```\n\n```")
    if len(body) > room:
        body = "..." + body[-(room - 3):]  # keep the most recent output
    return f"{header}```\n{body}\n```"


STATUS_LABELS = {"exited": ("🔴", "остановлен"), "unhealthy": ("🟠", "не проходит проверку здоровья")}


def build_telegram_message(name: str, status: str, timestamp: str, logs: str, reason: str) -> str:
    """Build the Telegram message (HTML mode), trimmed to the 4096 char limit."""
    icon, label = STATUS_LABELS.get(status, ("🚨", status))
    when = datetime.fromisoformat(timestamp).strftime("%d.%m.%Y %H:%M:%S UTC")
    header = (
        f"{icon} <b>{html.escape(name)}</b> — {html.escape(label)}\n"
        f"\n"
        f"💡 <b>Причина:</b> {html.escape(reason)}\n"
        f"🕐 <b>Время:</b> {when}\n"
        f"\n"
        f"📜 <b>Последние {LOG_TAIL_LINES} строк лога:</b>\n"
    )
    body = logs or "(логов нет)"
    room = TELEGRAM_MAX_CHARS - len(header) - len("<pre></pre>") - 3
    # Trim on the raw text (oldest lines first) so we never cut an HTML entity in half.
    trimmed = False
    while len(html.escape(body)) > room:
        body = body[max(1, len(body) // 10):]
        trimmed = True
    if trimmed:
        body = "..." + body
    return f"{header}<pre>{html.escape(body)}</pre>"


def send_discord(webhook_url: str, content: str) -> None:
    """Send a message through a Discord webhook."""
    post_json(webhook_url, {"content": content}, "Discord")


def webapp_base_url() -> str:
    """Public https URL of the web app (WEBAPP_URL, or https://DOMAIN), or ''."""
    url = (os.environ.get("WEBAPP_URL") or "").strip().rstrip("/")
    if not url and os.environ.get("DOMAIN"):
        url = "https://" + os.environ["DOMAIN"].strip()
    return url


def telegram_keyboard(chat_id: str, container_name: str):
    """Inline "open in app" button, or None when it cannot be used.

    Telegram only allows web_app buttons in *private* chats (positive numeric id)
    and only with https URLs. A bad button would make the whole message fail,
    so in any other case we send the alert without a button.
    """
    base = webapp_base_url()
    if not base.startswith("https://") or not str(chat_id).isdigit():
        return None
    url = f"{base}/?c={urllib.parse.quote(container_name, safe='')}"
    return {"inline_keyboard": [[{"text": "📊 Open in app", "web_app": {"url": url}}]]}


def send_telegram(token: str, chat_id: str, text: str, reply_markup=None) -> None:
    """Send a message through the Telegram Bot API (sendMessage)."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    post_json(f"https://api.telegram.org/bot{token}/sendMessage", payload, "Telegram")


def notify(settings: dict, name: str, status: str, timestamp: str, logs: str, reason: str) -> None:
    """Send the alert to every configured channel."""
    sent_any = False
    if settings.get("webhook_url"):
        send_discord(settings["webhook_url"],
                     build_discord_message(name, status, timestamp, logs, reason))
        sent_any = True
    if settings.get("telegram_token") and settings.get("telegram_chat_id"):
        chat_id = settings["telegram_chat_id"]
        send_telegram(settings["telegram_token"], chat_id,
                      build_telegram_message(name, status, timestamp, logs, reason),
                      telegram_keyboard(chat_id, name))
        sent_any = True
    if not sent_any:
        log.warning("No notification channel configured; failure only stored in DB")


# --------------------------------------------------------------------------- #
# Check cycle
# --------------------------------------------------------------------------- #
def handle_failure(container, status, conn, settings) -> None:
    """Record a failure in SQLite and notify all channels (unless muted)."""
    name = container.name
    timestamp = utc_now_iso()
    mute = get_active_mute(conn, name)

    if mute == "action":
        # The web app stopped/restarted this container on purpose.
        log.info("Container %s is %s (expected: action from the web app)", name, status)
        return

    log.warning("Container %s is %s", name, status)
    # Save to DB first so history is kept even if notifications fail.
    record_failure(conn, name, timestamp, status)

    if mute:
        log.info("Alerts for %s are muted (%s); not notifying", name, mute)
        return
    notify(settings, name, status, timestamp, tail_logs(container),
           diagnose(container.attrs, status))


def check_cycle(client, previous: dict, conn, settings) -> dict:
    """Run one poll. `previous` maps container id -> last seen status.

    Returns the new id -> status map. An alert fires only when a container
    *enters* a failure state (its status differs from the last cycle), so a
    container that stays exited is reported once, not every 30 seconds.
    """
    purge_expired_mutes(conn)
    current = {}
    for container in client.containers.list(all=True):
        try:
            status = effective_status(container)
        except NotFound:
            continue  # container was removed between list() and inspect
        current[container.id] = status
        if status in FAILURE_STATES and previous.get(container.id) != status:
            handle_failure(container, status, conn, settings)
    log.info("Checked %d container(s)", len(current))
    return current


# --------------------------------------------------------------------------- #
# CLI / main loop
# --------------------------------------------------------------------------- #
def positive_int(value: str) -> int:
    """argparse type: integer > 0."""
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Docker containers and alert via Discord and/or Telegram.")
    parser.add_argument("--once", action="store_true",
                        help="run a single check cycle and exit")
    parser.add_argument("--interval", type=positive_int, default=DEFAULT_INTERVAL,
                        help=f"polling interval in seconds (default {DEFAULT_INTERVAL})")
    parser.add_argument("--webhook-url", default=os.environ.get("DISCORD_WEBHOOK_URL"),
                        help="Discord webhook URL (or set DISCORD_WEBHOOK_URL)")
    parser.add_argument("--telegram-token", default=os.environ.get("TELEGRAM_BOT_TOKEN"),
                        help="Telegram bot token (or set TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--telegram-chat-id", default=os.environ.get("TELEGRAM_CHAT_ID"),
                        help="Telegram chat id (or set TELEGRAM_CHAT_ID)")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    settings = {
        "webhook_url": args.webhook_url,
        "telegram_token": args.telegram_token,
        "telegram_chat_id": args.telegram_chat_id,
    }
    if bool(args.telegram_token) != bool(args.telegram_chat_id):
        log.warning("Telegram needs BOTH a bot token and a chat id; Telegram is disabled")

    # Graceful shutdown: signals just set a flag; the loop exits between cycles.
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    conn = init_db(DB_PATH)
    client = None
    state = load_state(conn)
    exit_code = 0

    try:
        while not stop.is_set():
            try:
                if client is None:  # (re)connect lazily so a Docker outage doesn't kill us
                    client = docker.from_env()
                    client.ping()
                state = check_cycle(client, state, conn, settings)
                save_state(conn, state)
                exit_code = 0
            except DockerException as exc:
                log.error("Docker error: %s", exc)
                client = None
                exit_code = 1

            if args.once:
                break
            stop.wait(args.interval)  # sleeps, but wakes immediately on shutdown
    finally:
        conn.close()
        if client is not None:
            client.close()
        log.info("Stopped")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
