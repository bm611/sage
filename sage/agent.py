import openai

from .permissions import PermissionManager
from .providers import BaseProvider, ToolCallInfo
from .tools import ALL_TOOLS, TOOL_MAP
from .tools.base import ToolResult
from .ui import console, print_tool_call, print_tool_result


class AgentLoop:
    def __init__(self, provider: BaseProvider | None = None):
        self.provider = provider
        self.permissions = PermissionManager(console)
        self._tool_defs = [t.to_api_dict() for t in ALL_TOOLS]

    def run_turn(self, user_input: str) -> bool:
        """Process one user message. Returns False on fatal error."""
        if self.provider is None:
            console.print("[yellow]No model selected.[/yellow] Run [cyan]/models[/cyan] to pick one.")
            return True

        self.provider.add_user(user_input)

        if self.provider.should_compact():
            console.print("[dim]Compacting conversation history…[/dim]")
            self.provider.compact()

        while True:
            try:
                result = self.provider.stream_response(self._tool_defs)
            except openai.AuthenticationError:
                console.print("[red]Authentication error — check your API key.[/red]")
                return False
            except openai.APIConnectionError as e:
                console.print(f"[red]Connection error: {e}[/red]")
                # Remove the unanswered user message from history
                if self.provider.messages and self.provider.messages[-1]["role"] == "user":
                    self.provider.messages.pop()
                break
            except KeyboardInterrupt:
                console.print("\n[dim]Interrupted.[/dim]")
                break

            if result.stop_reason != "tool_use" or not result.tool_calls:
                break

            executed = [self._run_tool(tc) for tc in result.tool_calls]
            self.provider.add_tool_results(result.tool_calls, executed)

        return True

    def _run_tool(self, tc: ToolCallInfo) -> ToolResult:
        console.print()
        print_tool_call(tc.name, tc.input)

        if not self.permissions.check(tc.name, tc.input):
            r = ToolResult(content="Denied by user.", is_error=True, tool_use_id=tc.id)
            print_tool_result(tc.name, r.content, r.is_error)
            return r

        tool = TOOL_MAP.get(tc.name)
        if not tool:
            r = ToolResult(content=f"Unknown tool: {tc.name}", is_error=True, tool_use_id=tc.id)
        else:
            try:
                r = tool.execute(tc.input)
                r.tool_use_id = tc.id
            except Exception as e:
                r = ToolResult(content=str(e), is_error=True, tool_use_id=tc.id)

        print_tool_result(tc.name, r.content, r.is_error)
        return r
