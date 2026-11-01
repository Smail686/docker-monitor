#!/usr/bin/env python3
"""Telegram Mini App backend for the Docker monitor.

A small JSON API + static file server (standard library only). Every /api/ request
must carry Telegram's signed `initData` in the X-Telegram-Init-Data header; it is
verified with the bot token and the user must be on an allow-list.

Security model, in short:
  * the user is authenticated by Telegram's HMAC signature (no passwords, no cookies,
    therefore no CSRF);
  * only Telegram IDs listed in ADMIN_TELEGRAM_IDS / VIEWER_TELEGRAM_IDS get in;
  * the only write operations are start / stop / restart, mute settings;
  * containers labelled docker-monitor.protected=true (the monitor itself, this app,
    the proxy) cannot be controlled, so you cannot cut off the branch you sit on;
  * environment variables of containers are never exposed.
"""

import contextlib
import glob
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import sys
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import docker
from docker.errors import APIError, DockerException, NotFound

import monitor

log = logging.getLogger("webapp")

STATIC_DIR = (Path(__file__).resolve().parent / "static").resolve()
PROTECTED_LABEL = "docker-monitor.protected"
ACTIONS = {"start", "stop", "restart"}
ACTION_MUTE_SECONDS = 180      # how long an app-initiated stop/restart is "expected"
MAX_MUTE_MINUTES = 7 * 24 * 60
MAX_LOG_LINES = 500
MAX_LOG_CHARS = 100_000
MAX_BODY_BYTES = 4096
LIST_CACHE_TTL = 2.0           # seconds; protects Docker from many clients polling

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
# Telegram's script is the only third-party code. Inline styles are allowed because
# the Telegram client injects theme variables; all dynamic text is set via textContent.
CSP = ("default-src 'self'; script-src 'self' https://telegram.org; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'")


# --------------------------------------------------------------------------- #
# Errors and Telegram authentication
# --------------------------------------------------------------------------- #
class HttpError(Exception):
    """An error that maps directly onto a JSON error response."""

    def __init__(self, status: int, code: str, **extra):
        super().__init__(code)
        self.status, self.code, self.extra = status, code, extra


def validate_init_data(init_data: str, bot_token: str, max_age: int, now=None) -> dict:
    """Verify Telegram initData and return the Telegram user dict.

    Algorithm (core.telegram.org/bots/webapps): secret = HMAC_SHA256("WebAppData", token);
    hash = HMAC_SHA256(secret, data_check_string) where data_check_string is the
    key=value fields sorted by key and joined with newlines.
    """
    if not init_data:
        raise HttpError(401, "missing_init_data")
    try:
        pairs = urllib.parse.parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise HttpError(401, "invalid_init_data") from None
    fields = dict(pairs)
    received = fields.pop("hash", None)
    if not received:
        raise HttpError(401, "invalid_init_data")

    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    def signature(excluded: tuple) -> bytes:
        check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k not in excluded)
        return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest().encode()

    # Telegram added an extra `signature` field in 2024 and clients differ on whether it
    # is part of the signed string, so accept either form. Both are HMACs over genuine
    # fields, so this does not weaken the check.
    received_bytes = received.encode()
    if not (hmac.compare_digest(signature(()), received_bytes)
            or hmac.compare_digest(signature(("signature",)), received_bytes)):
        raise HttpError(401, "invalid_init_data")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError):
        raise HttpError(401, "invalid_init_data") from None

    now = time.time() if now is None else now
    if now - auth_date > max_age:
        raise HttpError(401, "expired")
    if auth_date - now > 300:  # timestamp from the future: clock skew or forgery
        raise HttpError(401, "invalid_init_data")
    user["id"] = user_id
    return user


def parse_ids(value: str) -> set:
    """Parse '123, 456' into a set of ints, ignoring junk."""
    ids = set()
    for part in re.split(r"[,\s;]+", value or ""):
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            log.warning("Ignoring invalid Telegram id %r", part)
    return ids


