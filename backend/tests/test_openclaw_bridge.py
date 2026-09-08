"""
Tests for app.services.openclaw_bridge.

These tests verify:
  - the exact CLI command constructed for dispatch (no --workspace flag,
    matching the real installed CLI's supported flags)
  - that launch failures (including the Windows
    "NotImplementedError: subprocess not supported on this event loop"
    failure mode this module was fixed for) are always turned into a
    DispatchError, never an uncaught exception
  - that dispatch never blocks waiting on the launched process (fire-and-forget)

No real `openclaw` process is ever launched: subprocess.Popen is monkeypatched.

Run with:
    DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q tests/test_openclaw_bridge.py
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATA_DIR", "/tmp/mf-test-data")
os.environ.setdefault("DEMO_MODE", "true")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

# Plain asyncio.run() is used below instead of pytest-asyncio/pytest.mark.asyncio
# so this test module doesn't add a new test-only dependency to the project.

from app.config import settings
from app.services import openclaw_bridge


@pytest.fixture(autouse=True)
def _fixed_openclaw_settings(monkeypatch):
    """Pin the settings the command is built from so assertions are stable
    regardless of the machine's .env / real workspace path."""
    monkeypatch.setattr(settings, "OPENCLAW_AGENT", "crestodian")
    monkeypatch.setattr(settings, "OPENCLAW_BACKEND_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(
        settings,
        "OPENCLAW_CLI_COMMAND_TEMPLATE",
        'openclaw agent --agent {agent} --message "{message}"',
    )
    monkeypatch.setattr(settings, "OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS", 5.0)
    yield


