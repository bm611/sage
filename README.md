# Sage

A local AI coding agent for the terminal.

## Features

- **Local AI Agent**: A Python-based CLI tool that can interact with the terminal through its package.
- **API Integration**: Uses openai, rich, httpx, click, and anthropic libraries to integrate with external APIs.
- **Command Line Interface**: Provides a simple command-line interface for interacting with the terminal.
- **Tooling**: Leverages specialized tools (Shell, Web, Filesystem) to provide context-aware actions.

## Architecture

Sage operates by translating high-level natural language prompts into a sequence of tool calls.

1. **Context Gathering**: The agent first gathers system context (e.g., running commands, file structure, environment variables) using the `context` module.
2. **Tool Selection**: Based on the context and the user's prompt, the agent selects the most appropriate tool (e.g., `shell`, `web`, `files`).
3. **Execution**: The tool is called, executes within its defined scope, and returns structured output.
4. **Response Generation**: The AI uses the structured output from the tool execution to synthesize a helpful, natural language response or command for the user.

## Getting Started

### Installation

```bash
pip install -e .
```

### Usage

The package can be invoked as:

```bash
sage <command>
```

**Basic Commands:**

- `help`: Show available commands.
- `list`: List installed packages.
- `version`: Show version information.

### Advanced Usage Examples

The true power of Sage comes from using its integrated tools:

**1. Shell Interaction (Running commands):**
*   **Goal:** See what the latest git commit is.
*   **Command:** `sage shell git rev-parse HEAD`

**2. File System Management:**
*   **Goal:** Find all Python files modified in the last two days.
*   **Command:** `sage files search-files --mtime 2d --ext py`

**3. Web Search:**
*   **Goal:** Find the current best practices for asynchronous Python code.
*   **Command:** `sage web search "best async python practices 2024"`