def load_config(env) -> dict:
    """Read and validate configuration from environment variables (fails fast)."""
    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required: it is used to verify Telegram logins.")
    admins = parse_ids(env.get("ADMIN_TELEGRAM_IDS", ""))
    chat_id = (env.get("TELEGRAM_CHAT_ID") or "").strip()
    if not admins and chat_id.isdigit():
        # A private chat id equals the user's Telegram id, so the person who receives
        # alerts in a private chat becomes the admin by default.
        admins = {int(chat_id)}
        log.info("ADMIN_TELEGRAM_IDS not set; using TELEGRAM_CHAT_ID %s as admin", chat_id)
    if not admins:
        raise SystemExit("Set ADMIN_TELEGRAM_IDS (your numeric Telegram id) - "
                         "nobody would be able to log in otherwise.")
    return {
        "token": token,
        "admins": admins,
        "viewers": parse_ids(env.get("VIEWER_TELEGRAM_IDS", "")) - admins,
        "max_age": int(env.get("INIT_DATA_MAX_AGE", "21600") or 21600),
        "base_url": monitor.webapp_base_url(),
    }


# --------------------------------------------------------------------------- #
# Application state
# --------------------------------------------------------------------------- #
class App:
    """Holds configuration, the Docker client and small caches (shared by all requests)."""

    def __init__(self, token, admins, viewers, db_path, max_age=21600,
                 client_factory=None, base_url=""):
        self.token, self.admins, self.viewers = token, set(admins), set(viewers)
        self.db_path, self.max_age, self.base_url = Path(db_path), max_age, base_url
        self._client_factory = client_factory or (lambda: docker.from_env(timeout=60))
        self._client = None
        self._client_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=8)
        self._cache = None
        self._cache_lock = threading.Lock()
        self._action_locks = {}
        self._guard = threading.Lock()
        monitor.init_db(self.db_path).close()

    # -- auth -------------------------------------------------------------- #
    def role_for(self, user_id: int):
        if user_id in self.admins:
            return "admin"
        if user_id in self.viewers:
            return "viewer"
        return None

    # -- database ---------------------------------------------------------- #
    @contextlib.contextmanager
    def db(self):
        """A short-lived connection (sqlite3 objects must not be shared across threads)."""
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- docker ------------------------------------------------------------ #
    def docker(self):
        with self._client_lock:
            if self._client is None:
                client = self._client_factory()
                client.ping()
                self._client = client
            return self._client

    def drop_client(self):
        with self._client_lock:
            self._client = None

    def invalidate(self):
        with self._cache_lock:
            self._cache = None

    def list_containers(self) -> list:
        """Summaries of all containers, cached for a couple of seconds."""
        with self._cache_lock:
            if self._cache and time.monotonic() - self._cache[0] < LIST_CACHE_TTL:
                return self._cache[1]

        def inspect(container):
            try:
                container.reload()  # list() gives a partial view; we need State.Health
                return summarize(container.attrs)
            except NotFound:
                return None  # removed while we were looking

        found = self.docker().containers.list(all=True)
        items = [i for i in self._pool.map(inspect, found) if i]
        items.sort(key=lambda i: i["name"].lower())
        with self._cache_lock:
            self._cache = (time.monotonic(), items)
        return items

    def action_lock(self, container_id: str) -> threading.Lock:
        with self._guard:
            return self._action_locks.setdefault(container_id, threading.Lock())


# --------------------------------------------------------------------------- #
# Docker data -> JSON
# --------------------------------------------------------------------------- #
def clean_ts(value):
    """Docker uses year 0001 for 'never'; turn that into None."""
    if not value or str(value).startswith("0001"):
        return None
    return value


def summarize(attrs: dict) -> dict:
    """Compact, safe view of `docker inspect` (never includes env vars)."""
    state = attrs.get("State") or {}
    config = attrs.get("Config") or {}
    labels = config.get("Labels") or {}
    cid = attrs.get("Id") or ""
    return {
        "id": cid,
        "short_id": cid[:12],
        "name": (attrs.get("Name") or "").lstrip("/"),
        "image": config.get("Image") or "",
        "status": monitor.status_from_attrs(attrs),
        "health": (state.get("Health") or {}).get("Status"),
        "started_at": clean_ts(state.get("StartedAt")),
        "finished_at": clean_ts(state.get("FinishedAt")),
        "exit_code": state.get("ExitCode"),
        "oom_killed": bool(state.get("OOMKilled")),
        "restart_count": attrs.get("RestartCount") or 0,
        "protected": labels.get(PROTECTED_LABEL) == "true",
    }


