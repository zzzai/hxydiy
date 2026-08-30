"""Pure release-gate evaluation shared by checks and deployment tooling."""

from dataclasses import dataclass
from typing import Mapping


REQUIRED_GATES = ("tests", "backup", "manifest", "current", "health")


@dataclass(frozen=True)
class ReleaseGateReport:
    ok: bool
    missing: tuple[str, ...]


def evaluate_release_gates(evidence: Mapping[str, object]) -> ReleaseGateReport:
    missing = tuple(name for name in REQUIRED_GATES if evidence.get(name) is not True)
    return ReleaseGateReport(ok=not missing, missing=missing)
