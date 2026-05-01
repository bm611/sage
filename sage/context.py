import os
import platform
from pathlib import Path

_MEMORY_NAMES = ["CLAUDE.md", "SAGE.md", ".sage/memory.md"]


def _load_project_memory() -> str:
    found: list[str] = []
    current = Path.cwd()

    for _ in range(5):
        for name in _MEMORY_NAMES:
            p = current / name
            if p.exists():
                try:
                    found.append(f"### {p}\n{p.read_text(encoding='utf-8').strip()}")
                except Exception:
                    pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    return "\n\n".join(found)


def build_system_prompt() -> str:
    cwd = os.getcwd()
    os_name = platform.system()
    shell = os.environ.get("SHELL", "sh").split("/")[-1]
    memory = _load_project_memory()

    prompt = f"""\
You are Sage, an AI coding assistant running in the terminal.

You help with software engineering tasks: reading and writing code, running commands, searching codebases, debugging, and explaining things.

Environment:
- Working directory: {cwd}
- OS: {os_name}
- Shell: {shell}

Guidelines:
- Be concise in prose, complete in code.
- Before editing a file, read it first to understand its structure.
- Prefer str_replace for targeted edits; use write_file for new files or full rewrites.
- When exploring an unfamiliar codebase, start with list_dir and glob.
- For shell commands, run them directly — don't narrate before executing."""

    if memory:
        prompt += f"\n\n## Project Notes\n\n{memory}"

    return prompt



