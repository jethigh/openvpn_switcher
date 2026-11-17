# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Real-time log streaming abstraction for OpenVPN service daemon."""

from collections import deque
import subprocess
import threading
from typing import Deque, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class LogStreamer(Protocol):
    """Protocol defining real-time log streaming interfaces."""

    def start(self) -> None:
        """Start the streaming background worker."""
        ...

    def stop(self) -> None:
        """Stop the streaming background worker and release resources."""
        ...

    def get_lines(self) -> List[str]:
        """Retrieve a snapshot of lines currently stored in the ring buffer."""
        ...

    def is_active(self) -> bool:
        """Check if the streamer is actively running."""
        ...

    def clear(self) -> None:
        """Clear the current log buffer."""
        ...


class JournalctlLogStreamer:
    """Streams OpenVPN systemd logs using journalctl in a background daemon thread."""

    def __init__(
        self,
        service_name: str = "openvpn",
        lines_tail: int = 100,
        max_buffer: int = 2000,
        use_sudo: bool = False,
    ) -> None:
        """Initialize JournalctlLogStreamer.

        Args:
            service_name: Name of the systemd service to stream.
            lines_tail: Number of historical lines to fetch initially.
            max_buffer: Maximum number of lines to retain in the ring buffer.
            use_sudo: Whether to execute journalctl with sudo.

        Raises:
            ValueError: If service_name is invalid or contains forbidden characters.
        """
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValueError("Service name must be a non-empty string.")

        service_name = service_name.strip()
        if any(c in service_name for c in " \t\r\n;&|><$"):
            raise ValueError(
                f"Invalid service name '{service_name}': cannot contain whitespace or shell metacharacters."
            )

        self.service_name = service_name
        self.unit_name = (
            service_name if service_name.endswith(".service") else f"{service_name}.service"
        )
        self.lines_tail = max(1, lines_tail)
        self.max_buffer = max(10, max_buffer)
        self.use_sudo = use_sudo

        self._buffer: Deque[str] = deque(maxlen=self.max_buffer)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None

    def _build_command(self) -> List[str]:
        """Construct the journalctl command arguments."""
        cmd: List[str] = []
        if self.use_sudo:
            cmd.append("sudo")
        cmd.extend(["journalctl", "-u", self.unit_name, "-n", str(self.lines_tail), "-f"])
        return cmd

    def _worker(self) -> None:
        """Background thread target that reads lines from journalctl process."""
        cmd = self._build_command()
        proc: Optional[subprocess.Popen] = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._process = proc

            if proc.stdout is not None:
                for line in proc.stdout:
                    if self._stop_event.is_set():
                        break
                    formatted = line.rstrip("\r\n")
                    with self._lock:
                        self._buffer.append(formatted)
        except FileNotFoundError as exc:
            with self._lock:
                self._buffer.append(f"[SYSTEM ERROR] journalctl executable not found: {exc}")
        except PermissionError as exc:
            with self._lock:
                self._buffer.append(f"[SYSTEM ERROR] Permission denied running journalctl: {exc}")
        except OSError as exc:
            with self._lock:
                self._buffer.append(f"[SYSTEM ERROR] Failed executing journalctl: {exc}")
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except (subprocess.TimeoutExpired, OSError):
                    try:
                        proc.kill()
                    except OSError:
                        pass
            self._process = None

    def start(self) -> None:
        """Start the background streaming thread."""
        if self.is_active():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker,
            name=f"log-streamer-{self.service_name}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop streaming and terminate the journalctl subprocess."""
        self._stop_event.set()
        proc = self._process
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=0.5)
            except (subprocess.TimeoutExpired, OSError):
                try:
                    proc.kill()
                except OSError:
                    pass

        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

    def get_lines(self) -> List[str]:
        """Return a snapshot of lines currently stored in the ring buffer."""
        with self._lock:
            return list(self._buffer)

    def is_active(self) -> bool:
        """Return True if background streaming thread is actively running."""
        return self._thread is not None and self._thread.is_alive()

    def clear(self) -> None:
        """Clear all lines currently stored in the buffer."""
        with self._lock:
            self._buffer.clear()


class MockLogStreamer:
    """Mock implementation of LogStreamer for testing."""

    def __init__(self, initial_lines: Optional[List[str]] = None) -> None:
        """Initialize MockLogStreamer.

        Args:
            initial_lines: Optional list of log lines to pre-populate.
        """
        self._lines: List[str] = list(initial_lines) if initial_lines is not None else []
        self._active: bool = False

    def start(self) -> None:
        """Start the simulated streaming session."""
        self._active = True

    def stop(self) -> None:
        """Stop the simulated streaming session."""
        self._active = False

    def get_lines(self) -> List[str]:
        """Return a copy of the stored log lines."""
        return list(self._lines)

    def is_active(self) -> bool:
        """Return the current streaming state."""
        return self._active

    def clear(self) -> None:
        """Clear all stored log lines."""
        self._lines.clear()

    def add_line(self, line: str) -> None:
        """Add a synthetic log line to the streamer buffer.

        Args:
            line: Log line text.
        """
        self._lines.append(line)
