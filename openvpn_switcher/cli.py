# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Command Line Interface (CLI) supporting dual headless and interactive TUI modes."""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

from openvpn_switcher.core.catalog import find_server_by_host, get_default_servers
from openvpn_switcher.core.config import ConfigManager
from openvpn_switcher.core.logs import JournalctlLogStreamer, LogStreamer
from openvpn_switcher.core.models import ProtocolType, ServerEntry
from openvpn_switcher.core.service import ServiceManager, SystemdServiceManager
from openvpn_switcher.core.template import TemplateManager
from openvpn_switcher.tui.app import OpenVpnApp


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser.

    Returns:
        Configured argparse.ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="openvpn-switcher",
        description="k9s-style OpenVPN server switcher, template engine, and systemd controller.",
    )

    # Server connection settings
    parser.add_argument(
        "-s",
        "--server",
        type=str,
        default=None,
        help="VPN server hostname or country code (e.g., de.trust.zone, DE, us.trust.zone)",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=None,
        help="Port number override (e.g., 1194, 443, 80)",
    )
    parser.add_argument(
        "--proto",
        type=str,
        choices=["udp", "tcp"],
        default=None,
        help="Transport protocol override (udp or tcp)",
    )

    # Daemon lifecycle controls
    parser.add_argument(
        "-r",
        "--restart",
        action="store_true",
        help="Restart OpenVPN systemd service",
    )
    parser.add_argument(
        "-st",
        "--status",
        action="store_true",
        help="Print OpenVPN systemd service status",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start OpenVPN systemd service",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop OpenVPN systemd service",
    )

    # Configuration file overrides
    parser.add_argument(
        "-t",
        "--template",
        type=str,
        default="/etc/openvpn/trustzone.conf.template",
        help="Path to master template file (default: /etc/openvpn/trustzone.conf.template)",
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        default="/etc/openvpn/trustzone.conf",
        help="Path to target active configuration file (default: /etc/openvpn/trustzone.conf)",
    )
    parser.add_argument(
        "--service",
        type=str,
        default="openvpn",
        help="Systemd service unit name (default: openvpn)",
    )
    parser.add_argument(
        "--no-sudo",
        action="store_true",
        help="Run systemctl commands without sudo elevation",
    )

    # User interface mode
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch interactive curses TUI dashboard",
    )

    return parser


def resolve_server(server_query: str) -> ServerEntry:
    """Resolve user query string to ServerEntry via catalog matching or dynamic construction.

    Args:
        server_query: Hostname, country code, or subdomain string.

    Returns:
        Resolved ServerEntry instance.
    """
    cleaned = server_query.strip()
    servers = get_default_servers()

    # Exact hostname lookup
    matched = find_server_by_host(servers, cleaned)
    if matched:
        return matched

    # Country code lookup (e.g. DE, US)
    query_upper = cleaned.upper()
    for s in servers:
        if s.country_code.upper() == query_upper:
            return s

    # Subdomain lookup (e.g. de -> de.trust.zone)
    query_lower = cleaned.lower()
    for s in servers:
        subdomain = s.hostname.split(".")[0].lower()
        if subdomain == query_lower:
            return s

    # Dynamic ServerEntry for arbitrary custom endpoints
    return ServerEntry(
        country_code="",
        country_name=cleaned,
        hostname=cleaned,
    )


def main(
    argv: Optional[List[str]] = None,
    template_manager: Optional[TemplateManager] = None,
    service_manager: Optional[ServiceManager] = None,
    log_streamer: Optional[LogStreamer] = None,
) -> int:
    """CLI application entrypoint executing headless actions or launching interactive TUI.

    Args:
        argv: Command-line argument list (defaults to sys.argv[1:] if None).
        template_manager: Optional injected TemplateManager instance.
        service_manager: Optional injected ServiceManager instance.
        log_streamer: Optional injected LogStreamer instance.

    Returns:
        Exit code (0 for success, non-zero on failure).
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    # Instantiate managers if not provided via dependency injection
    tm = template_manager or TemplateManager(
        template_path=args.template,
        target_path=args.config,
    )
    sm = service_manager or SystemdServiceManager(
        service_name=args.service,
        use_sudo=not args.no_sudo,
    )

    # Determine execution mode: TUI if no action flags or if explicitly requested
    has_action_flags = bool(
        args.server is not None
        or args.start
        or args.stop
        or args.restart
        or args.status
    )

    if not has_action_flags or args.tui:
        ls = log_streamer or JournalctlLogStreamer(
            service_name=args.service,
            use_sudo=not args.no_sudo,
        )
        try:
            OpenVpnApp.run_app(template_manager=tm, service_manager=sm, log_streamer=ls)
            return 0
        except Exception as err:
            sys.stderr.write(f"TUI Error: {err}\n")
            return 1

    # Headless execution pipeline
    try:
        # Step 1: Server endpoint configuration
        if args.server:
            server_entry = resolve_server(args.server)

            # Determine port override
            port = args.port if args.port is not None else server_entry.port
            if not isinstance(port, int) or port < 1 or port > 65535:
                sys.stderr.write(f"Error: Invalid port '{port}'. Port must be between 1 and 65535.\n")
                return 1

            # Determine protocol override
            if args.proto:
                protocol = ProtocolType.from_str(args.proto)
            else:
                protocol = server_entry.protocol

            # Strategy B template render & deploy (fallback to direct config if template absent)
            target_path = tm.target_path
            if tm.template_path.exists():
                tm.render_and_deploy(server_entry, port=port, protocol=protocol)
            elif target_path.exists():
                cm = ConfigManager(target_path)
                cm.set_remote(server_entry.hostname, port=port, protocol=protocol)
            else:
                tm.render_and_deploy(server_entry, port=port, protocol=protocol)

            print(
                f"Switched server to {server_entry.hostname} "
                f"({port} {protocol.value.upper()})"
            )

        # Step 2: Service stop command
        if args.stop:
            success = sm.stop()
            if not success:
                sys.stderr.write(f"Error: Failed to stop {args.service}: {sm.get_last_output()}\n")
                return 1
            print(f"Service {args.service} stopped.")

        # Step 3: Service start command
        if args.start:
            success = sm.start()
            if not success:
                sys.stderr.write(f"Error: Failed to start {args.service}: {sm.get_last_output()}\n")
                return 1
            print(f"Service {args.service} started.")

        # Step 4: Service restart command
        if args.restart:
            success = sm.restart()
            if not success:
                sys.stderr.write(f"Error: Failed to restart {args.service}: {sm.get_last_output()}\n")
                return 1
            print(f"Service {args.service} restarted.")

        # Step 5: Service status query
        if args.status:
            is_active = sm.status()
            print(is_active)

        return 0

    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1
