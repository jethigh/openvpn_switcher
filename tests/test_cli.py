# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for OpenVPN Switcher CLI and backward compatibility layer."""

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openvpn_switcher.cli import build_parser, main, resolve_server
from openvpn_switcher.core.catalog import get_default_servers
from openvpn_switcher.core.logs import MockLogStreamer
from openvpn_switcher.core.models import ProtocolType
from openvpn_switcher.core.service import MockServiceManager
from openvpn_switcher.core.template import TemplateManager
import openvpn_switcher as legacy_root


class TestCliParser:
    """Tests for CLI argument parser configuration and flag recognition."""

    def test_default_arguments(self) -> None:
        """Verify default argument configurations."""
        parser = build_parser()
        args = parser.parse_args([])

        assert args.server is None
        assert args.port is None
        assert args.proto is None
        assert args.restart is False
        assert args.status is False
        assert args.start is False
        assert args.stop is False
        assert args.template == "/etc/openvpn/trustzone.conf.template"
        assert args.config == "/etc/openvpn/trustzone.conf"
        assert args.service == "openvpn"
        assert args.no_sudo is False
        assert args.tui is False

    def test_help_flag_exits_cleanly(self) -> None:
        """Verify -h / --help prints help and exits with status 0."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--help"])
        assert exc.value.code == 0

    def test_invalid_argument_exits_with_code_2(self) -> None:
        """Verify unrecognized flags trigger exit code 2."""
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--unknown-flag"])
        assert exc.value.code == 2

    def test_flag_parsing_short_and_long(self) -> None:
        """Verify short and long flag parsing across all options."""
        parser = build_parser()
        args = parser.parse_args(
            [
                "-s", "de.trust.zone",
                "-p", "443",
                "--proto", "tcp",
                "-r",
                "-st",
                "--start",
                "--stop",
                "-t", "/tmp/tmpl.conf",
                "-c", "/tmp/out.conf",
                "--service", "openvpn-custom",
                "--no-sudo",
                "--tui",
            ]
        )

        assert args.server == "de.trust.zone"
        assert args.port == 443
        assert args.proto == "tcp"
        assert args.restart is True
        assert args.status is True
        assert args.start is True
        assert args.stop is True
        assert args.template == "/tmp/tmpl.conf"
        assert args.config == "/tmp/out.conf"
        assert args.service == "openvpn-custom"
        assert args.no_sudo is True
        assert args.tui is True


class TestServerResolution:
    """Tests for server query resolution."""

    def test_resolve_exact_hostname(self) -> None:
        """Verify matching by exact hostname."""
        server = resolve_server("us.trust.zone")
        assert server.hostname == "us.trust.zone"
        assert server.country_code == "US"

    def test_resolve_country_code(self) -> None:
        """Verify matching by two-letter country code."""
        server_de = resolve_server("de")
        assert server_de.hostname == "de.trust.zone"
        assert server_de.country_code == "DE"

        server_uk = resolve_server("UK")
        assert server_uk.hostname == "uk.trust.zone"

    def test_resolve_subdomain(self) -> None:
        """Verify matching by country subdomain prefix."""
        server = resolve_server("nl")
        assert server.hostname == "nl.trust.zone"

    def test_resolve_custom_endpoint(self) -> None:
        """Verify arbitrary custom endpoints return dynamic ServerEntry."""
        server = resolve_server("my-custom-vpn.org")
        assert server.hostname == "my-custom-vpn.org"
        assert server.country_code == ""


class TestCliHeadlessExecution:
    """Tests for CLI headless operation with mock services and file systems."""

    @pytest.fixture
    def workspace(self, tmp_path: Path):
        """Create mock workspace with template and target config."""
        tmpl = tmp_path / "trustzone.conf.template"
        tmpl.write_text("client\ndev tun\n{{REMOTE}}\n")
        conf = tmp_path / "trustzone.conf"
        conf.write_text("remote legacy.example.com 1194 udp\n")

        tm = TemplateManager(template_path=tmpl, target_path=conf)
        sm = MockServiceManager(initial_status=True)
        ls = MockLogStreamer(["Log entry"])

        return tm, sm, ls, tmpl, conf

    def test_switch_server_with_template(self, workspace) -> None:
        """Verify -s updates the target configuration via TemplateManager."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "de.trust.zone"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        content = conf.read_text()
        assert "remote de.trust.zone 1194 udp" in content

    def test_switch_server_with_port_and_protocol(self, workspace) -> None:
        """Verify -s with -p and --proto updates port and protocol."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "us.trust.zone", "-p", "443", "--proto", "tcp"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        content = conf.read_text()
        assert "remote us.trust.zone 443 tcp" in content

    def test_switch_server_country_code_resolution(self, workspace) -> None:
        """Verify -s with country code resolves to full hostname."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "FR"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        content = conf.read_text()
        assert "remote fr.trust.zone 1194 udp" in content

    def test_switch_server_invalid_port_returns_1(self, workspace) -> None:
        """Verify invalid port returns error exit code 1."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "de.trust.zone", "-p", "70000"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 1

    def test_switch_server_invalid_host_returns_1(self, workspace) -> None:
        """Verify invalid injection hostname returns error exit code 1."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "de.trust.zone\ninjected_command"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 1

    def test_service_start(self, workspace) -> None:
        """Verify --start calls start on ServiceManager."""
        tm, sm, ls, tmpl, conf = workspace
        sm._is_active = False
        ret = main(
            argv=["--start"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        assert "start" in sm.call_history
        assert sm.status() is True

    def test_service_stop(self, workspace) -> None:
        """Verify --stop calls stop on ServiceManager."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["--stop"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        assert "stop" in sm.call_history
        assert sm.status() is False

    def test_service_restart(self, workspace) -> None:
        """Verify -r / --restart calls restart on ServiceManager."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-r"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        assert "restart" in sm.call_history

    def test_service_status_active(self, workspace, capsys) -> None:
        """Verify -st prints True when service is active."""
        tm, sm, ls, tmpl, conf = workspace
        sm._is_active = True
        ret = main(
            argv=["-st"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "True" in captured.out

    def test_service_status_inactive(self, workspace, capsys) -> None:
        """Verify --status prints False when service is inactive."""
        tm, sm, ls, tmpl, conf = workspace
        sm._running = False
        ret = main(
            argv=["--status"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        captured = capsys.readouterr()
        assert "False" in captured.out

    def test_server_and_restart_combined(self, workspace) -> None:
        """Verify -s and -r can be combined in a single execution."""
        tm, sm, ls, tmpl, conf = workspace
        ret = main(
            argv=["-s", "ch.trust.zone", "-r"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 0
        assert "remote ch.trust.zone 1194 udp" in conf.read_text()
        assert "restart" in sm.call_history

    def test_direct_config_fallback_when_template_absent(self, tmp_path: Path) -> None:
        """Verify fallback to direct config editing when template file is absent."""
        absent_tmpl = tmp_path / "nonexistent.template"
        target_conf = tmp_path / "direct.conf"
        target_conf.write_text("client\ndev tun\nremote old.example.com 1194 udp\n")

        tm = TemplateManager(template_path=absent_tmpl, target_path=target_conf)
        sm = MockServiceManager(initial_status=True)

        ret = main(
            argv=["-s", "pl.trust.zone"],
            template_manager=tm,
            service_manager=sm,
        )
        assert ret == 0
        content = target_conf.read_text()
        assert "remote pl.trust.zone 1194 udp" in content

    def test_service_failure_returns_nonzero(self, workspace) -> None:
        """Verify failing service commands return exit code 1."""
        tm, sm, ls, tmpl, conf = workspace
        sm.should_fail = True
        ret = main(
            argv=["--start"],
            template_manager=tm,
            service_manager=sm,
            log_streamer=ls,
        )
        assert ret == 1


class TestCliTuiInvocation:
    """Tests for interactive TUI invocation logic."""

    @patch("openvpn_switcher.cli.OpenVpnApp.run_app")
    def test_no_args_launches_tui(self, mock_run_app: MagicMock, tmp_path: Path) -> None:
        """Verify invoking main with no arguments defaults to launching the TUI."""
        tmpl = tmp_path / "t.template"
        tmpl.write_text("client\n")
        conf = tmp_path / "t.conf"
        conf.write_text("client\n")
        tm = TemplateManager(tmpl, conf)
        sm = MockServiceManager()

        ret = main(argv=[], template_manager=tm, service_manager=sm)
        assert ret == 0
        mock_run_app.assert_called_once()

    @patch("openvpn_switcher.cli.OpenVpnApp.run_app")
    def test_tui_flag_launches_tui(self, mock_run_app: MagicMock, tmp_path: Path) -> None:
        """Verify --tui forces interactive TUI launch."""
        tmpl = tmp_path / "t.template"
        tmpl.write_text("client\n")
        conf = tmp_path / "t.conf"
        conf.write_text("client\n")
        tm = TemplateManager(tmpl, conf)
        sm = MockServiceManager()

        ret = main(argv=["--tui"], template_manager=tm, service_manager=sm)
        assert ret == 0
        mock_run_app.assert_called_once()

    @patch("openvpn_switcher.cli.OpenVpnApp.run_app")
    def test_tui_error_returns_nonzero(self, mock_run_app: MagicMock) -> None:
        """Verify uncaught TUI exceptions return exit code 1."""
        mock_run_app.side_effect = RuntimeError("Curses terminal error")
        ret = main(argv=["--tui"])
        assert ret == 1


class TestLegacyBackwardCompatibility:
    """Tests for root openvpn_switcher.py backward compatibility interfaces."""

    def test_legacy_module_exports(self) -> None:
        """Verify legacy class definitions and symbols are present in openvpn_switcher."""
        assert hasattr(legacy_root, "ServiceMonitor")
        assert hasattr(legacy_root, "TZ_Server")
        assert hasattr(legacy_root, "CONFIG")
        assert hasattr(legacy_root, "main")

    def test_legacy_tz_server_operations(self, tmp_path: Path) -> None:
        """Verify legacy TZ_Server in_config and set_config work identically."""
        conf = tmp_path / "legacy.conf"
        conf.write_text("client\nremote old.trust.zone 1194 udp\n")

        tz = legacy_root.TZ_Server(server="old.trust.zone", config_path=str(conf))
        assert tz.in_config() is True

        tz_new = legacy_root.TZ_Server(server="new.trust.zone", config_path=str(conf))
        assert tz_new.in_config() is False
        tz_new.set_config()
        assert tz_new.in_config() is True
        assert "remote new.trust.zone 1194 udp" in conf.read_text()

    def test_legacy_service_monitor_instance(self) -> None:
        """Verify ServiceMonitor initializes as a SystemdServiceManager."""
        sm = legacy_root.ServiceMonitor("openvpn-test")
        assert sm.service_name == "openvpn-test"
        assert sm.use_sudo is True
