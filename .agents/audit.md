# Audit Report: Step 3 (Template Editor Wizard and Modal Dialogs)

**Auditor**: Simplicio (Senior QA & Security Auditor)  
**Assisted-by**: Antigravity [Gemini 3.8 Flash (High)]  
**Status**: REJECTED  
**Target Files**:
- `openvpn_switcher/tui/wizard.py`
- `openvpn_switcher/tui/dialogs.py`
- `tests/test_wizard.py`

---

## Findings

STATUS: REJECTED

- **[CRITICAL]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/wizard.py:313`
  - **Issue**: `TemplateWizardScreen.run()` crashes immediately with `_curses.error: addwstr() returned ERR` when rendering the footer on the screen's bottom line.
  - **Rationale**: The footer is formatted as `footer.center(max_x)[:max_x]`. On row `max_y - 1`, writing a string of length `max_x` reaches the bottom-right character of the terminal window `(max_y - 1, max_x - 1)`. In curses/ncurses, writing to the bottom-right corner character advances the cursor beyond window bounds and causes `addstr()` to return `ERR` and raise `_curses.error`.
  - **Required Fix**: Slice the footer to `max_x - 1` so that the bottom-right cell is not written to, and wrap the footer `addstr` in exception handling:
    ```python
    footer_text = footer.center(max_x)[: max_x - 1]
    try:
        self.stdscr.addstr(max_y - 1, 0, footer_text, curses.A_REVERSE | curses.A_BOLD)
    except curses.error:
        pass
    ```

- **[HIGH]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/dialogs.py:76-81`
  - **Issue**: `ConfirmDialog` and `PortSelectDialog` crash with `curses.error` when the terminal window is small.
  - **Rationale**: If `max_y < 7` or `max_x < 20`, `ConfirmDialog` creates a window with fixed `height = 7`, exceeding `max_y`. In `PortSelectDialog`, if `max_y <= 6`, `height = min(max_y - 4, ...)` becomes `<= 2`, but ports are written starting at row `2 + idx`, exceeding window height and raising `curses.error`.
  - **Required Fix**: Add terminal size guards at the start of both dialog functions:
    ```python
    # In ConfirmDialog:
    max_y, max_x = stdscr.getmaxyx()
    if max_y < 7 or max_x < 24:
        return default_yes

    # In PortSelectDialog:
    max_y, max_x = stdscr.getmaxyx()
    if max_y < 7 or max_x < 24:
        return current_port
    ```

- **[HIGH]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/wizard.py:256-285`
  - **Issue**: `TemplateWizardScreen.run()` crashes on small terminals when `max_y < 10` or `max_x < 40`.
  - **Rationale**: Directives header panel occupies rows 0–4 and viewport starts at row 5 (`viewport_start_y = 5`). If `max_y < 10`, `viewport_start_y + row_idx` and `max_y - 1` (footer) collide and overflow window dimensions, raising `curses.error`.
  - **Required Fix**: Add a terminal size check at the beginning of `TemplateWizardScreen.run()`:
    ```python
    max_y, max_x = self.stdscr.getmaxyx()
    if max_y < 10 or max_x < 40:
        self.stdscr.clear()
        msg = "Terminal too small (min 40x10 required)"
        try:
            self.stdscr.addstr(max_y // 2, max(0, (max_x - len(msg)) // 2), msg[:max_x - 1], curses.A_BOLD)
        except curses.error:
            pass
        self.stdscr.refresh()
        key = self.stdscr.getch()
        if key in (27, ord("q"), ord("Q")):
            break
        continue
    ```

- **[MEDIUM]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/tui/wizard.py:204`
  - **Issue**: `_prompt_line_edit()` calls `curses.echo()` despite implementing a manual character collection and redrawing loop.
  - **Rationale**: `echo()` causes `win.getch()` to automatically write raw keystrokes at the cursor position. When combined with manual buffer updates and `clrtoeol()`, this produces double character echoing, control artifacts on backspace (`^?`), and border flickering.
  - **Required Fix**: Remove `curses.echo()` and keep `curses.noecho()` active throughout `_prompt_line_edit()`.

- **[LOW]** `/home/jethigh/Lab/python/openvpn_switcher/tests/test_wizard.py:1`
  - **Issue**: `tests/test_wizard.py` lacks automated test verification for curses rendering paths in `TemplateWizardScreen`, `ConfirmDialog`, and `PortSelectDialog`.
  - **Rationale**: Only headless state classes were tested, allowing the fatal bottom-right corner curses crash on screen launch to go undetected.
  - **Required Fix**: Add unit tests in `tests/test_wizard.py` utilizing mock curses windows (or `curses.wrapper` in headless pty) to verify that `ConfirmDialog`, `PortSelectDialog`, and `TemplateWizardScreen` render cleanly without throwing curses errors across standard and boundary terminal dimensions.
