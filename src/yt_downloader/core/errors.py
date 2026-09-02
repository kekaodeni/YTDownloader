"""Structured application errors safe to cross worker/UI boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ErrorContext:
    url: str = ""
    selected_format: str = ""
    output_directory: str = ""
    stage: str = ""
    traceback_text: str = ""
    log_excerpt: str = ""


@dataclass(frozen=True, slots=True)
class AppError(Exception):
    code: str
    user_message: str
    technical_message: str
    context: ErrorContext = field(default_factory=ErrorContext)

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", (self.user_message,))

    def __str__(self) -> str:
        return self.user_message


class OperationCancelled(AppError):
    def __init__(self, context: ErrorContext | None = None) -> None:
        super().__init__(
            code="cancelled",
            user_message="操作已取消。",
            technical_message="Operation cancelled by the user",
            context=context or ErrorContext(),
        )

