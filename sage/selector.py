import os
import select
import sys
import termios
import tty

import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from .discovery import ModelRef, Server, discover
from .providers import BaseProvider, OpenAICompatProvider
from .sysinfo import (
    estimate_size_from_id,
    fmt_gb,
    memory_status_markup,
    would_exceed_ram,
)


def _warm_up(base_url: str, model_id: str) -> str | None:
    """
    Force the server to load the model into memory by issuing a tiny
    chat completion. Returns an error string on failure, else None.
    Uses a generous read timeout because cold-loading large models can
    take tens of seconds to several minutes.
    """
    try:
        r = httpx.post(
            f"{base_url}/v1/chat/completions",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "."}],
                "max_tokens": 1,
                "stream": False,
            },
            headers={"Authorization": "Bearer not-needed"},
            timeout=httpx.Timeout(connect=5, read=600, write=10, pool=10),
        )
        r.raise_for_status()
        return None
    except Exception as e:
        return str(e)


def _getch() -> str:
    """Return a semantic key name from one raw keypress."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        ch = os.read(fd, 1)
        if ch == b"\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                seq = os.read(fd, 2)
                if seq == b"[A":
                    return "up"
                if seq == b"[B":
                    return "down"
            return "escape"
        if ch in (b"\r", b"\n"):
            return "enter"
        if ch == b"\x03":  # Ctrl-C
            return "quit"
        return ch.decode("utf-8", errors="ignore")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _model_size_bytes(model: ModelRef) -> int | None:
    return model.size_bytes if model.size_bytes else estimate_size_from_id(model.id)


def _render(
    items: list[tuple[Server, ModelRef]],
    selected: int,
    offline: list[Server],
) -> Panel:
    t = Text()
    t.append_text(Text.from_markup(memory_status_markup()))
    t.append("\n\n")

    for i, (srv, model) in enumerate(items):
        is_sel = i == selected
        t.append("  ▶ " if is_sel else "    ", style="bold cyan" if is_sel else "")
        if model.loaded:
            t.append("● ", style="green")
        else:
            t.append("○ ", style="yellow")
        t.append(srv.label, style="bold white" if is_sel else "white")
        t.append(" — ", style="dim")
        t.append(model.label, style="bold cyan" if is_sel else "")
        size = _model_size_bytes(model)
        if size:
            approx = "" if model.size_bytes else "~"
            t.append(f"  [{approx}{fmt_gb(size)}]", style="dim")
        if not model.loaded:
            t.append("  (cold)", style="dim yellow")
        t.append("\n")

    if offline:
        if items:
            t.append("\n")
        for srv in offline:
            t.append("    ○ ", style="dim")
            t.append(f"{srv.label} — offline\n", style="dim")

    return Panel(
        t,
        title="[bold cyan]  Select Model  [/bold cyan]",
        subtitle="[dim]↑↓ navigate  enter select  q cancel[/dim]",
        border_style="cyan",
        padding=(0, 1),
    )


def open_model_selector(
    console: Console,
    current_model: str | None = None,
    max_tokens: int | None = None,
    no_think: bool = False,
) -> BaseProvider | None:
    """
    Open the interactive model picker.
    Returns a configured provider on selection, or None if cancelled / nothing found.
    """
    with console.status("[dim]Probing local servers…[/dim]", spinner="dots"):
        servers, _ = discover()

    items: list[tuple[Server, ModelRef]] = [
        (srv, m) for srv in servers if srv.running for m in srv.models
    ]
    # Loaded (hot) models first; preserve original order within each group.
    items.sort(key=lambda pair: 0 if pair[1].loaded else 1)
    offline = [srv for srv in servers if not srv.running]

    if not items:
        console.print("[yellow]No local models found.[/yellow]")
        console.print(
            "[dim]Start Ollama (11434), LM Studio (1234), or llama.cpp (8080) and try again.[/dim]"
        )
        return None

    # Pre-select the currently active model if possible, else first loaded model.
    selected = 0
    if current_model:
        for i, (_, m) in enumerate(items):
            if m.id == current_model:
                selected = i
                break
    else:
        for i, (_, m) in enumerate(items):
            if m.loaded:
                selected = i
                break

    with Live(
        _render(items, selected, offline),
        console=console,
        refresh_per_second=30,
        transient=True,   # erase the panel after selection
    ) as live:
        while True:
            key = _getch()
            if key == "up":
                selected = max(0, selected - 1)
                live.update(_render(items, selected, offline))
            elif key == "down":
                selected = min(len(items) - 1, selected + 1)
                live.update(_render(items, selected, offline))
            elif key == "enter":
                break
            elif key in ("q", "escape", "quit"):
                return None

    srv, model = items[selected]

    if not model.loaded:
        size = _model_size_bytes(model)
        will_exceed, mem = would_exceed_ram(size)
        if will_exceed:
            approx = "" if model.size_bytes else "~"
            console.print(
                f"[bold red]⚠  Low memory warning[/bold red] — "
                f"loading [cyan]{model.label}[/cyan] (~{fmt_gb(size)}) "
                f"may exceed safe RAM."
            )
            console.print(
                f"[dim]System: {fmt_gb(mem.available)} free of "
                f"{fmt_gb(mem.total)} ({mem.percent:.0f}% used). "
                f"Loading another {approx}{fmt_gb(size)} could swap or freeze your machine.[/dim]"
            )
            try:
                ans = console.input("[yellow]Load anyway? [y/N] [/yellow]").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = ""
            if ans not in ("y", "yes"):
                console.print("[dim]Cancelled.[/dim]")
                return None

        with console.status(
            f"[dim]Loading [cyan]{model.label}[/cyan] into memory…  "
            f"(this can take a while for large models)[/dim]",
            spinner="dots",
        ):
            err = _warm_up(srv.base_url, model.id)
        if err:
            console.print(f"[yellow]Warm-up failed:[/yellow] {err}")
            console.print("[dim]Continuing anyway — the model will load on first prompt.[/dim]")

    console.print(f"[dim]Model:[/dim] [green]●[/green] [cyan]{srv.label} — {model.label}[/cyan]")
    return OpenAICompatProvider(
        model=model.id, base_url=srv.base_url, max_tokens=max_tokens, no_think=no_think
    )
