# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for ConfigManager."""

import os
from pathlib import Path

import pytest

from openvpn_switcher.core.config import ConfigManager
from openvpn_switcher.core.models import ProtocolType


class TestConfigManagerReading:
    """Tests for reading and parsing OpenVPN configuration files."""

    def test_get_active_remote_full_directive(self, tmp_path: Path) -> None:
        """Parse directive containing host, port, and protocol."""
        conf_file = tmp_path / "test.conf"
        conf_file.write_text("client\ndev tun\nremote de.trust.zone 1194 udp\nnobind\n")

        manager = ConfigManager(conf_file)
        result = manager.get_active_remote()
        assert result == ("de.trust.zone", 1194, ProtocolType.UDP)

    def test_get_active_remote_tcp_and_custom_port(self, tmp_path: Path) -> None:
        """Parse directive specifying TCP and non-default port."""
        conf_file = tmp_path / "test.conf"
        conf_file.write_text("client\nremote ch.trust.zone 443 tcp\n")

        manager = ConfigManager(conf_file)
        result = manager.get_active_remote()
        assert result == ("ch.trust.zone", 443, ProtocolType.TCP)

    def test_get_active_remote_omitted_protocol(self, tmp_path: Path) -> None:
        """Parse directive with omitted protocol (defaults to UDP)."""
        conf_file = tmp_path / "test.conf"
        conf_file.write_text("remote us.trust.zone 53\n")

        manager = ConfigManager(conf_file)
        result = manager.get_active_remote()
        assert result == ("us.trust.zone", 53, ProtocolType.UDP)

    def test_get_active_remote_omitted_port_and_protocol(self, tmp_path: Path) -> None:
        """Parse directive with only host (defaults to port 1194, UDP)."""
        conf_file = tmp_path / "test.conf"
        conf_file.write_text("remote pl.trust.zone\n")

        manager = ConfigManager(conf_file)
        result = manager.get_active_remote()
        assert result == ("pl.trust.zone", 1194, ProtocolType.UDP)

    def test_get_active_remote_ignores_comments(self, tmp_path: Path) -> None:
        """Ensure commented remote lines are ignored."""
        conf_file = tmp_path / "test.conf"
        content = (
            "# remote commented.trust.zone 1194 udp\n"
            "; remote semicolon.trust.zone 1194 udp\n"
            "remote real.trust.zone 1194 udp\n"
        )
        conf_file.write_text(content)

        manager = ConfigManager(conf_file)
        result = manager.get_active_remote()
        assert result == ("real.trust.zone", 1194, ProtocolType.UDP)

    def test_get_active_remote_nonexistent_file(self, tmp_path: Path) -> None:
        """Return None if configuration file does not exist."""
        conf_file = tmp_path / "nonexistent.conf"
        manager = ConfigManager(conf_file)
        assert manager.get_active_remote() is None

    def test_get_active_remote_no_remote_in_file(self, tmp_path: Path) -> None:
        """Return None if file exists but contains no remote directive."""
        conf_file = tmp_path / "empty.conf"
        conf_file.write_text("client\ndev tun\nproto udp\n")

        manager = ConfigManager(conf_file)
        assert manager.get_active_remote() is None

    def test_get_active_remote_quoted_host(self, tmp_path: Path) -> None:
        """Parse directive where hostname is enclosed in double or single quotes."""
        conf_file_double = tmp_path / "double.conf"
        conf_file_double.write_text('remote "de.trust.zone" 1194 udp\n')
        manager_double = ConfigManager(conf_file_double)
        assert manager_double.get_active_remote() == ("de.trust.zone", 1194, ProtocolType.UDP)

        conf_file_single = tmp_path / "single.conf"
        conf_file_single.write_text("remote 'ch.trust.zone' 443 tcp\n")
        manager_single = ConfigManager(conf_file_single)
        assert manager_single.get_active_remote() == ("ch.trust.zone", 443, ProtocolType.TCP)

    def test_in_config_matches(self, tmp_path: Path) -> None:
        """Verify in_config correctly identifies matching host (case-insensitive)."""
        conf_file = tmp_path / "test.conf"
        conf_file.write_text("remote de.trust.zone 1194 udp\n")

        manager = ConfigManager(conf_file)
        assert manager.in_config("de.trust.zone") is True
        assert manager.in_config("DE.TRUST.ZONE") is True
        assert manager.in_config("us.trust.zone") is False

    def test_in_config_missing_file(self, tmp_path: Path) -> None:
        """Verify in_config returns False when configuration is absent."""
        manager = ConfigManager(tmp_path / "absent.conf")
        assert manager.in_config("de.trust.zone") is False


