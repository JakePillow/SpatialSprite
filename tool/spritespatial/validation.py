from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"

    @property
    def rank(self) -> int:
        return (self.INFO, self.WARNING, self.ERROR, self.FATAL).index(self)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    severity: ValidationSeverity
    region_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["severity"] = self.severity.value
        return payload


@dataclass
class ValidationReport:
    stage: str
    issues: list[ValidationIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(
        self,
        severity: ValidationSeverity,
        code: str,
        message: str,
        *,
        region_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(ValidationIssue(code, message, severity, region_id, context or {}))

    def extend(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues.extend(issues)

    @property
    def highest_severity(self) -> ValidationSeverity:
        if not self.issues:
            return ValidationSeverity.INFO
        return max((issue.severity for issue in self.issues), key=lambda value: value.rank)

    @property
    def passed(self) -> bool:
        return not any(issue.severity.rank >= ValidationSeverity.ERROR.rank for issue in self.issues)

    @property
    def fatal(self) -> bool:
        return any(issue.severity is ValidationSeverity.FATAL for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        counts = {severity.value: 0 for severity in ValidationSeverity}
        for issue in self.issues:
            counts[issue.severity.value] += 1
        return {
            "schema": "spritespatial_validation_report_v1",
            "stage": self.stage,
            "passed": self.passed,
            "fatal": self.fatal,
            "highest_severity": self.highest_severity.value,
            "counts": counts,
            "issues": [issue.to_dict() for issue in self.issues],
            "metadata": self.metadata,
        }
