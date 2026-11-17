# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Unit tests for catalog and domain models."""

import pytest

from openvpn_switcher.core.catalog import (
    find_server_by_host,
    get_default_servers,
    get_ports_for_protocol,
)
from openvpn_switcher.core.models import (
    PROTOCOL_PORTS,
    ProtocolType,
    ServerEntry,
    ServiceState,
)


class TestProtocolModels:
    """Tests for ProtocolType and protocol port mapping."""

    def test_protocol_type_values(self) -> None:
        """Ensure protocol enum members match expected string values."""
        assert ProtocolType.UDP.value == "udp"
        assert ProtocolType.TCP.value == "tcp"

    def test_protocol_from_str_valid(self) -> None:
        """Test parsing valid protocol strings with various cases and whitespace."""
        assert ProtocolType.from_str("udp") == ProtocolType.UDP
        assert ProtocolType.from_str("UDP") == ProtocolType.UDP
        assert ProtocolType.from_str("  tcp  ") == ProtocolType.TCP
        assert ProtocolType.from_str("TCP") == ProtocolType.TCP

    def test_protocol_from_str_invalid(self) -> None:
        """Test that invalid protocol strings raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported protocol type"):
            ProtocolType.from_str("sctp")

    def test_protocol_ports_mapping(self) -> None:
        """Verify defined ports for UDP and TCP."""
        assert PROTOCOL_PORTS[ProtocolType.UDP] == [1194, 53, 80, 443]
        assert PROTOCOL_PORTS[ProtocolType.TCP] == [443, 80, 1194, 1443]

    def test_get_ports_for_protocol_returns_copy(self) -> None:
        """Ensure get_ports_for_protocol returns an isolated copy."""
        ports = get_ports_for_protocol(ProtocolType.UDP)
        assert ports == [1194, 53, 80, 443]
        ports.append(9999)
        # Original mapping remains unmodified
        assert get_ports_for_protocol(ProtocolType.UDP) == [1194, 53, 80, 443]


class TestDataClasses:
    """Tests for ServerEntry and ServiceState dataclasses."""

    def test_server_entry_defaults(self) -> None:
        """Verify default attribute values for ServerEntry."""
        server = ServerEntry(
            country_code="DE", country_name="Germany", hostname="de.trust.zone"
        )
        assert server.country_code == "DE"
        assert server.country_name == "Germany"
        assert server.hostname == "de.trust.zone"
        assert server.protocol == ProtocolType.UDP
        assert server.port == 1194
        assert server.is_active is False

    def test_service_state_defaults(self) -> None:
        """Verify default attribute values for ServiceState."""
        state = ServiceState(is_running=True, service_name="openvpn@trustzone")
        assert state.is_running is True
        assert state.service_name == "openvpn@trustzone"
        assert state.active_server == ""
        assert state.active_port == 1194
        assert state.active_protocol == ProtocolType.UDP


class TestCatalogFunctions:
    """Tests for server catalog registry functions."""

    def test_get_default_servers_contains_required_countries(self) -> None:
        """Ensure catalog contains major required countries."""
        servers = get_default_servers()
        country_codes = {s.country_code for s in servers}
        required_codes = {"DE", "US", "UK", "CH", "NL", "FR", "PL"}
        assert required_codes.issubset(country_codes)

    def test_get_default_servers_isolation(self) -> None:
        """Ensure modifications to returned servers do not affect subsequent calls."""
        servers1 = get_default_servers()
        servers1[0].is_active = True
        servers1[0].port = 8080

        servers2 = get_default_servers()
        assert servers2[0].is_active is False
        assert servers2[0].port == 1194

    def test_find_server_by_host_found(self) -> None:
        """Verify server lookup by hostname."""
        servers = get_default_servers()
        result = find_server_by_host(servers, "de.trust.zone")
        assert result is not None
        assert result.country_code == "DE"
        assert result.hostname == "de.trust.zone"

    def test_find_server_by_host_case_insensitive(self) -> None:
        """Verify server lookup is case and whitespace insensitive."""
        servers = get_default_servers()
        result = find_server_by_host(servers, "  DE.TRUST.ZONE  ")
        assert result is not None
        assert result.country_code == "DE"

    def test_find_server_by_host_not_found(self) -> None:
        """Verify find_server_by_host returns None when host is absent."""
        servers = get_default_servers()
        result = find_server_by_host(servers, "nonexistent.example.com")
        assert result is None
