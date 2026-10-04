# MADE BY SVJ
# Discord username scanner
#
# token mode -> POST username-attempt-unauthed with auth header (fast)
# proxy mode -> same endpoint through proxies from proxies.txt
# mock mode  -> simulated, clearly labelled
#
# config.json and proxies.txt must already exist in this folder.

from __future__ import annotations

import argparse
import asyncio
import base64
import itertools
import json as _json
import logging
import math
import os
import random
import shutil
import string
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

try:
    import msvcrt
except ImportError:
    msvcrt = None

from rich.console import Console, Group
from rich.live import Live
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

try:
    from aiohttp_socks import ProxyConnector
except ImportError:
    ProxyConnector = None

LOGGER = logging.getLogger("username-checker")
CONSOLE = Console()

C_BORDER = "red"
C_TITLE = "bold white"
C_LABEL = "bold white"
C_VALUE = "white"
C_ACCENT = "bold red"
C_DIM = "dim white"

_HERE = Path(__file__).resolve().parent
CONFIG_FILE = _HERE / "config.json"
PROXY_FILE = _HERE / "proxies.txt"

DEFAULT_PACE = 4.0


# ── ANSI helpers ────────────────────────────────────────────

def _rgb(r, g, b): return f"\033[38;2;{r};{g};{b}m"
def _goto(row, col): return f"\033[{row};{col}H"
def _write(v): sys.stdout.write(v); sys.stdout.flush()
def _clear(): return "\033[2J\033[H"
def _hide_cursor(): return "\033[?25l"
def _show_cursor(): return "\033[?25h"


def _key_pressed() -> bool:
    return msvcrt is not None and msvcrt.kbhit()


def _read_key() -> bytes:
    return msvcrt.getch() if msvcrt else b""


def _skip_pressed() -> bool:
    if _key_pressed():
        _read_key(); return True
    return False


def _term_size(default=(120, 35)):
    try:
        s = shutil.get_terminal_size(default)
        return s.columns, s.lines
    except Exception:
        return default


# ── CONFIG / PROXIES ────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONSOLE.print(f"[bold red]config.json not found at {CONFIG_FILE}[/]")
        return {}
    raw = CONFIG_FILE.read_text(encoding="utf-8")
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")
    try:
        return _json.loads(raw)
    except _json.JSONDecodeError as exc:
        CONSOLE.print(f"[bold red]config.json invalid JSON:[/] {exc.msg} line {exc.lineno}")
        return {}


def parse_tokens(cfg: dict) -> list[str]:
    out, seen = [], set()
    lst = cfg.get("discord_tokens")
    if isinstance(lst, list):
        for t in lst:
            s = str(t or "").strip()
            if s and s not in seen:
                seen.add(s); out.append(s)
    single = str(cfg.get("discord_token") or "").strip()
    if single and single not in seen:
        seen.add(single); out.append(single)
    return out


def load_proxies(path: Path) -> list[str]:
    if not path.exists():
        return []
    out, seen = [], set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if "://" not in s:
            s = "http://" + s
        try:
            parsed = urlparse(s)
            port = parsed.port
        except (ValueError, AttributeError):
            continue
        if parsed.hostname and port and s not in seen:
            seen.add(s); out.append(s)
    return out


# ── BOOT ANIMATION ──────────────────────────────────────────

BOOT_LOGO = r"""
██╗   ██╗███████╗███████╗██████╗ ███╗   ██╗ █████╗ ███╗   ███╗███████╗    ███████╗███╗   ██╗██╗██████╗ ███████╗██████╗
██║   ██║██╔════╝██╔════╝██╔══██╗████╗  ██║██╔══██╗████╗ ████║██╔════╝    ██╔════╝████╗  ██║██║██╔══██╗██╔════╝██╔══██╗
██║   ██║███████╗█████╗  ██████╔╝██╔██╗ ██║███████║██╔████╔██║█████╗      ███████╗██╔██╗ ██║██║██████╔╝█████╗  ██████╔╝
██║   ██║╚════██║██╔══╝  ██╔══██╗██║╚██╗██║██╔══██║██║╚██╔╝██║██╔══╝      ╚════██║██║╚██╗██║██║██╔═══╝ ██╔══╝  ██╔══██╗
╚██████╔╝███████║███████╗██║  ██║██║ ╚████║██║  ██║██║ ╚═╝ ██║███████╗    ███████║██║ ╚████║██║██║     ███████╗██║  ██║
 ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚═╝     ╚═╝╚══════╝    ╚══════╝╚═╝  ╚═══╝╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
""".strip("\n")

