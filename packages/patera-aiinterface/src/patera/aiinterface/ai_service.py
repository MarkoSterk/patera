"""
AI interface for Patera applications.

An AiService turns decorated methods into model calls:

    class Assistant(AiService):
        service_provider = OpenAIServiceProvider()
        history_provider = ChatHistory()            # for @history

        @history
        @system_prompt("You are a helpful assistant.")
        @user_prompt("<:message>")
        async def chat(self, session_id: str | None, message: str) -> ChatResponse: ...

Every call follows the same steps:

1. the user prompt is filled from the method's arguments (``<:name>``);
2. the messages start with the current system prompt;
3. with ``@history``, the session's last HISTORY_LIMIT messages follow
   (a ``session_id`` of None starts a new session). With HISTORY_SUMMARY, a
   digest of the older messages comes first, and the digest is updated in
   the background as the conversation grows;
4. with ``@augmentation``, the most relevant documents follow in a context
   message. With history and REWRITE_QUERY, a follow-up question is first
   rewritten into a standalone one for the search;
5. the user message goes last, and the service provider sends the messages;
6. with ``@history``, the user's message and the answer are saved (not the
   documents). A streamed answer is saved once the stream ends.

The returned ChatResponse carries the session id, so a new session's id can be
handed back to the client.
"""

from __future__ import annotations

import copy
import inspect
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Generic, Optional, TypeVar, cast

from pydantic import BaseModel, Field, model_validator

from patera import Patera
from patera.base_extension import BaseExtension
from patera.ctx import current_request, has_request_context, request_context
from patera.utilities import run_in_background

from .augmentation_provider.config import AugmentationConfig
from .history_provider import BaseHistoryProvider, HistorySummary
from .service_provider import BaseServiceProvider, ChatMessage, ChatResponse


DEFAULT_SUMMARY_PROMPT = (
    "You maintain the summary of a conversation between a user and an assistant. "
    "Merge the new messages into the summary. Keep facts, decisions, the user's "
    "preferences and goals, names, numbers and open questions; leave out small "
    "talk and repetition. Write in the language of the conversation, in the third "
    "person. Reply with the summary only."
)


class HistorySummaryConfig(BaseModel):
    """
    Rolling summary of long conversations (AiServiceConfig.HISTORY_SUMMARY).

    Each call sends the summary, then every message it does not cover. Once at
    least EVERY messages beyond the latest HISTORY_LIMIT are uncovered, they are
    merged into the summary in the background, so a call sends at most
    HISTORY_LIMIT + EVERY messages besides the summary.
    """

    EVERY: int = Field(
        10,
        ge=2,
        description="Messages beyond HISTORY_LIMIT that trigger a summary update",
    )
    MAX_WORDS: int = Field(250, ge=20, description="Length limit given to the model")
    PROMPT: str = Field(
        DEFAULT_SUMMARY_PROMPT, description="System prompt of the summary call"
    )
    TEMPLATE: str = Field(
        "Summary of the earlier conversation:\n<:summary>",
        description="Message that carries the summary; <:summary> is replaced",
    )


class AiServiceConfig(BaseModel):
    """
    AI service configuration model
    """

    API_KEY: Optional[str] = Field(None, description="API key for the AI provider")
    BASE_URL: str = Field(description="Base URL for the AI provider API")
    ORGANIZATION_ID: Optional[str] = Field(
        None, description="OpenAI organization ID (OpenAI-Organization header)"
    )
    PROJECT_ID: Optional[str] = Field(
        None, description="OpenAI project ID (OpenAI-Project header)"
    )
    TIMEOUT: int = Field(
        60, description="Timeout for AI provider requests in seconds. Default 60 s"
    )
    MODEL: str = Field(description="Model name to use for AI requests")
    TEMPERATURE: Optional[float] = Field(
        0.0, description="Temperature for AI model responses (None: provider default)"
    )
    RESPONSE_FORMAT: Optional[dict[str, Any]] = Field(
        None,
        description=(
            'Response format, e.g. {"type": "json_object"} or a "json_schema" '
            "format (OpenAI response_format; Ollama format). None: plain text."
        ),
    )
    MAX_RETRIES: int = Field(
        0, ge=0, description="Retries of a failed connection to the AI provider"
    )
    HISTORY_LIMIT: Optional[int] = Field(
        10,
        ge=1,
        description=(
            "With @history, how many of the session's latest messages are sent "
            "(user and assistant messages count separately). None sends all."
        ),
    )
    HISTORY_SUMMARY: Optional[HistorySummaryConfig] = Field(
        None,
        description="Rolling summary of older messages (off when not set).",
    )
    AUGMENTATION: Optional[AugmentationConfig] = Field(
        None,
        description="Settings of the augmentation provider (defaults when not set).",
    )

    @model_validator(mode="after")
    def _summary_needs_a_limit(self) -> "AiServiceConfig":
        if self.HISTORY_SUMMARY is not None and self.HISTORY_LIMIT is None:
            raise ValueError(
                "HISTORY_SUMMARY needs a HISTORY_LIMIT: the summary replaces the "
                "messages beyond that limit."
            )
        return self


