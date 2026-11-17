# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for LogStreamer implementations."""

import io
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from openvpn_switcher.core.logs import (
    JournalctlLogStreamer,
    LogStreamer,
    MockLogStreamer,
)


class TestJournalctlLogStreamer:
    """Tests for JournalctlLogStreamer subprocess management and buffer behavior."""

    def test_protocol_conformance(self) -> None:
        """Verify JournalctlLogStreamer conforms to LogStreamer Protocol."""
        streamer = JournalctlLogStreamer("openvpn")
        assert isinstance(streamer, LogStreamer)

    def test_service_name_validation(self) -> None:
        """Reject empty or dangerous service names."""
        with pytest.raises(ValueError, match="Service name must be a non-empty string"):
            JournalctlLogStreamer("")

        with pytest.raises(ValueError, match="Invalid service name"):
            JournalctlLogStreamer("openvpn; cat /etc/shadow")

    def test_command_construction(self) -> None:
        """Verify journalctl command array structure with and without sudo."""
        streamer_no_sudo = JournalctlLogStreamer("openvpn", lines_tail=50, use_sudo=False)
        assert streamer_no_sudo._build_command() == [
            "journalctl",
            "-u",
            "openvpn.service",
            "-n",
            "50",
            "-f",
        ]

        streamer_sudo = JournalctlLogStreamer("openvpn@trustzone", lines_tail=25, use_sudo=True)
        assert streamer_sudo._build_command() == [
            "sudo",
            "journalctl",
            "-u",
            "openvpn@trustzone.service",
            "-n",
            "25",
            "-f",
        ]

    @patch("subprocess.Popen")
    def test_streaming_and_buffer_retrieval(self, mock_popen: MagicMock) -> None:
        """Verify lines emitted by subprocess stdout are captured into ring buffer."""
        fake_stdout = io.StringIO(
            "Nov 18 00:00:01 openvpn[123]: Initialization Sequence Completed\n"
            "Nov 18 00:00:02 openvpn[123]: Peer Connection Initiated\n"
        )
        mock_proc = MagicMock()
        mock_proc.stdout = fake_stdout
        mock_popen.return_value = mock_proc

        streamer = JournalctlLogStreamer("openvpn", lines_tail=10)
        streamer.start()

        # Wait briefly for worker thread to process StringIO
        if streamer._thread:
            streamer._thread.join(timeout=1.0)

        lines = streamer.get_lines()
        assert len(lines) == 2
        assert "Initialization Sequence Completed" in lines[0]
        assert "Peer Connection Initiated" in lines[1]

        streamer.clear()
        assert streamer.get_lines() == []
        streamer.stop()

    @patch("subprocess.Popen")
    def test_ring_buffer_caps_at_max_buffer(self, mock_popen: MagicMock) -> None:
        """Verify the ring buffer does not exceed max_buffer elements."""
        sample_lines = "\n".join(f"Log event {i}" for i in range(30)) + "\n"
        fake_stdout = io.StringIO(sample_lines)

        mock_proc = MagicMock()
        mock_proc.stdout = fake_stdout
        mock_popen.return_value = mock_proc

        # Set max_buffer to 10
        streamer = JournalctlLogStreamer("openvpn", max_buffer=10)
        streamer.start()

        if streamer._thread:
            streamer._thread.join(timeout=1.0)

        lines = streamer.get_lines()
        assert len(lines) == 10
        assert lines[-1] == "Log event 29"
        assert lines[0] == "Log event 20"
        streamer.stop()

    @patch("subprocess.Popen")
    def test_missing_journalctl_handles_gracefully(self, mock_popen: MagicMock) -> None:
        """Verify FileNotFoundError does not crash streamer and registers system error message."""
        mock_popen.side_effect = FileNotFoundError("Executable journalctl not found")

        streamer = JournalctlLogStreamer("openvpn")
        streamer.start()

        if streamer._thread:
            streamer._thread.join(timeout=1.0)

        lines = streamer.get_lines()
        assert len(lines) == 1
        assert "[SYSTEM ERROR]" in lines[0]
        assert "journalctl executable not found" in lines[0]
        streamer.stop()

    @patch("subprocess.Popen")
    def test_permission_error_handles_gracefully(self, mock_popen: MagicMock) -> None:
        """Verify PermissionError does not crash streamer and registers system error message."""
        mock_popen.side_effect = PermissionError("Permission denied")

        streamer = JournalctlLogStreamer("openvpn")
        streamer.start()

        if streamer._thread:
            streamer._thread.join(timeout=1.0)

        lines = streamer.get_lines()
        assert len(lines) == 1
        assert "[SYSTEM ERROR]" in lines[0]
        assert "Permission denied running journalctl" in lines[0]
        streamer.stop()


class TestMockLogStreamer:
    """Tests for MockLogStreamer implementation."""

    def test_protocol_conformance(self) -> None:
        """Verify MockLogStreamer conforms to LogStreamer Protocol."""
        streamer = MockLogStreamer()
        assert isinstance(streamer, LogStreamer)

    def test_lifecycle_and_methods(self) -> None:
        """Test mock streamer start, stop, add_line, and clear methods."""
        initial_entries: List[str] = ["Initial log line 1", "Initial log line 2"]
        streamer = MockLogStreamer(initial_lines=initial_entries)

        assert streamer.is_active() is False
        assert streamer.get_lines() == initial_entries

        streamer.start()
        assert streamer.is_active() is True

        streamer.add_line("Runtime event")
        assert len(streamer.get_lines()) == 3
        assert streamer.get_lines()[-1] == "Runtime event"

        streamer.clear()
        assert streamer.get_lines() == []

        streamer.stop()
        assert streamer.is_active() is False
