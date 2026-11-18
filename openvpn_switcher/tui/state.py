# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Decoupled UI state machine and event handling for k9s-style OpenVPN Switcher."""

from enum import IntEnum
from typing import List, Optional

from openvpn_switcher.core.catalog import get_default_servers, get_ports_for_protocol
from openvpn_switcher.core.models import ProtocolType, ServerEntry, ServiceState


class TableColumn(IntEnum):
    """Selectable table columns in the server grid."""

    COUNTRY = 0
    PROTOCOL = 1
    PORT = 2


class TuiState:
    """Manages tabular navigation, search filtering, cell focus, and active VPN state."""

    def __init__(
        self,
        servers: Optional[List[ServerEntry]] = None,
        active_server_host: str = "",
        service_state: Optional[ServiceState] = None,
    ) -> None:
        """Initialize TuiState.

        Args:
            servers: List of available ServerEntry records (default: TrustZone catalogue).
            active_server_host: Hostname of currently active server directive.
            service_state: Runtime state of the systemd service.
        """
        self.servers: List[ServerEntry] = (
            list(servers) if servers is not None else get_default_servers()
        )
        self.filtered_servers: List[ServerEntry] = list(self.servers)
        self.active_server_host: str = active_server_host.strip().lower()
        self.selected_row: int = 0
        self.selected_col: TableColumn = TableColumn.COUNTRY
        self.search_query: str = ""
        self.is_searching: bool = False
        self.service_state: ServiceState = (
            service_state
            if service_state is not None
            else ServiceState(is_running=False, service_name="openvpn")
        )
        self.status_message: str = ""
        self._sync_active_flags()

    def _sync_active_flags(self) -> None:
        """Synchronize is_active flag across all server records."""
        for server in self.servers:
            server.is_active = (
                bool(self.active_server_host)
                and server.hostname.strip().lower() == self.active_server_host
            )
        for server in self.filtered_servers:
            server.is_active = (
                bool(self.active_server_host)
                and server.hostname.strip().lower() == self.active_server_host
            )

    def set_active_server(self, host: str) -> None:
        """Update active server hostname and synchronize server badges.

        Args:
            host: Active server hostname or empty string if stopped.
        """
        self.active_server_host = host.strip().lower()
        self.service_state.active_server = self.active_server_host
        self._sync_active_flags()

    def move_row(self, delta: int) -> None:
        """Move selected row by delta, constrained within bounds.

        Args:
            delta: Integer row offset (+1 for down, -1 for up).
        """
        if not self.filtered_servers:
            self.selected_row = 0
            return
        self.selected_row = max(0, min(len(self.filtered_servers) - 1, self.selected_row + delta))

    def move_col(self, delta: int) -> None:
        """Move selected column by delta with wrapping across columns.

        Args:
            delta: Integer column offset (+1 for right, -1 for left).
        """
        new_val = (int(self.selected_col) + delta) % 3
        self.selected_col = TableColumn(new_val)

    def set_col(self, col: TableColumn) -> None:
        """Directly focus a table column.

        Args:
            col: Target TableColumn enum member.
        """
        self.selected_col = col

    def get_selected_server(self) -> Optional[ServerEntry]:
        """Retrieve the server entry currently focused by cursor.

        Returns:
            The focused ServerEntry, or None if list is empty.
        """
        if 0 <= self.selected_row < len(self.filtered_servers):
            return self.filtered_servers[self.selected_row]
        return None

    def is_selected_active(self) -> bool:
        """Check if the currently selected row corresponds to the active server.

        Returns:
            True if currently selected server is the active remote, False otherwise.
        """
        server = self.get_selected_server()
        if server is None or not self.active_server_host:
            return False
        return server.hostname.strip().lower() == self.active_server_host

    def toggle_protocol_on_selected(self) -> Optional[ProtocolType]:
        """Toggle UDP <-> TCP on currently focused server and update default port if invalid.

        Returns:
            The new ProtocolType or None if no server is selected.
        """
        server = self.get_selected_server()
        if server is None:
            return None

        new_proto = ProtocolType.TCP if server.protocol == ProtocolType.UDP else ProtocolType.UDP
        server.protocol = new_proto

        valid_ports = get_ports_for_protocol(new_proto)
        if server.port not in valid_ports:
            server.port = valid_ports[0]

        return new_proto

    def update_port_on_selected(self, port: int) -> None:
        """Set custom port on the focused server.

        Args:
            port: Port integer.
        """
        server = self.get_selected_server()
        if server is not None:
            server.port = port

    def get_ports_for_selected(self) -> List[int]:
        """Return available standard ports for the focused server's protocol.

        Returns:
            List of supported integer ports.
        """
        server = self.get_selected_server()
        if server is None:
            return [1194]
        return get_ports_for_protocol(server.protocol)

    def filter(self, query: str) -> None:
        """Filter server list by search string across country name, code, and hostname.

        Args:
            query: Substring to match.
        """
        self.search_query = query.strip().lower()
        if not self.search_query:
            self.filtered_servers = list(self.servers)
        else:
            def _matches(s: ServerEntry) -> bool:
                if self.search_query in s.country_name.lower():
                    return True
                if self.search_query == s.country_code.lower():
                    return True
                subdomain = s.hostname.lower().split(".")[0]
                if self.search_query == subdomain or self.search_query in subdomain:
                    return True
                if "." in self.search_query and self.search_query in s.hostname.lower():
                    return True
                return False

            self.filtered_servers = [s for s in self.servers if _matches(s)]
        self.selected_row = 0
        self._sync_active_flags()
