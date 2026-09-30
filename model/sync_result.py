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
    cancelled: bool = field(default=False)
    notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        self._lock = threading.Lock()

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

    def add_skipped(self, count: int = 1):
        """Increment the skipped counter (thread-safe)."""
        with self._lock:
            self.skipped_count += count

    def add_note(self, message: str):
        with self._lock:
            self.notes.append(message)

    def merge(self, other: 'SyncResult') -> None:
        """Merge a coherent snapshot without nesting locks (including self-merge)."""
        with other._lock:
            success, failure, skipped = other.success_count, other.failure_count, other.skipped_count
            errors, notes, cancelled = list(other.errors), list(other.notes), other.cancelled
        with self._lock:
            self.success_count += success
            self.failure_count += failure
            self.skipped_count += skipped
            self.errors.extend(errors)
            self.notes.extend(notes)
            self.cancelled = self.cancelled or cancelled

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
        """Success percentage among attempted items; skipped items are excluded."""
        with self._lock:
            attempts = self.success_count + self.failure_count
            return self.success_count / attempts * 100 if attempts else 0.0

    def get_summary(self) -> str:
        """Get a human-readable summary of the sync result."""
        prefix = "Sync cancelled.\n\n" if self.cancelled else ""
        parts = [
            f"Completed: {self.success_count} succeeded",
        ]
        if self.failure_count > 0:
            parts.append(f"{self.failure_count} failed")
        if self.skipped_count > 0:
            parts.append(f"{self.skipped_count} skipped")

        summary = prefix + ", ".join(parts)
        if self.has_failures:
            summary += f"\n\nErrors:\n" + "\n".join(
                f"- {e.item_name}: {e.error_message}"
                for e in self.errors[:10]  # Show first 10 errors
            )
            if len(self.errors) > 10:
                summary += f"\n... and {len(self.errors) - 10} more errors"

        if self.notes:
            summary += "\n\nNotes:\n" + "\n".join(f"- {note}" for note in self.notes[:10])
            if len(self.notes) > 10:
                summary += f"\n... and {len(self.notes) - 10} more"

        return summary

    def __str__(self) -> str:
        return self.get_summary()