AppT = TypeVar("AppT", bound="Patera[Any]")
ServiceT = TypeVar("ServiceT", bound=BaseServiceProvider, default=BaseServiceProvider)


@dataclass(slots=True)
class _PreparedCall:
    """The messages of one call and what @history saves afterwards."""

    messages: list[ChatMessage]
    session_id: Any
    user_message: ChatMessage
    use_history: bool


_PLACEHOLDER = re.compile(r"<:([A-Za-z_][A-Za-z0-9_]*)>")


def _fill_placeholders(template: str, arguments: dict[str, Any]) -> str:
    """
    Replaces ``<:name>`` with the argument ``name`` in one pass: text that an
    argument inserts (a user's message, say) is never scanned again, so it
    cannot pull other arguments into the prompt. Unknown names stay as they are.
    """

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(arguments[name]) if name in arguments else match.group(0)

    return _PLACEHOLDER.sub(value, template)


def _is_streaming(func: Callable[..., Any]) -> bool:
    """True for methods annotated ``-> AsyncIterator[...]``."""
    annotation = inspect.get_annotations(func).get("return", "")
    return "AsyncIterator" in str(annotation) or "AsyncGenerator" in str(annotation)


class AiService(
    BaseExtension[AppT, AiServiceConfig],
    Generic[AppT, ServiceT],
):
    """
    Base extension for model calls. Set ``service_provider``, and
    ``history_provider`` / ``augmentation_provider`` when methods use
    ``@history`` / ``@augmentation``.
    """

    service_provider: ServiceT
    history_provider: Optional[BaseHistoryProvider] = None
    augmentation_provider: Any = None

    def init(self) -> None:
        """Checks the providers the methods need and prepares them."""
        name = type(self).__name__
        cls = type(self)
        methods: list[Any] = []
        for attribute in dir(cls):
            method = getattr(cls, attribute, None)
            if getattr(method, "__ai_method__", False):
                methods.append(method)
        needs_history = any(m.__use_history__ for m in methods)
        needs_augmentation = any(m.__use_augmentation__ for m in methods)

        self._summarizing: set[Any] = set()
        if needs_history:
            if not isinstance(self.history_provider, BaseHistoryProvider):
                raise TypeError(
                    f"{name} has @history methods, so it needs a history_provider "
                    "(a BaseHistoryProvider instance, e.g. SqlHistoryProvider)."
                )
            if (
                self.configs.HISTORY_SUMMARY is not None
                and not self.history_provider.supports_summaries
            ):
                raise TypeError(
                    f"HISTORY_SUMMARY is set, but {type(self.history_provider).__name__} "
                    "does not store summaries (implement load_since, load_summary and "
                    "save_summary, or use SqlHistoryProvider)."
                )
            # Each service gets its own copy: the class attribute is shared by
            # every application that uses this class.
            self.history_provider = copy.copy(self.history_provider)
            self.history_provider.bind(self)

        if self.augmentation_provider is not None or needs_augmentation:
            from .augmentation_provider import BaseAugmentationProvider

            provider = copy.copy(self.augmentation_provider)
            self.augmentation_provider = provider
            if not isinstance(provider, BaseAugmentationProvider):
                raise TypeError(
                    f"{name} has @augmentation methods, so it needs an "
                    "augmentation_provider (a BaseAugmentationProvider instance)."
                )
            # Checks that the embedding libraries are installed; the model
            # itself is loaded on first use, so CLI commands do not load it.
            provider.bind(self.augmentation_configs, self)

    @property
    def augmentation_configs(self) -> AugmentationConfig:
        """AiServiceConfig.AUGMENTATION, or the defaults when it is not set."""
        return self.configs.AUGMENTATION or AugmentationConfig.model_validate({})

    # ---- the pipeline -------------------------------------------------------

    async def _prepare(
        self, func: Callable[..., Any], arguments: dict[str, Any]
    ) -> _PreparedCall:
        use_history: bool = func.__use_history__  # type: ignore[attr-defined]
        use_augmentation: bool = func.__use_augmentation__  # type: ignore[attr-defined]
        system_prompt: str = func.__system_prompt__  # type: ignore[attr-defined]
        user_text = _fill_placeholders(func.__user_prompt__, arguments)  # type: ignore[attr-defined]

        messages: list[ChatMessage] = []
        if system_prompt:
            messages.append(
                ChatMessage(
                    role="system", content=_fill_placeholders(system_prompt, arguments)
                )
            )

        session_id: Any = None
        summary: Optional[HistorySummary] = None
        earlier: list[ChatMessage] = []
        if use_history:
            history = cast(BaseHistoryProvider, self.history_provider)
            session_id = arguments.get("session_id")
            if session_id is None:
                session_id = await history.new_session_id()
            elif self.configs.HISTORY_SUMMARY is not None:
                summary, earlier = await self._load_with_summary(history, session_id)
            else:
                earlier = await history.load(session_id, self.configs.HISTORY_LIMIT)
        if summary is not None:
            template = cast(HistorySummaryConfig, self.configs.HISTORY_SUMMARY).TEMPLATE
            messages.append(
                ChatMessage(
                    role="system", content=template.replace("<:summary>", summary.text)
                )
            )
        messages.extend(earlier)

        if use_augmentation:
            context = await self._context_message(user_text, earlier, summary)
            if context is not None:
                messages.append(context)

        user_message = ChatMessage(role="user", content=user_text)
        messages.append(user_message)
        return _PreparedCall(
            messages=messages,
            session_id=session_id,
            user_message=user_message,
            use_history=use_history,
        )

    async def _load_with_summary(
        self, history: BaseHistoryProvider, session_id: Any
    ) -> tuple[Optional[HistorySummary], list[ChatMessage]]:
        """The summary and every message after it (at most LIMIT + EVERY)."""
        summary = await history.load_summary(session_id)
        settings = cast(HistorySummaryConfig, self.configs.HISTORY_SUMMARY)
        cap = cast(int, self.configs.HISTORY_LIMIT) + settings.EVERY
        after = summary.covers_up_to if summary else None
        stored = await history.load_since(session_id, after, cap)
        return summary, [item.message for item in stored]

    def _plain_configs(self) -> AiServiceConfig:
        """Settings for helper calls: plain text, deterministic."""
        return self.configs.model_copy(
            update={"RESPONSE_FORMAT": None, "TEMPERATURE": 0.0}
        )

    async def update_summary(self, session_id: Any) -> bool:
        """
        Merges the session's oldest messages into its summary once at least
        EVERY messages beyond the latest HISTORY_LIMIT are not covered by it
        (see HistorySummaryConfig). Runs in the background after each answer;
        returns True if a new summary was saved. Safe to call at any time,
        also from a CLI command or a scheduled job.
        """
        settings = self.configs.HISTORY_SUMMARY
        if settings is None or session_id in self._summarizing:
            return False
        self._summarizing.add(session_id)
        try:
            history = cast(BaseHistoryProvider, self.history_provider)
            summary = await history.load_summary(session_id)
            after = summary.covers_up_to if summary else None
            uncovered = await history.load_since(session_id, after, None)
            keep = cast(int, self.configs.HISTORY_LIMIT)
            older = uncovered[: max(len(uncovered) - keep, 0)]
            if len(older) < settings.EVERY:
                return False
            text = await self._summarize(
                summary.text if summary else None, [item.message for item in older]
            )
            if not text:
                return False
            new = HistorySummary(text=text, covers_up_to=older[-1].position)
            return await history.save_summary(session_id, new, summary)
        finally:
            self._summarizing.discard(session_id)

    async def _update_summary_later(self, session_id: Any) -> None:
        """
        update_summary() for the background task: in a context of its own,
        because the request (and its database session) may be over by then.
        """
        with request_context(app=self.app):
            await self.update_summary(session_id)

    async def _summarize(
        self, previous: Optional[str], messages: list[ChatMessage]
    ) -> str:
        settings = cast(HistorySummaryConfig, self.configs.HISTORY_SUMMARY)
        transcript = "\n".join(f"{m.role}: {m.content}" for m in messages)
        request = (
            f"Summary so far:\n{previous or '(none yet)'}\n\n"
            f"New messages:\n{transcript}\n\n"
            f"Write the updated summary in at most {settings.MAX_WORDS} words."
        )
        prompt = [
            ChatMessage(role="system", content=settings.PROMPT),
            ChatMessage(role="user", content=request),
        ]
        response = await self.service_provider.complete(prompt, self._plain_configs())
        return response.message.content.strip()

    async def _context_message(
        self,
        user_text: str,
        earlier: list[ChatMessage],
        summary: Optional[HistorySummary] = None,
    ) -> Optional[ChatMessage]:
        """The retrieved documents as a context message (None if nothing matched)."""
        configs = self.augmentation_configs
        query = user_text
        if configs.REWRITE_QUERY and (earlier or summary):
            query = await self._standalone_question(user_text, earlier, summary)
        request = current_request.request if has_request_context() else None
        texts = await self.augmentation_provider.relevant_texts(query, request)
        if not texts:
            return None
        documents = "\n\n".join(
            f"[{number}] {text}" for number, text in enumerate(texts, 1)
        )
        return ChatMessage(
            role="system",
            content=configs.CONTEXT_TEMPLATE.replace("<:documents>", documents),
        )

    async def _standalone_question(
        self,
        user_text: str,
        earlier: list[ChatMessage],
        summary: Optional[HistorySummary] = None,
    ) -> str:
        """
        Asks the model to rewrite a follow-up question so it can be searched
        without the conversation ("what about the second one?" -> a full
        question). Falls back to the question itself if the answer is empty.
        """
        transcript = "\n".join(f"{m.role}: {m.content}" for m in earlier)
        if summary is not None:
            transcript = f"(summary of the earlier part) {summary.text}\n{transcript}"
        prompt = [
            ChatMessage(
                role="system", content=self.augmentation_configs.REWRITE_PROMPT
            ),
            ChatMessage(
                role="user",
                content=f"Conversation:\n{transcript}\n\nFollow-up question: {user_text}",
            ),
        ]
        # Plain text, deterministic: the method's RESPONSE_FORMAT does not apply.
        response = await self.service_provider.complete(prompt, self._plain_configs())
        return response.message.content.strip() or user_text

    async def _remember(self, call: _PreparedCall, answer: str) -> None:
        if call.use_history:
            await cast(BaseHistoryProvider, self.history_provider).append(
                call.session_id,
                [call.user_message, ChatMessage(role="assistant", content=answer)],
            )
            if self.configs.HISTORY_SUMMARY is not None:
                # After the answer, so the user never waits for the summary.
                run_in_background(self._update_summary_later, call.session_id)

    async def _complete(
        self, func: Callable[..., Any], arguments: dict[str, Any]
    ) -> ChatResponse:
        call = await self._prepare(func, arguments)
        response = await self.service_provider.complete(call.messages, self.configs)
        response.session_id = call.session_id
        await self._remember(call, response.message.content)
        return response

    async def _stream(
        self, func: Callable[..., Any], arguments: dict[str, Any]
    ) -> AsyncIterator[ChatResponse]:
        call = await self._prepare(func, arguments)
        parts: list[str] = []
        stream = self.service_provider.stream(call.messages, self.configs)
        try:
            async for chunk in stream:
                chunk.session_id = call.session_id
                if chunk.message.content:
                    parts.append(chunk.message.content)
                yield chunk
        finally:
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()
        await self._remember(call, "".join(parts))

    # ---- turning decorated methods into calls --------------------------------

    @staticmethod
    def _bind_arguments(func, self, args, kwargs) -> dict[str, Any]:
        """
        Maps positional and keyword arguments of an AI method call to the
        method's parameter names (used for <:name> placeholders in prompts).
        """
        signature = inspect.signature(func)
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        arguments: dict[str, Any] = {}
        for index, (name, value) in enumerate(bound.arguments.items()):
            if index == 0:  # self
                continue
            kind = signature.parameters[name].kind
            if kind is inspect.Parameter.VAR_KEYWORD:
                arguments.update(value)
            elif kind is not inspect.Parameter.VAR_POSITIONAL:
                arguments[name] = value
        return arguments

    @classmethod
    def _wrap_method(cls, func: Callable[..., Any]) -> Callable[..., Any]:
        if _is_streaming(func):

            @wraps(func)
            def stream(self, *args, **kwargs) -> AsyncIterator[ChatResponse]:
                # A plain function: `async for chunk in service.method(...)`.
                arguments = cls._bind_arguments(func, self, args, kwargs)
                return self._stream(func, arguments)

            wrapper: Callable[..., Any] = stream
        else:

            @wraps(func)
            async def complete(self, *args, **kwargs) -> ChatResponse:
                arguments = cls._bind_arguments(func, self, args, kwargs)
                return await self._complete(func, arguments)

            wrapper = complete

        for marker in (
            "__system_prompt__",
            "__user_prompt__",
            "__use_history__",
            "__use_augmentation__",
        ):
            setattr(wrapper, marker, getattr(func, marker))
        setattr(wrapper, "__ai_method__", True)
        return wrapper

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        for name, value in list(cls.__dict__.items()):
            if name.startswith("_") or not callable(value):
                continue
            if not hasattr(value, "__user_prompt__") and not hasattr(
                value, "__system_prompt__"
            ):
                continue
            for marker, default in (
                ("__system_prompt__", ""),
                ("__user_prompt__", ""),
                ("__use_history__", False),
                ("__use_augmentation__", False),
            ):
                if not hasattr(value, marker):
                    setattr(value, marker, default)
            if (
                value.__use_history__
                and "session_id" not in inspect.signature(value).parameters
            ):
                raise TypeError(
                    f"{cls.__name__}.{name} uses @history, so it needs a "
                    "`session_id` parameter (None starts a new session)."
                )
            setattr(cls, name, AiService._wrap_method(value))


