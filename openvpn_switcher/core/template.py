# Assisted-by: SAGREDO [Gemini 3.8 Flash (High)]
"""Master template engine and atomic configuration deployment."""

import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import List, Optional, Union

from openvpn_switcher.core.models import ProtocolType, ServerEntry

DEFAULT_TEMPLATE = """# TrustZone OpenVPN Client Template
# Managed by OpenVPN Switcher
client
dev tun
proto udp
resolv-retry infinite
nobind
persist-key
persist-tun
ca /etc/openvpn/ca.crt
auth-user-pass /etc/openvpn/credentials.txt
cipher AES-256-CBC
auth SHA256
verb 3
{{REMOTE}}
"""

REMOTE_LINE_PATTERN = re.compile(
    r"^\s*remote\s+(?P<host>\"[^\"]+\"|'[^']+'|[^\s#;]+)(?:\s+(?P<port>\d+))?(?:\s+(?P<proto>udp|tcp))?",
    re.IGNORECASE,
)


def _sanitize_multiple_remotes(
    lines: List[str], preferred_host: Optional[str] = None
) -> List[str]:
    """Ensure at most one active remote directive exists; comments out other active remotes.

    Args:
        lines: List of configuration lines.
        preferred_host: If specified, the active remote matching this host is preserved,
            while all other active remotes are commented out.

    Returns:
        List of sanitized configuration lines.
    """
    has_preferred = False
    if preferred_host:
        normalized_host = preferred_host.strip().lower()
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith(";")
                and REMOTE_LINE_PATTERN.match(line)
            ):
                match = REMOTE_LINE_PATTERN.match(line)
                if match:
                    line_host = match.group("host").strip("\"'").lower()
                    if line_host == normalized_host or normalized_host in stripped.lower():
                        has_preferred = True
                        break

    active_preserved = False
    result: List[str] = []

    for line in lines:
        stripped = line.strip()
        is_comment_or_empty = not stripped or stripped.startswith("#") or stripped.startswith(";")
        if not is_comment_or_empty and REMOTE_LINE_PATTERN.match(line):
            match = REMOTE_LINE_PATTERN.match(line)
            line_host = match.group("host").strip("\"'").lower() if match else ""

            if has_preferred and preferred_host:
                normalized_host = preferred_host.strip().lower()
                is_target = line_host == normalized_host or normalized_host in stripped.lower()
                if is_target and not active_preserved:
                    active_preserved = True
                    result.append(line)
                else:
                    result.append(f"# {line}")
            else:
                if not active_preserved:
                    active_preserved = True
                    result.append(line)
                else:
                    result.append(f"# {line}")
        else:
            result.append(line)

    return result


