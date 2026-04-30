from .base import Tool, ToolResult
from .shell import bash_tool
from .files import read_file_tool, write_file_tool, list_dir_tool, str_replace_tool
from .search import glob_tool, grep_tool
from .web import web_fetch_tool, web_search_tool

ALL_TOOLS: list[Tool] = [
    bash_tool,
    read_file_tool,
    write_file_tool,
    list_dir_tool,
    str_replace_tool,
    glob_tool,
    grep_tool,
    web_fetch_tool,
    web_search_tool,
]

TOOL_MAP: dict[str, Tool] = {tool.name: tool for tool in ALL_TOOLS}
