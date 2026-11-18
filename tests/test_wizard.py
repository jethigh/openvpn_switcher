# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for TemplateWizardState and TUI Dialogs."""

import curses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openvpn_switcher.core.template import TemplateManager
from openvpn_switcher.tui.dialogs import (
    ConfirmDialog,
    ConfirmDialogState,
    PortSelectDialog,
    PortSelectDialogState,
)
from openvpn_switcher.tui.wizard import TemplateWizardScreen, TemplateWizardState


class TestConfirmDialogState:
    """Tests for ConfirmDialogState headless input processing."""

    def test_initial_state(self) -> None:
        """Verify default_yes configuration sets initial selection."""
        state_yes = ConfirmDialogState("Title", "Message", default_yes=True)
        assert state_yes.selected is True

        state_no = ConfirmDialogState("Title", "Message", default_yes=False)
        assert state_no.selected is False

    def test_toggle_navigation(self) -> None:
        """Verify left/right/tab/h/l keys toggle selection."""
        state = ConfirmDialogState("Title", "Message", default_yes=True)

        for key in (curses.KEY_LEFT, curses.KEY_RIGHT, ord("\t"), ord("h"), ord("l")):
            prev = state.selected
            finished, result = state.handle_key(key)
            assert finished is False
            assert result == (not prev)
            assert state.selected == (not prev)

    def test_confirm_selection(self) -> None:
        """Verify enter key completes dialog returning current selection."""
        state = ConfirmDialogState("Title", "Message", default_yes=True)
        finished, result = state.handle_key(ord("\n"))
        assert finished is True
        assert result is True

        state.selected = False
        finished, result = state.handle_key(curses.KEY_ENTER)
        assert finished is True
        assert result is False

    def test_direct_hotkeys(self) -> None:
        """Verify 'y', 'n', ESC (27), and 'q' complete dialog immediately."""
        state = ConfirmDialogState("Title", "Message", default_yes=False)

        assert state.handle_key(ord("y")) == (True, True)
        assert state.handle_key(ord("Y")) == (True, True)
        assert state.handle_key(ord("n")) == (True, False)
        assert state.handle_key(ord("N")) == (True, False)
        assert state.handle_key(27) == (True, False)
        assert state.handle_key(ord("q")) == (True, False)


class TestPortSelectDialogState:
    """Tests for PortSelectDialogState headless selection logic."""

    def test_initial_selection(self) -> None:
        """Verify initial selected_index matches current_port."""
        ports = [1194, 53, 80, 443]
        state = PortSelectDialogState("Select Port", ports, current_port=80)
        assert state.selected_index == 2
        assert state.ports[state.selected_index] == 80

    def test_initial_selection_fallback_when_absent(self) -> None:
        """Verify fallback to index 0 when current_port is not in candidate list."""
        ports = [1194, 53, 80, 443]
        state = PortSelectDialogState("Select Port", ports, current_port=9999)
        assert state.selected_index == 0

    def test_vertical_navigation(self) -> None:
        """Verify up and down keys move selection index within bounds."""
        ports = [1194, 53, 80]
        state = PortSelectDialogState("Select Port", ports, current_port=1194)
        assert state.selected_index == 0

        # Down navigation
        state.handle_key(curses.KEY_DOWN)
        assert state.selected_index == 1
        state.handle_key(ord("j"))
        assert state.selected_index == 2

        # Clamp at bottom
        state.handle_key(curses.KEY_DOWN)
        assert state.selected_index == 2

        # Up navigation
        state.handle_key(curses.KEY_UP)
        assert state.selected_index == 1
        state.handle_key(ord("k"))
        assert state.selected_index == 0

        # Clamp at top
        state.handle_key(curses.KEY_UP)
        assert state.selected_index == 0

    def test_confirm_and_cancel(self) -> None:
        """Verify Enter selects port and ESC/q cancels."""
        ports = [1194, 53, 80]
        state = PortSelectDialogState("Select Port", ports, current_port=53)

        finished, selected_port = state.handle_key(ord("\n"))
        assert finished is True
        assert selected_port == 53

        state = PortSelectDialogState("Select Port", ports, current_port=53)
        finished, selected_port = state.handle_key(27)  # ESC
        assert finished is True
        assert selected_port is None

        state = PortSelectDialogState("Select Port", ports, current_port=53)
        finished, selected_port = state.handle_key(ord("q"))
        assert finished is True
        assert selected_port is None