class TemplateManager:
    """Manages baseline OpenVPN templates and atomic runtime configuration deployment."""

    def __init__(
        self,
        template_path: Union[str, Path] = "/etc/openvpn/trustzone.conf.template",
        target_path: Union[str, Path] = "/etc/openvpn/trustzone.conf",
        backup_enabled: bool = True,
    ) -> None:
        """Initialize TemplateManager.

        Args:
            template_path: Path to the source master template file.
            target_path: Path to the deployed runtime configuration file.
            backup_enabled: Whether to create a .bak file of the active target configuration before overwrite.
        """
        self.template_path = Path(template_path).expanduser().resolve()
        self.target_path = Path(target_path).expanduser().resolve()
        self.backup_enabled = backup_enabled

    def get_template_content(self) -> str:
        """Retrieve master template content, generating sensible default if file does not exist.

        Returns:
            The raw template string.
        """
        if self.template_path.exists() and self.template_path.is_file():
            try:
                return self.template_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return DEFAULT_TEMPLATE
        return DEFAULT_TEMPLATE

    def save_template_content(self, content: str) -> None:
        """Atomically persist template content to template_path.

        Args:
            content: Template string to persist.

        Raises:
            PermissionError: If destination directory is not writable.
            OSError: On filesystem write failure.
        """
        target_dir = self.template_path.parent
        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as err:
                raise PermissionError(
                    f"Template directory '{target_dir}' cannot be created: insufficient permissions."
                ) from err

        if not os.access(target_dir, os.W_OK):
            raise PermissionError(
                f"Template directory '{target_dir}' is not writable. Root or sudo privileges required."
            )

        original_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        if self.template_path.exists():
            if not os.access(self.template_path, os.W_OK):
                raise PermissionError(
                    f"Template file '{self.template_path}' is not writable. Root or sudo privileges required."
                )
            original_mode = stat.S_IMODE(self.template_path.stat().st_mode)

        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target_dir,
                mode="w",
                encoding="utf-8",
                delete=False,
                prefix="template_",
                suffix=".tmp",
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(content)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.chmod(temp_path, original_mode)
            os.replace(temp_path, self.template_path)
            temp_path = None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def render(
        self,
        server: ServerEntry,
        port: Optional[int] = None,
        protocol: Optional[Union[ProtocolType, str]] = None,
    ) -> str:
        """Render runtime configuration by injecting server endpoint into the master template.

        Args:
            server: The ServerEntry containing country and hostname.
            port: Port number override (default: server.port).
            protocol: Protocol override (default: server.protocol).

        Returns:
            The rendered OpenVPN configuration text.

        Raises:
            ValueError: If host, port, or protocol fail validation.
        """
        host = server.hostname
        if not isinstance(host, str) or not host.strip():
            raise ValueError("Host must be a non-empty string.")

        host = host.strip()
        if any(char in host for char in ("\r", "\n", "\t", " ", '"', "'", "#", ";")):
            raise ValueError(
                f"Invalid host '{host}': host cannot contain whitespace, newlines, quotes, or comment characters."
            )

        target_port = port if port is not None else server.port
        if (
            isinstance(target_port, bool)
            or not isinstance(target_port, int)
            or target_port < 1
            or target_port > 65535
        ):
            raise ValueError(
                f"Port must be an integer between 1 and 65535. Received: {target_port!r}"
            )

        target_proto_raw = protocol if protocol is not None else server.protocol
        if isinstance(target_proto_raw, ProtocolType):
            target_proto = target_proto_raw
        elif isinstance(target_proto_raw, str):
            target_proto = ProtocolType.from_str(target_proto_raw)
        else:
            raise ValueError(
                f"Invalid protocol '{target_proto_raw!r}'. Expected ProtocolType or 'udp'/'tcp'."
            )

        template = self.get_template_content()
        new_remote_line = f"remote {host} {target_port} {target_proto.value}"

        if "{{REMOTE}}" in template:
            rendered = template.replace("{{REMOTE}}", new_remote_line)
            lines = rendered.splitlines(keepends=True)
            return "".join(_sanitize_multiple_remotes(lines, preferred_host=host))

        if "{{HOST}}" in template or "{{PORT}}" in template or "{{PROTO}}" in template:
            rendered = template
            if "{{HOST}}" in rendered:
                rendered = rendered.replace("{{HOST}}", host)
            if "{{PORT}}" in rendered:
                rendered = rendered.replace("{{PORT}}", str(target_port))
            if "{{PROTO}}" in rendered:
                rendered = rendered.replace("{{PROTO}}", target_proto.value)
            lines = rendered.splitlines(keepends=True)
            return "".join(_sanitize_multiple_remotes(lines, preferred_host=host))

        # Direct replacement or append
        lines = template.splitlines(keepends=True)
        result_lines: List[str] = []
        replaced = False
        new_directive = f"{new_remote_line}\n"

        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith(";")
                and REMOTE_LINE_PATTERN.match(line)
            ):
                if not replaced:
                    result_lines.append(new_directive)
                    replaced = True
                else:
                    result_lines.append(f"# {line}")
            else:
                result_lines.append(line)

        if not replaced:
            if result_lines and not result_lines[-1].endswith("\n"):
                result_lines[-1] = result_lines[-1] + "\n"
            result_lines.append(new_directive)

        return "".join(result_lines)

    def validate(self, content: Optional[str] = None) -> List[str]:
        """Validate template syntax and presence of required OpenVPN directives.

        Args:
            content: Optional template content to validate; if None, loads template_path.

        Returns:
            A list of validation error descriptions, empty if completely valid.
        """
        raw_text = content if content is not None else self.get_template_content()
        errors: List[str] = []

        lines = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip() and not line.strip().startswith("#") and not line.strip().startswith(";")
        ]

        has_client = any(re.match(r"^client\b", line, re.IGNORECASE) for line in lines)
        if not has_client:
            errors.append("Missing required directive: 'client'")

        has_dev = any(re.match(r"^dev\s+\w+", line, re.IGNORECASE) for line in lines)
        if not has_dev:
            errors.append("Missing required directive: 'dev' (e.g., 'dev tun')")

        has_remote_token = (
            "{{REMOTE}}" in raw_text
            or "{{HOST}}" in raw_text
            or any(REMOTE_LINE_PATTERN.match(line) for line in lines)
        )
        if not has_remote_token:
            errors.append(
                "Missing remote directive or placeholder: template must include '{{REMOTE}}', '{{HOST}}', or a 'remote' directive."
            )

        return errors

    def render_and_deploy(
        self,
        server: ServerEntry,
        port: Optional[int] = None,
        protocol: Optional[Union[ProtocolType, str]] = None,
    ) -> Path:
        """Render configuration and atomically deploy to target_path with optional backup.

        Args:
            server: Destination server entry.
            port: Port override.
            protocol: Protocol override.

        Returns:
            The Path to the deployed target configuration.

        Raises:
            PermissionError: If target directory or file is not writable.
            OSError: On write failure.
        """
        rendered_content = self.render(server, port, protocol)
        target_dir = self.target_path.parent

        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as err:
                raise PermissionError(
                    f"Target directory '{target_dir}' cannot be created: insufficient permissions."
                ) from err

        if not os.access(target_dir, os.W_OK):
            raise PermissionError(
                f"Target directory '{target_dir}' is not writable. Root or sudo privileges required."
            )

        # Handle backup
        if self.backup_enabled and self.target_path.exists():
            backup_file = self.target_path.with_name(f"{self.target_path.name}.bak")
            try:
                shutil.copy2(self.target_path, backup_file)
            except OSError as err:
                raise OSError(f"Failed to create configuration backup at '{backup_file}': {err}") from err

        original_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
        if self.target_path.exists():
            if not os.access(self.target_path, os.W_OK):
                raise PermissionError(
                    f"Configuration file '{self.target_path}' is not writable. Root or sudo privileges required."
                )
            original_mode = stat.S_IMODE(self.target_path.stat().st_mode)

        temp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=target_dir,
                mode="w",
                encoding="utf-8",
                delete=False,
                prefix="trustzone_render_",
                suffix=".tmp",
            ) as temp_file:
                temp_path = temp_file.name
                temp_file.write(rendered_content)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.chmod(temp_path, original_mode)
            os.replace(temp_path, self.target_path)
            temp_path = None
            return self.target_path
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def import_from_config(self, config_path: Union[str, Path]) -> str:
        """Convert an existing OpenVPN configuration file into a baseline template.

        Args:
            config_path: Path to the existing configuration file.

        Returns:
            The generated template text containing the {{REMOTE}} token.

        Raises:
            FileNotFoundError: If the source configuration file does not exist.
        """
        source_path = Path(config_path).expanduser().resolve()
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Source configuration file '{source_path}' does not exist.")

        raw_content = source_path.read_text(encoding="utf-8", errors="replace")
        lines = raw_content.splitlines(keepends=True)
        result: List[str] = []
        replaced = False

        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith(";")
                and REMOTE_LINE_PATTERN.match(line)
            ):
                if not replaced:
                    result.append("{{REMOTE}}\n")
                    replaced = True
                else:
                    result.append(f"# {line}")
            else:
                result.append(line)

        if not replaced:
            if result and not result[-1].endswith("\n"):
                result[-1] = result[-1] + "\n"
            result.append("{{REMOTE}}\n")

        return "".join(result)
