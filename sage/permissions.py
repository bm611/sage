import json
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

_CONFIG_DIR = Path.home() / ".sage"
_PERMISSIONS_FILE = _CONFIG_DIR / "permissions.json"

# Read-only tools that are safe to run without prompting
_DEFAULT_ALLOW = {"read_file", "list_dir", "glob", "grep"}


class PermissionManager:
    def __init__(self, console: Console):
        self.console = console
        self._always_allow: set[str] = set(_DEFAULT_ALLOW)
        self._always_deny: set[str] = set()
        self._load()

    def _load(self):
        if _PERMISSIONS_FILE.exists():
            try:
                data = json.loads(_PERMISSIONS_FILE.read_text())
                self._always_allow = set(data.get("always_allow", _DEFAULT_ALLOW))
                self._always_deny = set(data.get("always_deny", []))
            except Exception:
                pass

    def _save(self):
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        _PERMISSIONS_FILE.write_text(
            json.dumps(
                {
                    "always_allow": sorted(self._always_allow),
                    "always_deny": sorted(self._always_deny),
                },
                indent=2,
            )
        )

    def check(self, tool_name: str, tool_input: dict) -> bool:
        if tool_name in self._always_deny:
            self.console.print(f"[red]Denied (always-deny):[/red] {tool_name}")
            return False
        if tool_name in self._always_allow:
            return True
        return self._prompt(tool_name, tool_input)

    def _format_preview(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "bash":
            return escape(tool_input.get("command", ""))
        if tool_name in ("write_file", "str_replace", "read_file"):
            path = tool_input.get("path", "")
            extra = ""
            if tool_name == "str_replace":
                old = tool_input.get("old_str", "")[:80]
                new = tool_input.get("new_str", "")[:80]
                extra = f"\n[dim]  - {escape(old)}[/dim]\n[dim]  + {escape(new)}[/dim]"
            elif tool_name == "write_file":
                chars = len(tool_input.get("content", ""))
                extra = f"  [dim]({chars} chars)[/dim]"
            return escape(path) + extra
        if tool_name in ("web_fetch", "web_search"):
            return escape(tool_input.get("url") or tool_input.get("query", ""))
        return escape(json.dumps(tool_input, indent=2)[:300])

    def _prompt(self, tool_name: str, tool_input: dict) -> bool:
        preview = self._format_preview(tool_name, tool_input)
        self.console.print()
        self.console.print(
            Panel(
                preview,
                title=f"[yellow bold]Allow [cyan]{tool_name}[/cyan]?[/yellow bold]",
                border_style="yellow",
                padding=(0, 1),
            )
        )
        self.console.print(
            "  [dim]\\[y][/dim] yes  "
            "[dim]\\[a][/dim] always  "
            "[dim]\\[n][/dim] no  "
            "[dim]\\[d][/dim] always-deny  "
            ": ",
            end="",
        )

        try:
            choice = self.console.input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            return False

        if choice == "a":
            self._always_allow.add(tool_name)
            self._save()
            return True
        if choice == "d":
            self._always_deny.add(tool_name)
            self._save()
            return False
        return choice == "y"
