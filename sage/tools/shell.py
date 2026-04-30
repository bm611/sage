import os
import subprocess

from .base import Tool, ToolResult


def _execute_bash(inp: dict) -> ToolResult:
    command = inp["command"]
    timeout = inp.get("timeout", 30)
    cwd = inp.get("working_dir", os.getcwd())

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout
        if result.stderr:
            output += ("\nSTDERR:\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit {result.returncode}]"
        return ToolResult(content=output or "(no output)", is_error=result.returncode != 0)
    except subprocess.TimeoutExpired:
        return ToolResult(content=f"Timed out after {timeout}s", is_error=True)
    except Exception as e:
        return ToolResult(content=str(e), is_error=True)


bash_tool = Tool(
    name="bash",
    description=(
        "Execute a shell command and return stdout/stderr. "
        "Use for running scripts, installing packages, checking git status, etc."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
            "working_dir": {"type": "string", "description": "Working directory (default: cwd)"},
        },
        "required": ["command"],
    },
    execute=_execute_bash,
)
