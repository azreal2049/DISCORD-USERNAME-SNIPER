from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "scripts"))

import sniper
from sniper import (
    CONSOLE,
    Dashboard,
    Lane,
    Metrics,
    ProbeResult,
    UsernameGenerator,
    mock_check,
    verify_token,
)


async def token_only_run(settings: sniper.Settings) -> None:
    """Run sniper.py's scanner and dashboard with direct token lanes only."""
    tokens = list(settings.discord_tokens)
    if settings.token and settings.token not in tokens:
        tokens.insert(0, settings.token)
    if not tokens:
        CONSOLE.print("[bold red]No discord_token found in config.json.[/]")
        return

    ok, profile = await verify_token(tokens[0])
    if not ok:
        detail = profile.get("_status") or profile.get("_error") or "unknown error"
        CONSOLE.print(f"[bold red]Token verification failed:[/] {detail}")
        return

    CONSOLE.print(
        f"[bold white]Token OK:[/] {profile.get('username', '?')} "
        f"(id {profile.get('id', '?')})"
    )

    lanes = [Lane("token", token=token) for token in tokens[:2]]
    lanes = lanes[:1]
    for lane in lanes:
        lane.pace = 4.0
        await lane.start()

    try:
        generator = UsernameGenerator(
            settings.length,
            settings.charset,
            settings.limit,
            settings.prefix,
        )
        usernames = generator.generate()
    except ValueError as exc:
        CONSOLE.print(f"[bold red]Generator error:[/] {exc}")
        for lane in lanes:
            await lane.close()
        return

    if not usernames:
        CONSOLE.print("[bold red]No usernames to scan.[/]")
        for lane in lanes:
            await lane.close()
        return

    metrics = Metrics()
    metrics.started = time.monotonic()
    dashboard = Dashboard(settings, lanes, metrics)
    queue: asyncio.Queue[str] = asyncio.Queue()
    for username in usernames:
        queue.put_nowait(username)

    write_lock = asyncio.Lock()

    async def save_hit(username: str) -> None:
        async with write_lock:
            try:
                with settings.output_file.open("a", encoding="utf-8") as file:
                    file.write(username + "\n")
            except OSError as exc:
                CONSOLE.print(f"[bold red]Could not save {username}:[/] {exc}")

    async def lane_worker(lane: Lane) -> None:
        while True:
            try:
                username = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                if lane.cooldown_until > time.monotonic():
                    await asyncio.sleep(lane.cooldown_until - time.monotonic())

                result: ProbeResult
                if settings.mock:
                    result = await mock_check(username)
                else:
                    result = await lane.check(username)

                if result.state == "available":
                    metrics.hits += 1
                    metrics.record("AVAILABLE", username, "bold red on white")
                    await save_hit(username)
                elif result.state == "taken":
                    metrics.record("TAKEN", username, "white")
                elif result.state == "rate_limited":
                    metrics.rate_limits += 1
                    metrics.record("RATE LIMIT", username, "bold yellow")
                    queue.put_nowait(username)
                elif result.state == "auth_fail":
                    metrics.errors += 1
                    metrics.record("TOKEN DEAD", username, "bold red")
                    return
                else:
                    metrics.errors += 1
                    metrics.record("ERROR", f"{username} {result.detail}", "dim white")
                metrics.checked += 1
            finally:
                queue.task_done()

    worker_tasks = [asyncio.create_task(lane_worker(lane)) for lane in lanes]
    try:
        with sniper.Live(
            dashboard.render(),
            console=CONSOLE,
            refresh_per_second=10,
            transient=False,
        ) as live:
            while not queue.empty() or any(not task.done() for task in worker_tasks):
                live.update(dashboard.render())
                await asyncio.sleep(0.15)
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            live.update(dashboard.render())
        CONSOLE.print(
            f"\n[bold white]Complete.[/] {metrics.hits} hit(s) saved to "
            f"{settings.output_file}"
        )
    finally:
        for lane in lanes:
            await lane.close()


original_run = sniper.run


async def merged_run(settings: sniper.Settings) -> None:
    if settings.discord_tokens:
        await token_only_run(settings)
    else:
        await original_run(settings)


sniper.run = merged_run


if __name__ == "__main__":
    sniper.main()