FuncT = TypeVar("FuncT", bound=Callable[..., Any])


def system_prompt(prompt: str) -> Callable[[FuncT], FuncT]:
    """
    Decorator for setting the system prompt. ``<:name>`` placeholders are
    filled from the method's arguments, as in the user prompt.
    """

    def decorator(func: FuncT) -> FuncT:
        cast(Any, func).__system_prompt__ = prompt
        return func

    return decorator


def user_prompt(prompt: str) -> Callable[[FuncT], FuncT]:
    """
    Decorator for setting the user prompt; ``<:name>`` placeholders are
    filled from the method's arguments.
    """

    def decorator(func: FuncT) -> FuncT:
        cast(Any, func).__user_prompt__ = prompt
        return func

    return decorator


def history(func: FuncT) -> FuncT:
    """
    Sends the session's earlier messages with the call and saves the new ones.
    The method needs a ``session_id`` parameter; None starts a new session.
    """
    cast(Any, func).__use_history__ = True
    return func


def augmentation(func: FuncT) -> FuncT:
    """
    Adds the texts of the documents most relevant to the user message, found
    by the service's augmentation provider.
    """
    cast(Any, func).__use_augmentation__ = True
    return func


__all__ = [
    "AiService",
    "AiServiceConfig",
    "HistorySummaryConfig",
    "ChatResponse",
    "augmentation",
    "history",
    "system_prompt",
    "user_prompt",
]