_HEX = "0123456789ABCDEF"
_bg_color = lambda r, g, b: f"\033[48;2;{r};{g};{b}m"


def _boot_hex_rain(width, height, duration=1.4):
    started = time.time()
    columns = {c: random.randint(-height, 0) for c in range(1, width + 1)}
    speeds = {c: random.uniform(0.6, 1.8) for c in range(1, width + 1)}
    while time.time() - started < duration:
        if _skip_pressed():
            return
        out = [_hide_cursor()]
        for col, y in columns.items():
            head = int(y)
            if 1 <= head <= height:
                ch = random.choice(_HEX)
                out.append(f"{_goto(head, col)}{_rgb(255,255,255)}{ch}")
            for trail in range(1, 6):
                row = head - trail
                if 1 <= row <= height:
                    intensity = max(0, 200 - trail * 35)
                    ch = random.choice(_HEX)
                    out.append(f"{_goto(row, col)}{_rgb(intensity,0,0)}{ch}")
            columns[col] = y + speeds[col]
            if columns[col] > height + 8:
                columns[col] = random.randint(-12, 0)
                speeds[col] = random.uniform(0.6, 1.8)
        _write("".join(out))
        time.sleep(0.035)
    _write(_clear())


def _boot_logo_build(width, height, logo_lines):
    lh, lw = len(logo_lines), max(len(l) for l in logo_lines)
    top, left = (height - lh) // 2, max(1, (width - lw) // 2)
    for progress in range(0, lw + 1, 2):
        if _skip_pressed():
            break
        out = [_hide_cursor()]
        glow_row = top + lh // 2
        if 1 <= glow_row <= height:
            out.append(f"{_goto(glow_row, 1)}{_bg_color(40,0,0)}{' ' * width}")
        for offset, line in enumerate(logo_lines):
            row = top + offset
            if not 1 <= row <= height:
                continue
            segment = ""
            for col, ch in enumerate(line):
                if col > progress:
                    segment += " "
                elif col == progress:
                    segment += f"{_rgb(255,255,255)}{ch}"
                elif col > progress - 8:
                    segment += f"{_rgb(255,80,80)}{ch}"
                else:
                    segment += f"{_rgb(180,0,0)}{ch}"
            out.append(f"{_goto(row, left)}{segment}")
        _write("".join(out))
        time.sleep(0.018)
    out = [_hide_cursor()]
    for offset, line in enumerate(logo_lines):
        row = top + offset
        if 1 <= row <= height:
            out.append(f"{_goto(row, left)}{_rgb(180,0,0)}{line}")
    _write("".join(out))


