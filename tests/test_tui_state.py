# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for TuiState, LogViewerScreen, and OpenVpnApp."""

import curses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openvpn_switcher.core.logs import MockLogStreamer
from openvpn_switcher.core.models import ProtocolType, ServerEntry, ServiceState
from openvpn_switcher.core.service import MockServiceManager
from openvpn_switcher.core.template import TemplateManager
from openvpn_switcher.tui.app import OpenVpnApp
from openvpn_switcher.tui.logs import LogViewerScreen
from openvpn_switcher.tui.state import TableColumn, TuiState


class TestTuiState:
    """Tests for headless TuiState state machine."""

    @pytest.fixture
    def sample_servers(self) -> list[ServerEntry]:
        """Return distinct server fixtures."""
        return [
            ServerEntry(country_code="DE", country_name="Germany", hostname="de.trust.zone", port=1194, protocol=ProtocolType.UDP),
            ServerEntry(country_code="US", country_name="United States", hostname="us.trust.zone", port=443, protocol=ProtocolType.TCP),
            ServerEntry(country_code="CH", country_name="Switzerland", hostname="ch.trust.zone", port=1194, protocol=ProtocolType.UDP),
        ]

    def test_initial_state(self, sample_servers: list[ServerEntry]) -> None:
        """Verify default cursor focus and server list synchronization."""
        state = TuiState(servers=sample_servers, active_server_host="de.trust.zone")
        assert state.selected_row == 0
        assert state.selected_col == TableColumn.COUNTRY
        assert state.is_selected_active() is True
        assert len(state.filtered_servers) == 3

    def test_row_navigation(self, sample_servers: list[ServerEntry]) -> None:
        """Verify moving rows down and up with clamping."""
        state = TuiState(servers=sample_servers)

        state.move_row(1)
        assert state.selected_row == 1

        state.move_row(1)
        assert state.selected_row == 2

        # Clamp at bottom
        state.move_row(1)
        assert state.selected_row == 2

        # Move up
        state.move_row(-1)
        assert state.selected_row == 1

        state.move_row(-1)
        assert state.selected_row == 0

        # Clamp at top
        state.move_row(-1)
        assert state.selected_row == 0

    def test_column_navigation_and_wrapping(self, sample_servers: list[ServerEntry]) -> None:
        """Verify moving columns wraps across COUNTRY, PROTOCOL, PORT."""
        state = TuiState(servers=sample_servers)
        assert state.selected_col == TableColumn.COUNTRY

        state.move_col(1)
        assert state.selected_col == TableColumn.PROTOCOL

        state.move_col(1)
        assert state.selected_col == TableColumn.PORT

        state.move_col(1)
        assert state.selected_col == TableColumn.COUNTRY

        # Left wrap
        state.move_col(-1)
        assert state.selected_col == TableColumn.PORT

    def test_toggle_protocol_on_selected(self, sample_servers: list[ServerEntry]) -> None:
        """Verify protocol toggling updates port if not valid for new protocol."""
        state = TuiState(servers=sample_servers)
        # Server 0 is DE, UDP, port 1194
        new_proto = state.toggle_protocol_on_selected()
        assert new_proto == ProtocolType.TCP
        server = state.get_selected_server()
        assert server is not None
        assert server.protocol == ProtocolType.TCP
        # 1194 is in TCP list [443, 80, 1194, 1443], so preserved
        assert server.port == 1194

        # Set port to 53 (valid in UDP, invalid in TCP)
        server.port = 53
        # Toggle back to TCP (53 invalid in TCP -> reset to default 443)
        server.protocol = ProtocolType.UDP
        state.toggle_protocol_on_selected()
        assert server.protocol == ProtocolType.TCP
        assert server.port == 443

    def test_update_port_on_selected(self, sample_servers: list[ServerEntry]) -> None:
        """Verify custom port update on selected row."""
        state = TuiState(servers=sample_servers)
        state.update_port_on_selected(80)
        server = state.get_selected_server()
        assert server is not None
        assert server.port == 80

    def test_search_filtering(self, sample_servers: list[ServerEntry]) -> None:
        """Verify searching filters by country name, code, and hostname."""
        state = TuiState(servers=sample_servers)

        state.filter("Germany")
        assert len(state.filtered_servers) == 1
        assert state.filtered_servers[0].country_code == "DE"

        state.filter("US")
        assert len(state.filtered_servers) == 1
        assert state.filtered_servers[0].country_code == "US"

        state.filter("trust.zone")
        assert len(state.filtered_servers) == 3

        state.filter("nonexistent")
        assert len(state.filtered_servers) == 0

        # Reset filter
        state.filter("")
        assert len(state.filtered_servers) == 3


