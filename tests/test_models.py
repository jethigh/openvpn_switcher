# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Unit tests for domain models and data structures."""

import pytest

from openvpn_switcher.core.models import (
    PROTOCOL_PORTS,
    ProtocolType,
    ServerEntry,
    ServiceState,
    TemplateConfig,
)


def test_protocol_type_values() -> None:
    """Verify ProtocolType members match expected string values."""
    assert ProtocolType.UDP.value == "udp"
    assert ProtocolType.TCP.value == "tcp"


def test_protocol_type_from_str() -> None:
    """Verify case-insensitive string parsing."""
    assert ProtocolType.from_str("udp") == ProtocolType.UDP
    assert ProtocolType.from_str("UDP") == ProtocolType.UDP
    assert ProtocolType.from_str("  tcp  ") == ProtocolType.TCP
    assert ProtocolType.from_str("TCP") == ProtocolType.TCP

    with pytest.raises(ValueError, match="Unsupported protocol type"):
        ProtocolType.from_str("invalid")


def test_protocol_ports_mapping() -> None:
    """Verify standard port lists for UDP and TCP."""
    assert PROTOCOL_PORTS[ProtocolType.UDP] == [1194, 53, 80, 443]
    assert PROTOCOL_PORTS[ProtocolType.TCP] == [443, 80, 1194, 1443]


def test_server_entry_defaults() -> None:
    """Verify ServerEntry default fields."""
    server = ServerEntry(country_code="DE", country_name="Germany", hostname="de.trust.zone")
    assert server.country_code == "DE"
    assert server.country_name == "Germany"
    assert server.hostname == "de.trust.zone"
    assert server.protocol == ProtocolType.UDP
    assert server.port == 1194
    assert server.is_active is False


def test_service_state_defaults() -> None:
    """Verify ServiceState default fields."""
    state = ServiceState(is_running=False, service_name="openvpn")
    assert state.is_running is False
    assert state.service_name == "openvpn"
    assert state.active_server == ""
    assert state.active_port == 1194
    assert state.active_protocol == ProtocolType.UDP


def test_template_config_defaults() -> None:
    """Verify TemplateConfig default fields."""
    config = TemplateConfig()
    assert config.template_path == "/etc/openvpn/trustzone.conf.template"
    assert config.target_path == "/etc/openvpn/trustzone.conf"
    assert config.backup_enabled is True
    assert config.content == ""
