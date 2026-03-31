from dataclasses import dataclass, field
from typing import List, Optional
import threading


@dataclass
class DownloadError:
    """Represents a single download failure."""
    item_name: str
    item_url: Optional[str]
    error_message: str


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    errors: List[DownloadError] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def add_success(self):
        """Increment the success counter (thread-safe)."""
        with self._lock:
            self.success_count += 1

    def add_failure(self, item_name: str, item_url: Optional[str], error_message: str):
        """Add a failure record (thread-safe)."""
        with self._lock:
            self.failure_count += 1
            self.errors.append(DownloadError(
                item_name=item_name,
                item_url=item_url,
                error_message=error_message
            ))

    def add_skipped(self):
        """Increment the skipped counter (thread-safe)."""
        with self._lock:
            self.skipped_count += 1

    @property
    def total(self) -> int:
        """Total number of items processed."""
        return self.success_count + self.failure_count + self.skipped_count

    @property
    def has_failures(self) -> bool:
        """Whether any failures occurred."""
        return self.failure_count > 0

    @property
    def success_rate(self) -> float:
        """Success rate as a percentage (0-100)."""
        if self.total == 0:
            return 0.0
        return (self.success_count / self.total) * 100

    def get_summary(self) -> str:
        """Get a human-readable summary of the sync result."""
        parts = [
            f"Completed: {self.success_count} succeeded",
        ]
        if self.failure_count > 0:
            parts.append(f"{self.failure_count} failed")
        if self.skipped_count > 0:
            parts.append(f"{self.skipped_count} skipped")

        summary = ", ".join(parts)
        if self.has_failures:
            summary += f"\n\nErrors:\n" + "\n".join(
                f"- {e.item_name}: {e.error_message}"
                for e in self.errors[:10]  # Show first 10 errors
            )
            if len(self.errors) > 10:
                summary += f"\n... and {len(self.errors) - 10} more errors"

        return summary

    def __str__(self) -> str:
        return self.get_summary()
