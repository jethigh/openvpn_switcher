# Architectural Specification: OpenVPN Switcher (Strategy B: Template-Based Rendering & TUI Wizard)

**Architect**: Salviati (Senior Software Architect & Technical Lead)  
**Assisted-by**: Antigravity [Gemini 3.8 Flash (High)]  
**Repository**: `/home/jethigh/Lab/python/openvpn_switcher`  
**Execution Strategy**: Strategy B (Master Template & Atomic Render Engine with Interactive Template Wizard)  

---

## 1. Executive Summary

This specification defines the architecture for modernizing the OpenVPN Switcher utility into a modular, production-grade application featuring:
1. **Strategy B Configuration Engine**: Decoupling the static OpenVPN baseline configuration into a Master Template file (e.g., `/etc/openvpn/trustzone.conf.template` or user-defined path). The runtime configuration (`/etc/openvpn/trustzone.conf`) is dynamically rendered and atomically deployed upon server switching, ensuring the master configuration remains immutable and free from corruption.
2. **Interactive Template Wizard**: A dedicated terminal interface allowing users to inspect, edit, validate, or generate baseline template directives (e.g., authentication paths, ciphers, MTU, device types) without leaving the tool.
3. **k9s-Style Terminal UI Dashboard**: Dual-axis cursor navigation across table cells (`Country`, `Protocol`, `Port`), interactive protocol toggling (`UDP` <-> `TCP`), fixed-port selection menus, and dynamic confirmation dialogs (`Enable` / `Disable`).
4. **Zero External Dependencies**: Pure Python 3 standard library implementation (`curses`, `subprocess`, `argparse`, `dataclasses`, `enum`, `tempfile`, `pathlib`).

### 1.1. Lifecycle & Version Control Rules

1. **Plan Commitment**: Commit agreed-upon architectural plan (`.agents/plan.md`) and push to remote.
2. **Audit Tracking**: Every Simplicio audit report (`.agents/audit.md`) must be committed.
3. **Step Completion Commitment**: After completing and verifying each atomic step (upon Simplicio approval), commit code, tests, and plan, and push to remote.
4. **Continuous Execution**: Repeat points 2 and 3 sequentially for every step until completion.
5. **Git Standards**: English commit messages with trailer: `Co-authored-by: Antigravity <antigravity@google.com>`.

---

## 2. Component Architecture & Data Flow

### 2.1. System Data Flow Diagram

```
+-----------------------------------------------------------------------------+
|                            Template Wizard (TUI)                            |
|       - Inspect directives       - Edit parameters       - Validate syntax  |
+-----------------------------------------------------------------------------+
                                      |
                                      v Writes/Updates
+-----------------------------------------------------------------------------+
|                     Master Template File (.template)                        |
|   (Defines: dev, auth-user-pass, ca, ciphers, {{REMOTE_DIRECTIVE}})         |
+-----------------------------------------------------------------------------+
                                      |
                                      v Ingests template
+-----------------------------------------------------------------------------+
|                      TemplateManager / RenderEngine                         |
|   1. Injects selected remote host, port, protocol                           |
|   2. Validates rendered configuration syntax                                |
|   3. Writes to temporary file in target directory                           |
|   4. Executes atomic rename (os.replace) to target destination              |
+-----------------------------------------------------------------------------+
                                      |
                                      v Atomically writes
+-----------------------------------------------------------------------------+
|                  Active OpenVPN Configuration File (.conf)                  |
|                      e.g., /etc/openvpn/trustzone.conf                      |
+-----------------------------------------------------------------------------+
                                      |
                                      v Triggers restart
+-----------------------------------------------------------------------------+
|                   SystemdServiceManager (systemctl)                         |
|                       sudo systemctl restart openvpn                        |
+-----------------------------------------------------------------------------+
```

### 2.2. Directory & Package Layout

```
openvpn_switcher/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── models.py            # ProtocolType, ServerEntry, ServiceState, TemplateConfig
│   ├── catalog.py           # Country & server registry, port profile mappings
│   ├── template.py          # TemplateManager: template storage, validation, atomic rendering
│   ├── config.py            # Active config reader & backward-compatibility adapter
│   ├── service.py           # ServiceManager protocol, SystemdServiceManager, MockServiceManager
│   └── logs.py              # LogStreamer protocol, JournalctlLogStreamer, MockLogStreamer
├── tui/
│   ├── __init__.py
│   ├── app.py               # Main Curses application loop (k9s dashboard)
│   ├── dialogs.py           # Modal confirmation and port-picker popups
│   ├── wizard.py            # Template Wizard screen (edit/import/validate template)
│   ├── logs.py              # Interactive live log streaming viewer
│   └── state.py             # UI state machine and event handling decoupled from curses
├── cli.py                   # Argument parser (CLI switches + TUI invocation)
├── pyproject.toml           # Packaging and test configuration
└── openvpn_switcher.py      # Top-level executable wrapper
tests/
├── __init__.py
├── test_catalog.py
├── test_models.py
├── test_template.py
├── test_config.py
├── test_service.py
├── test_logs.py
├── test_wizard.py
├── test_tui_state.py
└── test_cli.py
```