class FakePopen:
    """Stand-in for subprocess.Popen that never actually launches anything."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242


def test_build_command_matches_installed_cli_contract():
    """The dispatch command must exactly match the CLI flags verified
    manually against the real installed OpenClaw CLI:
        openclaw agent --agent crestodian --message "..."
    (or, on Windows, the resolved openclaw.cmd shim in place of the bare
    "openclaw" name -- see _resolve_openclaw_executable) and must NOT
    include --workspace, which the installed CLI doesn't support.

    This intentionally does not mock shutil.which/_IS_WINDOWS: it exercises
    the real platform-dependent resolution, so on Windows it asserts
    against the actual resolved openclaw.cmd shim rather than the bare,
    unlaunchable "openclaw" name.
    """
    command = openclaw_bridge._build_command("inv-123")

    executable_name = Path(command[0]).name.lower()
    if openclaw_bridge._IS_WINDOWS:
        # On Windows, command[0] must be the resolved openclaw.cmd shim
        # (subprocess.Popen can't directly launch the bare "openclaw"
        # POSIX shell script or the "openclaw.ps1" script), never the bare
        # "openclaw" name.
        assert executable_name == "openclaw.cmd"
        assert command[0] != "openclaw"
    else:
        assert executable_name == "openclaw"

    assert "agent" in command
    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "crestodian"
    assert "--message" in command
    assert "inv-123" in command[-1]

    # The installed CLI does not support --workspace -- must never appear.
    assert "--workspace" not in command


def test_build_command_message_contains_investigation_id_and_base_url():
    command = openclaw_bridge._build_command("inv-abc")
    message = command[-1]
    assert "inv-abc" in message
    assert settings.OPENCLAW_BACKEND_BASE_URL in message


def test_dispatch_uses_popen_not_create_subprocess_exec():
    """Regression test for the Windows crash: dispatch must not depend on
    asyncio.create_subprocess_exec (which requires Proactor-loop subprocess
    support and raises NotImplementedError when that's unavailable). It
    should instead launch via subprocess.Popen so it works on any event
    loop / platform.

    Does not mock shutil.which/_IS_WINDOWS, so the executable resolved into
    launched_command[0] reflects the real platform: the openclaw.cmd shim
    on Windows, or the bare "openclaw" name elsewhere.
    """
    with patch("app.services.openclaw_bridge.subprocess.Popen", side_effect=FakePopen) as mock_popen, \
         patch("app.services.openclaw_bridge.asyncio.create_subprocess_exec") as mock_exec:
        result = asyncio.run(openclaw_bridge.dispatch_to_openclaw("inv-999"))

    mock_exec.assert_not_called()
    mock_popen.assert_called_once()
    launched_command = mock_popen.call_args[0][0]

    executable_name = Path(launched_command[0]).name.lower()
    if openclaw_bridge._IS_WINDOWS:
        assert executable_name == "openclaw.cmd"
        assert launched_command[0] != "openclaw"
    else:
        assert executable_name == "openclaw"

    assert launched_command[1:4] == ["agent", "--agent", "crestodian"]
    assert "--workspace" not in launched_command

    assert result["dispatched"] is True
    assert result["agent"] == "crestodian"
    assert result["pid"] == 4242


def test_dispatch_raises_dispatch_error_when_binary_missing():
    with patch(
        "app.services.openclaw_bridge.subprocess.Popen",
        side_effect=FileNotFoundError("no such file: openclaw"),
    ):
        with pytest.raises(openclaw_bridge.DispatchError):
            asyncio.run(openclaw_bridge.dispatch_to_openclaw("inv-1"))


def test_dispatch_converts_windows_notimplementederror_to_dispatch_error():
    """This is the exact failure this fix addresses: on a SelectorEventLoop
    on Windows, subprocess creation used to raise NotImplementedError deep
    inside asyncio, which was not caught anywhere and surfaced as an
    uncaught ASGI background-task traceback. It must now be turned into a
    DispatchError like every other launch failure.
    """
    with patch(
        "app.services.openclaw_bridge.subprocess.Popen",
        side_effect=NotImplementedError(
            "subprocess not supported by SelectorEventLoop on Windows"
        ),
    ):
        with pytest.raises(openclaw_bridge.DispatchError):
            asyncio.run(openclaw_bridge.dispatch_to_openclaw("inv-2"))


def test_dispatch_does_not_block_on_the_launched_process():
    """Fire-and-forget: dispatch_to_openclaw must return as soon as the
    process is launched, without waiting for it to exit or do any work."""

    def fast_popen(*args, **kwargs):
        return FakePopen(*args, **kwargs)

    async def _run():
        with patch("app.services.openclaw_bridge.subprocess.Popen", side_effect=fast_popen):
            return await asyncio.wait_for(
                openclaw_bridge.dispatch_to_openclaw("inv-3"), timeout=2.0
            )

    result = asyncio.run(_run())
    assert result["dispatched"] is True


def test_popen_kwargs_detach_process_appropriately():
    """On Windows, the child must be launched detached (new process group +
    DETACHED_PROCESS) so it survives independently and doesn't inherit a
    console. On POSIX, it should start a new session."""
    if openclaw_bridge._IS_WINDOWS:
        assert "creationflags" in openclaw_bridge._POPEN_KWARGS
    else:
        assert openclaw_bridge._POPEN_KWARGS.get("start_new_session") is True


# --- Windows executable resolution ------------------------------------
#
# These tests force openclaw_bridge._IS_WINDOWS = True (via monkeypatch) so
# the Windows resolution branch is exercised and verified regardless of the
# OS actually running the test suite (CI runs on Linux).

def _fake_which_factory(available: dict):
    """Build a shutil.which() stand-in: `available` maps exact program name
    -> the fake resolved path to return (or None if not found)."""

    def _fake_which(program):
        return available.get(program)

    return _fake_which


def test_windows_resolution_prefers_openclaw_cmd_shim(monkeypatch):
    """This is the core fix: given the npm install described in the bug
    report --

        C:\\Users\\DELL\\AppData\\Roaming\\npm\\openclaw
        C:\\Users\\DELL\\AppData\\Roaming\\npm\\openclaw.cmd
        C:\\Users\\DELL\\AppData\\Roaming\\npm\\openclaw.ps1

    -- resolution must pick the .cmd shim, since that's the one
    subprocess.Popen/CreateProcess can actually execute directly, unlike
    the extension-less shell script or the .ps1 script.
    """
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    fake_cmd_path = r"C:\Users\DELL\AppData\Roaming\npm\openclaw.cmd"
    monkeypatch.setattr(
        openclaw_bridge.shutil,
        "which",
        _fake_which_factory({"openclaw.cmd": fake_cmd_path}),
    )

    resolved = openclaw_bridge._resolve_openclaw_executable("openclaw")

    assert resolved == fake_cmd_path


def test_windows_resolution_does_not_hardcode_username_or_path(monkeypatch):
    """Resolution must go through shutil.which (PATH-based), not any
    hard-coded user-specific path -- verified by pointing the fake PATH
    lookup at a completely different, unrelated location and confirming
    that's what comes back."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    arbitrary_path = r"D:\tools\openclaw-install\openclaw.cmd"
    monkeypatch.setattr(
        openclaw_bridge.shutil,
        "which",
        _fake_which_factory({"openclaw.cmd": arbitrary_path}),
    )

    resolved = openclaw_bridge._resolve_openclaw_executable("openclaw")

    assert resolved == arbitrary_path
    # Never falls back to a literal hard-coded DELL/AppData-style path.
    assert "DELL" not in resolved


def test_windows_resolution_falls_back_through_candidates(monkeypatch):
    """If .cmd isn't found but .exe is, .exe should be used -- resolution
    tries each Windows candidate in order rather than failing immediately."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    fake_exe_path = r"C:\tools\openclaw.exe"
    monkeypatch.setattr(
        openclaw_bridge.shutil,
        "which",
        _fake_which_factory({"openclaw.exe": fake_exe_path}),  # no .cmd available
    )

    resolved = openclaw_bridge._resolve_openclaw_executable("openclaw")

    assert resolved == fake_exe_path


def test_windows_resolution_never_returns_bare_or_ps1(monkeypatch):
    """Even when nothing is found on PATH, resolution must never fall back
    to the bare 'openclaw' name (POSIX shell script, unusable on Windows)
    or 'openclaw.ps1' (not directly executable by subprocess.Popen)."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(openclaw_bridge.shutil, "which", _fake_which_factory({}))

    resolved = openclaw_bridge._resolve_openclaw_executable("openclaw")

    assert resolved != "openclaw"
    assert not resolved.endswith(".ps1")
    assert resolved.endswith(".cmd")


def test_build_command_on_windows_uses_resolved_cmd_shim(monkeypatch):
    """End-to-end for _build_command: on Windows, the constructed command's
    program (argv[0]) must be the resolved openclaw.cmd path, and the CLI
    flags must still exactly match the verified installed-CLI syntax with
    no --workspace flag."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    fake_cmd_path = r"C:\Users\DELL\AppData\Roaming\npm\openclaw.cmd"
    monkeypatch.setattr(
        openclaw_bridge.shutil,
        "which",
        _fake_which_factory({"openclaw.cmd": fake_cmd_path}),
    )

    command = openclaw_bridge._build_command("inv-win-1")

    assert command[0] == fake_cmd_path
    assert command[1:4] == ["agent", "--agent", "crestodian"]
    assert command[4] == "--message"
    assert "inv-win-1" in command[5]
    assert "--workspace" not in command


def test_build_command_respects_configured_agent_name(monkeypatch):
    """OPENCLAW_AGENT must remain fully configurable and flow through to
    the constructed command -- not hard-coded to 'crestodian' in code, even
    though that's the current configured value."""
    monkeypatch.setattr(settings, "OPENCLAW_AGENT", "some-other-agent")

    command = openclaw_bridge._build_command("inv-agent-check")

    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "some-other-agent"


def test_dispatch_windows_cmd_shim_end_to_end(monkeypatch):
    """Full dispatch path on a simulated Windows install: resolves to the
    .cmd shim and launches it via subprocess.Popen (never
    create_subprocess_exec), with the exact verified CLI syntax."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(
        openclaw_bridge,
        "_POPEN_KWARGS",
        {"creationflags": 0x00000200 | 0x00000008},
    )
    fake_cmd_path = r"C:\Users\DELL\AppData\Roaming\npm\openclaw.cmd"
    monkeypatch.setattr(
        openclaw_bridge.shutil,
        "which",
        _fake_which_factory({"openclaw.cmd": fake_cmd_path}),
    )

    with patch("app.services.openclaw_bridge.subprocess.Popen", side_effect=FakePopen) as mock_popen:
        result = asyncio.run(openclaw_bridge.dispatch_to_openclaw("inv-win-e2e"))

    launched_command = mock_popen.call_args[0][0]
    assert launched_command[0] == fake_cmd_path
    assert launched_command[1:4] == ["agent", "--agent", "crestodian"]
    assert "--workspace" not in launched_command
    assert result["dispatched"] is True


def test_dispatch_failure_when_cmd_shim_not_resolvable(monkeypatch):
    """If openclaw.cmd genuinely can't be found on PATH, dispatch must
    raise a clear DispatchError (never silently fall back to native mode --
    that's the caller's job, gated by OPENCLAW_ALLOW_NATIVE_FALLBACK)."""
    monkeypatch.setattr(openclaw_bridge, "_IS_WINDOWS", True)
    monkeypatch.setattr(openclaw_bridge.shutil, "which", _fake_which_factory({}))

    with patch(
        "app.services.openclaw_bridge.subprocess.Popen",
        side_effect=FileNotFoundError("[WinError 2] The system cannot find the file specified"),
    ):
        with pytest.raises(openclaw_bridge.DispatchError) as exc_info:
            asyncio.run(openclaw_bridge.dispatch_to_openclaw("inv-win-missing"))

    assert "openclaw.cmd" in str(exc_info.value)
