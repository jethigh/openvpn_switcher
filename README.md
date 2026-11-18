# OpenVPN Switcher

**Runtime Environment**: Python 3.9+  
**Operating System**: Linux (Systemd)  
**Dependencies**: Standard Library only (Zero external runtime dependencies)  

---

## 1. System Overview

OpenVPN Switcher is a terminal-based utility and dashboard modeled after `k9s` for managing OpenVPN client connections on Linux systems. It provides dual-mode operation:

1. **Interactive Terminal UI (TUI)**: A curses-based dashboard providing dual-axis cell navigation across countries, protocols, and ports, interactive connection control, a configuration template editor wizard, and a real-time streaming log viewer.
2. **Headless Command-Line Interface (CLI)**: A scriptable command-line interface for querying service status, switching server endpoints, and controlling the underlying systemd service daemon in automated workflows.

Configuration management adheres to **Strategy B (Master Template & Atomic Render Engine)**: baseline configuration directives (certificates, authentication paths, cipher suites, device types) remain immutable within a master template file. When a connection is established, the target runtime configuration is rendered and atomically deployed via temporary file replacement (`os.replace`), preventing partial writes, file corruption, or credential exposure.

---

## 2. Architecture and Component Matrix

```
openvpn_switcher/
├── core/
│   ├── models.py       # Domain entities: ProtocolType, ServerEntry, ServiceState, TemplateConfig
│   ├── catalog.py      # Country and server registry, port profile definitions
│   ├── template.py     # TemplateManager: template validation, placeholder rendering, atomic deployment
│   ├── config.py       # ConfigManager: runtime configuration parser and legacy adapter
│   ├── service.py      # ServiceManager protocol and SystemdServiceManager
│   └── logs.py         # LogStreamer protocol and JournalctlLogStreamer
├── tui/
│   ├── app.py          # OpenVpnApp: main curses dashboard and event loop
│   ├── state.py        # TuiState: headless state machine for table navigation and cell actions
│   ├── dialogs.py      # Modal confirmation and fixed-port selection dialogs
│   ├── wizard.py       # TemplateWizardScreen: interactive configuration and template editor
│   └── logs.py         # LogViewerScreen: real-time streaming journal viewer
└── cli.py              # Dual-mode command-line parser and entrypoint dispatcher
```

| Component | Responsibility | External Interface |
| :--- | :--- | :--- |
| `TemplateManager` | Ingestion, validation, and atomic deployment of OpenVPN configurations | Filesystem POSIX `os.replace` |
| `SystemdServiceManager` | Systemd service lifecycle management (`status`, `start`, `stop`, `restart`) | `systemctl` CLI via `subprocess` |
| `JournalctlLogStreamer` | Real-time daemon log capture into a thread-safe ring buffer | `journalctl -u {service} -f` |
| `OpenVpnApp` | Full-screen interactive terminal user interface | Linux terminal via `curses` |
| `cli.main` | Argument parsing and execution routing | Standard POSIX CLI |

---

## 3. Interactive Terminal UI (TUI)

Executing `openvpn_switcher.py` without arguments launches the full-screen terminal interface.

### 3.1. Navigation and Keybinding Reference

