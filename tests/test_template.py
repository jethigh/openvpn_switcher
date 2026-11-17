# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Comprehensive unit tests for TemplateManager."""

import os
from pathlib import Path

import pytest

from openvpn_switcher.core.models import ProtocolType, ServerEntry
from openvpn_switcher.core.template import DEFAULT_TEMPLATE, TemplateManager


class TestTemplateManagerBasics:
    """Tests for template retrieval, storage, and validation."""

    def test_get_template_content_returns_default_when_missing(self, tmp_path: Path) -> None:
        """Verify default template is returned if template file does not exist."""
        manager = TemplateManager(
            template_path=tmp_path / "missing.template",
            target_path=tmp_path / "target.conf",
        )
        content = manager.get_template_content()
        assert content == DEFAULT_TEMPLATE
        assert "{{REMOTE}}" in content

    def test_save_template_content_and_retrieve(self, tmp_path: Path) -> None:
        """Verify atomic saving and subsequent reading of custom template content."""
        template_file = tmp_path / "custom.template"
        manager = TemplateManager(
            template_path=template_file,
            target_path=tmp_path / "target.conf",
        )
        custom_content = "client\ndev tun\n{{REMOTE}}\n"
        manager.save_template_content(custom_content)

        assert template_file.exists()
        assert manager.get_template_content() == custom_content

    def test_validate_template_valid(self, tmp_path: Path) -> None:
        """Ensure a valid template returns no validation errors."""
        manager = TemplateManager(
            template_path=tmp_path / "test.template",
            target_path=tmp_path / "target.conf",
        )
        valid_content = "client\ndev tun\n{{REMOTE}}\n"
        errors = manager.validate(valid_content)
        assert errors == []

    def test_validate_template_missing_directives(self, tmp_path: Path) -> None:
        """Ensure missing directives are properly identified."""
        manager = TemplateManager(
            template_path=tmp_path / "test.template",
            target_path=tmp_path / "target.conf",
        )
        invalid_content = "proto udp\nnobind\n"
        errors = manager.validate(invalid_content)
        assert any("client" in e for e in errors)
        assert any("dev" in e for e in errors)
        assert any("remote" in e.lower() for e in errors)


