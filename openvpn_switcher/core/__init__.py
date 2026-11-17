# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Core domain models, catalog, and configuration management."""

from openvpn_switcher.core.catalog import (
    find_server_by_host,
    get_default_servers,
    get_ports_for_protocol,
)
from openvpn_switcher.core.config import ConfigManager
from openvpn_switcher.core.models import (
    PROTOCOL_PORTS,
    ProtocolType,
    ServerEntry,
    ServiceState,
    TemplateConfig,
)
from openvpn_switcher.core.service import (
    MockServiceManager,
    ServiceManager,
    SystemdServiceManager,
)
from openvpn_switcher.core.template import TemplateManager

__all__ = [
    "ConfigManager",
    "MockServiceManager",
    "PROTOCOL_PORTS",
    "ProtocolType",
    "ServerEntry",
    "ServiceManager",
    "ServiceState",
    "SystemdServiceManager",
    "TemplateConfig",
    "TemplateManager",
    "find_server_by_host",
    "get_default_servers",
    "get_ports_for_protocol",
]
