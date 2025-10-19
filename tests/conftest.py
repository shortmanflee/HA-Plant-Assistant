"""Pytest conftest to ensure the repository root is on sys.path for imports."""

import asyncio
import contextlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _event_loop_session():
    """
    Create a fresh event loop for the test session and set it as current.

    Some plugins call `asyncio.get_event_loop()` at import/setup time. On
    newer Python versions this raises when no loop is set on the main
    thread. Providing this session-scoped loop ensures compatibility for the
    Home Assistant test plugin used in these tests.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        yield loop
    finally:
        with contextlib.suppress(Exception):
            loop.call_soon_threadsafe(loop.stop)
        loop.close()


# Ensure a main-thread event loop exists at import time so pytest plugins
# that call `asyncio.get_event_loop()` during fixture setup won't raise.
# `_import_time_loop` is module-scoped so later fallback helpers can reference
# it safely.
_import_time_loop = None
try:
    asyncio.get_event_loop()
except RuntimeError:
    _import_time_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_import_time_loop)
    # Close on process exit
    with contextlib.suppress(Exception):
        import atexit

        if _import_time_loop is not None:
            atexit.register(_import_time_loop.close)
    # Try to populate the installed event loop policy's thread-local storage
    # so policies like Home Assistant's HassEventLoopPolicy return our loop
    # from `get_event_loop()` instead of raising.
    with contextlib.suppress(Exception):
        policy = asyncio.get_event_loop_policy()
        local = getattr(policy, "_local", None)
        if local is not None:
            with contextlib.suppress(Exception):
                local._loop = _import_time_loop
                local._set_called = True
    # If the installed event loop policy still raises when `get_event_loop`
    # is called (some Home Assistant test policies do), provide a fallback by
    # overriding `asyncio.get_event_loop` to return our import-time loop.
    _real_get_event_loop = asyncio.get_event_loop

    def _get_event_loop_override():
        try:
            return _real_get_event_loop()
        except RuntimeError:
            return _import_time_loop

    with contextlib.suppress(Exception):
        asyncio.get_event_loop = _get_event_loop_override  # type: ignore[assignment]

# Ensure the installed event loop policy is the default policy so that
# `asyncio.get_event_loop()` calls made by pytest plugins don't invoke the
# Home Assistant-specific policy which may raise if it hasn't been primed.
with contextlib.suppress(Exception):
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())

# If Home Assistant's runner policy is imported and installed, its
# `get_event_loop` implementation may raise when no loop is set. Try to
# patch it to provide a safe fallback that returns the current loop or the
# import-time loop created above.
with contextlib.suppress(Exception):
    import importlib

    ha_runner = importlib.import_module("homeassistant.runner")
    orig_get = getattr(ha_runner.HassEventLoopPolicy, "get_event_loop", None)

    def _ha_safe_get_event_loop(self):
        try:
            if orig_get:
                return orig_get(self)
        except RuntimeError:
            pass
        # Avoid calling `asyncio.get_event_loop()` here to prevent recursion
        # into this patched method. Prefer the import-time loop if we created
        # one; otherwise create a new loop, install it, and return it.
        if _import_time_loop is not None:
            return _import_time_loop
        loop = asyncio.new_event_loop()
        with contextlib.suppress(Exception):
            asyncio.set_event_loop(loop)
        return loop

    with contextlib.suppress(Exception):
        ha_runner.HassEventLoopPolicy.get_event_loop = _ha_safe_get_event_loop