| Key / Sequence | Context | Operational Function |
| :--- | :--- | :--- |
| `↑` / `↓` (or `k` / `j`) | Server Grid | Navigates the active row across available server endpoints. |
| `←` / `→` (or `h` / `l` / `TAB`) | Server Grid | Navigates cell cursor across functional columns (`Country`, `Protocol`, `Port`). |
| `ENTER` on **`Country`** | Cell Action | - If server is **inactive**: Prompts `"Enable {country} server ?"` `[ Yes / No ]`. On `Yes`, renders template, atomically deploys configuration, and starts/restarts OpenVPN.<br>- If server is **active**: Prompts `"Stop {country} server ?"` `[ Yes / No ]`. On `Yes`, stops the OpenVPN service daemon. |
| `ENTER` on **`Protocol`** | Cell Action | Toggles transport protocol between `UDP` and `TCP`. Automatically reconciles the active port with standard protocol defaults. |
| `ENTER` on **`Port`** | Cell Action | Displays a modal dialog listing fixed standard ports for the active transport protocol. |
| `c` | Global | Opens the **Configuration & Template Wizard** (`TemplateWizardScreen`). |
| `l` | Global | Opens the **Real-Time Streaming Log Viewer** (`LogViewerScreen`). |
| `s` | Quick Action | Issues an immediate `start` command to the systemd service. |
| `x` | Quick Action | Issues an immediate `stop` command to the systemd service. |
| `r` | Quick Action | Issues an immediate `restart` command to the systemd service. |
| `/` | Table | Activates instantaneous filtering across country names, ISO codes, and hostnames. |
| `q` / `ESC` | Global | Exits the active modal screen or terminates the application cleanly. |

### 3.2. Visual State Hierarchy

- **Active / Connected Server**: Rendered across all columns in **Bold Green** text with an explicit status badge (`● [ACTIVE]`). This styling persists even when cursor focus is shifted to other rows.
- **Inactive / Idle Servers**: Rendered in standard terminal foreground text with an `[IDLE]` status tag.
- **Cursor Selection**: The currently focused interactive cell is highlighted via reverse video attributes.
- **Terminal Layout Guard**: Table columns are strictly formatted to 74 columns to guarantee zero line wrapping on standard 80x24 terminal displays. Terminals smaller than minimum dimensions (50x10) display an adaptive warning prompt.

### 3.3. Configuration & Template Wizard (`c`)

Accessible via the `c` shortcut, this view enables direct manipulation of the baseline OpenVPN template:

| Action Shortcut | Function | Description |
| :--- | :--- | :--- |
| `e` | Edit Line | Opens an in-place modal prompt to modify the directive on the highlighted line. |
| `i` | Import Active Configuration | Ingests `/etc/openvpn/trustzone.conf`, strips existing active `remote` directives, substitutes `{{REMOTE}}`, and loads it into the editor buffer. |
| `v` | Validate Syntax | Verifies baseline directives (`client`, `dev`, `remote` or placeholder tokens). |
| `s` | Save Template | Commits editor contents to `/etc/openvpn/trustzone.conf.template` via atomic write semantics. |
| `ESC` / `q` | Exit | Discards uncommitted buffer modifications and returns to the server dashboard. |

### 3.4. Real-Time Streaming Log Viewer (`l`)

Accessible via the `l` shortcut, this view attaches to the systemd journal daemon:

| Control | Function | Description |
| :--- | :--- | :--- |
| `f` / `s` | Toggle Follow Mode | Enables or pauses automatic downward scrolling as new log lines arrive. |
| `↑` / `↓` | Line Scroll | Scrolls manually through buffered log lines (automatically pauses follow mode). |
| `PGUP` / `PGDN` | Page Scroll | Traverses buffer by page intervals. |
| `HOME` / `END` | Boundary Jump | Jumps immediately to buffer origin or latest log entries. |
| `c` | Clear Buffer | Clears current terminal view buffer. |
| `ESC` / `q` | Terminate Stream | Halts background streaming subprocess and returns to main table. |

---

## 4. Command-Line Interface (CLI)

The application supports non-interactive execution for automation scripts and cron jobs.

### 4.1. Command Syntax

```bash
openvpn-switcher [OPTIONS]
```

Or direct script execution:

```bash
./openvpn_switcher.py [OPTIONS]
```

### 4.2. Parameter Matrix