class TestTemplateManagerRendering:
    """Tests for placeholder interpolation, directives replacement, and sanitization."""

    @pytest.fixture
    def sample_server(self) -> ServerEntry:
        """Return a sample ServerEntry."""
        return ServerEntry(
            country_code="DE",
            country_name="Germany",
            hostname="de.trust.zone",
            protocol=ProtocolType.UDP,
            port=1194,
        )

    def test_render_with_remote_placeholder(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify {{REMOTE}} token is correctly replaced."""
        template_file = tmp_path / "template.conf"
        template_file.write_text("client\ndev tun\n{{REMOTE}}\nnobind\n")
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server, port=443, protocol=ProtocolType.TCP)
        assert "remote de.trust.zone 443 tcp" in rendered
        assert "{{REMOTE}}" not in rendered

    def test_render_with_individual_tokens(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify {{HOST}}, {{PORT}}, and {{PROTO}} tokens are interpolated."""
        template_file = tmp_path / "template.conf"
        template_file.write_text("client\ndev tun\nremote {{HOST}} {{PORT}} {{PROTO}}\n")
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server, port=80, protocol=ProtocolType.TCP)
        assert "remote de.trust.zone 80 tcp\n" in rendered
        assert "{{HOST}}" not in rendered

    def test_render_with_tokens_preceded_by_legacy_remote(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify preceding legacy remote is commented out and token-interpolated server remains active."""
        template_file = tmp_path / "template.conf"
        content = (
            "client\n"
            "dev tun\n"
            "remote legacy.trust.zone 1194 udp\n"
            "remote {{HOST}} {{PORT}} {{PROTO}}\n"
            "nobind\n"
        )
        template_file.write_text(content)
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server, port=443, protocol=ProtocolType.TCP)
        assert "# remote legacy.trust.zone 1194 udp\n" in rendered
        assert "remote de.trust.zone 443 tcp\n" in rendered

    def test_render_without_placeholders_replaces_active_remote(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify replacement of existing active remote directive when tokens are absent."""
        template_file = tmp_path / "template.conf"
        template_file.write_text("client\ndev tun\nremote old.server 1194 udp\nnobind\n")
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server, port=53, protocol=ProtocolType.UDP)
        assert "remote de.trust.zone 53 udp" in rendered
        assert "old.server" not in rendered

    def test_render_without_placeholders_appends_remote_if_missing(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify remote directive is appended when no remote exists in template."""
        template_file = tmp_path / "template.conf"
        template_file.write_text("client\ndev tun\nnobind\n")
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server)
        lines = rendered.splitlines()
        assert lines[-1] == "remote de.trust.zone 1194 udp"

    def test_render_comments_out_duplicate_active_remotes(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify that duplicate active remotes are commented out."""
        template_file = tmp_path / "template.conf"
        content = (
            "client\n"
            "dev tun\n"
            "remote first.server 1194 udp\n"
            "nobind\n"
            "remote second.server 443 tcp\n"
        )
        template_file.write_text(content)
        manager = TemplateManager(template_path=template_file, target_path=tmp_path / "target.conf")

        rendered = manager.render(sample_server, port=1194, protocol=ProtocolType.UDP)
        assert "remote de.trust.zone 1194 udp\n" in rendered
        assert "# remote second.server 443 tcp" in rendered

    def test_render_validates_inputs(self, tmp_path: Path, sample_server: ServerEntry) -> None:
        """Verify input validation prevents injections and illegal values."""
        manager = TemplateManager(
            template_path=tmp_path / "template.conf",
            target_path=tmp_path / "target.conf",
        )

        # Host with newline injection
        bad_server = ServerEntry(
            country_code="XX",
            country_name="Bad",
            hostname="de.trust.zone\nremote evil.org 1194 udp",
        )
        with pytest.raises(ValueError, match="Invalid host"):
            manager.render(bad_server)

        # Port validation
        with pytest.raises(ValueError, match="Port must be an integer"):
            manager.render(sample_server, port=70000)

        with pytest.raises(ValueError, match="Port must be an integer"):
            manager.render(sample_server, port=True)  # type: ignore[arg-type]

        # Protocol validation
        with pytest.raises(ValueError, match="Unsupported protocol type"):
            manager.render(sample_server, protocol="sctp")  # type: ignore[arg-type]


class TestTemplateManagerDeployAndImport:
    """Tests for deploying configurations, backups, and importing from existing files."""

    @pytest.fixture
    def sample_server(self) -> ServerEntry:
        """Return a sample ServerEntry."""
        return ServerEntry(
            country_code="US",
            country_name="United States",
            hostname="us.trust.zone",
            protocol=ProtocolType.UDP,
            port=1194,
        )

    def test_render_and_deploy_with_backup(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify atomic deploy creates .bak backup of existing target configuration."""
        template_file = tmp_path / "master.template"
        template_file.write_text("client\ndev tun\n{{REMOTE}}\n")

        target_file = tmp_path / "trustzone.conf"
        target_file.write_text("old runtime configuration")

        manager = TemplateManager(
            template_path=template_file,
            target_path=target_file,
            backup_enabled=True,
        )
        deployed_path = manager.render_and_deploy(sample_server, port=53, protocol=ProtocolType.UDP)

        assert deployed_path == target_file
        assert "remote us.trust.zone 53 udp" in target_file.read_text()

        backup_file = tmp_path / "trustzone.conf.bak"
        assert backup_file.exists()
        assert backup_file.read_text() == "old runtime configuration"

    def test_render_and_deploy_without_backup(
        self, tmp_path: Path, sample_server: ServerEntry
    ) -> None:
        """Verify atomic deploy does not create .bak when backup_enabled is False."""
        template_file = tmp_path / "master.template"
        template_file.write_text("client\ndev tun\n{{REMOTE}}\n")

        target_file = tmp_path / "trustzone.conf"
        target_file.write_text("initial config")

        manager = TemplateManager(
            template_path=template_file,
            target_path=target_file,
            backup_enabled=False,
        )
        manager.render_and_deploy(sample_server)

        backup_file = tmp_path / "trustzone.conf.bak"
        assert not backup_file.exists()

    def test_import_from_config_replaces_remote_with_token(self, tmp_path: Path) -> None:
        """Verify import_from_config converts active remote line into {{REMOTE}} token."""
        existing_conf = tmp_path / "existing.conf"
        content = (
            "# Existing OpenVPN configuration\n"
            "client\n"
            "dev tun\n"
            "remote de.trust.zone 1194 udp\n"
            "nobind\n"
            "remote backup.trust.zone 443 tcp\n"
        )
        existing_conf.write_text(content)

        manager = TemplateManager(
            template_path=tmp_path / "template.conf",
            target_path=tmp_path / "target.conf",
        )
        imported_template = manager.import_from_config(existing_conf)

        assert "{{REMOTE}}\n" in imported_template
        assert "de.trust.zone" not in imported_template
        assert "# remote backup.trust.zone 443 tcp" in imported_template

    def test_import_from_config_nonexistent_raises(self, tmp_path: Path) -> None:
        """Verify import_from_config raises FileNotFoundError for missing file."""
        manager = TemplateManager(
            template_path=tmp_path / "template.conf",
            target_path=tmp_path / "target.conf",
        )
        with pytest.raises(FileNotFoundError):
            manager.import_from_config(tmp_path / "missing.conf")

    def test_save_and_deploy_permission_error(self, tmp_path: Path) -> None:
        """Verify PermissionError is raised when destination directory is unwritable."""
        readonly_dir = tmp_path / "readonly_dir"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, 0o555)

        manager = TemplateManager(
            template_path=readonly_dir / "template.conf",
            target_path=readonly_dir / "target.conf",
        )

        try:
            with pytest.raises(PermissionError, match="not writable"):
                manager.save_template_content("client\n")
        finally:
            os.chmod(readonly_dir, 0o755)

    def test_render_and_deploy_atomic_file_integrity(
        self, tmp_path: Path, sample_server: ServerEntry, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Verify atomic replacement via inode changes and resilience to write failure."""
        template_file = tmp_path / "template.conf"
        template_file.write_text("client\ndev tun\n{{REMOTE}}\n")

        target_file = tmp_path / "trustzone.conf"
        target_file.write_text("initial runtime configuration\n")
        initial_inode = target_file.stat().st_ino

        manager = TemplateManager(
            template_path=template_file,
            target_path=target_file,
            backup_enabled=False,
        )

        # 1. Successful deploy changes inode (proving os.replace was used atomically)
        manager.render_and_deploy(sample_server, port=1194, protocol=ProtocolType.UDP)
        new_inode = target_file.stat().st_ino
        assert new_inode != initial_inode
        assert "remote us.trust.zone 1194 udp" in target_file.read_text()

        # Record current state for failure simulation
        stable_content = target_file.read_text()
        stable_inode = target_file.stat().st_ino

        # 2. Simulate failure during atomic replacement (os.replace raises OSError)
        def mock_replace_fail(src: str, dst: str) -> None:
            raise OSError("Simulated filesystem I/O error during atomic replace")

        monkeypatch.setattr(os, "replace", mock_replace_fail)

        with pytest.raises(OSError, match="Simulated filesystem I/O error"):
            manager.render_and_deploy(sample_server, port=443, protocol=ProtocolType.TCP)

        # Target file must remain untouched with original content and inode
        assert target_file.read_text() == stable_content
        assert target_file.stat().st_ino == stable_inode

        # Temporary files must be cleaned up in finally block with zero partial writes
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []
