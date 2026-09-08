"""
Bridge between this FastAPI backend and the external, already-running
OpenClaw CLI/agent ("crestodian").

IMPORTANT / UNVERIFIED: this environment does not have the OpenClaw CLI
installed, so the exact command-line contract below could not be executed
or verified against a live `openclaw` binary. It is built from what the
integration brief says has already been tested manually ("OpenClaw
installation and Gemini connection have already been tested successfully
from the CLI") and from the project's own openclaw/README.md description
of the architecture (external agent driving the platform via its HTTP
API). Before relying on this in production, run the command
OPENCLAW_CLI_COMMAND_TEMPLATE resolves to by hand once, confirm crestodian
actually picks up the investigation, and adjust the template in .env if the
real CLI's flags differ -- no code change should be needed for that.

Design constraints this module follows (per the integration brief):
- Never run the OpenClaw CLI as a blocking subprocess held open for the
  whole investigation. We only launch it (fire-and-forget) to notify/wake
  the agent with the investigation ID; the agent is expected to then drive
  the investigation forward itself by calling the backend's own
  /api/investigations/{id}/agent/* endpoints.
- Never log secrets (GEMINI_API_KEY, BRAVE_API_KEY, XAI_API_KEY, .env).
- Never silently fall back to native mode; that's an explicit opt-in
  (OPENCLAW_ALLOW_NATIVE_FALLBACK) handled by the caller, not this module.
"""
import asyncio
import functools
import logging
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone

from app.config import settings, DATA_DIR

logger = logging.getLogger("openclaw.dispatch")

_IS_WINDOWS = sys.platform.startswith("win")

# Where the dispatched CLI's actual stdout/stderr get captured. Previously
# this was DEVNULL'd entirely -- when the agent run failed instantly (wrong
# args, missing tool-calling support, auth error, etc.) there was zero way
# to see why: the log only ever showed "dispatch_launched", never what the
# process actually printed before exiting. Every dispatch now gets its own
# timestamped log file here instead.
OPENCLAW_DISPATCH_LOG_DIR = DATA_DIR / "openclaw_dispatch_logs"
OPENCLAW_DISPATCH_LOG_DIR.mkdir(parents=True, exist_ok=True)

# On Windows, uvicorn/FastAPI commonly ends up running on a
# SelectorEventLoop (the ProactorEventLoop is not always compatible with
# certain server setups / reload workers), and asyncio.create_subprocess_exec
# unconditionally requires the Proactor loop's subprocess support. When it's
# missing, create_subprocess_exec raises NotImplementedError -- which is NOT
# an OSError, so it was previously escaping our error handling entirely and
# surfacing as an uncaught ASGI background-task traceback.
#
# Fix: don't depend on the event loop's subprocess machinery at all. Launch
# via the plain, synchronous subprocess.Popen (which merely starts the
# process and returns immediately -- it does not block on the child), run
# inside a worker thread via loop.run_in_executor so the FastAPI event loop
# is never blocked. This works identically on the Selector and Proactor
# event loops, and on POSIX.

# Detach the child so it survives independently of the backend process and
# doesn't pop up a console window when the backend itself is run without one.
if _IS_WINDOWS:
    _POPEN_KWARGS = {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008),
    }
else:
    _POPEN_KWARGS = {"start_new_session": True}


class DispatchError(Exception):
    """Raised when the OpenClaw CLI could not be launched at all
    (binary missing, workspace missing, etc). Does NOT mean the agent run
    itself failed -- we never wait for that."""


# On Windows, `openclaw` (as installed by npm) is not a single executable --
# npm generates three shims: `openclaw` (a POSIX shell script, unusable on
# Windows), `openclaw.ps1` (a PowerShell script, which PowerShell resolves
# to interactively but which subprocess.Popen cannot execute directly
# without invoking powershell.exe), and `openclaw.cmd` (a plain Windows
# batch wrapper that any Win32 CreateProcess call, including
# subprocess.Popen, can execute directly). PowerShell's own command
# resolution order picks `.ps1` before `.cmd`, which is why `openclaw`
# "worked manually from PowerShell" but the very same bare name fails from
# Python: subprocess.Popen does NOT perform PATHEXT-based extension
# resolution the way cmd.exe/PowerShell do when given an extension-less
# program name in an argument list, so `shutil.which("openclaw")` /
# `Popen(["openclaw", ...])` can fail to find it even though it's on PATH.
#
# Fix: on Windows, explicitly resolve and launch the `.cmd` shim.
_WINDOWS_EXECUTABLE_CANDIDATES = ("openclaw.cmd", "openclaw.exe", "openclaw.bat")


def _resolve_openclaw_executable(program: str) -> str:
    """Resolve the actual executable to launch for `program` (normally
    "openclaw"), dynamically via PATH lookup -- never a hard-coded
    user-specific path.

    On Windows this deliberately looks for the `.cmd` shim first (see the
    module-level comment above) rather than relying on Python's default
    PATH search, which does not reproduce PowerShell/cmd.exe's PATHEXT
    resolution and can miss the shim entirely even though `openclaw` works
    fine when typed interactively.

    On non-Windows platforms this is just shutil.which(program) (falling
    back to the bare name so the OS itself produces a clear
    FileNotFoundError if it's genuinely missing).
    """
    if not _IS_WINDOWS:
        return shutil.which(program) or program

    if program.lower() != "openclaw":
        # Caller (e.g. a custom OPENCLAW_CLI_COMMAND_TEMPLATE) already named
        # a specific executable -- respect it as-is, just resolve via PATH.
        return shutil.which(program) or program

    for candidate in _WINDOWS_EXECUTABLE_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    # Nothing found -- return the preferred candidate so the resulting
    # FileNotFoundError / DispatchError message names the file we actually
    # looked for (openclaw.cmd), not the bare, unresolvable "openclaw".
    return _WINDOWS_EXECUTABLE_CANDIDATES[0]