| Flag | Long Option | Argument | Description | Default |
| :--- | :--- | :--- | :--- | :--- |
| `-s` | `--server` | `HOSTNAME \| CODE` | Target server hostname or country ISO code (e.g., `de.trust.zone`, `PL`, `US`). | None |
| `-p` | `--port` | `INTEGER` | Port number override (1–65535). | Protocol default |
| | `--proto` | `udp \| tcp` | Transport protocol override. | `udp` |
| `-r` | `--restart` | None | Restarts the target OpenVPN systemd unit. | `False` |
| `-st` | `--status` | None | Queries service status and prints boolean (`True` / `False`). | `False` |
| | `--start` | None | Starts the OpenVPN systemd unit. | `False` |
| | `--stop` | None | Stops the OpenVPN systemd unit. | `False` |
| `-t` | `--template` | `PATH` | Path to master OpenVPN template file. | `/etc/openvpn/trustzone.conf.template` |
| `-c` | `--config` | `PATH` | Path to target active OpenVPN configuration file. | `/etc/openvpn/trustzone.conf` |
| | `--service` | `NAME` | Name of the systemd service unit. | `openvpn` |
| | `--no-sudo` | None | Disables `sudo` prefix when executing `systemctl` commands. | `False` |
| | `--tui` | None | Explicitly invokes the interactive curses TUI dashboard. | `False` |

### 4.3. Exit Codes

| Code | Categorization | Description |
| :--- | :--- | :--- |
| `0` | Success | Command completed successfully, or status query returned `True`. |
| `1` | Runtime Failure | Service command failure, status query returned `False`, or permission denied. |
| `2` | Syntax / Argument Error | Invalid arguments supplied to CLI parser, or invalid port/host parameter values. |

### 4.4. CLI Execution Examples

```bash
# Query active OpenVPN daemon status
./openvpn_switcher.py -st

# Switch endpoint to Switzerland using UDP 1194 and restart service
./openvpn_switcher.py -s CH -p 1194 --proto udp -r

# Switch endpoint to custom server via TCP 443 with custom template and target paths
./openvpn_switcher.py -s de.trust.zone -p 443 --proto tcp -t /path/to/template.conf -c /path/to/trustzone.conf -r

# Stop active OpenVPN daemon without sudo elevation
./openvpn_switcher.py --no-sudo --stop
```

---

## 5. Configuration Template Specification

The master template file (`/etc/openvpn/trustzone.conf.template`) maintains all static directives required by the provider.

### 5.1. Directive Interpolation Rules

The render engine supports three placeholder paradigms:

1. **Explicit Remote Token**:
   ```openvpn
   client
   dev tun
   {{REMOTE}}
   auth-user-pass /etc/openvpn/credentials.txt
   ```
   Renders as: `remote de.trust.zone 1194 udp`

2. **Granular Component Tokens**:
   ```openvpn
   client
   dev tun
   remote {{HOST}} {{PORT}} {{PROTO}}
   ```
   Renders as: `remote de.trust.zone 443 tcp`

3. **Fallback Directive Matching**:
   If no tokens exist, the engine matches existing `^remote\s+.*` lines and replaces them in-place. If no `remote` directive exists, the directive is appended to the file.
4. **Failover Leak Prevention**:
   Any secondary or obsolete active `remote` directives in the template are automatically commented out (`# remote ...`), preventing accidental connection failover.

---

## 6. Backward Compatibility Layer

For legacy integrations written against the original 2018 script, `openvpn_switcher.py` exports the following backward-compatible symbols:

- `ServiceMonitor`: Alias of `SystemdServiceManager`.
- `TZ_Server`: Backward-compatible adapter wrapping `ConfigManager`.
- `CONFIG`: Default path string `/etc/openvpn/trustzone.conf`.

---

## 7. Verification and Testing

The project maintains 100% test coverage across domain models, configuration parsing, template rendering, systemd service management, log streaming, curses dialogs, and CLI routing.

To execute the test suite:

```bash
pytest tests/ -W error -v
```

Verification covers 146 unit test cases executing in isolated environments using standard temporary file fixtures (`tmp_path`) and mock process controllers.