class TestTemplateWizardState:
    """Tests for TemplateWizardState decoupled business logic."""

    @pytest.fixture
    def manager(self, tmp_path: Path) -> TemplateManager:
        """Return a TemplateManager pointing to isolated temp files."""
        tmpl_file = tmp_path / "trustzone.conf.template"
        tmpl_file.write_text("client\ndev tun\n{{REMOTE}}\nverb 3\n")
        target_file = tmp_path / "trustzone.conf"
        return TemplateManager(template_path=tmpl_file, target_path=target_file)

    def test_load_and_initial_state(self, manager: TemplateManager) -> None:
        """Verify initial loading of template into state."""
        state = TemplateWizardState(manager)
        assert len(state.lines) >= 4
        assert "client" in state.lines[0]
        assert state.modified is False
        assert state.cursor_line == 0
        assert state.scroll_offset == 0

    def test_set_content(self, manager: TemplateManager) -> None:
        """Verify setting custom content updates lines and marks modified."""
        state = TemplateWizardState(manager)
        new_content = "client\ndev tun\nnobind\n{{REMOTE}}\n"
        state.set_content(new_content)

        assert state.content == new_content
        assert len(state.lines) == 4
        assert state.modified is True
        assert state.lines[2] == "nobind"

    def test_edit_line(self, manager: TemplateManager) -> None:
        """Verify editing current line modifies content and sets modified."""
        state = TemplateWizardState(manager)
        state.cursor_line = 1
        state.edit_current_line("dev tap")

        assert state.lines[1] == "dev tap"
        assert "dev tap" in state.content
        assert state.modified is True

    def test_add_and_delete_line(self, manager: TemplateManager) -> None:
        """Verify adding and deleting lines at cursor."""
        state = TemplateWizardState(manager)
        initial_count = len(state.lines)

        state.cursor_line = 0
        state.add_line("proto udp")
        assert len(state.lines) == initial_count + 1
        assert state.lines[1] == "proto udp"
        assert state.cursor_line == 1
        assert state.modified is True

        state.delete_current_line()
        assert len(state.lines) == initial_count
        assert state.lines[1] != "proto udp"

    def test_navigation_methods(self, manager: TemplateManager) -> None:
        """Verify line and page cursor navigation."""
        state = TemplateWizardState(manager)
        assert state.cursor_line == 0

        state.move_down()
        assert state.cursor_line == 1

        state.move_up()
        assert state.cursor_line == 0

        state.page_down(page_size=2)
        assert state.cursor_line == 2

        state.page_up(page_size=2)
        assert state.cursor_line == 0

    def test_validate_success(self, manager: TemplateManager) -> None:
        """Verify validation succeeds when directives are present."""
        state = TemplateWizardState(manager)
        errors = state.validate()
        assert errors == []
        assert "Validation passed" in state.status_message

    def test_validate_failure(self, manager: TemplateManager) -> None:
        """Verify validation errors are captured when essential directives are missing."""
        state = TemplateWizardState(manager)
        state.set_content("verb 3\n")
        errors = state.validate()

        assert len(errors) > 0
        assert "Validation failed" in state.status_message

    def test_save_persists_to_file(self, manager: TemplateManager) -> None:
        """Verify save() writes modified content atomically and resets modified flag."""
        state = TemplateWizardState(manager)
        state.edit_current_line("client # customized")

        success, msg = state.save()
        assert success is True
        assert state.modified is False
        assert "saved successfully" in msg.lower()

        # Check persisted file on disk
        persisted = manager.get_template_content()
        assert "client # customized" in persisted

    def test_import_from_config(self, manager: TemplateManager, tmp_path: Path) -> None:
        """Verify importing an existing config file populates the template buffer."""
        runtime_conf = tmp_path / "runtime.conf"
        runtime_conf.write_text("client\ndev tun\nremote de.trust.zone 1194 udp\nnobind\n")

        state = TemplateWizardState(manager)
        success, msg = state.import_from_config(runtime_conf)

        assert success is True
        assert "{{REMOTE}}" in state.content
        assert "de.trust.zone" not in state.content
        assert state.modified is True

    def test_import_from_config_nonexistent(self, manager: TemplateManager, tmp_path: Path) -> None:
        """Verify importing from a nonexistent path returns failure without crashing."""
        state = TemplateWizardState(manager)
        success, msg = state.import_from_config(tmp_path / "missing.conf")

        assert success is False
        assert "failed" in msg.lower()