class TestLogViewerScreenCurses:
    """Tests for LogViewerScreen curses rendering."""

    def test_small_terminal_guard(self) -> None:
        """Verify LogViewerScreen displays warning on small terminal and exits upon 'q'."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (8, 30)  # below 10x40
        mock_stdscr.getch.return_value = ord("q")

        streamer = MockLogStreamer(["Initial log message"])
        viewer = LogViewerScreen(mock_stdscr, streamer, "openvpn")
        viewer.run()

        calls = [c[0] for c in mock_stdscr.addstr.call_args_list]
        assert any("Terminal too small" in c[2] for c in calls)

    def test_standard_render_and_exit(self) -> None:
        """Verify LogViewerScreen renders header, logs, footer and handles quit key."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        streamer = MockLogStreamer(["Log line 1", "Log line 2"])
        viewer = LogViewerScreen(mock_stdscr, streamer, "openvpn")
        viewer.run()

        mock_stdscr.erase.assert_called()
        mock_stdscr.refresh.assert_called()


class TestOpenVpnAppCurses:
    """Tests for OpenVpnApp curses rendering and event dispatching."""

    @pytest.fixture
    def app_fixture(self, tmp_path: Path) -> OpenVpnApp:
        """Create an OpenVpnApp with mock dependencies."""
        tmpl_file = tmp_path / "trustzone.conf.template"
        tmpl_file.write_text("client\ndev tun\n{{REMOTE}}\n")
        target_file = tmp_path / "trustzone.conf"
        target_file.write_text("remote de.trust.zone 1194 udp\n")

        tm = TemplateManager(template_path=tmpl_file, target_path=target_file)
        sm = MockServiceManager(initial_status=True)
        ls = MockLogStreamer(["Daemon initialized"])
        state = TuiState(active_server_host="de.trust.zone")

        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)

        app = OpenVpnApp(mock_stdscr, state, tm, sm, ls)
        return app

    def test_app_small_terminal_guard(self, app_fixture: OpenVpnApp) -> None:
        """Verify OpenVpnApp displays warning on terminal smaller than 50x10 and exits on 'q'."""
        app_fixture.stdscr.getmaxyx.return_value = (8, 40)  # below 50x10
        app_fixture.stdscr.getch.return_value = ord("q")

        app_fixture.run()
        calls = [c[0] for c in app_fixture.stdscr.addstr.call_args_list]
        assert any("Terminal too small" in c[2] for c in calls)

    def test_app_standard_render_and_quit(self, app_fixture: OpenVpnApp) -> None:
        """Verify OpenVpnApp renders header, table grid, footer and exits cleanly on 'q'."""
        app_fixture.stdscr.getmaxyx.return_value = (24, 80)
        app_fixture.stdscr.getch.return_value = ord("q")

        app_fixture.run()
        app_fixture.stdscr.clear.assert_called()
        app_fixture.stdscr.refresh.assert_called()

    def test_app_service_control_hotkeys(self, app_fixture: OpenVpnApp) -> None:
        """Verify service control hotkeys 's', 'x', 'r' trigger service manager methods."""
        app_fixture.stdscr.getmaxyx.return_value = (24, 80)
        # Sequence of keys: 's', 'x', 'r', then 'q'
        app_fixture.stdscr.getch.side_effect = [ord("s"), ord("x"), ord("r"), ord("q")]

        app_fixture.run()
        assert "start" in app_fixture.service_manager.call_history  # type: ignore[attr-defined]
        assert "stop" in app_fixture.service_manager.call_history   # type: ignore[attr-defined]
        assert "restart" in app_fixture.service_manager.call_history # type: ignore[attr-defined]

    def test_app_search_flow(self, app_fixture: OpenVpnApp) -> None:
        """Verify typing '/' triggers search mode and typing updates filter."""
        app_fixture.stdscr.getmaxyx.return_value = (24, 80)
        # Sequence: '/', 'u', 's', Enter, 'q'
        app_fixture.stdscr.getch.side_effect = [
            ord("/"),
            ord("u"),
            ord("s"),
            10,  # Enter
            ord("q"),
        ]

        app_fixture.run()
        assert "us" in app_fixture.state.search_query.lower()

    def test_render_table_80_columns_no_overflow(self, app_fixture: OpenVpnApp) -> None:
        """Verify that table rows and headers fit strictly within 80 columns without wrapping."""
        app_fixture.stdscr.reset_mock()
        app_fixture._render_table(start_y=4, max_y=24, max_x=80)

        # Inspect all addstr calls made during table rendering
        for call in app_fixture.stdscr.addstr.call_args_list:
            args = call[0]
            col_x = args[1]
            text = args[2]
            # End column index must be strictly less than 80 (indexes 0 to 79)
            assert col_x + len(text) <= 80, f"Overflow detected: col {col_x} + len {len(text)} > 80 (text: '{text}')"

    def test_handle_enter_action_protocol(self, app_fixture: OpenVpnApp) -> None:
        """Verify Enter on PROTOCOL toggles transport protocol."""
        app_fixture.state.selected_col = TableColumn.PROTOCOL
        server = app_fixture.state.get_selected_server()
        assert server is not None
        initial_proto = server.protocol

        app_fixture._handle_enter_action()
        assert server.protocol != initial_proto
        assert "Protocol toggled" in app_fixture.state.status_message

    @patch("openvpn_switcher.tui.app.PortSelectDialog")
    def test_handle_enter_action_port(
        self, mock_port_dialog: MagicMock, app_fixture: OpenVpnApp
    ) -> None:
        """Verify Enter on PORT opens PortSelectDialog and updates port."""
        mock_port_dialog.return_value = 80
        app_fixture.state.selected_col = TableColumn.PORT
        server = app_fixture.state.get_selected_server()
        assert server is not None

        app_fixture._handle_enter_action()
        assert server.port == 80
        assert "Port updated to 80" in app_fixture.state.status_message

    @patch("openvpn_switcher.tui.app.ConfirmDialog")
    def test_handle_enter_action_country_stop_active(
        self, mock_confirm: MagicMock, app_fixture: OpenVpnApp
    ) -> None:
        """Verify Enter on COUNTRY when active prompts to stop connection."""
        mock_confirm.return_value = True
        app_fixture.state.selected_col = TableColumn.COUNTRY
        assert app_fixture.state.is_selected_active() is True

        app_fixture._handle_enter_action()
        mock_confirm.assert_called_once()
        assert "Stop" in mock_confirm.call_args[0][1]
        assert "stop" in app_fixture.service_manager.call_history  # type: ignore[attr-defined]
        assert app_fixture.state.active_server_host == ""

    @patch("openvpn_switcher.tui.app.ConfirmDialog")
    def test_handle_enter_action_country_enable_inactive(
        self, mock_confirm: MagicMock, app_fixture: OpenVpnApp
    ) -> None:
        """Verify Enter on COUNTRY when inactive renders template, deploys, and restarts."""
        mock_confirm.return_value = True
        app_fixture.state.selected_col = TableColumn.COUNTRY
        # Move to inactive server (row 1 is US)
        app_fixture.state.move_row(1)
        assert app_fixture.state.is_selected_active() is False
        target_server = app_fixture.state.get_selected_server()
        assert target_server is not None

        app_fixture._handle_enter_action()
        mock_confirm.assert_called_once()
        assert "Enable" in mock_confirm.call_args[0][1]
        assert app_fixture.state.active_server_host == target_server.hostname.lower()
        assert "Connected to" in app_fixture.state.status_message

    def test_app_run_stops_log_streamer_on_exit(self, app_fixture: OpenVpnApp) -> None:
        """Verify background log streamer is stopped when OpenVpnApp.run exits."""
        app_fixture.log_streamer.start()
        assert app_fixture.log_streamer.is_active() is True

        app_fixture.stdscr.getmaxyx.return_value = (24, 80)
        app_fixture.stdscr.getch.return_value = ord("q")

        app_fixture.run()
        assert app_fixture.log_streamer.is_active() is False
