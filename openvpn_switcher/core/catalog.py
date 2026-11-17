# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""VPN server catalog and endpoint registry."""

from copy import deepcopy
from typing import List, Optional

from openvpn_switcher.core.models import PROTOCOL_PORTS, ProtocolType, ServerEntry

_DEFAULT_SERVERS: List[ServerEntry] = [
    ServerEntry(country_code="DE", country_name="Germany", hostname="de.trust.zone"),
    ServerEntry(country_code="US", country_name="United States", hostname="us.trust.zone"),
    ServerEntry(country_code="UK", country_name="United Kingdom", hostname="uk.trust.zone"),
    ServerEntry(country_code="CH", country_name="Switzerland", hostname="ch.trust.zone"),
    ServerEntry(country_code="NL", country_name="Netherlands", hostname="nl.trust.zone"),
    ServerEntry(country_code="FR", country_name="France", hostname="fr.trust.zone"),
    ServerEntry(country_code="PL", country_name="Poland", hostname="pl.trust.zone"),
    ServerEntry(country_code="SE", country_name="Sweden", hostname="se.trust.zone"),
    ServerEntry(country_code="CA", country_name="Canada", hostname="ca.trust.zone"),
    ServerEntry(country_code="AU", country_name="Australia", hostname="au.trust.zone"),
    ServerEntry(country_code="IT", country_name="Italy", hostname="it.trust.zone"),
    ServerEntry(country_code="ES", country_name="Spain", hostname="es.trust.zone"),
    ServerEntry(country_code="JP", country_name="Japan", hostname="jp.trust.zone"),
    ServerEntry(country_code="SG", country_name="Singapore", hostname="sg.trust.zone"),
    ServerEntry(country_code="BR", country_name="Brazil", hostname="br.trust.zone"),
    ServerEntry(country_code="IN", country_name="India", hostname="in.trust.zone"),
    ServerEntry(country_code="ZA", country_name="South Africa", hostname="za.trust.zone"),
]


def get_default_servers() -> List[ServerEntry]:
    """Retrieve a copy of default TrustZone VPN server entries.

    Returns:
        A list of ServerEntry instances.
    """
    return deepcopy(_DEFAULT_SERVERS)


def find_server_by_host(servers: List[ServerEntry], host: str) -> Optional[ServerEntry]:
    """Locate a server entry by its hostname.

    Args:
        servers: List of ServerEntry records to search.
        host: Hostname to match (case-insensitive).

    Returns:
        The matching ServerEntry or None if not found.
    """
    normalized_host = host.strip().lower()
    for server in servers:
        if server.hostname.strip().lower() == normalized_host:
            return server
    return None


def get_ports_for_protocol(protocol: ProtocolType) -> List[int]:
    """Return available ports mapped to the given protocol.

    Args:
        protocol: The transport protocol (UDP or TCP).

    Returns:
        A copy of the list of supported port integers.
    """
    return list(PROTOCOL_PORTS.get(protocol, [1194]))