---

## 3. Detailed Component Specifications

### 3.1. Template Engine (`openvpn_switcher/core/template.py`)

The template engine manages the lifecycle of template configurations:

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `template_path` | `Path` | `/etc/openvpn/trustzone.conf.template` | Source template path containing baseline directives |
| `target_path` | `Path` | `/etc/openvpn/trustzone.conf` | Target runtime configuration path |
| `backup_enabled` | `bool` | `True` | Creates `.bak` file prior to atomic replacement |

#### Directive Replacement Rules:
1. If the template contains explicit token `{{REMOTE}}`, replace with `remote <host> <port> <proto>`.
2. If tokens `{{HOST}}`, `{{PORT}}`, `{{PROTO}}` exist, interpolate each independently.
3. If no tokens exist, locate existing `^remote\s+.*` directive and replace it. If absent, append `remote <host> <port> <proto>` to the end of the configuration.
4. Subsequent active `remote` directives in the template are commented out (`# remote ...`) to prevent accidental failovers.
5. All file operations utilize `tempfile.NamedTemporaryFile` within the target directory followed by `os.replace` for atomic POSIX semantics.

### 3.2. Template Editor Wizard (`openvpn_switcher/tui/wizard.py`)

The wizard provides a form-driven modal interface:
1. **Directives Display**: Shows current baseline parameters (Client mode, Device, Authentication file, Data ciphers, MTU, DNS handling).
2. **Actions**:
   - `[e] Edit Directives`: Modify values directly.
   - `[i] Import from Active Config`: Strips active `remote` directive from `/etc/openvpn/trustzone.conf` and converts it into a clean baseline template.
   - `[v] Validate`: Checks that critical directives (`client`, `dev`, `auth-user-pass` or certificates) exist.
   - `[s] Save Template`: Atomically commits changes to `template_path`.
   - `[ESC] Exit / Cancel`: Discards modifications and returns to main table.

### 3.3. k9s-Style Dashboard (`openvpn_switcher/tui/app.py` & `dialogs.py`)

#### Dual-Axis Navigation Grid:
- **Columns**: `[COUNTRY]`, `[PROTOCOL]`, `[PORT]`, `[SERVER HOSTNAME]`.
- **Row Selector**: Up/Down (`k`/`j`) highlights current server row.
- **Column Selector**: Left/Right (`h`/`l`/`TAB`) highlights the active cell.

#### Visual State Representation:
- **Working / Active Server**:
  - Rendered in distinct **Bold Green** text with an active status badge (e.g. `[ACTIVE]` or `● CONNECTED`).
  - Remains visually distinct even when cursor navigates to other rows.
- **Inactive / Non-working Servers**:
  - Rendered in standard foreground color with `[IDLE]` status badge.
- **Cursor Highlight**:
  - Currently focused cell highlighted with reverse video / standout attribute.

#### Cell Actions & Interactive Service Control:
- On `PROTOCOL`: Pressing `ENTER` toggles between `UDP` and `TCP` and updates available port selections.
- On `PORT`: Pressing `ENTER` displays `PortSelectDialog` showing fixed ports for the active protocol:
  - UDP: `1194`, `53`, `80`, `443`
  - TCP: `443`, `80`, `1194`, `1443`
- On `COUNTRY`: Pressing `ENTER` displays interactive service control modal:
  - If server is **inactive / non-working**:
    Prompt: `"Enable {country} server ?"` with options `[ Yes ]` and `[ No ]`.
    On `Yes`: Renders master template with `{host}`, `{port}`, `{proto}`, atomically writes runtime configuration, and starts/restarts the OpenVPN service.
  - If server is **currently active / working**:
    Prompt: `"Stop {country} server ?"` with options `[ Yes ]` and `[ No ]`.
    On `Yes`: Stops the OpenVPN service and updates server status to `[IDLE]`.
- On `c`: Opens the **Configuration & Template Wizard** (`TemplateWizard`).
- On `l`: Opens the **Live Log Viewer** (`LogViewerScreen`) to stream systemd journal / OpenVPN logs in real time.

### 3.4. Interactive Live Log Streamer (`openvpn_switcher/tui/logs.py` & `core/logs.py`)

The log viewer provides real-time visibility into OpenVPN daemon operations inspired by `k9s` pod log streaming:

1. **Streaming Engine (`core/logs.py`)**:
   - `JournalctlLogStreamer`: Executes `journalctl -u {service_name}.service -n 100 -f` as an asynchronous background subprocess.
   - Pushes streaming log entries into a thread-safe ring buffer (`collections.deque(maxlen=2000)`).
   - `MockLogStreamer`: Injects synthetic log entries for automated headless testing.
