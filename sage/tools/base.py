from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolResult:
    content: str
    tool_use_id: str = ""
    is_error: bool = False


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    execute: Callable[[dict[str, Any]], ToolResult]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
