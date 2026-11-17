# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""OpenVPN configuration file reader and atomic updater."""

import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Optional, Tuple, Union

from openvpn_switcher.core.models import ProtocolType

REMOTE_PATTERN = re.compile(
    r"^\s*remote\s+(?P<host>\"[^\"]+\"|'[^']+'|[^\s#;]+)(?:\s+(?P<port>\d+))?(?:\s+(?P<proto>udp|tcp))?",
    re.IGNORECASE,
)


class ConfigManager:
    """Manages reading and atomic updating of OpenVPN configuration files."""

    def __init__(self, config_path: Union[str, Path] = "/etc/openvpn/trustzone.conf") -> None:
        """Initialize ConfigManager.

        Args:
            config_path: Path to the target OpenVPN configuration file.
        """
        self.config_path = Path(config_path).expanduser().resolve()

    def get_active_remote(self) -> Optional[Tuple[str, int, ProtocolType]]:
        """Parse configuration and extract active remote endpoint details.

        Returns:
            A tuple of (hostname, port, protocol) if found, otherwise None.
        """
        if not self.config_path.exists() or not self.config_path.is_file():
            return None

        try:
            with open(self.config_path, "r", encoding="utf-8", errors="replace") as file_handle:
                for line in file_handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith(";"):
                        continue

                    match = REMOTE_PATTERN.match(line)
                    if match:
                        host = match.group("host").strip("\"'")
                        port_str = match.group("port")
                        proto_str = match.group("proto")

                        port = int(port_str) if port_str else 1194
                        proto = (
                            ProtocolType.from_str(proto_str)
                            if proto_str
                            else ProtocolType.UDP
                        )
                        return (host, port, proto)
        except OSError:
            return None

        return None

    def in_config(self, host: str) -> bool:
        """Check if the specified host matches the active remote directive.

        Args:
            host: Target hostname to check.

        Returns:
            True if the host is actively configured, False otherwise.
        """
        active = self.get_active_remote()
        if active is None:
            return False
        return active[0].strip().lower() == host.strip().lower()

    def set_remote(
        self,
        host: str,
        port: int = 1194,
        protocol: Union[ProtocolType, str] = ProtocolType.UDP,
    ) -> bool:
        """Replace or append the remote directive using atomic file replacement.

        Args:
            host: Destination VPN server hostname or IP address.
            port: Destination port number (1-65535).
            protocol: Transport protocol (UDP or TCP).

        Returns:
            True upon successful atomic update.

        Raises:
            ValueError: If host, port, or protocol fail validation.
            PermissionError: If target directory or file is not writable.
            OSError: On underlying filesystem errors.
        """
        if not isinstance(host, str) or not host.strip():
            raise ValueError("Host must be a non-empty string.")

        host = host.strip()
        if any(char in host for char in ("\r", "\n", "\t", " ", '"', "'", "#", ";")):
            raise ValueError(
                f"Invalid host '{host}': host cannot contain whitespace, newlines, quotes, or comment characters."
            )

        if isinstance(port, bool) or not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(
                f"Port must be an integer between 1 and 65535. Received: {port!r}"
            )

        if isinstance(protocol, ProtocolType):
            validated_proto = protocol
        elif isinstance(protocol, str):
            validated_proto = ProtocolType.from_str(protocol)
        else:
            raise ValueError(
                f"Invalid protocol '{protocol!r}'. Expected ProtocolType or 'udp'/'tcp'."
            )

        target_dir = self.config_path.parent

        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as err:
                raise PermissionError(
                    f"Target directory '{target_dir}' cannot be created: insufficient permissions."
                ) from err

        if not os.access(target_dir, os.W_OK):
            raise PermissionError(
                f"Target directory '{target_dir}' is not writable. Root or sudo privileges required."
            )

        new_remote_line = f"remote {host} {port} {validated_proto.value}\n"
        lines = []
        replaced = False

        original_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH  # 0o644 default

        if self.config_path.exists():
            if not os.access(self.config_path, os.W_OK):
                raise PermissionError(
                    f"Configuration file '{self.config_path}' is not writable. Root or sudo privileges required."
                )
            try:
                original_mode = stat.S_IMODE(self.config_path.stat().st_mode)
                with open(self.config_path, "r", encoding="utf-8", errors="replace") as file_handle:
                    for line in file_handle:
                        stripped = line.strip()
                        is_active_remote = (
                            bool(stripped)
                            and not stripped.startswith("#")
                            and not stripped.startswith(";")
                            and bool(REMOTE_PATTERN.match(line))
                        )
                        if is_active_remote:
                            if not replaced:
                                lines.append(new_remote_line)
                                replaced = True
                            else:
                                # Comment out subsequent active remotes to prevent unexpected failover/leaks
                                lines.append(f"# {line}")
                            continue
                        lines.append(line)
            except PermissionError as err:
                raise PermissionError(
                    f"Cannot read configuration file '{self.config_path}': insufficient permissions."
                ) from err

        if not replaced:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] = lines[-1] + "\n"
            lines.append(new_remote_line)

        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target_dir,
                mode="w",
                encoding="utf-8",
                delete=False,
                prefix="trustzone_",
                suffix=".tmp",
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.writelines(lines)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.chmod(temp_path, original_mode)
            os.replace(temp_path, self.config_path)
            temp_path = None
            return True
        except PermissionError as err:
            raise PermissionError(
                f"Failed writing atomic temporary configuration file in '{target_dir}': permission denied."
            ) from err
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
