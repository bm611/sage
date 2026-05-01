import json
import shutil

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme

_THEME = Theme(
    {
        "sage.user": "bold bright_blue",
        "sage.tool": "bold cyan",
        "sage.ok": "green",
        "sage.err": "red",
        "sage.dim": "dim white",
        "sage.warn": "yellow",
    }
)

console = Console(theme=_THEME, highlight=False)

_SAGE_ASCII = r"""
   ███████╗ █████╗  ██████╗ ███████╗
   ██╔════╝██╔══██╗██╔════╝ ██╔════╝
   ███████╗███████║██║  ███╗█████╗  
   ╚════██║██╔══██║██║   ██║██╔══╝  
   ███████║██║  ██║╚██████╔╝███████╗
   ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
"""


def print_welcome():
    from .sysinfo import memory_status_markup

    term_width = shutil.get_terminal_size().columns

    console.print()
    for line in _SAGE_ASCII.strip("\n").split("\n"):
        text = Text(line, style="bold cyan")
        text.pad_left((term_width - len(line.rstrip())) // 2)
        console.print(text)

    console.print()
    console.print(
        "[sage.dim]AI coding assistant  ·  /help for commands  ·  /quit to exit[/sage.dim]",
        justify="center",
    )
    console.print(memory_status_markup(), justify="center")
    console.print()


def prompt_user() -> str | None:
    """Get user input with a styled input area. Returns None on EOF/Interrupt."""
    term_width = shutil.get_terminal_size().columns
    try:
        console.print()
        header = "─" * max(0, term_width - 8)
        console.print(
            f"[bright_blue]╭─[/bright_blue] [bold bright_blue]You[/bold bright_blue] [bright_blue]{header}[/bright_blue]"
        )
        user_input = console.input("[bold bright_blue]╰▸ [/bold bright_blue]").strip()
        return user_input
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None


def print_tool_call(tool_name: str, tool_input: dict):
    if tool_name == "bash":
        body = Syntax(
            tool_input.get("command", ""),
            "bash",
            theme="monokai",
            word_wrap=True,
            background_color="default",
        )
    elif tool_name == "str_replace":
        old = escape(tool_input.get("old_str", "")[:300])
        new = escape(tool_input.get("new_str", "")[:300])
        path = escape(tool_input.get("path", ""))
        body = Text.from_markup(
            f"[sage.dim]file:[/sage.dim] {path}\n"
            f"[red]- {old}[/red]\n"
            f"[green]+ {new}[/green]"
        )
    elif "path" in tool_input:
        parts = [f"[sage.dim]path:[/sage.dim] {escape(tool_input['path'])}"]
        for k, v in tool_input.items():
            if k != "path":
                parts.append(f"[sage.dim]{k}:[/sage.dim] {escape(str(v)[:120])}")
        body = Text.from_markup("\n".join(parts))
    elif "url" in tool_input or "query" in tool_input:
        val = tool_input.get("url") or tool_input.get("query", "")
        body = Text(escape(val))
    else:
        body = Text(escape(json.dumps(tool_input, indent=2)[:400]))

    console.print(
        Panel(
            body,
            title=f"[sage.tool]{tool_name}[/sage.tool]",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def print_tool_result(tool_name: str, content: str, is_error: bool):
    style = "red" if is_error else "green"
    title = "[sage.err]error[/sage.err]" if is_error else "[sage.ok]done[/sage.ok]"

    display = content
    if len(display) > 3000:
        display = (
            display[:3000]
            + f"\n[sage.dim]… {len(content) - 3000} more chars[/sage.dim]"
        )

    if tool_name == "read_file" and not is_error:
        body: object = Syntax(
            display,
            "text",
            theme="monokai",
            line_numbers=False,
            background_color="default",
        )
    else:
        body = Text.from_markup(escape(display))

    console.print(Panel(body, title=title, border_style=style, padding=(0, 1)))


def print_token_usage(context_tokens: int, token_budget: int = 128_000):
    percentage = min(100, (context_tokens / token_budget) * 100)
    console.print(
        f"[sage.dim]{percentage:.1f}% of {token_budget // 1000}k context[/sage.dim]",
        justify="right",
    )