def _boot_idle(width, height, logo_lines, duration=2.2):
    lh, lw = len(logo_lines), max(len(l) for l in logo_lines)
    top, left = (height - lh) // 2, max(1, (width - lw) // 2)

    margin_r = max(2, top - 3)
    margin_b = max(2, top + lh + 3)
    corner_left = max(2, left - 4)
    corner_right = min(width - 1, left + lw + 4)

    frame = 0
    started = time.time()
    title = "S V J   ·   S N I P E R"

    while time.time() - started < duration:
        if _key_pressed():
            _read_key()
            return
        frame += 1
        out = [_hide_cursor()]

        for r in range(max(1, top - 3), min(height, top + lh + 4)):
            out.append(f"{_goto(r, 1)}{' ' * width}")

        gold = f"{_rgb(255, 215, 0)}"
        if 1 <= margin_r <= height:
            out.append(f"{_goto(margin_r, corner_left)}{gold}╔")
            out.append(f"{_goto(margin_r, corner_right)}{gold}╗")
        if 1 <= margin_b <= height:
            out.append(f"{_goto(margin_b, corner_left)}{gold}╚")
            out.append(f"{_goto(margin_b, corner_right)}{gold}╝")

        title_col = max(1, (width - len(title)) // 2)
        out.append(f"{_goto(margin_r + 1, title_col)}{gold}\033[1m{title}\033[0m")

        sweep = int((frame * 2) % (lw + 40)) - 20
        for offset, line in enumerate(logo_lines):
            row = top + offset
            colored = ""
            for col, ch in enumerate(line):
                if ch == " ":
                    colored += ch
                elif abs(col - sweep) <= 1:
                    colored += f"{_rgb(255,255,255)}{ch}"
                elif abs(col - sweep) <= 4:
                    colored += f"{_rgb(255,60,60)}{ch}"
                else:
                    colored += f"{_rgb(160,0,0)}{ch}"
            out.append(f"{_goto(row, left)}{colored}")

        pulse = abs(math.sin(frame * 0.08))
        pr = int(120 + 135 * pulse)
        prompt = "[ LOADING ]"
        prompt_col = max(1, (width - len(prompt)) // 2)
        out.append(
            f"{_goto(margin_b - 1, prompt_col)}"
            f"\033[1m{_rgb(pr, 0, 0)}{prompt}\033[0m"
        )

        _write("".join(out))
        time.sleep(0.03)


def cinematic_boot():
    logo_lines = [l.rstrip() for l in BOOT_LOGO.split("\n")]
    width, height = _term_size()
    _write(_hide_cursor() + _clear())
    try:
        _boot_hex_rain(width, height)
        _boot_logo_build(width, height, logo_lines)
        _boot_idle(width, height, logo_lines)
    except Exception:
        pass
    finally:
        _write(_show_cursor() + "\033[0m" + _clear())


# ── SETTINGS / METRICS ──────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Settings:
    length: int
    charset_name: str
    prefix: str | None
    limit: int | None
    mode: str
    pace: float
    proxy_lanes: int
    output_file: Path
    discord_tokens: tuple = ()
    proxies: tuple = ()
    interactive: bool = True

    @property
    def charset(self) -> str:
        return {
            "letters": string.ascii_lowercase,
            "digits": string.digits,
            "mixed": string.ascii_lowercase + string.digits,
        }[self.charset_name]


@dataclass
class Metrics:
    checked: int = 0
    hits: int = 0
    errors: int = 0
    rate_limits: int = 0
    started: float = field(default_factory=time.monotonic)
    recent_log: deque = field(default_factory=lambda: deque(maxlen=14))

    @property
    def rps(self) -> float:
        return self.checked / max(time.monotonic() - self.started, 0.001)

    def record(self, label, username, style):
        self.recent_log.append((style, f"[{label}] {username}"))


class UsernameGenerator:
    def __init__(self, length, charset, limit, prefix=None):
        self.length, self.charset, self.limit = length, charset, limit
        self.prefix = (prefix or "").strip().lower() or None

    def generate(self) -> list:
        prefix = self.prefix or ""
        fill_len = self.length - len(prefix)
        if fill_len <= 0:
            return [prefix] if prefix else []
        total = len(self.charset) ** fill_len
        if self.limit is not None and self.limit < total:
            indexes = random.sample(range(total), self.limit)
            return [prefix + self._decode(i, fill_len) for i in indexes]
        values = [prefix + "".join(p) for p in itertools.product(self.charset, repeat=fill_len)]
        random.shuffle(values)
        return values

    def _decode(self, index, length):
        res = []
        base = len(self.charset)
        for _ in range(length):
            index, r = divmod(index, base)
            res.append(self.charset[r])
        return "".join(reversed(res))


DISCORD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DISCORD_ME = "https://discord.com/api/v9/users/@me"
DISCORD_CHECK = "https://discord.com/api/v9/unique-username/username-attempt-unauthed"


def _super_properties() -> str:
    payload = {
        "os": "Windows", "browser": "Chrome", "device": "",
        "system_locale": "en-US", "browser_user_agent": DISCORD_UA,
        "browser_version": "124.0.0.0", "os_version": "10",
        "referrer": "https://discord.com/register",
        "referring_domain": "discord.com",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable", "client_build_number": 300000,
        "client_event_source": None,
    }
    raw = _json.dumps(payload, separators=(",", ":")).encode()
    return base64.b64encode(raw).decode()


def _base_headers(token=None) -> dict:
    h = {
        "User-Agent": DISCORD_UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/register",
        "X-Super-Properties": _super_properties(),
    }
    if token:
        h["Authorization"] = token
    return h


async def verify_token(token: str):
    if not token:
        return False, {"_error": "empty"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as s:
            async with s.get(DISCORD_ME, headers=_base_headers(token)) as r:
                if r.status == 200:
                    return True, await r.json(content_type=None)
                body = ""
                try:
                    body = (await r.text())[:200]
                except Exception:
                    pass
                return False, {"_status": r.status, "_body": body}
    except Exception as exc:
        return False, {"_error": type(exc).__name__}


@dataclass
class ScanResult:
    username: str
    state: str
    retry_after: float = 0.0
    detail: str = ""


async def token_check(session, username: str) -> ScanResult:
    try:
        async with session.post(DISCORD_CHECK, json={"username": username}) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                taken = data.get("taken")
                if taken is None:
                    return ScanResult(username, "error", detail="no taken field")
                return ScanResult(username, "taken" if taken else "available")

            if r.status == 429:
                retry = 1.0
                try:
                    data = await r.json(content_type=None)
                    retry = float(data.get("retry_after", 1.0))
                except Exception:
                    h = r.headers.get("Retry-After")
                    if h:
                        try:
                            retry = float(h)
                        except ValueError:
                            pass
                if retry > 100:
                    retry = retry / 1000.0
                retry = min(max(retry, 1.0), 120.0)
                return ScanResult(username, "rate_limited", retry_after=retry)

            if r.status == 401:
                return ScanResult(username, "auth_fail", detail="401 token invalid")

            if r.status == 403:
                return ScanResult(username, "error", detail="403 blocked")

            body = ""
            try:
                body = (await r.text())[:160]
            except Exception:
                pass
            return ScanResult(username, "error", detail=f"HTTP {r.status}: {body}")

    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return ScanResult(username, "error", detail=type(exc).__name__)


async def proxy_check(session, username: str, proxy: str) -> ScanResult:
    request_proxy = proxy if not proxy.startswith("socks") else None
    try:
        async with session.post(
            DISCORD_CHECK, json={"username": username}, proxy=request_proxy
        ) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                taken = data.get("taken")
                if taken is None:
                    return ScanResult(username, "error", detail="no taken field")
                return ScanResult(username, "taken" if taken else "available")

            if r.status == 429:
                retry = 1.0
                try:
                    data = await r.json(content_type=None)
                    retry = float(data.get("retry_after", 1.0))
                except Exception:
                    pass
                return ScanResult(username, "rate_limited", retry_after=min(retry, 60.0))

            if r.status == 403:
                return ScanResult(username, "error", detail="403 blocked")

            body = ""
            try:
                body = (await r.text())[:120]
            except Exception:
                pass
            return ScanResult(username, "error", detail=f"HTTP {r.status}: {body}")

    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        return ScanResult(username, "error", detail=type(exc).__name__)


class Dashboard:
    def __init__(self, settings, metrics, lane_count):
        self.settings = settings
        self.metrics = metrics
        self.lane_count = lane_count

    def render(self):
        mode_label = {"mock": "MOCK", "proxy": "PROXY"}.get(self.settings.mode, "TOKEN")
        spin = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int(time.monotonic() * 10) % 10]

        header = Table.grid(expand=True)
        for _ in range(4):
            header.add_column(style=C_LABEL, ratio=1)
        header.add_row(
            "MODE", f"[{C_ACCENT}]{mode_label}[/]",
            "LENGTH", f"[{C_VALUE}]{self.settings.length}c"
                       f"{' | ' + self.settings.prefix if self.settings.prefix else ''}[/]",
        )
        header.add_row(
            "CHARSET", f"[{C_VALUE}]{self.settings.charset_name}[/]",
            "PACE", f"[{C_VALUE}]{self.settings.pace:.1f}s | lanes {self.lane_count}[/]",
        )

        m = Table.grid(expand=True, padding=(0, 2))
        for _ in range(2):
            m.add_column(justify="right", style=C_LABEL)
            m.add_column(justify="left", style=C_VALUE)
        m.add_row("CHECKED", str(self.metrics.checked),
                  "HITS", f"[bold red]{self.metrics.hits}[/]")
        m.add_row("ERRORS", str(self.metrics.errors),
                  "429s", f"[bold red]{self.metrics.rate_limits}[/]")
        m.add_row("RPS", f"{self.metrics.rps:.2f}",
                  "STATUS", f"[bold red]{spin} ACTIVE[/]")

        audit = Text()
        for style, line in self.metrics.recent_log:
            audit.append(line + "\n", style=style)

        return Group(
            Panel(header, title=f"[{C_TITLE}]{spin} SNIPER // SESSION[/]", border_style=C_BORDER),
            Panel(m, title=f"[{C_TITLE}]LIVE METRICS[/]", border_style=C_BORDER),
            Panel(audit or Text("Waiting for results...", style=C_DIM),
                  title=f"[{C_TITLE}]AUDIT LOG[/]", border_style=C_BORDER),
        )


async def run(settings: Settings) -> None:
    metrics = Metrics()
    queue: asyncio.Queue = asyncio.Queue()

    try:
        gen = UsernameGenerator(
            settings.length, settings.charset, settings.limit, settings.prefix
        )
        usernames = gen.generate()
    except ValueError as exc:
        CONSOLE.print(f"[bold red]Generator error:[/] {exc}")
        return

    if not usernames:
        CONSOLE.print("[bold red]No usernames to scan.[/]")
        return
    for u in usernames:
        queue.put_nowait(u)

    write_lock = asyncio.Lock()

    async def save_hit(u: str):
        async with write_lock:
            try:
                with settings.output_file.open("a", encoding="utf-8") as h:
                    h.write(u + "\n")
            except OSError as exc:
                LOGGER.warning("write %s failed: %s", u, exc)

    if settings.mode == "mock":
        async def worker():
            while True:
                try:
                    u = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await asyncio.sleep(0.02)
                    roll = random.random()
                    if roll < 0.08:
                        metrics.hits += 1
                        metrics.record("DEMO AVAILABLE", u, "bold red on white")
                        await save_hit(u)
                    else:
                        metrics.record("DEMO TAKEN", u, "white")
                    metrics.checked += 1
                finally:
                    queue.task_done()

        worker_tasks = [asyncio.create_task(worker())]
        dashboard = Dashboard(settings, metrics, 1)

    elif settings.mode == "token":
        token = settings.discord_tokens[0]
        session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20.0),
            headers=_base_headers(token),
        )

        async def worker():
            while True:
                try:
                    u = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    result = await token_check(session, u)
                    if result.state == "available":
                        metrics.hits += 1
                        metrics.record("AVAILABLE", u, "bold red on white")
                        await save_hit(u)
                    elif result.state == "taken":
                        metrics.record("TAKEN", u, "white")
                    elif result.state == "rate_limited":
                        metrics.rate_limits += 1
                        metrics.record("RATE LIMIT", f"{u} ({result.retry_after:.0f}s)", "bold red")
                        await asyncio.sleep(result.retry_after)
                        queue.put_nowait(u)
                        continue
                    elif result.state == "auth_fail":
                        metrics.errors += 1
                        metrics.record("TOKEN DEAD", u, "bold red")
                        return
                    else:
                        metrics.errors += 1
                        if metrics.errors <= 10 or metrics.errors % 25 == 0:
                            metrics.record("ERROR", f"{u} {result.detail}", "dim white")
                    metrics.checked += 1
                    await asyncio.sleep(settings.pace)
                finally:
                    queue.task_done()

        worker_tasks = [asyncio.create_task(worker())]
        dashboard = Dashboard(settings, metrics, 1)

    else:
        pool = list(settings.proxies)

        async def lane_worker(proxy: str):
            headers = _base_headers()
            connector = None
            if proxy.startswith("socks"):
                if ProxyConnector is None:
                    return
                connector = ProxyConnector.from_url(proxy)
            async with aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=15.0),
                headers=headers,
            ) as session:
                while True:
                    try:
                        u = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        result = await proxy_check(session, u, proxy)
                        if result.state == "available":
                            metrics.hits += 1
                            metrics.record("AVAILABLE", u, "bold red on white")
                            await save_hit(u)
                        elif result.state == "taken":
                            metrics.record("TAKEN", u, "white")
                        elif result.state == "rate_limited":
                            metrics.rate_limits += 1
                            queue.put_nowait(u)
                            return
                        else:
                            metrics.errors += 1
                            if metrics.errors <= 10 or metrics.errors % 25 == 0:
                                metrics.record("ERROR", f"{u} {result.detail}", "dim white")
                            queue.put_nowait(u)
                            return
                        metrics.checked += 1
                        await asyncio.sleep(settings.pace)
                    finally:
                        queue.task_done()

        lane_count = max(1, min(settings.proxy_lanes, len(pool) or 1))
        worker_tasks = [asyncio.create_task(lane_worker(p)) for p in pool[:lane_count]]
        dashboard = Dashboard(settings, metrics, lane_count)

    metrics.started = time.monotonic()

    try:
        with Live(dashboard.render(), console=CONSOLE,
                  refresh_per_second=10, transient=False) as live:
            while not queue.empty() or any(not t.done() for t in worker_tasks):
                live.update(dashboard.render())
                await asyncio.sleep(0.2)
            for t in worker_tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            live.update(dashboard.render())
        CONSOLE.print(
            f"\n[bold white]Complete.[/] {metrics.hits} hit(s) saved to {settings.output_file}"
        )
    finally:
        pass