def _build_message(investigation_id: str) -> str:
    return (
        f"New media-forensics investigation dispatched: investigation_id={investigation_id}. "
        f"Use the media-ingestion skill to confirm state, then drive the investigation via the "
        f"backend API at {settings.OPENCLAW_BACKEND_BASE_URL} "
        f"(GET /api/investigations/{investigation_id}, then the /agent/* tool endpoints)."
    )


def _build_command(investigation_id: str) -> list[str]:
    message = _build_message(investigation_id)
    rendered = settings.OPENCLAW_CLI_COMMAND_TEMPLATE.format(
        agent=settings.OPENCLAW_AGENT,
        workspace=settings.OPENCLAW_WORKSPACE,
        investigation_id=investigation_id,
        base_url=settings.OPENCLAW_BACKEND_BASE_URL,
        message=message,
    )
    # Always parse with posix=True: this is just tokenizing a shell-style
    # string (no filesystem access), and posix mode is what correctly
    # *strips* the quote characters around "{message}" so the launched
    # process receives the plain message text as a single argument rather
    # than a string with literal, un-stripped quote characters baked into
    # it (which posix=False -- previously used "on Windows" -- does not
    # do). The default template no longer embeds any Windows path
    # (--workspace was removed), so there's no remaining need for
    # posix=False's raw-backslash handling.
    parts = shlex.split(rendered, posix=True)
    parts[0] = _resolve_openclaw_executable(parts[0])
    return parts


async def dispatch_to_openclaw(investigation_id: str) -> dict:
    """
    Launches (does not await) the OpenClaw CLI pointed at `crestodian` with
    this investigation's ID. Returns a small dict describing whether the
    process was launched, for logging/event purposes. Never raises for
    "the agent later failed" -- only for "we could not even start it."
    """
    command = _build_command(investigation_id)
    dispatch_time = datetime.now(timezone.utc).isoformat()

    logger.info(
        "openclaw.dispatch investigation_id=%s agent=%s workspace=%s time=%s",
        investigation_id, settings.OPENCLAW_AGENT, settings.OPENCLAW_WORKSPACE, dispatch_time,
    )

    safe_time = dispatch_time.replace(":", "-")
    log_path = OPENCLAW_DISPATCH_LOG_DIR / f"{investigation_id}_{safe_time}.log"
    log_file = open(log_path, "w", encoding="utf-8", errors="replace")
    log_file.write(f"$ {' '.join(command)}\n\n")
    log_file.flush()

    loop = asyncio.get_running_loop()
    launch = functools.partial(
        subprocess.Popen,
        command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        **_POPEN_KWARGS,
    )

    try:
        proc = await asyncio.wait_for(
            loop.run_in_executor(None, launch),
            timeout=settings.OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as e:
        logger.error(
            "openclaw.dispatch_failed investigation_id=%s reason=binary_not_found detail=%s",
            investigation_id, e,
        )
        log_file.close()
        raise DispatchError(
            f"OpenClaw CLI ('{command[0]}') was not found on PATH. On Windows this looks for "
            f"the npm-generated {', '.join(_WINDOWS_EXECUTABLE_CANDIDATES)} shim(s) specifically "
            f"(not the extension-less 'openclaw' or 'openclaw.ps1'). Is OpenClaw installed "
            f"(`npm install -g openclaw` or similar) and is its install directory on the PATH "
            f"of the account running this backend process?"
        ) from e
    except asyncio.TimeoutError as e:
        logger.error(
            "openclaw.dispatch_failed investigation_id=%s reason=launch_timeout",
            investigation_id,
        )
        log_file.close()
        raise DispatchError(
            f"OpenClaw CLI did not launch within "
            f"{settings.OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS}s."
        ) from e
    except OSError as e:
        logger.error(
            "openclaw.dispatch_failed investigation_id=%s reason=os_error detail=%s",
            investigation_id, e,
        )
        log_file.close()
        raise DispatchError(f"Failed to launch OpenClaw CLI: {e}") from e
    except Exception as e:
        # Catch-all safety net: NotImplementedError (Windows event-loop
        # subprocess gaps), permission errors on some Windows setups, etc.
        # We must never let a launch failure escape as an uncaught
        # exception out of dispatch_to_openclaw -- the caller relies on
        # DispatchError being the only failure mode it needs to handle.
        logger.error(
            "openclaw.dispatch_failed investigation_id=%s reason=unexpected detail=%s: %s",
            investigation_id, type(e).__name__, e,
        )
        log_file.close()
        raise DispatchError(f"Failed to launch OpenClaw CLI: {type(e).__name__}: {e}") from e

    # The child process (or its OS-level duplicate of the handle) keeps
    # writing to the file after this -- safe for the parent to close its
    # own copy now.
    log_file.close()

    logger.info(
        "openclaw.dispatch_launched investigation_id=%s agent=%s pid=%s log=%s",
        investigation_id, settings.OPENCLAW_AGENT, proc.pid, log_path,
    )
    return {
        "dispatched": True,
        "agent": settings.OPENCLAW_AGENT,
        "workspace": settings.OPENCLAW_WORKSPACE,
        "pid": proc.pid,
        "dispatch_time": dispatch_time,
        "log_path": str(log_path),
    }
