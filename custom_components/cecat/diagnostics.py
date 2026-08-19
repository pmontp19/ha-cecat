"""Diagnostics support for cecat (docs/03-feature-spec.md §3.6).

Backs the "Download diagnostics" button HA's core ``diagnostics`` component
adds to a config entry once this module exists: ``diagnostics`` discovers
``diagnostics.py`` per integration lazily, no manifest change needed. The
config-entry handler (not the device one) matches both the sibling repos
(docs/02-existing-integrations.md) and the export contract of §3.6, whose
first field is the config entry itself.

The export is the §3.6 contract in full, field by field: the redacted config
entry, the raw response of the last successful cycle (useful precisely
because the text is dirty), the ``Last-Modified`` in force, the three
accumulated sets of unrecognised literals, and the consecutive-failure
count. The three sets are separate on purpose: without ``unknown_activated``
an unexpected ``plaactivat`` literal from the field (docs/03 §7 criterion 5b,
docs/01 §12 trap 14) would have no channel to be seen in at all.

Redaction: verified there is nothing to redact. The entry carries no data at
all (``data={}``) and its only option is ``scan_interval_min``
(``config_flow.py``): no coordinates, no tokens, no personal data, and the
feed itself has none either (docs/03 §3.6). ``TO_REDACT`` therefore stays
empty, but the entry still passes through ``async_redact_data`` so a future
field lands redacted by default instead of in the clear.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import CecatConfigEntry

__all__ = ["async_get_config_entry_diagnostics"]

# Deliberately empty: verified above. The redaction pass stays so the export
# keeps a single code path for entry data and options.
TO_REDACT: set[str] = set()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CecatConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a cecat config entry (docs/03 §3.6)."""
    coordinator = entry.runtime_data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        # The raw rows of the last successful 200, verbatim: fields the
        # parser ignores, literals exactly as sent, ``None`` before the
        # first success.
        "last_raw_response": coordinator.last_raw_response,
        "last_modified": coordinator.last_modified,
        # Sorted so the export is deterministic and JSON-native (a set is
        # neither).
        "unknown_phases": sorted(coordinator.unknown_phases),
        "unknown_acronyms": sorted(coordinator.unknown_acronyms),
        "unknown_activated": sorted(coordinator.unknown_activated),
        "consecutive_failures": coordinator.consecutive_failures,
    }