def detail(attrs: dict) -> dict:
    """summarize() plus extra fields for the detail screen."""
    info = summarize(attrs)
    ports = []
    for container_port, bindings in ((attrs.get("NetworkSettings") or {}).get("Ports") or {}).items():
        if bindings:
            ports += [f"{b.get('HostPort')}→{container_port}" for b in bindings]
        else:
            ports.append(container_port)
    health = (attrs.get("State") or {}).get("Health") or {}
    last = (health.get("Log") or [None])[-1]
    info["ports"] = list(dict.fromkeys(ports))  # drop IPv4/IPv6 duplicates, keep order
    info["created"] = clean_ts(attrs.get("Created"))
    info["health_output"] = ANSI_RE.sub("", (last or {}).get("Output") or "")[:500].strip() or None
    return info


def compute_stats(raw: dict) -> dict:
    """CPU % and memory from one Docker stats sample (tolerant of missing fields)."""
    cpu_stats, pre = raw.get("cpu_stats") or {}, raw.get("precpu_stats") or {}
    cpu_delta = ((cpu_stats.get("cpu_usage") or {}).get("total_usage", 0)
                 - (pre.get("cpu_usage") or {}).get("total_usage", 0))
    system_delta = cpu_stats.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
    cpus = (cpu_stats.get("online_cpus")
            or len((cpu_stats.get("cpu_usage") or {}).get("percpu_usage") or []) or 1)
    cpu = cpu_delta / system_delta * cpus * 100 if system_delta > 0 and cpu_delta >= 0 else 0.0

    mem = raw.get("memory_stats") or {}
    cache = (mem.get("stats") or {}).get("inactive_file") or (mem.get("stats") or {}).get("cache") or 0
    used = max((mem.get("usage") or 0) - cache, 0)  # same definition as `docker stats`
    limit = mem.get("limit") or 0
    return {
        "available": True,
        "cpu_percent": round(cpu, 1),
        "mem_used": used,
        "mem_limit": limit,
        "mem_percent": round(used / limit * 100, 1) if limit else 0.0,
    }


def read_cpu_times():
    """(idle, total) jiffies of the whole host from the first line of /proc/stat."""
    fields = [int(x) for x in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    return fields[3] + fields[4], sum(fields[:8])  # idle + iowait, user..steal


def read_meminfo() -> dict:
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        info[key] = int(rest.split()[0]) * 1024
    return info


def read_temperature():
    """Hottest thermal zone in °C, or None when the host exposes none."""
    temps = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        with contextlib.suppress(OSError, ValueError):
            temps.append(int(Path(path).read_text()) / 1000)
    return round(max(temps), 1) if temps else None


def percent(used: int, total: int) -> float:
    return round(used / total * 100, 1) if total else 0.0


def collect_system(info: dict) -> dict:
    """Host CPU, memory, disk, load and uptime (/proc shows the host inside a container)."""
    idle1, total1 = read_cpu_times()
    time.sleep(0.3)
    idle2, total2 = read_cpu_times()
    cpu = (1 - (idle2 - idle1) / (total2 - total1)) * 100 if total2 > total1 else 0.0

    mem = read_meminfo()
    ram_used = mem["MemTotal"] - mem["MemAvailable"]
    swap_used = mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)
    disk = shutil.disk_usage("/")
    return {
        "host": info.get("Name", ""),
        "os": info.get("OperatingSystem", ""),
        "kernel": info.get("KernelVersion", ""),
        "cores": os.cpu_count() or 1,
        "cpu_percent": round(cpu, 1),
        "load": [round(x, 2) for x in os.getloadavg()],
        "temp": read_temperature(),
        "ram_used": ram_used, "ram_total": mem["MemTotal"], "ram_percent": percent(ram_used, mem["MemTotal"]),
        "swap_used": swap_used, "swap_total": mem.get("SwapTotal", 0),
        "swap_percent": percent(swap_used, mem.get("SwapTotal", 0)),
        "disk_used": disk.used, "disk_total": disk.total, "disk_percent": percent(disk.used, disk.total),
        "uptime": int(float(Path("/proc/uptime").read_text().split()[0])),
        "containers": info.get("Containers", 0), "containers_running": info.get("ContainersRunning", 0),
    }


# --------------------------------------------------------------------------- #
# Database queries
# --------------------------------------------------------------------------- #
def active_mutes(conn) -> list:
    """User-visible mutes (manual + maintenance); 'action' mutes are internal."""
    rows = conn.execute(
        "SELECT container_name, kind, until FROM mutes "
        "WHERE until > ? AND kind != 'action' ORDER BY until",
        (monitor.utc_now_iso(),),
    ).fetchall()
    return [dict(r) for r in rows]


