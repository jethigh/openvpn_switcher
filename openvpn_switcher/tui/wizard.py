# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Interactive Template Editor Wizard and decoupled state logic."""

import curses
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from openvpn_switcher.core.template import TemplateManager
from openvpn_switcher.tui.dialogs import ConfirmDialog


class TemplateWizardState:
    """Decoupled logic engine for Template Editor Wizard."""

    def __init__(self, template_manager: TemplateManager) -> None:
        """Initialize TemplateWizardState.

        Args:
            template_manager: TemplateManager instance for storage and validation.
        """
        self.template_manager = template_manager
        self.content: str = ""
        self.lines: List[str] = []
        self.cursor_line: int = 0
        self.scroll_offset: int = 0
        self.modified: bool = False
        self.status_message: str = ""
        self.errors: List[str] = []
        self.load()

    def load(self) -> str:
        """Load template content from storage and initialize line buffer.

        Returns:
            The loaded template string.
        """
        self.content = self.template_manager.get_template_content()
        self.lines = self.content.splitlines()
        if not self.lines:
            self.lines = [""]
        self.cursor_line = 0
        self.scroll_offset = 0
        self.modified = False
        self.errors = []
        self.status_message = "Template loaded."
        return self.content

    def set_content(self, content: str) -> None:
        """Set custom template content and update line buffers.

        Args:
            content: Raw template string.
        """
        self.content = content
        self.lines = content.splitlines()
        if not self.lines:
            self.lines = [""]
        self.cursor_line = min(self.cursor_line, len(self.lines) - 1)
        self.modified = True
        self.status_message = "Content updated."

    def import_from_config(self, config_path: Union[str, Path]) -> Tuple[bool, str]:
        """Convert an existing OpenVPN configuration into the active template buffer.

        Args:
            config_path: Path to the runtime configuration file.

        Returns:
            Tuple of (success_boolean, message).
        """
        try:
            imported = self.template_manager.import_from_config(config_path)
            self.set_content(imported)
            msg = f"Successfully imported template from {config_path}"
            self.status_message = msg
            return (True, msg)
        except Exception as exc:
            msg = f"Import failed: {exc}"
            self.status_message = msg
            return (False, msg)

    def validate(self) -> List[str]:
        """Execute syntax and directive validation against current content.

        Returns:
            List of validation errors, empty if completely valid.
        """
        self.content = "\n".join(self.lines) + "\n"
        self.errors = self.template_manager.validate(self.content)
        if not self.errors:
            self.status_message = "Validation passed: template syntax is valid."
        else:
            self.status_message = f"Validation failed: {len(self.errors)} error(s) found."
        return self.errors

    def save(self) -> Tuple[bool, str]:
        """Persist current buffer atomically to the master template file.

        Returns:
            Tuple of (success_boolean, message).
        """
        self.content = "\n".join(self.lines) + "\n"
        try:
            self.template_manager.save_template_content(self.content)
            self.modified = False
            msg = "Template saved successfully."
            self.status_message = msg
            return (True, msg)
        except Exception as exc:
            msg = f"Failed to save template: {exc}"
            self.status_message = msg
            return (False, msg)

    def move_up(self) -> None:
        """Move cursor up one line, scrolling view if necessary."""
        if self.cursor_line > 0:
            self.cursor_line -= 1
            if self.cursor_line < self.scroll_offset:
                self.scroll_offset = self.cursor_line

    def move_down(self) -> None:
        """Move cursor down one line, scrolling view if necessary."""
        if self.cursor_line < len(self.lines) - 1:
            self.cursor_line += 1

    def page_up(self, page_size: int = 15) -> None:
        """Move cursor up by page_size."""
        self.cursor_line = max(0, self.cursor_line - page_size)
        self.scroll_offset = max(0, self.scroll_offset - page_size)

    def page_down(self, page_size: int = 15) -> None:
        """Move cursor down by page_size."""
        self.cursor_line = min(len(self.lines) - 1, self.cursor_line + page_size)

    def edit_current_line(self, new_text: str) -> None:
        """Replace the text of the line currently under the cursor.

        Args:
            new_text: New string for the line.
        """
        if 0 <= self.cursor_line < len(self.lines):
            self.lines[self.cursor_line] = new_text
            self.content = "\n".join(self.lines) + "\n"
            self.modified = True
            self.status_message = f"Line {self.cursor_line + 1} edited."

    def add_line(self, text: str = "") -> None:
        """Insert a new line immediately below the current cursor position.

        Args:
            text: Text for the new line.
        """
        insert_idx = self.cursor_line + 1 if self.lines else 0
        self.lines.insert(insert_idx, text)
        self.cursor_line = insert_idx
        self.content = "\n".join(self.lines) + "\n"
        self.modified = True
        self.status_message = f"New line inserted at {insert_idx + 1}."

    def delete_current_line(self) -> None:
        """Remove the line currently under the cursor."""
        if not self.lines:
            return
        del self.lines[self.cursor_line]
        if not self.lines:
            self.lines = [""]
        self.cursor_line = min(self.cursor_line, len(self.lines) - 1)
        self.content = "\n".join(self.lines) + "\n"
        self.modified = True
        self.status_message = "Line deleted."


