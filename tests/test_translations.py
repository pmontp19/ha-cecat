"""Tests for translations and icons: key parity across the three languages.

Catalan is the reference language (docs/03-feature-spec.md §1): ``ca.json``
carries the canonical wording and ``es``/``en`` are faithful translations of
it. This module guards the two invariants that keep that true as the files
evolve (docs/05 T11 acceptance):

* **Deep key-set parity.** ``strings.json`` and ``translations/{ca,es,en}.json``
  walk the exact same key paths. A key added to one file and forgotten in the
  others renders as a raw ``entity.components.cecat.…`` path in the UI of the
  missing languages, so any divergence fails here, not in a user's dashboard.
* **Icons are fixed ``mdi:`` values, parsed as JSON.** ``icons.json`` is read
  with ``json.loads``, never grepped: a grep would pass on a syntactically
  broken file. Every entity gets a Home Assistant icon and no value may
  derive from ``plaicona``, whose use as entity art the open-data licence
  forbids (docs/01-data-sources.md §11 point 3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "cecat"

TRANSLATION_FILES = (
    "strings.json",
    "translations/ca.json",
    "translations/es.json",
    "translations/en.json",
)

LANGUAGES = ("ca", "es", "en")

# The four translation keys pinned in sensor.py / binary_sensor.py
# (docs/03-feature-spec.md §3): the whole entity surface of the integration.
ENTITY_KEYS = {
    "sensor": ("max_phase", "plans", "last_updated"),
    "binary_sensor": ("plan_activated",),
}

# The five ENUM options of ``sensor.cecat_max_phase`` in severity order
# (docs/03-feature-spec.md §3.1): ``unrecognized`` included, never the
# reserved ``unknown``.
MAX_PHASE_STATES = ("none", "prealerta", "alerta", "emergencia", "unrecognized")

# hassfest's icons.json contract: a fixed Material Design Icons reference.
MDI_PATTERN = re.compile(r"^mdi:[a-z0-9-]+$")


def _load(name: str) -> dict[str, Any]:
    """Parse one component JSON file (icons and strings are JSON, not text)."""
    return json.loads((COMPONENT_DIR / name).read_text(encoding="utf-8"))


def _key_paths(value: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Every leaf path of a nested dict, as a flat set of tuples."""
    if isinstance(value, dict):
        paths: set[tuple[str, ...]] = set()
        for key, child in value.items():
            paths |= _key_paths(child, (*prefix, key))
        return paths
    return {prefix}


@pytest.mark.parametrize("filename", TRANSLATION_FILES[1:])
def test_key_parity_with_strings(filename: str) -> None:
    """Each translation walks the same key paths as ``strings.json``."""
    reference = _key_paths(_load("strings.json"))
    assert _key_paths(_load(filename)) == reference


def test_key_parity_across_languages() -> None:
    """``ca``, ``es`` and ``en`` share one deep key set."""
    key_sets = {
        language: _key_paths(_load(f"translations/{language}.json"))
        for language in LANGUAGES
    }
    assert key_sets["ca"] == key_sets["es"] == key_sets["en"]


def test_every_leaf_is_a_nonempty_string() -> None:
    """No placeholder, empty or non-string leaf anywhere."""
    for filename in TRANSLATION_FILES:
        data = _load(filename)

        def _check(
            node: Any, path: tuple[str, ...] = (), *, _file: str = filename
        ) -> None:
            if isinstance(node, dict):
                for key, child in node.items():
                    _check(child, (*path, key))
                return
            assert isinstance(node, str) and node.strip(), (
                f"{_file}{'/'.join(path)} is not a non-empty string"
            )

        _check(data)


@pytest.mark.parametrize("language", LANGUAGES)
def test_entity_keys_present(language: str) -> None:
    """The four entities have a ``name`` in every language."""
    entities = _load(f"translations/{language}.json")["entity"]
    for platform, keys in ENTITY_KEYS.items():
        for key in keys:
            assert isinstance(entities[platform][key]["name"], str)


@pytest.mark.parametrize("language", LANGUAGES)
def test_max_phase_states_translated(language: str) -> None:
    """All five ENUM values carry a translated state label."""
    state = _load(f"translations/{language}.json")["entity"]["sensor"]["max_phase"][
        "state"
    ]
    assert set(state) == set(MAX_PHASE_STATES)
    assert all(isinstance(label, str) and label for label in state.values())


@pytest.mark.parametrize("language", LANGUAGES)
def test_flow_fields_present(language: str) -> None:
    """Config and options flow fields and errors carry a key."""
    data = _load(f"translations/{language}.json")
    user_data = data["config"]["step"]["user"]["data"]
    assert isinstance(user_data["scan_interval_min"], str)
    assert isinstance(data["config"]["error"]["cannot_connect"], str)
    init_data = data["options"]["step"]["init"]["data"]
    assert isinstance(init_data["scan_interval_min"], str)


def test_icons_are_fixed_mdi_per_entity() -> None:
    """``icons.json`` (parsed, not grepped) maps every entity to one ``mdi:``.

    The icons are deliberately generic Home Assistant artwork: the official
    plan symbols are ``plaicona`` assets whose use the open-data licence
    restricts (docs/01-data-sources.md §11 point 3), so nothing here may
    point at the Generalitat's document container.
    """
    icons = _load("icons.json")["entity"]
    for platform, keys in ENTITY_KEYS.items():
        for key in keys:
            value = icons[platform][key]["default"]
            assert MDI_PATTERN.match(value), f"{platform}.{key}: {value!r}"

    def _icon_strings(node: Any) -> list[str]:
        if isinstance(node, dict):
            return [s for child in node.values() for s in _icon_strings(child)]
        return [node] if isinstance(node, str) else []

    for value in _icon_strings(icons):
        assert "dadesobertes" not in value and "gencat" not in value
