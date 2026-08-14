"""Scaffold smoke tests.

Real coverage starts at T2 (fixtures) and T3 (models). These exist so the CI
``pytest tests/`` step has something to run before T2 lands.
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.cecat.const import (
    ATTRIBUTION,
    BASE_URL,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    EVENT_ESCALATION,
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_PHASE_STARTED,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
    PARAMS,
)


def test_domain_is_cecat() -> None:
    assert DOMAIN == "cecat"


def test_base_url_is_socrata_dataset() -> None:
    assert BASE_URL == "https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json"


def test_params_select_all_with_system_fields() -> None:
    assert PARAMS == {"$select": ":*,*"}


def test_scan_interval_bounds() -> None:
    assert MIN_SCAN_INTERVAL_MIN <= DEFAULT_SCAN_INTERVAL_MIN <= MAX_SCAN_INTERVAL_MIN


def test_event_names_are_domain_prefixed() -> None:
    for event in (
        EVENT_PHASE_STARTED,
        EVENT_PHASE_ENDED,
        EVENT_PHASE_CHANGED,
        EVENT_ESCALATION,
    ):
        assert event.startswith(f"{DOMAIN}_")


def test_attribution_is_non_empty_string() -> None:
    assert isinstance(ATTRIBUTION, str) and ATTRIBUTION.strip()


def test_manifest_loads_and_declares_domain() -> None:
    manifest_path = Path(__file__).resolve().parents[1] / "custom_components/cecat/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["domain"] == DOMAIN
    assert manifest["integration_type"] == "service"
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["requirements"] == []
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