def set_mute(conn, name: str, kind: str, seconds: int) -> str:
    until = monitor.utc_iso(datetime.now(timezone.utc) + timedelta(seconds=seconds))
    conn.execute("INSERT OR REPLACE INTO mutes (container_name, kind, until) VALUES (?, ?, ?)",
                 (name, kind, until))
    return until


def log_action(conn, user: dict, container: str, action: str, ok: bool, detail_text: str = ""):
    name = (user.get("username") or user.get("first_name") or str(user["id"]))[:64]
    conn.execute(
        "INSERT INTO actions (at, user_id, user_name, container_name, action, ok, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (monitor.utc_now_iso(), user["id"], name, container, action, int(ok), detail_text[:300]),
    )


def int_param(query: dict, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(query.get(key, [default])[0])
    except (TypeError, ValueError):
        raise HttpError(400, "bad_parameter", parameter=key) from None
    return max(low, min(high, value))


# --------------------------------------------------------------------------- #
# API handlers: f(app, req) -> JSON-serialisable dict
# req has: user, role, query, body, match
# --------------------------------------------------------------------------- #
def api_me(app, req):
    user = req.user
    return {
        "user": {"id": user["id"], "name": user.get("first_name") or user.get("username") or ""},
        "role": req.role,
        "server_time": monitor.utc_now_iso(),
    }


def api_containers(app, req):
    items = app.list_containers()
    with app.db() as conn:
        mutes = active_mutes(conn)
    maintenance = next((m for m in mutes if m["container_name"] == "*"), None)
    return {
        "containers": items,
        "mutes": [m for m in mutes if m["container_name"] != "*"],
        "maintenance": maintenance,
        "server_time": monitor.utc_now_iso(),
    }


def get_container(app, container_id):
    container = app.docker().containers.get(container_id)
    container.reload()
    return container


def api_container(app, req):
    return {"container": detail(get_container(app, req.match["cid"]).attrs)}


def api_logs(app, req):
    lines = int_param(req.query, "tail", 100, 1, MAX_LOG_LINES)
    raw = get_container(app, req.match["cid"]).logs(tail=lines, timestamps=False)
    text = ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).rstrip()
    if len(text) > MAX_LOG_CHARS:
        text = "…" + text[-MAX_LOG_CHARS:]
    return {"logs": text, "lines": lines}


def api_stats(app, req):
    container = get_container(app, req.match["cid"])
    if monitor.status_from_attrs(container.attrs) != "running":
        return {"available": False}
    return compute_stats(container.stats(stream=False))


def api_system(app, req):
    return collect_system(app.docker().info())


def api_action(app, req):
    action = req.body.get("action")
    if action not in ACTIONS:
        raise HttpError(400, "bad_action")
    container = get_container(app, req.match["cid"])
    info = summarize(container.attrs)
    if info["protected"]:
        raise HttpError(403, "protected")

    lock = app.action_lock(info["id"])
    if not lock.acquire(blocking=False):  # ignore double taps / parallel requests
        raise HttpError(409, "busy")
    try:
        with app.db() as conn:
            if action in ("stop", "restart"):
                # Tell the monitor this is intentional, so it does not raise an alert.
                set_mute(conn, info["name"], "action", ACTION_MUTE_SECONDS)
        ok, error_text = True, ""
        try:
            kwargs = {} if action == "start" else {"timeout": 10}
            getattr(container, action)(**kwargs)
        except APIError as exc:
            ok, error_text = False, getattr(exc, "explanation", None) or str(exc)
        with app.db() as conn:
            log_action(conn, req.user, info["name"], action, ok, error_text)
        app.invalidate()
        log.info("User %s: %s %s -> %s", req.user["id"], action, info["name"], "ok" if ok else error_text)
        if not ok:
            raise HttpError(502, "docker_error", message=error_text)
        container.reload()
        return {"container": summarize(container.attrs)}
    finally:
        lock.release()