2. **Viewer Interface (`tui/logs.py`)**:
   - **Header**: Displays unit name (`openvpn.service`), stream status (`STREAMING` / `PAUSED`), and buffer capacity.
   - **Auto-scroll (Follow Mode)**: Automatically scrolls to the bottom as new lines arrive; automatically pauses autoscroll when user scrolls upward.
   - **Controls**:
     - `f` or `s`: Toggle auto-scroll / follow mode.
     - `↑` / `↓` / `PGUP` / `PGDN`: Scroll through log history.
     - `HOME` / `END`: Jump to beginning / latest log output.
     - `c`: Clear current view buffer.
     - `ESC` / `q`: Cleanly terminate stream subprocess and return to main dashboard.

---

## 4. Verification and Quality Gates

| Verification Gate | Tool / Command | Success Criteria |
| :--- | :--- | :--- |
| Unit Test Suite | `/home/jethigh/.local/bin/pytest tests/ -v` | 100% tests passing, zero warnings |
| Atomic File Integrity | Dedicated test in `test_template.py` | Verify file inode changes atomically, no partial writes on error |
| Template Syntax Validation | `TemplateManager.validate()` | Detects missing essential directives, prevents corrupt renders |
| Language & Code Hygiene | Universal Language Check | English only across identifiers, comments, docstrings, CLI output |

---

## 5. Sequential Implementation Roadmap

### Step 1: Core Domain Models, Catalog, and Template Engine (COMPLETED / EXTENDED)
- **Files**:
  - `openvpn_switcher/core/models.py`
  - `openvpn_switcher/core/catalog.py`
  - `openvpn_switcher/core/template.py`
  - `openvpn_switcher/core/config.py`
  - `tests/test_catalog.py`
  - `tests/test_models.py`
  - `tests/test_template.py`
  - `tests/test_config.py`
- **Requirements**:
  - Extend models to support `TemplateConfig`.
  - Implement `TemplateManager` with placeholder interpolation, default template generation, syntax validation, and atomic rendering.
  - Integrate `ConfigManager` to read active status and support Strategy B rendering.
- **Verification Command**:
  `/home/jethigh/.local/bin/pytest tests/test_catalog.py tests/test_models.py tests/test_template.py tests/test_config.py -v`
- **Status**: COMPLETED (APPROVED by Simplicio)

### Step 2: Service Management Protocol, Systemd Controller, and Log Streamer
- **Files**:
  - `openvpn_switcher/core/service.py`
  - `openvpn_switcher/core/logs.py`
  - `tests/test_service.py`
  - `tests/test_logs.py`
- **Requirements**:
  - `ServiceManager` protocol (`status`, `start`, `stop`, `restart`, `get_last_output`).
  - `SystemdServiceManager` capturing stdout/stderr with sudo support.
  - `MockServiceManager` for testing.
  - `JournalctlLogStreamer` with background thread and ring buffer.
  - `MockLogStreamer` for testing log stream events.
- **Verification Command**:
  `/home/jethigh/.local/bin/pytest tests/test_service.py tests/test_logs.py -v`
- **Status**: COMPLETED (APPROVED by Simplicio)

### Step 3: Template Editor Wizard and Modal Dialogs
- **Files**:
  - `openvpn_switcher/tui/dialogs.py` (ConfirmDialog, PortSelectDialog)
  - `openvpn_switcher/tui/wizard.py` (TemplateWizard state and rendering)
  - `tests/test_wizard.py` (Headless testing of template wizard import, edit, validation)
- **Requirements**:
  - Modal popups with keyboard traps and clean curses window restoration.
  - Template editing, validation, and import from existing config.
- **Verification Command**:
  `/home/jethigh/.local/bin/pytest tests/test_wizard.py -v`
- **Status**: PENDING

### Step 4: k9s-Style TUI Application Loop, Live Log Viewer, and Controller
- **Files**:
  - `openvpn_switcher/tui/state.py` (State machine for table, cell cursor, and keybindings)
  - `openvpn_switcher/tui/logs.py` (Interactive live log streaming screen)
  - `openvpn_switcher/tui/app.py` (Curses application loop, status header, table, footer)
  - `tests/test_tui_state.py`
- **Requirements**:
  - Dual-axis navigation with highlighted cell.
  - Active working server highlighted in distinct Bold Green with status badge.
  - Interactive Country cell action: "Enable {country} server ?" (starts/restarts) or "Stop {country} server ?" (stops).
  - Search filtering (`/`), service control (`s`, `x`, `r`), configuration wizard shortcut (`c`), live log viewer shortcut (`l`).
- **Verification Command**:
  `/home/jethigh/.local/bin/pytest tests/test_tui_state.py -v`
- **Status**: PENDING

### Step 5: CLI Dual Mode, Script Wrapper, and Full Suite Quality Gate
- **Files**:
  - `openvpn_switcher/cli.py`
  - `openvpn_switcher.py`
  - `pyproject.toml`
  - `tests/test_cli.py`
- **Requirements**:
  - Support headless flags (`--server`, `--start`, `--stop`, `--restart`, `--status`, `--template`, `--config`).
  - Interactive TUI default when executed without arguments or with `--tui`.
  - Full backward compatibility with existing command invocations.
- **Verification Command**:
  `/home/jethigh/.local/bin/pytest tests/ -v`
- **Status**: PENDING