class TemplateWizardScreen:
    """Curses interface renderer for the Template Editor Wizard."""

    def __init__(self, stdscr: Any, state: TemplateWizardState) -> None:
        """Initialize TemplateWizardScreen.

        Args:
            stdscr: Main curses screen window.
            state: Active TemplateWizardState instance.
        """
        self.stdscr = stdscr
        self.state = state

    def _prompt_line_edit(self, prompt: str, initial: str = "") -> Optional[str]:
        """Display single-line input prompt in a centered modal dialog.

        Args:
            prompt: Header text.
            initial: Pre-filled text.

        Returns:
            The entered string, or None if cancelled.
        """
        max_y, max_x = self.stdscr.getmaxyx()
        width = min(max_x - 4, 70)
        height = 5
        start_y = max(0, (max_y - height) // 2)
        start_x = max(0, (max_x - width) // 2)

        win = curses.newwin(height, width, start_y, start_x)
        win.keypad(True)
        try:
            curses.noecho()
            curses.curs_set(1)
        except curses.error:
            pass

        try:
            win.clear()
            win.box()
            win.addstr(0, 2, f" {prompt} ", curses.A_BOLD)
            win.addstr(1, 2, "Enter value (ESC to cancel):")
            win.addstr(2, 2, initial)
            win.refresh()

            # Read user input
            buffer = list(initial)
            col = len(buffer)
            while True:
                win.move(2, 2)
                win.clrtoeol()
                win.box()
                win.addstr(0, 2, f" {prompt} ", curses.A_BOLD)
                win.addstr(1, 2, "Enter value (ESC to cancel):")
                curr_str = "".join(buffer)[: width - 6]
                win.addstr(2, 2, curr_str)
                win.move(2, 2 + len(curr_str))
                win.refresh()

                key = win.getch()
                if key in (27,):  # ESC
                    return None
                if key in (10, 13, curses.KEY_ENTER):
                    return "".join(buffer)
                if key in (curses.KEY_BACKSPACE, 127, 8):
                    if buffer:
                        buffer.pop()
                elif 32 <= key <= 126:
                    buffer.append(chr(key))
        finally:
            try:
                curses.curs_set(0)
            except curses.error:
                pass
            del win
            self.stdscr.touchwin()
            self.stdscr.refresh()

    def run(self) -> None:
        """Main rendering and event loop for the Template Editor Wizard."""
        self.stdscr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        while True:
            self.stdscr.clear()
            max_y, max_x = self.stdscr.getmaxyx()

            # Small terminal guard (minimum 40x10)
            if max_y < 10 or max_x < 40:
                msg = "Terminal too small (min 40x10 required)"
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

            # 1. Header
            header_title = "CONFIGURATION & TEMPLATE WIZARD"
            mod_badge = " [MODIFIED]" if self.state.modified else " [SAVED]"
            header_line = f"{header_title}{mod_badge}".center(max_x)[: max_x - 1]
            try:
                self.stdscr.addstr(0, 0, header_line, curses.A_REVERSE | curses.A_BOLD)
            except curses.error:
                pass

            # 2. Metadata / Status Info Panel
            tmpl_path_str = f"Template: {self.state.template_manager.template_path}"
            target_path_str = f"Target: {self.state.template_manager.target_path}"
            try:
                self.stdscr.addstr(1, 1, tmpl_path_str[: max_x - 2], curses.A_DIM)
                self.stdscr.addstr(2, 1, target_path_str[: max_x - 2], curses.A_DIM)

                if self.state.errors:
                    err_summary = f"ERRORS ({len(self.state.errors)}): {self.state.errors[0]}"
                    self.stdscr.addstr(3, 1, err_summary[: max_x - 2], curses.A_BOLD)
                else:
                    self.stdscr.addstr(3, 1, self.state.status_message[: max_x - 2], curses.A_NORMAL)

                self.stdscr.addstr(4, 0, "-" * max(0, max_x - 1), curses.A_DIM)
            except curses.error:
                pass

            # 3. Editor Viewport
            viewport_start_y = 5
            viewport_height = max(1, max_y - viewport_start_y - 2)

            # Ensure cursor is within visible viewport
            if self.state.cursor_line < self.state.scroll_offset:
                self.state.scroll_offset = self.state.cursor_line
            elif self.state.cursor_line >= self.state.scroll_offset + viewport_height:
                self.state.scroll_offset = self.state.cursor_line - viewport_height + 1

            for row_idx in range(viewport_height):
                line_idx = self.state.scroll_offset + row_idx
                if line_idx >= len(self.state.lines):
                    break

                line_num_str = f"{line_idx + 1:3d} | "
                line_text = self.state.lines[line_idx]
                full_display = f"{line_num_str}{line_text}"[: max_x - 2]

                screen_y = viewport_start_y + row_idx
                try:
                    if line_idx == self.state.cursor_line:
                        self.stdscr.addstr(
                            screen_y,
                            1,
                            full_display.ljust(max_x - 2),
                            curses.A_REVERSE | curses.A_BOLD,
                        )
                    else:
                        self.stdscr.addstr(screen_y, 1, full_display)
                except curses.error:
                    pass

            # 4. Footer controls (safely clipped to max_x - 1 to prevent bottom-right cell crash)
            footer = (
                "[e] Edit Line  [a] Add Line  [d] Delete  [i] Import  [v] Validate  [s] Save  [ESC/q] Exit"
            )
            footer_text = footer.center(max_x)[: max_x - 1]
            try:
                self.stdscr.addstr(
                    max_y - 1, 0, footer_text, curses.A_REVERSE | curses.A_BOLD
                )
            except curses.error:
                pass

            self.stdscr.refresh()
            key = self.stdscr.getch()

            if key in (curses.KEY_UP, ord("k")):
                self.state.move_up()
            elif key in (curses.KEY_DOWN, ord("j")):
                self.state.move_down()
            elif key in (curses.KEY_PPAGE,):
                self.state.page_up(viewport_height)
            elif key in (curses.KEY_NPAGE,):
                self.state.page_down(viewport_height)
            elif key in (ord("v"), ord("V")):
                self.state.validate()
            elif key in (ord("s"), ord("S")):
                self.state.save()
            elif key in (ord("i"), ord("I")):
                cfg_path = self._prompt_line_edit(
                    "Import Config", str(self.state.template_manager.target_path)
                )
                if cfg_path:
                    self.state.import_from_config(cfg_path)
            elif key in (ord("e"), ord("E")):
                current_text = (
                    self.state.lines[self.state.cursor_line] if self.state.lines else ""
                )
                edited = self._prompt_line_edit(
                    f"Edit Line {self.state.cursor_line + 1}", current_text
                )
                if edited is not None:
                    self.state.edit_current_line(edited)
            elif key in (ord("a"), ord("A")):
                new_line = self._prompt_line_edit("Add Directive Line", "")
                if new_line is not None:
                    self.state.add_line(new_line)
            elif key in (ord("d"), ord("D")):
                if ConfirmDialog(
                    self.stdscr,
                    "Delete Line",
                    f"Delete line {self.state.cursor_line + 1}?",
                    default_yes=False,
                ):
                    self.state.delete_current_line()
            elif key in (27, ord("q"), ord("Q")):
                if self.state.modified:
                    if ConfirmDialog(
                        self.stdscr,
                        "Unsaved Changes",
                        "Discard unsaved template modifications?",
                        default_yes=False,
                    ):
                        break
                else:
                    break
