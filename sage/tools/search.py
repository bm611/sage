import glob as _glob
import subprocess

from .base import Tool, ToolResult


def _glob_search(inp: dict) -> ToolResult:
    pattern = inp["pattern"]
    base = inp.get("base_dir", ".")

    try:
        matches = sorted(_glob.glob(pattern, root_dir=base, recursive=True))
        if not matches:
            return ToolResult(content="No matches found")
        return ToolResult(content="\n".join(matches))
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


def _grep(inp: dict) -> ToolResult:
    pattern = inp["pattern"]
    path = inp.get("path", ".")
    case_sensitive = inp.get("case_sensitive", True)
    include = inp.get("include")

    try:
        # Prefer ripgrep, fall back to grep
        try:
            cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
            if not case_sensitive:
                cmd.append("-i")
            if include:
                cmd.extend(["--glob", include])
            cmd.extend([pattern, path])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except FileNotFoundError:
            cmd = ["grep", "-rn", "--color=never"]
            if not case_sensitive:
                cmd.append("-i")
            if include:
                cmd.extend(["--include", include])
            cmd.extend([pattern, path])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        output = result.stdout.strip()
        if not output:
            return ToolResult(content="No matches found")

        lines = output.splitlines()
        if len(lines) > 100:
            output = "\n".join(lines[:100]) + f"\n... ({len(lines) - 100} more lines truncated)"
        return ToolResult(content=output)
    except subprocess.TimeoutExpired:
        return ToolResult(content="Search timed out", is_error=True)
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


glob_tool = Tool(
    name="glob",
    description="Find files matching a glob pattern. Supports ** for recursive matching.",
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py'"},
            "base_dir": {"type": "string", "description": "Directory to search from (default: cwd)"},
        },
        "required": ["pattern"],
    },
    execute=_glob_search,
)

grep_tool = Tool(
    name="grep",
    description="Search for a regex pattern in files. Uses ripgrep if available.",
    input_schema={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search for"},
            "path": {"type": "string", "description": "File or directory to search (default: cwd)"},
            "case_sensitive": {"type": "boolean", "description": "Case-sensitive search (default: true)"},
            "include": {"type": "string", "description": "Glob to filter files, e.g. '*.py'"},
        },
        "required": ["pattern"],
    },
    execute=_grep,
)
