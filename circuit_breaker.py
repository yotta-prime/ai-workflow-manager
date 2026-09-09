"""
Document Reference: circuit_breaker.py
System: Project Chronicle - Enterprise AI Workflow Manager
Branch: A.14.12
Description: Resilient Circuit Breaker protecting external task operations (RM-005).
"""

import time
from enum import Enum
from typing import Any, Callable, Dict, Optional


class CircuitState(str, Enum):
    CLOSED = "CLOSED"  # Normal operational flow
    OPEN = "OPEN"  # Blocking invocations due to error threshold
    HALF_OPEN = "HALF_OPEN"  # Trial invocations to probe recovery


class TaskServiceCircuitBreaker:
    """
    Implements the Circuit Breaker pattern mapped to Threat RM-005:
    Integrations Service Outage Cascade.
    """

    def __init__(
        self,
        name: str = "ChronicleTaskService",
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 5.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: Optional[float] = None
        self.success_count: int = 0

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        now = time.time()
        if self.state == CircuitState.OPEN:
            if (
                self.last_failure_time is not None
                and (now - self.last_failure_time) >= self.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
            else:
                raise RuntimeError(
                    f"Circuit breaker '{self.name}' is OPEN. Operation rejected."
                )

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as exc:
            self._record_failure()
            raise exc

    def _record_success(self) -> None:
        self.failure_count = 0
        self.success_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED

    def _record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# Global singleton instance for the service
chronicle_circuit_breaker = TaskServiceCircuitBreaker()
