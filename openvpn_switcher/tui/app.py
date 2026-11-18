# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""k9s-style interactive terminal application and controller for OpenVPN Switcher."""

import curses
from typing import Any, Optional

from openvpn_switcher.core.config import ConfigManager
from openvpn_switcher.core.logs import JournalctlLogStreamer, LogStreamer
from openvpn_switcher.core.service import ServiceManager, SystemdServiceManager
from openvpn_switcher.core.template import TemplateManager
from openvpn_switcher.tui.dialogs import ConfirmDialog, PortSelectDialog
from openvpn_switcher.tui.logs import LogViewerScreen
from openvpn_switcher.tui.state import TableColumn, TuiState
from openvpn_switcher.tui.wizard import TemplateWizardScreen, TemplateWizardState


class OpenVpnApp:
    """Main terminal controller and UI engine inspired by k9s."""

    def __init__(
        self,
        stdscr: Any,
        state: TuiState,
        template_manager: TemplateManager,
        service_manager: ServiceManager,
        log_streamer: LogStreamer,
    ) -> None:
        """Initialize OpenVpnApp.

        Args:
            stdscr: Main curses screen window.
            state: UI state machine instance.
            template_manager: Master template rendering engine.
            service_manager: Systemd service management controller.
            log_streamer: Real-time daemon log streamer.
        """
        self.stdscr = stdscr
        self.state = state
        self.template_manager = template_manager
        self.service_manager = service_manager
        self.log_streamer = log_streamer
        self.config_manager = ConfigManager(self.template_manager.target_path)
        self.init_colors()
        self.refresh_service_state()

    def init_colors(self) -> None:
        """Initialize curses color pairs."""
        try:
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                # Pair 1: Normal text / header
                curses.init_pair(1, curses.COLOR_WHITE, -1)
                # Pair 2: Active / Running (Green)
                curses.init_pair(2, curses.COLOR_GREEN, -1)
                # Pair 3: Selection / Inverted
                curses.init_pair(3, curses.COLOR_BLACK, curses.COLOR_WHITE)
                # Pair 4: Inactive / Dimmed
                curses.init_pair(4, curses.COLOR_CYAN, -1)
                # Pair 5: Warnings / Badges
                curses.init_pair(5, curses.COLOR_YELLOW, -1)
        except (curses.error, Exception):
            pass

    @staticmethod
    def _safe_color_pair(pair_number: int) -> int:
        """Safely retrieve color pair attribute without throwing in headless environments."""
        try:
            return curses.color_pair(pair_number)
        except (curses.error, Exception):
            return curses.A_NORMAL

    def refresh_service_state(self) -> None:
        """Query systemd and active configuration to sync state."""
        try:
            self.state.service_state.is_running = self.service_manager.status()
        except Exception:
            self.state.service_state.is_running = False

        # Read active remote from config file
        active_remote = self.config_manager.get_active_remote()
        if active_remote:
            self.state.service_state.active_port = active_remote[1]
            self.state.service_state.active_protocol = active_remote[2]

        if self.state.service_state.is_running and active_remote:
            self.state.service_state.active_server = active_remote[0]
            self.state.set_active_server(active_remote[0])
        else:
            self.state.service_state.active_server = ""
            self.state.set_active_server("")

    def _render_header(self, max_x: int) -> int:
        """Render k9s-style status header.

        Args:
            max_x: Screen width.

        Returns:
            The number of lines rendered.
        """
        unit_name = f"{self.state.service_state.service_name}.service"
        is_running = self.state.service_state.is_running
        status_str = "[ACTIVE]" if is_running else "[INACTIVE]"
        status_attr = (
            self._safe_color_pair(2) | curses.A_BOLD
            if is_running
            else self._safe_color_pair(5) | curses.A_BOLD
        )

        title = " OPENVPN SWITCHER "
        line0 = f"{title}".ljust(max_x - 1)[: max_x - 1]
        try:
            self.stdscr.addstr(0, 0, line0, curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass

        # Details
        active_host = self.state.active_server_host or "None"
        info_line = (
            f" Context: trustzone  Unit: {unit_name}  Status: {status_str}  Active: {active_host}"
        )
        try:
            self.stdscr.addstr(1, 0, info_line[: max_x - 1])
            self.stdscr.addstr(1, len(f" Context: trustzone  Unit: {unit_name}  Status: "), status_str, status_attr)
        except curses.error:
            pass

        # Status feedback message or search query
        if self.state.is_searching:
            search_str = f" Search [/]: {self.state.search_query}_"
            try:
                self.stdscr.addstr(2, 0, search_str[: max_x - 1], curses.A_BOLD | self._safe_color_pair(5))
            except curses.error:
                pass
        else:
            msg = self.state.status_message or "Ready"
            msg_line = f" Message: {msg}"
            try:
                self.stdscr.addstr(2, 0, msg_line[: max_x - 1], curses.A_DIM)
            except curses.error:
                pass

        try:
            self.stdscr.addstr(3, 0, "-" * max(0, max_x - 1), curses.A_DIM)
        except curses.error:
            pass

        return 4

    def _render_table(self, start_y: int, max_y: int, max_x: int) -> None:
        """Render server grid table.

        Args:
            start_y: Starting row.
            max_y: Screen height.
            max_x: Screen width.
        """
        # Compact column layout for standard 80x24 terminals:
        # SEL(2) at 1 | COUNTRY(18) at 4 | PROTO(6) at 23 | PORT(6) at 30 | HOSTNAME(24) at 37 | STATUS(12) at 62
        header_cols = (
            f" {'SEL':2s} {'COUNTRY':18s} {'PROTO':6s} {'PORT':6s} {'SERVER HOSTNAME':24s} {'STATUS':12s}"
        )
        try:
            self.stdscr.addstr(start_y, 0, header_cols[: max_x - 1], curses.A_BOLD | curses.A_UNDERLINE)
        except curses.error:
            pass

        viewport_start_y = start_y + 1
        viewport_height = max(1, max_y - viewport_start_y - 2)

        # Scrolling calculation
        scroll_offset = 0
        if self.state.selected_row >= viewport_height:
            scroll_offset = self.state.selected_row - viewport_height + 1

        for row_idx in range(viewport_height):
            server_idx = scroll_offset + row_idx
            if server_idx >= len(self.state.filtered_servers):
                break

            server = self.state.filtered_servers[server_idx]
            is_active = (
                bool(self.state.active_server_host)
                and server.hostname.strip().lower() == self.state.active_server_host
            )
            is_row_selected = server_idx == self.state.selected_row

            screen_y = viewport_start_y + row_idx

            # Selector badge
            sel_marker = ">" if is_row_selected else " "
            country_display = f"{server.country_code} - {server.country_name}"[:18]
            proto_display = server.protocol.value.upper()[:6]
            port_display = str(server.port)[:6]
            host_display = server.hostname[:24]
            status_display = "● [ACTIVE]" if is_active else "[IDLE]"

            # Active connection rendered in Bold Green across the row
            row_attr = (
                self._safe_color_pair(2) | curses.A_BOLD
                if is_active
                else curses.A_NORMAL
            )

            attr_country = row_attr
            attr_proto = row_attr
            attr_port = row_attr
            attr_host = row_attr

            if is_row_selected:
                if self.state.selected_col == TableColumn.COUNTRY:
                    attr_country = curses.A_REVERSE | curses.A_BOLD
                elif self.state.selected_col == TableColumn.PROTOCOL:
                    attr_proto = curses.A_REVERSE | curses.A_BOLD
                elif self.state.selected_col == TableColumn.PORT:
                    attr_port = curses.A_REVERSE | curses.A_BOLD

            status_attr = (
                self._safe_color_pair(2) | curses.A_BOLD
                if is_active
                else self._safe_color_pair(4)
            )

            def _draw(col_x: int, text: str, width: int, attr: int) -> None:
                avail = max_x - 1 - col_x
                if avail <= 0:
                    return
                clipped = f"{text:{width}s}"[: min(width, avail)]
                try:
                    self.stdscr.addstr(screen_y, col_x, clipped, attr)
                except curses.error:
                    pass

            _draw(1, sel_marker, 2, curses.A_BOLD if is_row_selected else curses.A_NORMAL)
            _draw(4, country_display, 18, attr_country)
            _draw(23, proto_display, 6, attr_proto)
            _draw(30, port_display, 6, attr_port)
            _draw(37, host_display, 24, attr_host)
            _draw(62, status_display, 12, status_attr)

    def _render_footer(self, max_y: int, max_x: int) -> None:
        """Render hotkey actions footer clipped to max_x - 1.

        Args:
            max_y: Screen height.
            max_x: Screen width.
        """
        footer = (
            "[ENTER] Action  [h/l/Tab] Col  [↑/↓] Row  [/] Search  [c] Wizard  [l] Logs  [s/x/r] Daemon  [q] Exit"
        )
        footer_text = footer.center(max_x)[: max_x - 1]
        try:
            self.stdscr.addstr(max_y - 1, 0, footer_text, curses.A_REVERSE | curses.A_BOLD)
        except curses.error:
            pass

    def run(self) -> None:
        """Main application execution loop."""
        self.stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        try:
            while True:
                self.stdscr.clear()
                max_y, max_x = self.stdscr.getmaxyx()

                # Small terminal guard (minimum 50x10)
                if max_y < 10 or max_x < 50:
                    msg = "Terminal too small (min 50x10 required)"
                    try:
                        self.stdscr.addstr(0, 0, msg[: max_x - 1], curses.A_BOLD)
                        self.stdscr.addstr(1, 0, "Press ESC/q to exit...", curses.A_DIM)
                    except curses.error:
                        pass
                    self.stdscr.refresh()
                    key = self.stdscr.getch()
                    if key in (27, ord("q"), ord("Q")):
                        break
                    continue

                # Render UI
                header_height = self._render_header(max_x)
                self._render_table(header_height, max_y, max_x)
                self._render_footer(max_y, max_x)
                self.stdscr.refresh()

                key = self.stdscr.getch()

                # Search bar input mode
                if self.state.is_searching:
                    if key in (27,):  # ESC cancels search
                        self.state.is_searching = False
                        self.state.filter("")
                    elif key in (10, 13, curses.KEY_ENTER):
                        self.state.is_searching = False
                    elif key in (curses.KEY_BACKSPACE, 127, 8):
                        if self.state.search_query:
                            self.state.filter(self.state.search_query[:-1])
                    elif 32 <= key <= 126:
                        self.state.filter(self.state.search_query + chr(key))
                    continue

                # Standard Navigation & Hotkeys
                if key in (curses.KEY_UP, ord("k")):
                    self.state.move_row(-1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    self.state.move_row(1)
                elif key in (curses.KEY_LEFT, ord("h")):
                    self.state.move_col(-1)
                elif key in (curses.KEY_RIGHT, ord("l"), ord("\t")):
                    self.state.move_col(1)
                elif key in (ord("/"),):
                    self.state.is_searching = True
                elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER, 10, 13):
                    self._handle_enter_action()
                elif key in (ord("c"), ord("C")):
                    wizard_state = TemplateWizardState(self.template_manager)
                    wizard = TemplateWizardScreen(self.stdscr, wizard_state)
                    wizard.run()
                    self.refresh_service_state()
                elif key in (ord("l"), ord("L")):
                    log_screen = LogViewerScreen(
                        self.stdscr,
                        self.log_streamer,
                        service_name=self.state.service_state.service_name,
                    )
                    log_screen.run()
                elif key in (ord("s"), ord("S")):
                    self.service_manager.start()
                    self.refresh_service_state()
                    self.state.status_message = "Service start command executed."
                elif key in (ord("x"), ord("X")):
                    self.service_manager.stop()
                    self.refresh_service_state()
                    self.state.status_message = "Service stop command executed."
                elif key in (ord("r"), ord("R")):
                    self.service_manager.restart()
                    self.refresh_service_state()
                    self.state.status_message = "Service restart command executed."
                elif key in (27, ord("q"), ord("Q")):
                    break
        finally:
            if self.log_streamer is not None and self.log_streamer.is_active():
                self.log_streamer.stop()

    def _handle_enter_action(self) -> None:
        """Handle Enter key action on currently focused cell."""
        server = self.state.get_selected_server()
        if server is None:
            return

        if self.state.selected_col == TableColumn.PROTOCOL:
            new_proto = self.state.toggle_protocol_on_selected()
            if new_proto:
                self.state.status_message = f"Protocol toggled to {new_proto.value.upper()}"
        elif self.state.selected_col == TableColumn.PORT:
            ports = self.state.get_ports_for_selected()
            chosen_port = PortSelectDialog(
                self.stdscr,
                f"Select Port ({server.protocol.value.upper()})",
                ports,
                server.port,
            )
            if chosen_port is not None:
                self.state.update_port_on_selected(chosen_port)
                self.state.status_message = f"Port updated to {chosen_port}"
        elif self.state.selected_col == TableColumn.COUNTRY:
            is_active = self.state.is_selected_active()
            if is_active:
                prompt = f"Stop {server.country_name} server ?"
                if ConfirmDialog(self.stdscr, "Stop Connection", prompt, default_yes=False):
                    success = self.service_manager.stop()
                    if success:
                        self.state.set_active_server("")
                        self.state.status_message = f"Stopped {server.country_name} server."
                    else:
                        self.state.status_message = (
                            f"Failed to stop: {self.service_manager.get_last_output()}"
                        )
                    self.refresh_service_state()
            else:
                prompt = f"Enable {server.country_name} server ?"
                if ConfirmDialog(self.stdscr, "Enable Connection", prompt, default_yes=True):
                    try:
                        self.template_manager.render_and_deploy(
                            server, port=server.port, protocol=server.protocol
                        )
                        success = (
                            self.service_manager.restart()
                            if self.state.service_state.is_running
                            else self.service_manager.start()
                        )
                        if success:
                            self.state.set_active_server(server.hostname)
                            self.state.status_message = (
                                f"Connected to {server.country_name} "
                                f"({server.hostname}:{server.port} {server.protocol.value.upper()})"
                            )
                        else:
                            self.state.status_message = (
                                f"Start failed: {self.service_manager.get_last_output()}"
                            )
                    except Exception as err:
                        self.state.status_message = f"Deploy failed: {err}"
                    self.refresh_service_state()

    @staticmethod
    def run_app(
        template_manager: Optional[TemplateManager] = None,
        service_manager: Optional[ServiceManager] = None,
        log_streamer: Optional[LogStreamer] = None,
    ) -> None:
        """Entrypoint wrapper launching OpenVpnApp under curses.wrapper.

        Args:
            template_manager: Optional TemplateManager.
            service_manager: Optional ServiceManager.
            log_streamer: Optional LogStreamer.
        """
        def _main(stdscr: Any) -> None:
            tm = template_manager or TemplateManager()
            sm = service_manager or SystemdServiceManager()
            ls = log_streamer or JournalctlLogStreamer()
            state = TuiState()
            app = OpenVpnApp(stdscr, state, tm, sm, ls)
            app.run()

        curses.wrapper(_main)
