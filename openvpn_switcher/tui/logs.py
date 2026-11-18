# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Interactive live log viewer screen for real-time systemd journal output."""

import curses
from typing import Any, List

from openvpn_switcher.core.logs import LogStreamer


class LogViewerScreen:
    """Curses screen for viewing and following real-time OpenVPN log streams."""

    def __init__(
        self,
        stdscr: Any,
        log_streamer: LogStreamer,
        service_name: str = "openvpn",
    ) -> None:
        """Initialize LogViewerScreen.

        Args:
            stdscr: Active curses main window.
            log_streamer: LogStreamer providing continuous log lines.
            service_name: Display name of the monitored service unit.
        """
        self.stdscr = stdscr
        self.log_streamer = log_streamer
        self.service_name = service_name
        self.follow_mode: bool = True
        self.scroll_offset: int = 0

    def run(self) -> None:
        """Main rendering and event loop for the log viewer."""
        self.stdscr.keypad(True)
        self.stdscr.timeout(100)  # Non-blocking poll every 100ms
        try:
            curses.curs_set(0)
        except curses.error:
            pass

        # Ensure streaming is active
        if not self.log_streamer.is_active():
            self.log_streamer.start()

        try:
            while True:
                max_y, max_x = self.stdscr.getmaxyx()

                # Boundary check: minimum terminal dimensions
                if max_y < 10 or max_x < 40:
                    self.stdscr.clear()
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

                lines: List[str] = self.log_streamer.get_lines()
                viewport_height = max(1, max_y - 4)

                # Follow mode logic: keep view scrolled to the tail
                if self.follow_mode:
                    self.scroll_offset = max(0, len(lines) - viewport_height)
                else:
                    max_scroll = max(0, len(lines) - viewport_height)
                    self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

                self.stdscr.erase()

                # 1. Header Line
                status_badge = "[FOLLOW / LIVE]" if self.follow_mode else "[PAUSED]"
                line_count_str = f"({len(lines)} lines)"
                header_text = (
                    f" LOG STREAM: {self.service_name}.service  {status_badge}  {line_count_str} "
                )
                try:
                    self.stdscr.addstr(
                        0,
                        0,
                        header_text.center(max_x)[: max_x - 1],
                        curses.A_REVERSE | curses.A_BOLD,
                    )
                    self.stdscr.addstr(1, 0, "-" * max(0, max_x - 1), curses.A_DIM)
                except curses.error:
                    pass

                # 2. Viewport log lines
                for row_idx in range(viewport_height):
                    line_idx = self.scroll_offset + row_idx
                    if line_idx >= len(lines):
                        break
                    screen_y = 2 + row_idx
                    line_content = lines[line_idx][: max_x - 2]
                    try:
                        self.stdscr.addstr(screen_y, 1, line_content)
                    except curses.error:
                        pass

                # 3. Footer controls
                footer = (
                    "[f/s] Follow/Pause  [↑/↓/PgUp/PgDn] Scroll  [c] Clear  [ESC/q] Back to Table"
                )
                try:
                    self.stdscr.addstr(
                        max_y - 1,
                        0,
                        footer.center(max_x)[: max_x - 1],
                        curses.A_REVERSE | curses.A_BOLD,
                    )
                except curses.error:
                    pass

                self.stdscr.refresh()
                key = self.stdscr.getch()

                if key in (27, ord("q"), ord("Q")):  # ESC or q
                    break
                if key in (ord("f"), ord("F"), ord("s"), ord("S")):
                    self.follow_mode = not self.follow_mode
                elif key in (curses.KEY_UP, ord("k")):
                    self.follow_mode = False
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif key in (curses.KEY_DOWN, ord("j")):
                    max_scroll = max(0, len(lines) - viewport_height)
                    self.scroll_offset = min(max_scroll, self.scroll_offset + 1)
                    if self.scroll_offset >= max_scroll:
                        self.follow_mode = True
                elif key in (curses.KEY_PPAGE,):
                    self.follow_mode = False
                    self.scroll_offset = max(0, self.scroll_offset - viewport_height)
                elif key in (curses.KEY_NPAGE,):
                    max_scroll = max(0, len(lines) - viewport_height)
                    self.scroll_offset = min(max_scroll, self.scroll_offset + viewport_height)
                    if self.scroll_offset >= max_scroll:
                        self.follow_mode = True
                elif key in (curses.KEY_HOME,):
                    self.follow_mode = False
                    self.scroll_offset = 0
                elif key in (curses.KEY_END,):
                    self.follow_mode = True
                elif key in (ord("c"), ord("C")):
                    self.log_streamer.clear()
                    self.scroll_offset = 0
        finally:
            self.stdscr.timeout(-1)  # Restore blocking input
            self.stdscr.touchwin()
            self.stdscr.refresh()
