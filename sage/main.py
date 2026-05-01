import sys

import click

from .agent import AgentLoop
from .discovery import discover
from .providers import BaseProvider, OpenAICompatProvider, _TOKEN_BUDGET
from .selector import open_model_selector
from .ui import console, print_token_usage, print_welcome

_HELP = """\
Commands:
  /help           Show this help
  /quit  /exit    Exit
  /models         Open model selector
  /think on|off   Toggle thinking mode (Qwen3, DeepSeek-R1, …)
  /clear          Clear conversation history
  /tokens         Show token usage
  /compact        Compact conversation history
  /tools          List available tools
  /allow <tool>   Always-allow a tool without prompting
  /ram            Show current system memory usage
"""


def _auto_select(max_tokens: int | None, no_think: bool = False) -> BaseProvider | None:
    """Pick the first available local model silently, preferring loaded ones."""
    servers, _ = discover()

    # Prefer already-loaded models so we don't trigger a cold-load on startup.
    candidates: list[tuple] = []  # (loaded_first_key, srv, model)
    for srv in servers:
        if not srv.running:
            continue
        for m in srv.models:
            candidates.append((0 if m.loaded else 1, srv, m))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0])
    _, srv, model = candidates[0]

    provider = OpenAICompatProvider(
        model=model.id,
        base_url=srv.base_url,
        max_tokens=max_tokens,
        no_think=no_think,
    )
    cold_note = "" if model.loaded else " [yellow](cold)[/yellow]"
    console.print(
        f"[dim]Model:[/dim] [green]●[/green] "
        f"[cyan]{srv.label} — {model.label}[/cyan]{cold_note}  "
        f"[dim](change with /models)[/dim]"
    )
    return provider


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--max-tokens",
    default=None,
    type=int,
    help="Cap output tokens per response. If unset, the server decides (uses remaining context).",
)
@click.option(
    "--local",
    "-l",
    default=None,
    metavar="URL",
    help="Connect directly to an OpenAI-compat server (e.g. http://localhost:11434)",
)
@click.option("--yes", "-y", is_flag=True, help="Auto-approve all tool calls")
@click.option(
    "--no-think",
    is_flag=True,
    help="Disable chain-of-thought for thinking-capable models (Qwen3, DeepSeek-R1, …). "
    "Recommended when tool calls are emitted as text inside the <think> block.",
)
@click.argument("prompt", nargs=-1)
def main(
    max_tokens: int | None,
    local: str | None,
    yes: bool,
    no_think: bool,
    prompt: tuple[str, ...],
):
    """Sage — AI coding agent for your terminal."""

    provider: BaseProvider | None = None

    if local:
        import httpx

        try:
            r = httpx.get(
                f"{local}/v1/models",
                timeout=3,
                headers={"Authorization": "Bearer not-needed"},
            )
            models = [m["id"] for m in r.json().get("data", [])]
        except Exception:
            models = []
        if not models:
            console.print(f"[red]No models found at {local}[/red]")
            sys.exit(1)
        provider = OpenAICompatProvider(
            model=models[0], base_url=local, max_tokens=max_tokens, no_think=no_think
        )
        console.print(
            f"[dim]Model:[/dim] [green]●[/green] [cyan]{local} — {models[0]}[/cyan]"
        )
    else:
        with console.status("[dim]Detecting local models…[/dim]", spinner="dots"):
            provider = _auto_select(max_tokens, no_think=no_think)
        if provider is None:
            console.print(
                "[yellow]No local models found.[/yellow]  "
                "Start Ollama, LM Studio, or llama.cpp, then run [cyan]/models[/cyan]."
            )

    agent = AgentLoop(provider=provider)

    if yes:
        from .tools import TOOL_MAP

        agent.permissions._always_allow.update(TOOL_MAP.keys())

    # One-shot mode — requires a model
    if prompt:
        if agent.provider is None:
            console.print("[red]No model available for one-shot mode.[/red]")
            sys.exit(1)
        agent.run_turn(" ".join(prompt))
        console.print()
        print_token_usage(provider.input_tokens, provider.output_tokens, _TOKEN_BUDGET)
        return

    print_welcome()

    while True:
        try:
            console.print()
            user_input = console.input(
                "[bold bright_blue]>[/bold bright_blue] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input.split()
            cmd, args = parts[0].lower(), parts[1:]

            if cmd in ("/quit", "/exit"):
                break
            elif cmd == "/help":
                console.print(_HELP)
            elif cmd == "/models":
                current = agent.provider.model if agent.provider else None
                new_provider = open_model_selector(
                    console,
                    current_model=current,
                    max_tokens=max_tokens,
                    no_think=no_think,
                )
                if new_provider:
                    agent.provider = new_provider
                    provider = new_provider
                    console.print("[dim]Conversation reset for new model.[/dim]")
            elif cmd == "/think":
                if not args or args[0].lower() not in ("on", "off"):
                    state = "off" if no_think else "on"
                    console.print(
                        f"[dim]Thinking is currently {state}. Use /think on|off.[/dim]"
                    )
                else:
                    no_think = args[0].lower() == "off"
                    if agent.provider and isinstance(
                        agent.provider, OpenAICompatProvider
                    ):
                        agent.provider.no_think = no_think
                    console.print(
                        f"[dim]Thinking {'disabled' if no_think else 'enabled'}.[/dim]"
                    )
            elif cmd == "/clear":
                if agent.provider:
                    agent.provider.messages.clear()
                    agent.provider.input_tokens = 0
                    agent.provider.output_tokens = 0
                console.print("[dim]Conversation cleared.[/dim]")
            elif cmd == "/tokens":
                p = agent.provider
                print_token_usage(
                    p.input_tokens if p else 0,
                    p.output_tokens if p else 0,
                    _TOKEN_BUDGET,
                )
            elif cmd == "/ram":
                from .sysinfo import memory_status_markup

                console.print(memory_status_markup())
            elif cmd == "/compact":
                if agent.provider:
                    agent.provider.compact()
                    console.print("[dim]Compacted.[/dim]")
            elif cmd == "/tools":
                from .tools import ALL_TOOLS

                rows = "\n".join(
                    f"  [cyan]{t.name:<16}[/cyan] {t.description[:60]}"
                    for t in ALL_TOOLS
                )
                console.print(rows)
            elif cmd == "/allow":
                if args:
                    agent.permissions._always_allow.add(args[0])
                    agent.permissions._save()
                    console.print(f"[dim]Always allowing: {args[0]}[/dim]")
                else:
                    console.print(
                        f"[dim]Always-allowed: {sorted(agent.permissions._always_allow)}[/dim]"
                    )
            else:
                console.print(f"[dim]Unknown command: {cmd}. Type /help.[/dim]")
            continue

        if not agent.run_turn(user_input):
            break

        p = agent.provider
        if p:
            print_token_usage(p.input_tokens, p.output_tokens, _TOKEN_BUDGET)

    console.print("[dim]Bye.[/dim]")
