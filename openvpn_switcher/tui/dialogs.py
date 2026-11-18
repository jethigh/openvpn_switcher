# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Modal dialogs for interactive curses TUI."""

import curses
from typing import Any, List, Optional, Tuple


class ConfirmDialogState:
    """Headless state machine for confirmation dialogs."""

    def __init__(self, title: str, message: str, default_yes: bool = True) -> None:
        """Initialize ConfirmDialogState.

        Args:
            title: Title text for the dialog window.
            message: Confirmation message body.
            default_yes: Whether [ Yes ] is focused by default.
        """
        self.title = title
        self.message = message
        self.selected: bool = default_yes

    def handle_key(self, key: int) -> Tuple[bool, bool]:
        """Process keyboard input.

        Args:
            key: Curses keycode integer.

        Returns:
            Tuple of (is_finished, result_boolean).
        """
        # Toggle selection
        if key in (
            curses.KEY_LEFT,
            curses.KEY_RIGHT,
            ord("\t"),
            ord("h"),
            ord("l"),
        ):
            self.selected = not self.selected
            return (False, self.selected)

        # Confirm choice
        if key in (ord("\n"), ord("\r"), curses.KEY_ENTER, 10, 13):
            return (True, self.selected)

        # Direct hotkeys
        if key in (ord("y"), ord("Y")):
            return (True, True)
        if key in (ord("n"), ord("N"), 27, ord("q")):  # 27 is ESC
            return (True, False)

        return (False, self.selected)


def ConfirmDialog(
    stdscr: Any,
    title: str,
    message: str,
    default_yes: bool = True,
) -> bool:
    """Render a centered modal confirmation dialog and block until selection.

    Args:
        stdscr: Active curses screen window.
        title: Modal box title.
        message: Prompt text to display.
        default_yes: Initial focused button (True for Yes, False for No).

    Returns:
        True if user confirmed (Yes), False otherwise (No or cancelled).
    """
    max_y, max_x = stdscr.getmaxyx()
    if max_y < 7 or max_x < 24:
        return default_yes

    state = ConfirmDialogState(title, message, default_yes)

    width = min(max_x - 4, max(46, len(message) + 8, len(title) + 8))
    width = max(20, min(width, max_x - 2))
    height = 7
    start_y = max(0, (max_y - height) // 2)
    start_x = max(0, (max_x - width) // 2)

    win = curses.newwin(height, width, start_y, start_x)
    win.keypad(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    try:
        while True:
            win.clear()
            win.box()

            # Render title
            title_text = f" {state.title} "
            title_x = max(2, (width - len(title_text)) // 2)
            win.addstr(0, title_x, title_text, curses.A_BOLD)

            # Render message
            msg_text = state.message[: width - 4]
            msg_x = max(2, (width - len(msg_text)) // 2)
            win.addstr(2, msg_x, msg_text)

            # Render buttons: [ Yes ]   [ No ]
            btn_yes = "[ Yes ]"
            btn_no = "[ No ]"
            spacing = 4
            total_btn_len = len(btn_yes) + spacing + len(btn_no)
            btn_start_x = max(2, (width - total_btn_len) // 2)

            attr_yes = curses.A_REVERSE | curses.A_BOLD if state.selected else curses.A_NORMAL
            attr_no = curses.A_REVERSE | curses.A_BOLD if not state.selected else curses.A_NORMAL

            win.addstr(4, btn_start_x, btn_yes, attr_yes)
            win.addstr(4, btn_start_x + len(btn_yes) + spacing, btn_no, attr_no)

            win.refresh()

            key = win.getch()
            finished, result = state.handle_key(key)
            if finished:
                return result
    finally:
        del win
        stdscr.touchwin()
        stdscr.refresh()


class PortSelectDialogState:
    """Headless state machine for port selection dialogs."""

    def __init__(self, title: str, ports: List[int], current_port: int) -> None:
        """Initialize PortSelectDialogState.

        Args:
            title: Title text for the dialog window.
            ports: Candidate port integers.
            current_port: Port currently active for highlighting.
        """
        self.title = title
        self.ports = list(ports)
        self.current_port = current_port
        try:
            self.selected_index = self.ports.index(current_port)
        except ValueError:
            self.selected_index = 0

    def handle_key(self, key: int) -> Tuple[bool, Optional[int]]:
        """Process keyboard input.

        Args:
            key: Curses keycode integer.

        Returns:
            Tuple of (is_finished, selected_port_or_None).
        """
        if not self.ports:
            return (True, None)

        if key in (curses.KEY_UP, ord("k")):
            self.selected_index = max(0, self.selected_index - 1)
            return (False, None)

        if key in (curses.KEY_DOWN, ord("j")):
            self.selected_index = min(len(self.ports) - 1, self.selected_index + 1)
            return (False, None)

        if key in (ord("\n"), ord("\r"), curses.KEY_ENTER, 10, 13):
            return (True, self.ports[self.selected_index])

        if key in (27, ord("q"), ord("Q")):  # 27 is ESC
            return (True, None)

        return (False, None)


def PortSelectDialog(
    stdscr: Any,
    title: str,
    ports: List[int],
    current_port: int,
) -> Optional[int]:
    """Render a centered modal popup for port selection and return the chosen port.

    Args:
        stdscr: Active curses screen window.
        title: Modal box title.
        ports: List of available port integers.
        current_port: Active port.

    Returns:
        Selected port integer or None if cancelled.
    """
    max_y, max_x = stdscr.getmaxyx()
    if max_y < 7 or max_x < 24:
        return current_port

    state = PortSelectDialogState(title, ports, current_port)

    width = min(max_x - 4, max(36, len(title) + 8))
    width = max(20, min(width, max_x - 2))
    height = min(max_y - 2, len(ports) + 4)
    start_y = max(0, (max_y - height) // 2)
    start_x = max(0, (max_x - width) // 2)

    win = curses.newwin(height, width, start_y, start_x)
    win.keypad(True)
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    try:
        while True:
            win.clear()
            win.box()

            # Render title
            title_text = f" {state.title} "
            title_x = max(2, (width - len(title_text)) // 2)
            win.addstr(0, title_x, title_text, curses.A_BOLD)

            # Render candidate ports
            for idx, port in enumerate(state.ports):
                row = 2 + idx
                if row >= height - 1:
                    break

                is_active = port == state.current_port
                active_badge = " (active)" if is_active else ""
                port_str = f"  Port {port}{active_badge}"

                if idx == state.selected_index:
                    attr = curses.A_REVERSE | curses.A_BOLD
                    line_text = f"> {port_str.lstrip()}"
                else:
                    attr = curses.A_NORMAL
                    line_text = f"  {port_str.lstrip()}"

                padded = line_text.ljust(width - 4)[: width - 4]
                win.addstr(row, 2, padded, attr)

            win.refresh()

            key = win.getch()
            finished, selected_port = state.handle_key(key)
            if finished:
                return selected_port
    finally:
        del win
        stdscr.touchwin()
        stdscr.refresh()
