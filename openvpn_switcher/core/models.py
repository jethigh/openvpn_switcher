# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Domain entities and constants for OpenVPN Switcher."""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List


class ProtocolType(str, Enum):
    """Supported OpenVPN transport protocols."""

    UDP = "udp"
    TCP = "tcp"

    @classmethod
    def from_str(cls, value: str) -> "ProtocolType":
        """Convert a string value to ProtocolType with case-insensitivity.

        Args:
            value: The string representation of the protocol ('udp' or 'tcp').

        Returns:
            The matching ProtocolType enum member.

        Raises:
            ValueError: If the string does not match any protocol.
        """
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        raise ValueError(f"Unsupported protocol type: '{value}'. Expected 'udp' or 'tcp'.")


PROTOCOL_PORTS: Dict[ProtocolType, List[int]] = {
    ProtocolType.UDP: [1194, 53, 80, 443],
    ProtocolType.TCP: [443, 80, 1194, 1443],
}


@dataclass
class ServerEntry:
    """Represents a remote VPN server entry in the catalog."""

    country_code: str
    country_name: str
    hostname: str
    protocol: ProtocolType = ProtocolType.UDP
    port: int = 1194
    is_active: bool = False


@dataclass
class ServiceState:
    """Represents the runtime state of the OpenVPN systemd unit."""

    is_running: bool
    service_name: str
    active_server: str = ""
    active_port: int = 1194
    active_protocol: ProtocolType = ProtocolType.UDP


@dataclass
class TemplateConfig:
    """Represents configuration settings and paths for the master template."""

    template_path: str = "/etc/openvpn/trustzone.conf.template"
    target_path: str = "/etc/openvpn/trustzone.conf"
    backup_enabled: bool = True
    content: str = ""
