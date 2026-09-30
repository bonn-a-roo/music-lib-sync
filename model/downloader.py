from abc import ABC, abstractmethod
from typing import Callable

from model.song import Song
from model.sync_result import SyncResult


class Downloader(ABC):
    log_callback: Callable[[str], None] | None = None

    @abstractmethod
    def download(self, songs: list[Song], download_path: str,
                 progress_callback: Callable[[int, int, str], None] | None = None) -> SyncResult:
        pass

    @abstractmethod
    def cancel(self) -> None:
        pass

    @abstractmethod
    def is_cancelled(self) -> bool:
        pass

    def preflight(self) -> list[str]:
        return []
