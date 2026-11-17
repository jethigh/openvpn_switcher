# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""OpenVPN service management protocol and systemd implementation."""

import subprocess
from typing import List, Protocol, runtime_checkable


@runtime_checkable
class ServiceManager(Protocol):
    """Protocol defining service management operations."""

    def status(self) -> bool:
        """Check if the target service is active and running."""
        ...

    def start(self) -> bool:
        """Start the target service."""
        ...

    def stop(self) -> bool:
        """Stop the target service."""
        ...

    def restart(self) -> bool:
        """Restart the target service."""
        ...

    def get_last_output(self) -> str:
        """Retrieve output or error message from the most recent command."""
        ...


class SystemdServiceManager:
    """Manages systemd services using systemctl commands."""

    def __init__(
        self,
        service_name: str = "openvpn",
        use_sudo: bool = True,
        timeout: int = 15,
    ) -> None:
        """Initialize SystemdServiceManager.

        Args:
            service_name: Name of the systemd service (e.g., 'openvpn' or 'openvpn@trustzone').
            use_sudo: Whether to prepend 'sudo' to systemctl commands.
            timeout: Subprocess command timeout in seconds.

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
        self.use_sudo = use_sudo
        self.timeout = timeout
        self.last_output: str = ""

    def _build_command(self, action: str) -> List[str]:
        """Construct the systemctl command array.

        Args:
            action: systemctl subcommand (is-active, start, stop, restart).

        Returns:
            List of command arguments.
        """
        cmd: List[str] = []
        if self.use_sudo:
            cmd.append("sudo")
        cmd.extend(["systemctl", action, self.unit_name])
        return cmd

    def _run_command(self, action: str) -> bool:
        """Execute a systemctl command and capture results.

        Args:
            action: systemctl subcommand to execute.

        Returns:
            True if command succeeded with exit code 0, False otherwise.
        """
        cmd = self._build_command(action)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            self.last_output = stderr if stderr else stdout
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.last_output = (
                f"Command '{' '.join(cmd)}' timed out after {self.timeout} seconds."
            )
            return False
        except FileNotFoundError as exc:
            self.last_output = f"Command '{cmd[0]}' not found on this system: {exc}"
            return False
        except OSError as exc:
            self.last_output = f"Failed to execute command '{' '.join(cmd)}': {exc}"
            return False

    def status(self) -> bool:
        """Check if service is active using `systemctl is-active`.

        Returns:
            True if service is active (exit code 0), False otherwise.
        """
        return self._run_command("is-active")

    def start(self) -> bool:
        """Start the systemd unit."""
        return self._run_command("start")

    def stop(self) -> bool:
        """Stop the systemd unit."""
        return self._run_command("stop")

    def restart(self) -> bool:
        """Restart the systemd unit."""
        return self._run_command("restart")

    def get_last_output(self) -> str:
        """Retrieve output or error message from the most recent command."""
        return self.last_output


class MockServiceManager:
    """Mock implementation of ServiceManager for testing and emulation."""

    def __init__(self, initial_status: bool = False) -> None:
        """Initialize MockServiceManager.

        Args:
            initial_status: Initial running state of the mock service.
        """
        self._running: bool = initial_status
        self.last_output: str = ""
        self.call_history: List[str] = []

    def status(self) -> bool:
        """Return current simulated status."""
        self.call_history.append("status")
        self.last_output = "active" if self._running else "inactive"
        return self._running

    def start(self) -> bool:
        """Simulate starting the service."""
        self.call_history.append("start")
        self._running = True
        self.last_output = "Service started successfully."
        return True

    def stop(self) -> bool:
        """Simulate stopping the service."""
        self.call_history.append("stop")
        self._running = False
        self.last_output = "Service stopped successfully."
        return True

    def restart(self) -> bool:
        """Simulate restarting the service."""
        self.call_history.append("restart")
        self._running = True
        self.last_output = "Service restarted successfully."
        return True

    def get_last_output(self) -> str:
        """Return the output from the last mock operation."""
        return self.last_output
