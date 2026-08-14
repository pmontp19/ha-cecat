"""Every fixture loads and is a list, as the live endpoint always returns.

The CECAT Socrata endpoint always answers with a JSON array of row objects,
even when empty (``docs/01-data-sources.md`` §4: the empty state is ``[]``).
This parametric test pins that contract for all eleven fixtures at once: the
six real captures copied verbatim from ``docs/captures/`` and the five
``_SYNTHETIC`` rows that carry a ``_comment`` declaring they are not evidence
(``AGENTS.md`` evidence discipline, ``docs/04-architecture.md`` §9 table).
"""

from __future__ import annotations

import pytest

from .conftest import FIXTURES_DIR, load_fixture

REAL_FIXTURES = [
    "alerta_2026_08_06",
    "camps_sistema_2026_08_06",
    "prealerta_2024_12_02",
    "buit_2026_06_16",
    "dos_plans_2026_01_19",
    "pdf_url_accents_2026_07_03",
]

SYNTHETIC_FIXTURES = [
    "emergencia_SYNTHETIC",
    "emergencia_plaactivat_rar_SYNTHETIC",
    "fase_desconeguda_SYNTHETIC",
    "camps_absents_SYNTHETIC",
    "dos_procicat_SYNTHETIC",
]

ALL_FIXTURES = REAL_FIXTURES + SYNTHETIC_FIXTURES


@pytest.mark.parametrize(("name"), ALL_FIXTURES)
def test_fixture_is_a_list(name: str) -> None:
    """Every fixture parses to a list, like a real endpoint response."""
    data = load_fixture(name)
    assert isinstance(data, list)


@pytest.mark.parametrize(("name"), SYNTHETIC_FIXTURES)
def test_synthetic_fixture_carries_comment(name: str) -> None:
    """Each synthetic row carries a ``_comment`` declaring it is not evidence."""
    data = load_fixture(name)
    assert isinstance(data, list)
    assert len(data) > 0
    for row in data:
        assert isinstance(row, dict)
        assert "_comment" in row
        assert isinstance(row["_comment"], str)
        assert row["_comment"].strip()


def test_fixture_names_match_disk() -> None:
    """The fixture set on disk is exactly the eleven named in the spec."""
    on_disk = {p.stem for p in FIXTURES_DIR.glob("*.json")}
    assert on_disk == set(ALL_FIXTURES)


def test_real_fixtures_have_no_system_projection_split_violation() -> None:
    """``alerta`` has no system fields; ``camps_sistema`` is the same row with them.

    Acceptance criterion (``docs/05-implementation-plan.md`` T2): the two
    fixtures are the same row under two projections, captured 42 minutes apart,
    and neither is hand-edited to match the other. They share ``comunicatpdf``,
    ``fasedatahora`` and ``descripcio``; only ``camps_sistema`` carries
    ``:created_at`` / ``:id`` / ``:updated_at`` / ``:version``.
    """
    alerta = load_fixture("alerta_2026_08_06")
    sistema = load_fixture("camps_sistema_2026_08_06")
    assert isinstance(alerta, list) and len(alerta) == 1
    assert isinstance(sistema, list) and len(sistema) == 1
    alerta_row, sistema_row = alerta[0], sistema[0]
    system_keys = {k for k in alerta_row if k.startswith(":")} | {
        k for k in sistema_row if k.startswith(":")
    }
    assert system_keys == {":id", ":created_at", ":updated_at", ":version"}
    assert not any(k.startswith(":") for k in alerta_row)
    for shared in ("plaacronim", "planom", "plafase", "plaactivat", "fasedatahora"):
        assert alerta_row[shared] == sistema_row[shared]
    assert alerta_row["comunicatpdf"] == sistema_row["comunicatpdf"]
    assert alerta_row["descripcio"] == sistema_row["descripcio"]


def test_buit_fixture_is_exactly_empty_list() -> None:
    """The empty-state fixture is the literal ``[]`` capture."""
    raw = (FIXTURES_DIR / "buit_2026_06_16.json").read_text(encoding="utf-8")
    assert raw.strip() == "[]"
    assert load_fixture("buit_2026_06_16") == []


def test_pdf_url_fixture_keeps_accents_unescaped() -> None:
    """``comunicatpdf.url`` keeps ``ó``, ``à`` and ``'`` unescaped (trap 7)."""
    row = load_fixture("pdf_url_accents_2026_07_03")[0]
    url = row["comunicatpdf"]["url"]
    assert "ó" in url
    assert "à" in url
    assert "'" in url
    assert "\\u" not in url
    assert "\\" not in url