def parse_args(argv=None) -> Settings:
    p = argparse.ArgumentParser(description="Discord username scanner")
    p.add_argument("command", nargs="?", choices=("start",))
    p.add_argument("--length", type=int, choices=(3, 4, 5, 6, 7, 8), default=4)
    p.add_argument("--charset", choices=("letters", "digits", "mixed"), default="letters")
    p.add_argument("--prefix", default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--mode", choices=("token", "proxy", "mock"), default="token")
    p.add_argument("--pace", type=float, default=DEFAULT_PACE)
    p.add_argument("--proxy-lanes", type=int, default=10)
    p.add_argument("--output", type=Path, default=_HERE / "hits.txt")
    args = p.parse_args(argv)

    if args.limit is not None and args.limit < 1:
        p.error("limit must be positive")
    if args.proxy_lanes < 1:
        p.error("proxy-lanes must be >= 1")
    if args.pace <= 0:
        p.error("pace must be > 0")

    interactive = args.command == "start" or (argv is None and len(sys.argv) == 1)
    cfg = load_config()
    tokens = tuple(parse_tokens(cfg))
    proxies: tuple = ()
    if args.mode == "proxy":
        proxies = tuple(load_proxies(PROXY_FILE))

    return Settings(
        length=args.length, charset_name=args.charset, prefix=args.prefix,
        limit=args.limit, mode=args.mode, pace=args.pace,
        proxy_lanes=args.proxy_lanes, output_file=args.output,
        discord_tokens=tokens, proxies=proxies, interactive=interactive,
    )


def interactive_settings(output_file, tokens, proxies) -> Settings:
    CONSOLE.print("[bold white]SNIPER[/]  Discord username scanner")
    CONSOLE.print("Type [bold white]start[/] to begin, or [bold white]quit[/] to exit.")
    while True:
        cmd = CONSOLE.input("[red]>[/] ").strip().lower()
        if cmd in {"quit", "exit", "q"}:
            raise KeyboardInterrupt
        if cmd == "start":
            break
        CONSOLE.print("Use start or quit.", style="bold red")

    if not tokens:
        cfg = load_config()
        tokens = tuple(parse_tokens(cfg))

    CONSOLE.print("")
    CONSOLE.print("[bold white]Choose mode:[/]")
    CONSOLE.print("  [bold red]token[/]  - fast check endpoint with your token")
    CONSOLE.print("  [bold red]proxy[/]  - same endpoint through proxies.txt")
    CONSOLE.print("  [bold red]mock[/]   - simulated only")
    while True:
        mode = CONSOLE.input(
            "[red]mode[/] [token/proxy/mock] (default token): "
        ).strip().lower() or "token"
        if mode in {"token", "proxy", "mock"}:
            break
        CONSOLE.print("Type token, proxy, or mock.", style="bold red")

    if mode == "proxy" and not proxies:
        proxies = tuple(load_proxies(PROXY_FILE))

    if mode == "token":
        if not tokens:
            CONSOLE.print("[bold red]No token found in config.json.[/]")
            return interactive_settings(output_file, (), proxies)
        CONSOLE.print("[white]Verifying token via /users/@me...[/]")
        ok, prof = asyncio.run(verify_token(tokens[0]))
        if not ok:
            detail = prof.get("_status") or prof.get("_error") or "?"
            CONSOLE.print(f"[bold red]Token invalid ({detail}).[/]")
            return interactive_settings(output_file, (), proxies)
        CONSOLE.print(
            f"[bold white]Token OK:[/] {prof.get('username', '?')} "
            f"(id {prof.get('id', '?')})"
        )
        tokens = (tokens[0],)

    if mode == "proxy" and not proxies:
        CONSOLE.print("[bold red]proxies.txt is empty or missing.[/]")
        return interactive_settings(output_file, tokens, ())

    length = int(CONSOLE.input("Length [3-8] (default 4): ").strip() or "4")
    if length not in {3, 4, 5, 6, 7, 8}:
        raise ValueError("length must be 3-8")
    charset = CONSOLE.input(
        "Charset [letters/digits/mixed] (default letters): "
    ).strip().lower() or "letters"
    if charset not in {"letters", "digits", "mixed"}:
        raise ValueError("invalid charset")

    prefix = CONSOLE.input("Prefix (optional, blank = random): ").strip().lower() or None
    if prefix and len(prefix) >= length:
        raise ValueError("prefix too long")

    limit = int(CONSOLE.input("How many usernames? (default 500): ").strip() or "500")
    if limit < 1:
        raise ValueError("limit must be positive")

    pace = DEFAULT_PACE
    if mode == "token":
        pace_text = CONSOLE.input(
            f"Pace between requests in seconds (default {DEFAULT_PACE:.0f}): "
        ).strip()
        if pace_text:
            pace = float(pace_text)
            if pace < 0.5:
                raise ValueError("pace must be >= 0.5")

    proxy_lanes = 10
    if mode == "proxy":
        proxy_lanes = int(CONSOLE.input(
            f"Parallel lanes (default 10, {len(proxies)} proxies): "
        ).strip() or "10")

    return Settings(
        length=length, charset_name=charset, prefix=prefix, limit=limit,
        mode=mode, pace=pace, proxy_lanes=proxy_lanes,
        output_file=output_file,
        discord_tokens=tokens if mode == "token" else (),
        proxies=proxies if mode == "proxy" else (),
        interactive=True,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING, format="%(message)s",
        handlers=[RichHandler(console=CONSOLE, show_path=False)],
    )
    try:
        if os.getenv("SNIPER_NO_BOOT") != "1":
            cinematic_boot()

        settings = parse_args()
        if settings.interactive:
            settings = interactive_settings(
                output_file=settings.output_file,
                tokens=settings.discord_tokens,
                proxies=settings.proxies,
            )
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        CONSOLE.print("\n[bold red]Stopped by user.[/]")
    except OSError as exc:
        CONSOLE.print(f"[bold red]I/O error:[/] {exc}")
    except (ValueError, EOFError) as exc:
        CONSOLE.print(f"[bold red]Input error:[/] {exc}")


if __name__ == "__main__":
    main()