def api_failures(app, req):
    limit = int_param(req.query, "limit", 50, 1, 200)
    before = int_param(req.query, "before", 0, 0, 2**62)
    name = (req.query.get("container") or [""])[0]
    if name and not NAME_RE.match(name):
        raise HttpError(400, "bad_parameter", parameter="container")

    sql, args = "SELECT id, container_name, failed_at, reason FROM failures WHERE 1=1", []
    if name:
        sql += " AND container_name = ?"
        args.append(name)
    if before:
        sql += " AND id < ?"
        args.append(before)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit + 1)  # one extra row tells us whether there is another page

    with app.db() as conn:
        rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        result = {"items": rows[:limit], "has_more": len(rows) > limit}
        if not before:
            now = datetime.now(timezone.utc)
            day = monitor.utc_iso(now - timedelta(hours=24))
            week = monitor.utc_iso(now - timedelta(days=7))
            count = lambda cutoff: conn.execute(  # noqa: E731
                "SELECT COUNT(*) FROM failures WHERE failed_at >= ?", (cutoff,)).fetchone()[0]
            result["summary"] = {
                "last_24h": count(day),
                "last_7d": count(week),
                "total": conn.execute("SELECT COUNT(*) FROM failures").fetchone()[0],
                "top": [dict(r) for r in conn.execute(
                    "SELECT container_name, COUNT(*) AS count FROM failures WHERE failed_at >= ? "
                    "GROUP BY container_name ORDER BY count DESC, container_name LIMIT 5", (week,))],
            }
    return result


def api_mutes(app, req):
    with app.db() as conn:
        return {"mutes": active_mutes(conn)}


def api_mute_set(app, req):
    name = req.body.get("container_name")
    minutes = req.body.get("minutes")
    if not isinstance(name, str) or not (name == "*" or NAME_RE.match(name)):
        raise HttpError(400, "bad_container_name")
    if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= MAX_MUTE_MINUTES:
        raise HttpError(400, "bad_minutes")
    kind = "maintenance" if name == "*" else "manual"
    with app.db() as conn:
        until = set_mute(conn, name, kind, minutes * 60)
        log_action(conn, req.user, name if name != "*" else "(all)", f"mute {minutes}m", True)
    return {"container_name": name, "kind": kind, "until": until}


def api_mute_delete(app, req):
    name = req.body.get("container_name")
    if not isinstance(name, str) or not (name == "*" or NAME_RE.match(name)):
        raise HttpError(400, "bad_container_name")
    with app.db() as conn:
        conn.execute("DELETE FROM mutes WHERE container_name = ? AND kind IN ('manual', 'maintenance')",
                     (name,))
        log_action(conn, req.user, name if name != "*" else "(all)", "unmute", True)
    return {"ok": True}


