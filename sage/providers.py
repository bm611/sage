import json
import sys
from dataclasses import dataclass, field

import openai
import tiktoken
from rich.live import Live
from rich.markdown import Markdown

from .context import build_system_prompt
from .ui import console

_COMPACT_THRESHOLD = 0.80
_TOKEN_BUDGET = 128_000

# Cache for tokenizer to avoid re-initializing
_tokenizer = None


def _get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            _tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tokenizer = None
    return _tokenizer


def _estimate_tokens(text: str) -> int:
    """Estimate token count using tiktoken, fallback to character approximation."""
    tokenizer = _get_tokenizer()
    if tokenizer:
        try:
            return len(tokenizer.encode(text))
        except Exception:
            pass
    # Fallback: approximate 4 chars per token
    return len(text) // 4


@dataclass
class ToolCallInfo:
    id: str
    name: str
    input: dict


@dataclass
class StreamResult:
    stop_reason: str
    text: str
    tool_calls: list[ToolCallInfo] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


class BaseProvider:
    def __init__(self, model: str, max_tokens: int | None = None):
        self.model = model
        self.max_tokens = max_tokens  # None = let the server decide
        self.messages: list[dict] = []
        self.system_prompt = build_system_prompt()
        self.input_tokens = 0
        self.output_tokens = 0

    def should_compact(self) -> bool:
        return self.input_tokens > _TOKEN_BUDGET * _COMPACT_THRESHOLD

    def add_user(self, text: str):
        raise NotImplementedError

    def stream_response(self, tool_defs: list[dict]) -> StreamResult:
        raise NotImplementedError

    def add_tool_results(self, tool_calls: list[ToolCallInfo], results: list):
        raise NotImplementedError

    def compact(self):
        raise NotImplementedError


class OpenAICompatProvider(BaseProvider):
    def __init__(
        self,
        model: str,
        base_url: str,
        max_tokens: int | None = None,
        no_think: bool = False,
    ):
        super().__init__(model, max_tokens)
        self.base_url = base_url
        self.no_think = no_think
        self.client = openai.OpenAI(base_url=f"{base_url}/v1", api_key="not-needed")

    def add_user(self, text: str):
        self.messages.append({"role": "user", "content": text})

    def _to_openai_tools(self, tool_defs: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in tool_defs
        ]

    def stream_response(self, tool_defs: list[dict]) -> StreamResult:
        oai_tools = self._to_openai_tools(tool_defs)
        messages = [{"role": "system", "content": self.system_prompt}] + self.messages

        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            stream=True,
        )
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        if oai_tools:
            kwargs["tools"] = oai_tools
        if self.no_think:
            # Qwen3 / DeepSeek-R1 etc. honor this through their chat templates.
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

        stream = self.client.chat.completions.create(**kwargs)

        full_text = ""
        reasoning_text = ""
        tool_acc: dict[int, dict] = {}
        finish_reason: str | None = None
        reasoning_started = False

        console.print()
        with Live(Markdown(""), console=console, refresh_per_second=10) as live:
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                # Track token usage from streaming response
                if chunk.usage:
                    self.input_tokens = chunk.usage.prompt_tokens
                    self.output_tokens = chunk.usage.completion_tokens

                # Some local backends (LM Studio + Qwen3, DeepSeek, etc.) stream
                # the model's chain-of-thought in a non-standard `reasoning_content`
                # field. Show it dimmed so the user can see the model is working.
                reasoning_chunk = getattr(delta, "reasoning_content", None)
                if reasoning_chunk:
                    if not reasoning_started:
                        sys.stdout.write("\x1b[2m")  # dim on
                        reasoning_started = True
                    reasoning_text += reasoning_chunk
                    sys.stdout.write(reasoning_chunk)
                    sys.stdout.flush()

                if delta.content:
                    if reasoning_started:
                        sys.stdout.write("\x1b[0m\n")  # dim off + newline before answer
                        reasoning_started = False
                    full_text += delta.content
                    live.update(Markdown(full_text))

                if delta.tool_calls:
                    if reasoning_started:
                        sys.stdout.write("\x1b[0m\n")
                        reasoning_started = False
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_acc:
                            tool_acc[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_acc[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_acc[idx]["name"] += tc.function.name
                            if tc.function.arguments:
                                tool_acc[idx]["arguments"] += tc.function.arguments

        if reasoning_started:
            sys.stdout.write("\x1b[0m")  # always close the dim attribute
            reasoning_started = False

        # Estimate tokens if API didn't provide usage info
        if self.input_tokens == 0 and self.output_tokens == 0:
            # Estimate input tokens from messages
            messages_text = " ".join(str(m) for m in self.messages)
            self.input_tokens = _estimate_tokens(messages_text)
            # Estimate output tokens from generated text
            self.output_tokens = _estimate_tokens(full_text)

        if full_text:
            sys.stdout.write("\n")
            sys.stdout.flush()
        elif not tool_acc:
            # Nothing visible to the user — surface why so it isn't a mystery.
            if finish_reason == "length":
                cap = (
                    f"max_tokens={self.max_tokens}"
                    if self.max_tokens
                    else "the server's context window"
                )
                console.print(
                    f"[yellow]Model hit {cap} before producing an answer."
                    f" Try /compact, raise --max-tokens, or pick a non-thinking model.[/yellow]"
                )
            elif reasoning_text:
                console.print(
                    "[yellow]Model produced only reasoning content and no final answer."
                    f" finish_reason={finish_reason!r}.[/yellow]"
                )
            else:
                console.print(
                    f"[yellow]Empty response from model (finish_reason={finish_reason!r}).[/yellow]"
                )

        tool_calls = []
        for _, tc in sorted(tool_acc.items()):
            try:
                inp = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                inp = {}
            tool_calls.append(
                ToolCallInfo(
                    id=tc["id"] or f"call_{len(tool_calls)}",
                    name=tc["name"],
                    input=inp,
                )
            )

        assistant_msg: dict = {"role": "assistant", "content": full_text or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                }
                for tc in tool_calls
            ]
        self.messages.append(assistant_msg)

        return StreamResult(
            stop_reason="tool_use" if tool_calls else "end_turn",
            text=full_text,
            tool_calls=tool_calls,
        )

    def add_tool_results(self, tool_calls: list[ToolCallInfo], results: list):
        for tc, r in zip(tool_calls, results):
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": r.content,
                }
            )

    def compact(self):
        if len(self.messages) < 6:
            return
        to_summarize = self.messages[:-4]
        keep = self.messages[-4:]
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "system", "content": self.system_prompt}]
            + to_summarize
            + [
                {
                    "role": "user",
                    "content": "Summarize this conversation — key decisions, files changed, context needed to continue.",
                }
            ],
        )
        summary = resp.choices[0].message.content or ""
        self.messages = [
            {"role": "user", "content": f"[Conversation summary]\n\n{summary}"},
            {
                "role": "assistant",
                "content": "Understood, continuing from the summary.",
            },
        ] + keep
        self.input_tokens = 0
        self.output_tokens = 0
