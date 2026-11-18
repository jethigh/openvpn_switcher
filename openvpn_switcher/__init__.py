# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""OpenVPN Switcher package and legacy interface compatibility layer."""

from typing import Optional

from openvpn_switcher.cli import main
from openvpn_switcher.core.config import ConfigManager
from openvpn_switcher.core.service import SystemdServiceManager

__version__ = "1.0.0"

CONFIG = "/etc/openvpn/trustzone.conf"


class ServiceMonitor(SystemdServiceManager):
    """Backward compatibility wrapper for legacy ServiceMonitor class."""

    def __init__(self, service: str = "openvpn") -> None:
        super().__init__(service_name=service, use_sudo=True)


class TZ_Server:
    """Backward compatibility wrapper for legacy TZ_Server class."""

    def __init__(self, server: Optional[str] = None, config_path: str = CONFIG) -> None:
        self.server = server or ""
        self.config_manager = ConfigManager(config_path)

    def in_config(self) -> bool:
        """Check whether self.server is currently configured."""
        return self.config_manager.in_config(self.server)

    def set_config(self) -> None:
        """Set self.server as active in the configuration file."""
        if self.server:
            self.config_manager.set_remote(self.server)


__all__ = [
    "CONFIG",
    "ServiceMonitor",
    "TZ_Server",
    "main",
    "__version__",
]
