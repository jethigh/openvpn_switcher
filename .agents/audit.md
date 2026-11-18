# Audit Report: Step 4 (k9s-Style TUI Application Loop, Live Log Viewer, and Controller)

**Auditor**: Simplicio (Senior QA & Security Auditor)  
**Assisted-by**: Antigravity [Gemini 3.8 Flash (High)]  
**Status**: REJECTED  
**Target Files**:
- `openvpn_switcher/tui/app.py`
- `tests/test_tui_state.py`

---

## Findings

STATUS: REJECTED

- **[CRITICAL]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/app.py:158, 217-224`
  - **Issue**: `_render_table()` column layout exceeds standard 80-column terminal width, causing curses to wrap and corrupt adjacent table rows.
  - **Rationale**: `header_cols` is 84 columns wide, and `status_display` is drawn starting at column 73 with width 12. In a standard 80-column terminal (`max_x = 80`), 73 + 12 = 85. In curses, writing past column 79 automatically wraps onto column 0 of the next row (`screen_y + 1`), overwriting the selector marker and country name of the next server (e.g. rendering `V    SE - Sweden` instead of `     SE - Sweden`).
  - **Required Fix**: Compact column positions to fit well within 80 columns (e.g. `SEL` 2 at col 1, `COUNTRY` 18 at col 4, `PROTO` 6 at col 23, `PORT` 6 at col 30, `HOSTNAME` 24 at col 37, `STATUS` 12 at col 62 = total 74 columns), and ensure each column string is safely clipped to `max(0, max_x - 1 - col_start)` so no line ever overflows.
    ```python
    # Example compact layout:
    header_cols = f" {'SEL':2s} {'COUNTRY':18s} {'PROTO':6s} {'PORT':6s} {'SERVER HOSTNAME':24s} {'STATUS':12s}"
    ...
    self.stdscr.addstr(screen_y, 1, f"{sel_marker:2s}"[:max(0, max_x - 2)])
    self.stdscr.addstr(screen_y, 4, f"{country_display:18s}"[:max(0, max_x - 5)], attr_country)
    self.stdscr.addstr(screen_y, 23, f"{proto_display:6s}"[:max(0, max_x - 24)], attr_proto)
    self.stdscr.addstr(screen_y, 30, f"{port_display:6s}"[:max(0, max_x - 31)], attr_port)
    self.stdscr.addstr(screen_y, 37, f"{host_display:24s}"[:max(0, max_x - 38)], attr_host)
    self.stdscr.addstr(screen_y, 62, f"{status_display:12s}"[:max(0, max_x - 63)], status_attr)
    ```

- **[HIGH]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/app.py:242`
  - **Issue**: Process and thread leak when exiting `OpenVpnApp.run()`.
  - **Rationale**: If the live log viewer (`l`) was opened during the session, `self.log_streamer` was started. `OpenVpnApp.run()` lacks a `finally:` block to call `self.log_streamer.stop()`. Consequently, the background daemon thread and the `journalctl -u ... -f` child process remain running in the background after the TUI application exits.
  - **Required Fix**: Wrap the `run()` loop in `try ... finally` and stop the log streamer:
    ```python
    try:
        while True:
            ...
    finally:
        if self.log_streamer is not None and self.log_streamer.is_active():
            self.log_streamer.stop()
    ```

- **[MEDIUM]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/app.py:197-201`
  - **Issue**: Active working server does not display distinct Bold Green styling on the country column when unfocused.
  - **Rationale**: Plan Section 3.3 specifies: `"Working / Active Server: Rendered in distinct Bold Green text with an active status badge... Remains visually distinct even when cursor navigates to other rows."` Currently, only the hostname column is colored green, while `attr_country` defaults to `A_NORMAL`.
  - **Required Fix**: When `is_active` is True and the cell is not selected with reverse video, set `attr_country = self._safe_color_pair(2) | curses.A_BOLD`.

- **[MEDIUM]** `/home/jethigh/Lab/python/openvpn_switcher/tests/test_tui_state.py:227`
  - **Issue**: Incomplete unit test coverage for `OpenVpnApp._handle_enter_action`, table row wrapping in 80-column terminals, and log streamer teardown.
  - **Rationale**: No tests verify that pressing Enter on Country triggers the Enable/Stop confirmation dialogs, that pressing Enter on Protocol toggles protocol, that pressing Enter on Port triggers PortSelectDialog, or that `_render_table` does not wrap across rows in standard 80x24 terminal dimensions.
  - **Required Fix**: Add test cases in `tests/test_tui_state.py` for:
    1. `_handle_enter_action` for Country: Stop connection flow when active, Enable connection flow when inactive.
    2. `_handle_enter_action` for Protocol and Port.
    3. `_render_table` rendering in an 80x24 mock window asserting no row wrapping occurs.
    4. Asserting `log_streamer.stop()` is invoked when `OpenVpnApp.run()` exits.
