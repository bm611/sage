import os
import platform
from pathlib import Path

_MEMORY_NAMES = ["CLAUDE.md", "SAGE.md", ".sage/memory.md"]
_TOKEN_BUDGET = 160_000


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


class ConversationContext:
    def __init__(self):
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt()
        self.input_tokens = 0
        self.output_tokens = 0

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant(self, content: list):
        self.messages.append({"role": "assistant", "content": content})

    def add_tool_results(self, results: list[dict]):
        self.messages.append({"role": "user", "content": results})

    def update_usage(self, input_tokens: int, output_tokens: int):
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def should_compact(self) -> bool:
        return self.input_tokens > _TOKEN_BUDGET * 0.8

    def compact(self, client, model: str):
        if len(self.messages) < 6:
            return

        to_summarize = self.messages[:-4]
        keep = self.messages[-4:]

        resp = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=to_summarize
            + [
                {
                    "role": "user",
                    "content": (
                        "Summarize the conversation so far in a few paragraphs. "
                        "Include key decisions, files changed, and any context needed to continue."
                    ),
                }
            ],
        )
        summary = resp.content[0].text
        self.messages = [
            {"role": "user", "content": f"[Conversation summary]\n\n{summary}"},
            {"role": "assistant", "content": "Understood, continuing from the summary."},
        ] + keep
        self.input_tokens = 0
        self.output_tokens = 0
