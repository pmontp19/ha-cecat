"""Tests for the cecat __init__ stubs.

Real coordinator setup lands in T5; these only exercise the placeholder
return values so coverage stays above the gate during scaffold.
"""

from __future__ import annotations

from custom_components.cecat import async_setup_entry, async_unload_entry


async def test_async_setup_entry_returns_true(hass) -> None:
    """Scaffold setup returns True unconditionally."""
    assert await async_setup_entry(hass, object()) is True  # type: ignore[arg-type]


async def test_async_unload_entry_returns_true(hass) -> None:
    """Scaffold unload returns True unconditionally."""
    assert await async_unload_entry(hass, object()) is True  # type: ignore[arg-type]
