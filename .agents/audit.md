# Audit Report: Step 1 (Core Domain Models & Strategy B Template Engine)

**Auditor**: Simplicio (Senior QA & Security Auditor)  
**Assisted-by**: Antigravity [Gemini 3.8 Flash (High)]  
**Status**: REJECTED  
**Target Files**:
- `openvpn_switcher/core/template.py`
- `tests/test_template.py`

---

## Findings

STATUS: REJECTED

- **[HIGH]** `/home/jethigh/Lab/python/openvpn_switcher/openvpn_switcher/core/template.py:236`
  - **Issue**: In `TemplateManager.render()`, when interpolating `{{HOST}}`, `_sanitize_multiple_remotes(lines)` blindly preserves whichever active `remote` directive appears first in the template. If an active `remote` directive precedes `remote {{HOST}} ...`, the legacy remote directive remains active and the newly interpolated server directive is commented out (`# remote ...`).
  - **Rationale**: If a user template has an existing active remote before a `{{HOST}}` token, or imports a configuration where a remote line is preserved, the rendered configuration will connect to the legacy remote instead of the selected server, leading to silent connection failure or traffic routing to the wrong VPN endpoint.
  - **Required Fix**: When processing lines in Branch 2 (`{{HOST}}`), identify the newly interpolated remote line (the line containing `host`) as the active remote, and ensure all other active `remote` directives are commented out, consistent with Branch 1.
    ```python
        if "{{HOST}}" in template or "{{PORT}}" in template or "{{PROTO}}" in template:
            rendered = template
            if "{{HOST}}" in rendered:
                rendered = rendered.replace("{{HOST}}", host)
            if "{{PORT}}" in rendered:
                rendered = rendered.replace("{{PORT}}", str(target_port))
            if "{{PROTO}}" in rendered:
                rendered = rendered.replace("{{PROTO}}", target_proto.value)
            lines = rendered.splitlines(keepends=True)
            result: List[str] = []
            target_remote_seen = False
            for line in lines:
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and not stripped.startswith(";")
                    and REMOTE_LINE_PATTERN.match(line)
                ):
                    if not target_remote_seen and host in stripped:
                        target_remote_seen = True
                        result.append(line)
                    else:
                        result.append(f"# {line}")
                else:
                    result.append(line)
            return "".join(result)
    ```

- **[MEDIUM]** `/home/jethigh/Lab/python/openvpn_switcher/tests/test_template.py:276`
  - **Issue**: Missing dedicated atomic file integrity verification test explicitly required by `.agents/plan.md` Section 4.
  - **Rationale**: Plan Section 4 mandates: `"Atomic File Integrity | Dedicated test in test_template.py | Verify file inode changes atomically, no partial writes on error"`. Currently, `tests/test_template.py` does not assert inode changes (`stat().st_ino`) across `render_and_deploy()`, nor does it verify that an aborted write leaves the original file and inode completely untouched.
  - **Required Fix**: Add a dedicated test `test_render_and_deploy_atomic_file_integrity` in `tests/test_template.py` that:
    1. Records `initial_inode = target_file.stat().st_ino`.
    2. Executes `manager.render_and_deploy(sample_server)`.
    3. Asserts `target_file.stat().st_ino != initial_inode` to prove atomic replacement (rename/replace) rather than in-place mutation.
    4. Simulates a write failure (e.g. mocking `os.replace` to raise `OSError`) and verifies that `target_file` content and inode remain intact with zero partial writes and temporary files cleaned up.
