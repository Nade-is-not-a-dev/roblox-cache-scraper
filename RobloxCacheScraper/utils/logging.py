"""Simple thread-safe log buffer for the GUI."""

import logging
import threading
from pathlib import Path


class LogBuffer:
    """A thread-safe rolling log buffer that also writes to a file."""

    def __init__(self, max_lines: int = 10000):
        self._lines: list[str] = []
        self._max_lines = max_lines
        self._lock = threading.Lock()

    def log(self, tag: str, message: str) -> None:
        """Add a log entry with the given tag."""
        line = f'[{tag}] {message}'
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._max_lines:
                self._lines.pop(0)

    def get_lines(self) -> list[str]:
        """Return all buffered log lines."""
        with self._lock:
            return list(self._lines)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


log_buffer = LogBuffer()


def setup_file_logging(log_path: Path) -> None:
    """Configure file-based logging."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(str(log_path), encoding='utf-8'),
            logging.StreamHandler(),
        ],
        force=True,
    )