class TestConfigManagerWriting:
    """Tests for atomic updating and writing of configuration files."""

    def test_set_remote_replaces_existing_and_preserves_structure(self, tmp_path: Path) -> None:
        """Verify replacing remote preserves other directives, comments, and empty lines."""
        conf_file = tmp_path / "openvpn.conf"
        initial_content = (
            "# Client configuration file\n"
            "client\n"
            "dev tun\n"
            "\n"
            "remote old.trust.zone 1194 udp\n"
            "\n"
            "nobind\n"
            "persist-key\n"
        )
        conf_file.write_text(initial_content)

        manager = ConfigManager(conf_file)
        success = manager.set_remote("nl.trust.zone", 443, ProtocolType.TCP)
        assert success is True

        updated_content = conf_file.read_text()
        expected_content = (
            "# Client configuration file\n"
            "client\n"
            "dev tun\n"
            "\n"
            "remote nl.trust.zone 443 tcp\n"
            "\n"
            "nobind\n"
            "persist-key\n"
        )
        assert updated_content == expected_content
        assert manager.get_active_remote() == ("nl.trust.zone", 443, ProtocolType.TCP)

    def test_set_remote_appends_when_no_remote_present(self, tmp_path: Path) -> None:
        """Verify appending remote directive when none existed."""
        conf_file = tmp_path / "openvpn.conf"
        conf_file.write_text("client\ndev tun\n")

        manager = ConfigManager(conf_file)
        success = manager.set_remote("uk.trust.zone", 1194, ProtocolType.UDP)
        assert success is True

        lines = conf_file.read_text().splitlines()
        assert lines == ["client", "dev tun", "remote uk.trust.zone 1194 udp"]

    def test_set_remote_creates_new_file_if_absent(self, tmp_path: Path) -> None:
        """Verify file creation when target configuration file does not yet exist."""
        conf_file = tmp_path / "new_dir" / "trustzone.conf"
        manager = ConfigManager(conf_file)
        success = manager.set_remote("fr.trust.zone", 80, ProtocolType.TCP)
        assert success is True

        assert conf_file.exists()
        assert conf_file.read_text() == "remote fr.trust.zone 80 tcp\n"

    def test_set_remote_atomic_leaves_no_temporary_files(self, tmp_path: Path) -> None:
        """Ensure no temporary files remain in directory after writing."""
        conf_file = tmp_path / "openvpn.conf"
        conf_file.write_text("remote de.trust.zone 1194 udp\n")

        manager = ConfigManager(conf_file)
        manager.set_remote("us.trust.zone", 53, ProtocolType.UDP)

        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_set_remote_raises_permission_error_on_unwritable_directory(
        self, tmp_path: Path
    ) -> None:
        """Ensure PermissionError is raised when the target directory cannot be written."""
        readonly_dir = tmp_path / "readonly_dir"
        readonly_dir.mkdir()
        # Drop write permissions
        os.chmod(readonly_dir, 0o555)

        conf_file = readonly_dir / "trustzone.conf"
        manager = ConfigManager(conf_file)

        try:
            with pytest.raises(PermissionError, match="not writable"):
                manager.set_remote("de.trust.zone", 1194, ProtocolType.UDP)
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)

    def test_set_remote_raises_permission_error_on_unwritable_file(
        self, tmp_path: Path
    ) -> None:
        """Ensure PermissionError is raised when existing file is read-only."""
        conf_file = tmp_path / "readonly.conf"
        conf_file.write_text("remote de.trust.zone 1194 udp\n")
        os.chmod(conf_file, 0o444)

        manager = ConfigManager(conf_file)

        try:
            with pytest.raises(PermissionError, match="not writable"):
                manager.set_remote("us.trust.zone", 1194, ProtocolType.UDP)
        finally:
            os.chmod(conf_file, 0o644)

    def test_set_remote_validates_host_injection(self, tmp_path: Path) -> None:
        """Reject hosts with newlines, spaces, comment characters, quotes, or empty strings."""
        manager = ConfigManager(tmp_path / "test.conf")

        invalid_hosts = [
            "",
            "   ",
            "de.trust.zone\nremote evil.org 1194 udp",
            "de.trust.zone\rremote evil.org",
            "de trust zone",
            "de.trust.zone#comment",
            "de.trust.zone;comment",
            '"de.trust.zone"',
            "'de.trust.zone'",
        ]
        for bad_host in invalid_hosts:
            with pytest.raises(ValueError, match="Invalid host|Host must be a non-empty string"):
                manager.set_remote(bad_host, 1194, ProtocolType.UDP)

    def test_set_remote_validates_port(self, tmp_path: Path) -> None:
        """Reject invalid ports (< 1, > 65535, bools, non-integers)."""
        manager = ConfigManager(tmp_path / "test.conf")

        invalid_ports = [0, -1, 65536, 70000, True, False, "1194", 1194.0]
        for bad_port in invalid_ports:
            with pytest.raises(ValueError, match="Port must be an integer between 1 and 65535"):
                manager.set_remote("de.trust.zone", bad_port, ProtocolType.UDP)  # type: ignore[arg-type]

    def test_set_remote_validates_protocol(self, tmp_path: Path) -> None:
        """Ensure protocol strings are accepted or rejected if invalid."""
        conf_file = tmp_path / "test.conf"
        manager = ConfigManager(conf_file)

        # Valid string protocols
        assert manager.set_remote("de.trust.zone", 1194, "udp") is True
        assert manager.get_active_remote() == ("de.trust.zone", 1194, ProtocolType.UDP)

        assert manager.set_remote("de.trust.zone", 443, "tcp") is True
        assert manager.get_active_remote() == ("de.trust.zone", 443, ProtocolType.TCP)

        # Invalid protocol
        with pytest.raises(ValueError, match="Unsupported protocol type"):
            manager.set_remote("de.trust.zone", 1194, "sctp")  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="Invalid protocol"):
            manager.set_remote("de.trust.zone", 1194, 123)  # type: ignore[arg-type]

    def test_set_remote_multiple_active_remotes_comments_out_subsequent(
        self, tmp_path: Path
    ) -> None:
        """Ensure subsequent active remotes are commented out to prevent failover/leaks."""
        conf_file = tmp_path / "multi.conf"
        initial_content = (
            "client\n"
            "dev tun\n"
            "remote first.trust.zone 1194 udp\n"
            "nobind\n"
            "remote second.trust.zone 443 tcp\n"
            "remote third.trust.zone 80 udp\n"
            "persist-key\n"
        )
        conf_file.write_text(initial_content)

        manager = ConfigManager(conf_file)
        success = manager.set_remote("active.trust.zone", 53, ProtocolType.UDP)
        assert success is True

        expected_content = (
            "client\n"
            "dev tun\n"
            "remote active.trust.zone 53 udp\n"
            "nobind\n"
            "# remote second.trust.zone 443 tcp\n"
            "# remote third.trust.zone 80 udp\n"
            "persist-key\n"
        )
        assert conf_file.read_text() == expected_content
        assert manager.get_active_remote() == ("active.trust.zone", 53, ProtocolType.UDP)
