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


@dataclass(frozen=True, slots=True)
class CancellationCleanupReport:
    task_id: str = ""
    output_directory: str = ""
    failed_paths: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return not self.failed_paths


class OperationCancelled(AppError):
    def __init__(
        self,
        context: ErrorContext | None = None,
        cleanup_report: CancellationCleanupReport | None = None,
    ) -> None:
        super().__init__(
            code="cancelled",
            user_message="操作已取消。",
            technical_message="Operation cancelled by the user",
            context=context or ErrorContext(),
        )
        object.__setattr__(self, "cleanup_report", cleanup_report)