def api_actions(app, req):
    limit = int_param(req.query, "limit", 30, 1, 100)
    with app.db() as conn:
        rows = conn.execute(
            "SELECT at, user_name, container_name, action, ok, detail FROM actions "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return {"items": [dict(r) for r in rows]}


CID = r"(?P<cid>[0-9a-f]{12,64})"
ROUTES = [  # (method, path regex, handler, admin only)
    ("GET", r"/api/me", api_me, False),
    ("GET", r"/api/containers", api_containers, False),
    ("GET", rf"/api/containers/{CID}", api_container, False),
    ("GET", rf"/api/containers/{CID}/logs", api_logs, False),
    ("GET", rf"/api/containers/{CID}/stats", api_stats, False),
    ("POST", rf"/api/containers/{CID}/action", api_action, True),
    ("GET", r"/api/system", api_system, False),
    ("GET", r"/api/failures", api_failures, False),
    ("GET", r"/api/mutes", api_mutes, False),
    ("POST", r"/api/mutes", api_mute_set, True),
    ("POST", r"/api/mutes/delete", api_mute_delete, True),
    ("GET", r"/api/actions", api_actions, False),
]
ROUTES = [(m, re.compile(f"^{p}$"), h, a) for m, p, h, a in ROUTES]


# --------------------------------------------------------------------------- #
# HTTP layer
# --------------------------------------------------------------------------- #
def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "DockerMonitor"
        sys_version = ""

        def log_message(self, fmt, *args):  # route access logs through logging, at debug level
            log.debug("%s %s", self.address_string(), fmt % args)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        # -- responses ------------------------------------------------------ #
        def _send(self, status, body: bytes, content_type, extra=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload):
            self._send(status, json.dumps(payload).encode(), "application/json",
                       {"Cache-Control": "no-store"})

        # -- static files --------------------------------------------------- #
        def _static(self, path):
            if path == "/healthz":
                return self._send(200, b"ok", "text/plain")
            if path in ("/", "/index.html"):
                name = "index.html"
            elif path.startswith("/static/"):
                name = urllib.parse.unquote(path[len("/static/"):])
            else:
                raise HttpError(404, "not_found")
            target = (STATIC_DIR / name).resolve()
            if STATIC_DIR not in target.parents or not target.is_file() \
                    or target.suffix not in CONTENT_TYPES:
                raise HttpError(404, "not_found")
            body = target.read_bytes()
            headers = {"Cache-Control": "no-cache"}
            if name == "index.html":
                # Cache-busting: Telegram's WebView caches assets aggressively, so the
                # asset URLs carry a version derived from the files' modification times.
                version = str(int(max(p.stat().st_mtime for p in STATIC_DIR.iterdir() if p.is_file())))
                body = body.replace(b"__V__", version.encode())
                headers.update({"Cache-Control": "no-store", "Content-Security-Policy": CSP})
            self._send(200, body, CONTENT_TYPES[target.suffix], headers)

        # -- API ------------------------------------------------------------ #
        def _read_body(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise HttpError(400, "bad_request") from None
            if length > MAX_BODY_BYTES:
                raise HttpError(413, "too_large")
            if not length:
                return {}
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                raise HttpError(400, "bad_json") from None
            if not isinstance(body, dict):
                raise HttpError(400, "bad_json")
            return body

        def _api(self, method, path, query):
            route, match, path_known = None, None, False
            for r_method, regex, handler, admin_only in ROUTES:
                found = regex.match(path)
                if not found:
                    continue
                path_known = True
                if r_method == method:
                    route, match = (handler, admin_only), found
                    break
            if route is None:
                raise HttpError(405 if path_known else 404,
                                "method_not_allowed" if path_known else "not_found")

            user = validate_init_data(self.headers.get("X-Telegram-Init-Data", ""),
                                      app.token, app.max_age)
            role = app.role_for(user["id"])
            if role is None:
                log.warning("Rejected Telegram user id=%s (not in the allow-list)", user["id"])
                raise HttpError(403, "forbidden", user_id=user["id"])
            handler, admin_only = route
            if admin_only and role != "admin":
                raise HttpError(403, "read_only")
            body = self._read_body() if method == "POST" else {}
            req = SimpleNamespace(user=user, role=role, query=query, body=body, match=match)
            self._json(200, handler(app, req))

        def _dispatch(self, method):
            try:
                parts = urllib.parse.urlsplit(self.path)
                if parts.path.startswith("/api/"):
                    self._api(method, parts.path, urllib.parse.parse_qs(parts.query))
                elif method == "GET":
                    self._static(parts.path)
                else:
                    raise HttpError(405, "method_not_allowed")
            except HttpError as exc:
                self._json(exc.status, {"error": exc.code, **exc.extra})
            except NotFound:
                self._json(404, {"error": "container_not_found"})
            except APIError as exc:
                self._json(502, {"error": "docker_error",
                                 "message": getattr(exc, "explanation", None) or str(exc)})
            except DockerException as exc:
                log.error("Docker unavailable: %s", exc)
                app.drop_client()
                self._json(503, {"error": "docker_unavailable"})
            except Exception:  # noqa: BLE001 - never leak internals to the client
                log.exception("Unhandled error for %s %s", method, self.path.split("?")[0])
                self._json(500, {"error": "internal_error"})

    return Handler


def set_menu_button(token: str, url: str) -> None:
    """Make the bot's chat menu button open the app (setChatMenuButton)."""
    monitor.post_json(
        f"https://api.telegram.org/bot{token}/setChatMenuButton",
        {"menu_button": {"type": "web_app", "text": "Containers", "web_app": {"url": url}}},
        "Telegram menu button",
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Telegram Mini App for the Docker monitor.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    cfg = load_config(os.environ)
    app = App(cfg["token"], cfg["admins"], cfg["viewers"], monitor.DB_PATH,
              cfg["max_age"], base_url=cfg["base_url"])
    server = ThreadingHTTPServer((args.host, args.port), make_handler(app))
    server.daemon_threads = True

    # Graceful shutdown: shutdown() must run outside the serving thread.
    def stop(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    if cfg["base_url"].startswith("https://"):
        # Network call: do it in the background so a slow Telegram API cannot delay startup.
        threading.Thread(target=set_menu_button, args=(cfg["token"], cfg["base_url"]),
                         daemon=True).start()
    else:
        log.warning("No https WEBAPP_URL/DOMAIN configured: the bot menu button is not updated")

    log.info("Web app on %s:%s (admins: %d, viewers: %d)", args.host, args.port,
             len(cfg["admins"]), len(cfg["viewers"]))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        log.info("Stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
