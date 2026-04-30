from pathlib import Path

from .base import Tool, ToolResult


def _read_file(inp: dict) -> ToolResult:
    path = Path(inp["path"]).expanduser()
    start = inp.get("start_line")
    end = inp.get("end_line")

    try:
        if not path.exists():
            return ToolResult(content=f"File not found: {path}", is_error=True)
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)

        offset = (start - 1) if start else 0
        if start or end:
            lines = lines[(start - 1 if start else 0) : end]

        numbered = "".join(f"{offset + i + 1:5} | {line}" for i, line in enumerate(lines))
        return ToolResult(content=numbered or "(empty file)")
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


def _write_file(inp: dict) -> ToolResult:
    path = Path(inp["path"]).expanduser()
    content = inp["content"]

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(content=f"Wrote {len(content)} chars to {path}")
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


def _list_dir(inp: dict) -> ToolResult:
    path = Path(inp.get("path", ".")).expanduser().resolve()

    try:
        if not path.exists():
            return ToolResult(content=f"Not found: {path}", is_error=True)
        if not path.is_dir():
            return ToolResult(content=f"Not a directory: {path}", is_error=True)

        entries = []
        for entry in sorted(path.iterdir()):
            if entry.is_dir():
                entries.append(f"{entry.name}/")
            else:
                size = entry.stat().st_size
                if size >= 1024 * 1024:
                    size_str = f"{size / 1024 / 1024:.1f}MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.1f}KB"
                else:
                    size_str = f"{size}B"
                entries.append(f"{entry.name}  ({size_str})")

        return ToolResult(content="\n".join(entries) or "(empty)")
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


def _str_replace(inp: dict) -> ToolResult:
    path = Path(inp["path"]).expanduser().resolve()
    old_str = inp["old_str"]
    new_str = inp["new_str"]

    try:
        if not path.exists():
            return ToolResult(content=f"File not found: {path}", is_error=True)

        content = path.read_text(encoding="utf-8")
        count = content.count(old_str)

        if count == 0:
            return ToolResult(content=f"String not found in {path}", is_error=True)
        if count > 1:
            return ToolResult(
                content=f"Found {count} occurrences — provide more context to make it unique",
                is_error=True,
            )

        path.write_text(content.replace(old_str, new_str, 1), encoding="utf-8")
        return ToolResult(content=f"Replaced in {path}")
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


read_file_tool = Tool(
    name="read_file",
    description="Read a file's contents with line numbers. Use start_line/end_line to read a slice.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "start_line": {"type": "integer", "description": "First line to read (1-indexed)"},
            "end_line": {"type": "integer", "description": "Last line to read (inclusive)"},
        },
        "required": ["path"],
    },
    execute=_read_file,
)

write_file_tool = Tool(
    name="write_file",
    description="Write content to a file, creating it and any parent dirs if needed.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    execute=_write_file,
)

list_dir_tool = Tool(
    name="list_dir",
    description="List files and subdirectories in a directory.",
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: cwd)"},
        },
    },
    execute=_list_dir,
)

str_replace_tool = Tool(
    name="str_replace",
    description=(
        "Replace an exact string in a file. The old_str must appear exactly once. "
        "Preferred for targeted edits — faster and safer than writing the whole file."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "old_str": {"type": "string", "description": "Exact string to find (must be unique in file)"},
            "new_str": {"type": "string", "description": "Replacement string"},
        },
        "required": ["path", "old_str", "new_str"],
    },
    execute=_str_replace,
)
