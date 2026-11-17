# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for ServiceManager implementations."""

import subprocess
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from openvpn_switcher.core.service import (
    MockServiceManager,
    ServiceManager,
    SystemdServiceManager,
)


class TestSystemdServiceManager:
    """Tests for SystemdServiceManager command construction and execution."""

    def test_protocol_conformance(self) -> None:
        """Verify SystemdServiceManager conforms to ServiceManager Protocol."""
        manager = SystemdServiceManager("openvpn")
        assert isinstance(manager, ServiceManager)

    def test_service_name_unit_formatting(self) -> None:
        """Ensure unit names receive .service suffix if not already present."""
        mgr1 = SystemdServiceManager("openvpn")
        assert mgr1.unit_name == "openvpn.service"

        mgr2 = SystemdServiceManager("openvpn@trustzone.service")
        assert mgr2.unit_name == "openvpn@trustzone.service"

    def test_service_name_validation(self) -> None:
        """Reject empty or shell-metacharacter-containing service names."""
        with pytest.raises(ValueError, match="Service name must be a non-empty string"):
            SystemdServiceManager("")

        with pytest.raises(ValueError, match="Invalid service name"):
            SystemdServiceManager("openvpn; rm -rf /")

        with pytest.raises(ValueError, match="Invalid service name"):
            SystemdServiceManager("openvpn openvpn")

    @patch("subprocess.run")
    def test_status_returns_true_on_zero_exit_code(self, mock_run: MagicMock) -> None:
        """Verify status() returns True when systemctl is-active returns 0."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "systemctl", "is-active", "openvpn.service"],
            returncode=0,
            stdout="active\n",
            stderr="",
        )

        manager = SystemdServiceManager("openvpn", use_sudo=True)
        assert manager.status() is True
        mock_run.assert_called_once_with(
            ["sudo", "systemctl", "is-active", "openvpn.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    @patch("subprocess.run")
    def test_status_returns_false_on_nonzero_exit_code(self, mock_run: MagicMock) -> None:
        """Verify status() returns False when systemctl is-active returns non-zero."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "systemctl", "is-active", "openvpn.service"],
            returncode=3,
            stdout="inactive\n",
            stderr="",
        )

        manager = SystemdServiceManager("openvpn", use_sudo=True)
        assert manager.status() is False

    @patch("subprocess.run")
    def test_start_stop_restart_with_sudo(self, mock_run: MagicMock) -> None:
        """Verify start, stop, and restart execute correct commands when use_sudo=True."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        manager = SystemdServiceManager("openvpn@trustzone", use_sudo=True)

        assert manager.start() is True
        mock_run.assert_called_with(
            ["sudo", "systemctl", "start", "openvpn@trustzone.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        assert manager.stop() is True
        mock_run.assert_called_with(
            ["sudo", "systemctl", "stop", "openvpn@trustzone.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        assert manager.restart() is True
        mock_run.assert_called_with(
            ["sudo", "systemctl", "restart", "openvpn@trustzone.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    @patch("subprocess.run")
    def test_commands_without_sudo(self, mock_run: MagicMock) -> None:
        """Verify commands omit sudo when use_sudo=False."""
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        manager = SystemdServiceManager("openvpn", use_sudo=False)
        assert manager.start() is True
        mock_run.assert_called_with(
            ["systemctl", "start", "openvpn.service"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

    @patch("subprocess.run")
    def test_error_capture_on_failure(self, mock_run: MagicMock) -> None:
        """Verify stderr is captured when command exits with non-zero code."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["sudo", "systemctl", "restart", "openvpn.service"],
            returncode=1,
            stdout="",
            stderr="Job for openvpn.service failed because the control process exited with error code.\n",
        )

        manager = SystemdServiceManager("openvpn")
        success = manager.restart()
        assert success is False
        assert "failed because the control process exited" in manager.get_last_output()

    @patch("subprocess.run")
    def test_timeout_handling(self, mock_run: MagicMock) -> None:
        """Verify TimeoutExpired is handled cleanly without raising."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["sudo", "systemctl", "start"], timeout=15)

        manager = SystemdServiceManager("openvpn")
        assert manager.start() is False
        assert "timed out after 15 seconds" in manager.get_last_output()

    @patch("subprocess.run")
    def test_file_not_found_handling(self, mock_run: MagicMock) -> None:
        """Verify FileNotFoundError is handled cleanly."""
        mock_run.side_effect = FileNotFoundError("No such file: 'sudo'")

        manager = SystemdServiceManager("openvpn")
        assert manager.start() is False
        assert "not found on this system" in manager.get_last_output()

    @patch("subprocess.run")
    def test_permission_error_handling(self, mock_run: MagicMock) -> None:
        """Verify PermissionError is handled cleanly."""
        mock_run.side_effect = PermissionError("Operation not permitted")

        manager = SystemdServiceManager("openvpn")
        assert manager.stop() is False
        assert "Permission denied executing" in manager.get_last_output()


class TestMockServiceManager:
    """Tests for MockServiceManager."""

    def test_protocol_conformance(self) -> None:
        """Verify MockServiceManager conforms to ServiceManager Protocol."""
        manager = MockServiceManager()
        assert isinstance(manager, ServiceManager)

    def test_lifecycle_and_history(self) -> None:
        """Test mock start, stop, restart state transitions and call history."""
        manager = MockServiceManager(initial_status=False)
        assert manager.status() is False
        assert manager.get_last_output() == "inactive"

        assert manager.start() is True
        assert manager.status() is True
        assert manager.get_last_output() == "active"

        assert manager.stop() is True
        assert manager.status() is False
        assert manager.get_last_output() == "inactive"

        assert manager.restart() is True
        assert manager.status() is True

        expected_history: List[str] = [
            "status",
            "start",
            "status",
            "stop",
            "status",
            "restart",
            "status",
        ]
        assert manager.call_history == expected_history