class TestCursesRendering:
    """Tests for curses modal dialog and wizard screen rendering."""

    def test_confirm_dialog_small_terminal_guard(self) -> None:
        """Verify small terminal dimensions return default_yes immediately."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (5, 20)  # below 7x24

        res_yes = ConfirmDialog(mock_stdscr, "Confirm", "Enable server?", default_yes=True)
        assert res_yes is True

        res_no = ConfirmDialog(mock_stdscr, "Confirm", "Enable server?", default_yes=False)
        assert res_no is False

    def test_port_select_dialog_small_terminal_guard(self) -> None:
        """Verify small terminal dimensions return current_port immediately."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (5, 20)  # below 7x24

        res = PortSelectDialog(mock_stdscr, "Ports", [1194, 53, 80], current_port=53)
        assert res == 53

    @patch("curses.newwin")
    def test_confirm_dialog_standard_dimensions_render(self, mock_newwin: MagicMock) -> None:
        """Verify ConfirmDialog renders properly on standard terminal dimensions."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)

        mock_win = MagicMock()
        mock_win.getch.return_value = ord("\n")  # Confirm selection
        mock_newwin.return_value = mock_win

        result = ConfirmDialog(mock_stdscr, "Confirm Action", "Enable Germany server?", default_yes=True)
        assert result is True
        mock_win.box.assert_called()
        mock_win.refresh.assert_called()

    @patch("curses.newwin")
    def test_port_select_dialog_standard_dimensions_render(self, mock_newwin: MagicMock) -> None:
        """Verify PortSelectDialog renders candidates properly and returns selected port."""
        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)

        mock_win = MagicMock()
        mock_win.getch.return_value = ord("\n")  # Confirm selection
        mock_newwin.return_value = mock_win

        result = PortSelectDialog(mock_stdscr, "Port Selection", [1194, 53, 80], current_port=1194)
        assert result == 1194
        mock_win.box.assert_called()
        mock_win.refresh.assert_called()

    def test_template_wizard_screen_small_terminal_guard(self, tmp_path: Path) -> None:
        """Verify wizard displays warning on small terminal and exits cleanly upon 'q'."""
        tmpl_file = tmp_path / "trustzone.conf.template"
        tmpl_file.write_text("client\ndev tun\n{{REMOTE}}\n")
        manager = TemplateManager(template_path=tmpl_file, target_path=tmp_path / "trustzone.conf")
        state = TemplateWizardState(manager)

        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (8, 30)  # below 10x40
        mock_stdscr.getch.return_value = ord("q")

        screen = TemplateWizardScreen(mock_stdscr, state)
        screen.run()

        calls = [c[0] for c in mock_stdscr.addstr.call_args_list]
        assert any(c[0] == 0 and c[1] == 0 and "Terminal too small" in c[2] for c in calls)
        mock_stdscr.refresh.assert_called()

    def test_template_wizard_screen_standard_render_and_exit(self, tmp_path: Path) -> None:
        """Verify wizard renders header, status, viewport, footer and exits cleanly upon 'q'."""
        tmpl_file = tmp_path / "trustzone.conf.template"
        tmpl_file.write_text("client\ndev tun\n{{REMOTE}}\n")
        manager = TemplateManager(template_path=tmpl_file, target_path=tmp_path / "trustzone.conf")
        state = TemplateWizardState(manager)

        mock_stdscr = MagicMock()
        mock_stdscr.getmaxyx.return_value = (24, 80)
        mock_stdscr.getch.return_value = ord("q")

        screen = TemplateWizardScreen(mock_stdscr, state)
        screen.run()

        mock_stdscr.clear.assert_called()
        mock_stdscr.refresh.assert_called()
