"""Tests for the CECAT data model and tolerant parser.

Every acceptance criterion of ``docs/05-implementation-plan.md`` T3 (lines
86-108) has an assertion here, grouped thematically. No network: all data comes
from the fixtures copied in ``tests/fixtures/`` (real captures) or built inline
for the scalar edge cases. The CET/CEST pair is the test that proves the offset
is resolved from the date, not wired to a constant.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from custom_components.cecat.models import (
    ACTIVAT_ABSENT,
    ACTIVATING_PHASES,
    PHASE_ORDER,
    PLAN_NAMES,
    CecatState,
    Phase,
    PlanActivation,
    _severity,
    max_phase,
    normalise_phase,
    plan_name,
    resolve_activated,
    resolve_started_at,
)

from .conftest import load_fixture

# ---------------------------------------------------------------------------
# started_at: the two timestamp paths and the CET/CEST proof
# ---------------------------------------------------------------------------


def test_created_at_path_truncates_to_seconds() -> None:
    """``camps_sistema`` is the only fixture with ``:created_at`` (``.349Z``).

    The sub-second fraction is truncated to whole seconds and the source is
    ``created_at`` (criterion: ``2026-08-05T11:18:09+00:00``).
    """
    row = load_fixture("camps_sistema_2026_08_06")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.phase is Phase.ALERTA
    assert plan.activated is True
    assert plan.started_at == datetime(2026, 8, 5, 11, 18, 9, tzinfo=UTC)
    assert plan.started_at_source == "created_at"


def test_fasedatahora_path_same_minute_as_created_at() -> None:
    """``alerta`` is the same row without system fields, so ``fasedatahora`` wins.

    Both paths give the same minute on real data (criterion:
    ``2026-08-05T11:18:00+00:00``, ``started_at_source = "fasedatahora"``).
    """
    row = load_fixture("alerta_2026_08_06")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.started_at == datetime(2026, 8, 5, 11, 18, 0, tzinfo=UTC)
    assert plan.started_at_source == "fasedatahora"
    assert plan.started_at.replace(second=0) == datetime(
        2026, 8, 5, 11, 18, 0, tzinfo=UTC
    )


def test_fasedatahora_winter_is_cet() -> None:
    """``16/01/2026 19:54`` is January, CET (UTC+1): ``2026-01-16T18:54:00+00:00``.

    This is the test that proves the offset is not wired to a constant.
    """
    row = {
        "plaacronim": "INUNCAT",
        "plafase": "ALERTA",
        "fasedatahora": "16/01/2026 19:54",
    }
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.started_at == datetime(2026, 1, 16, 18, 54, 0, tzinfo=UTC)
    assert plan.started_at_source == "fasedatahora"


def test_fasedatahora_summer_is_cest() -> None:
    """``05/08/2026 13:18`` is August, CEST (UTC+2): ``2026-08-05T11:18:00+00:00``."""
    row = {
        "plaacronim": "INUNCAT",
        "plafase": "ALERTA",
        "fasedatahora": "05/08/2026 13:18",
    }
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.started_at == datetime(2026, 8, 5, 11, 18, 0, tzinfo=UTC)
    assert plan.started_at_source == "fasedatahora"


def test_unparseable_fasedatahora_and_no_created_at_is_none_none() -> None:
    """An unreadable ``fasedatahora`` and no ``:created_at`` is ``(None, None)``."""
    for bad in ("", "   ", "not a date", "31/12", None):
        assert resolve_started_at({"fasedatahora": bad}) == (None, None)
    assert resolve_started_at({}) == (None, None)


def test_created_at_takes_priority_over_fasedatahora() -> None:
    """When both are present, ``:created_at`` wins even if ``fasedatahora`` differs."""
    started, source = resolve_started_at(
        {
            ":created_at": "2026-08-05T11:18:09.349Z",
            "fasedatahora": "99/99/9999 99:99",
        }
    )
    assert started == datetime(2026, 8, 5, 11, 18, 9, tzinfo=UTC)
    assert source == "created_at"


def test_unparseable_created_at_falls_back_to_fasedatahora() -> None:
    """An unreadable ``:created_at`` degrades to the ``fasedatahora`` path."""
    started, source = resolve_started_at(
        {":created_at": "not-a-timestamp", "fasedatahora": "05/08/2026 13:18"}
    )
    assert started == datetime(2026, 8, 5, 11, 18, 0, tzinfo=UTC)
    assert source == "fasedatahora"


def test_non_string_created_at_falls_back_to_fasedatahora() -> None:
    """A non-string or empty ``:created_at`` degrades to the fallback path."""
    for bad in (None, "", "   ", 42, []):
        started, source = resolve_started_at(
            {":created_at": bad, "fasedatahora": "05/08/2026 13:18"}
        )
        assert started == datetime(2026, 8, 5, 11, 18, 0, tzinfo=UTC)
        assert source == "fasedatahora"


def test_naive_created_at_assumed_utc() -> None:
    """A ``:created_at`` without timezone is assumed UTC (the SMP model is UTC)."""
    started, source = resolve_started_at({":created_at": "2026-08-05T11:18:09"})
    assert started == datetime(2026, 8, 5, 11, 18, 9, tzinfo=UTC)
    assert source == "created_at"


# ---------------------------------------------------------------------------
# normalise_phase: diacritics, case, whitespace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["EMERGÈNCIA", "EMERGENCIA", "emergència", " Emergencia ", "alerta", "prealerta"],
)
def test_normalise_phase_strip_diacritics_and_case(raw: str) -> None:
    expected = {
        "EMERGÈNCIA": Phase.EMERGENCIA,
        "EMERGENCIA": Phase.EMERGENCIA,
        "emergència": Phase.EMERGENCIA,
        " Emergencia ": Phase.EMERGENCIA,
        "alerta": Phase.ALERTA,
        "prealerta": Phase.PREALERTA,
    }[raw]
    phase, phase_raw = normalise_phase(raw)
    assert phase is expected
    # the raw literal is preserved verbatim, including surrounding whitespace
    assert phase_raw == raw


def test_normalise_phase_unknown_keeps_literal() -> None:
    phase, phase_raw = normalise_phase("MÀXIMA")
    assert phase is Phase.UNRECOGNIZED
    assert phase_raw == "MÀXIMA"


def test_normalise_phase_none_is_unrecognized() -> None:
    assert normalise_phase(None) == (Phase.UNRECOGNIZED, "")


# ---------------------------------------------------------------------------
# resolve_activated: AD-6 (phase governs), sentinel, recognised literals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["SI", "si", " SI ", "Si"])
def test_resolve_activated_si_is_true_no_warning(raw: str) -> None:
    assert resolve_activated(raw, Phase.EMERGENCIA) == (True, None)


@pytest.mark.parametrize("raw", ["NO", "no", " No "])
def test_resolve_activated_no_is_false_no_warning(raw: str) -> None:
    assert resolve_activated(raw, Phase.ALERTA) == (False, None)


@pytest.mark.parametrize("phase", [Phase.EMERGENCIA, Phase.ALERTA])
@pytest.mark.parametrize("raw", ["true", "Activat", ""])
def test_resolve_activated_unexpected_on_high_phase_is_true_with_literal(
    raw: str, phase: Phase
) -> None:
    """An unexpected or empty ``plaactivat`` on ALERTA/EMERGENCIA derives True."""
    assert resolve_activated(raw, phase) == (True, raw)


@pytest.mark.parametrize("phase", [Phase.EMERGENCIA, Phase.ALERTA])
def test_resolve_activated_absent_on_high_phase_is_absent_sentinel(
    phase: Phase,
) -> None:
    """A missing ``plaactivat`` on ALERTA/EMERGENCIA is True with the sentinel."""
    assert resolve_activated(None, phase) == (True, ACTIVAT_ABSENT)
    assert ACTIVAT_ABSENT == "<absent>"


@pytest.mark.parametrize("raw", ["true", "Activat", "", None])
def test_resolve_activated_unrecognised_on_prealerta_is_false_ad6(raw: object) -> None:
    """PREALERTA governs: the same unrecognisable values give ``False`` (AD-6)."""
    activated, _ = resolve_activated(raw, Phase.PREALERTA)  # type: ignore[arg-type]
    assert activated is False


def test_resolve_activated_unknown_phase_and_unknown_plaactivat() -> None:
    """Both literals unrecognised: ``activated = False``, no exception, both kept."""
    activated, second = resolve_activated("Activat", Phase.UNRECOGNIZED)
    assert activated is False
    assert second == "Activat"
    # absent plaactivat on an unrecognised phase is still not silent
    assert resolve_activated(None, Phase.UNRECOGNIZED) == (False, ACTIVAT_ABSENT)


def test_emergencia_plaactivat_variants_all_true_row_by_row() -> None:
    """The three EMERGÈNCIA rows each give ``activated = True``, asserted per row.

    The three ``(acronym, phase)`` keys are distinct because the acronyms are
    (INUNCAT, INFOCAT, NEUCAT): with a repeated acronym they would collapse.
    """
    rows = load_fixture("emergencia_plaactivat_rar_SYNTHETIC")
    plans = [PlanActivation.from_row(row) for row in rows]
    assert len(plans) == 3
    keys = {plan.key for plan in plans}
    assert len(keys) == 3
    for plan in plans:
        assert plan.phase is Phase.EMERGENCIA
        assert plan.activated is True
    # 'Si' and ' SI ' both normalise to the recognised literal 'si' (no warning,
    # activated_raw None); only the absent field yields the '<absent>' sentinel.
    second_elements = sorted(plan.activated_raw or "" for plan in plans)
    assert second_elements == ["", "", "<absent>"]


# ---------------------------------------------------------------------------
# _severity and max_phase
# ---------------------------------------------------------------------------


def test_severity_unrecognized_is_minus_one_and_does_not_raise() -> None:
    assert _severity(Phase.UNRECOGNIZED) == -1


def test_severity_of_phase_order_members_is_their_position() -> None:
    """The four phases of ``PHASE_ORDER`` return their position (criterion)."""
    assert len(PHASE_ORDER) == 4
    for index, phase in enumerate(PHASE_ORDER):
        assert _severity(phase) == index


def test_max_phase_empty_is_none() -> None:
    assert max_phase([]) is Phase.NONE


def test_max_phase_all_unrecognized_is_unrecognized() -> None:
    assert max_phase([Phase.UNRECOGNIZED]) is Phase.UNRECOGNIZED
    assert max_phase([Phase.UNRECOGNIZED, Phase.UNRECOGNIZED]) is Phase.UNRECOGNIZED


def test_max_phase_mix_ignores_unrecognized() -> None:
    """A mix gives the maximum recognised phase; the unknown never wins."""
    assert max_phase([Phase.UNRECOGNIZED, Phase.ALERTA]) is Phase.ALERTA
    assert max_phase([Phase.PREALERTA, Phase.EMERGENCIA, Phase.UNRECOGNIZED]) is (
        Phase.EMERGENCIA
    )


# ---------------------------------------------------------------------------
# from_row against fixtures
# ---------------------------------------------------------------------------


def test_prealerta_fixture_phase_and_activated_false() -> None:
    """``prealerta_2024_12_02``: PREALERTA, ``activated = False``, ``\\n`` kept."""
    row = load_fixture("prealerta_2024_12_02")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.phase is Phase.PREALERTA
    assert plan.activated is False
    assert plan.phase_raw == "PREALERTA"
    assert "\n" in (plan.description or "")


def test_camps_absents_fixture_no_keyerror() -> None:
    """``camps_absents_SYNTHETIC``: optional fields absent, no exception."""
    row = load_fixture("camps_absents_SYNTHETIC")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.acronym == "TRANSCAT"
    assert plan.communique_url is None
    assert plan.description is None


def test_comunicatpdf_or_plaicona_non_dict_is_none() -> None:
    """A non-dict ``comunicatpdf``/``plaicona`` reads as ``None`` without raising."""
    for bad in (None, "not a dict", 42, []):
        plan = PlanActivation.from_row(
            {"plaacronim": "X", "plafase": "ALERTA", "comunicatpdf": bad}
        )
        assert plan is not None
        assert plan.communique_url is None


def test_pdf_url_accents_pass_through_verbatim() -> None:
    """``communique_url`` keeps ``ó``, ``à`` and ``'`` unescaped (trap 7)."""
    row = load_fixture("pdf_url_accents_2026_07_03")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    url = plan.communique_url
    assert url is not None
    assert "ó" in url
    assert "à" in url
    assert "'" in url


def test_unknown_acronym_falls_back_to_acronym_as_name() -> None:
    """``PENTA``/``NOPLA`` produce a valid row with ``name`` = the acronym."""
    for acronym in ("PENTA", "NOPLA", "WATVER"):
        plan = PlanActivation.from_row(
            {"plaacronim": acronym, "plafase": "ALERTA", "plaactivat": "SI"}
        )
        assert plan is not None
        assert plan.acronym == acronym
        assert plan.name == acronym
        assert acronym not in PLAN_NAMES


def test_fase_desconeguda_fixture_is_unrecognized_with_literal() -> None:
    """``fase_desconeguda_SYNTHETIC``: ``MÀXIMA`` → UNRECOGNIZED, no raise."""
    row = load_fixture("fase_desconeguda_SYNTHETIC")[0]
    plan = PlanActivation.from_row(row)
    assert plan is not None
    assert plan.phase is Phase.UNRECOGNIZED
    assert plan.phase_raw == "MÀXIMA"


def test_from_row_non_dict_returns_none() -> None:
    """A non-dict row yields ``None`` so the caller can discard it."""
    for bad in (None, "string", 42, []):
        assert PlanActivation.from_row(bad) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PLAN_NAMES
# ---------------------------------------------------------------------------


def test_plan_names_contains_the_thirteen_observed_acronyms() -> None:
    """The 13 acronyms with observed communications, and no invented entry."""
    expected = {
        "INUNCAT",
        "PROCICAT",
        "VENTCAT",
        "INFOCAT",
        "AEROCAT",
        "TRANSCAT",
        "NEUCAT",
        "PLASEQTA",
        "PLASEQCAT",
        "ALLAUCAT",
        "CAMCAT",
        "RADCAT",
        "SISMICAT",
    }
    assert set(PLAN_NAMES) == expected
    # PENTA and NOPLA are the canonical unknown acronyms (trap 5): they must
    # stay out so the fallback is exercisable.
    assert "PENTA" not in PLAN_NAMES
    assert "NOPLA" not in PLAN_NAMES


def test_plan_names_values_match_registry_risc_labels() -> None:
    """The display names come from the official registry ``risc`` field."""
    assert PLAN_NAMES["INUNCAT"] == "Inundacions"
    assert PLAN_NAMES["VENTCAT"] == "Ventades"
    assert PLAN_NAMES["NEUCAT"] == "Nevades"
    assert PLAN_NAMES["SISMICAT"] == "Sísmic"


def test_plan_name_uppercases_and_falls_back() -> None:
    assert plan_name("inuncat") == "Inundacions"
    assert plan_name("INUNCAT") == "Inundacions"
    assert plan_name("PENTA") == "PENTA"
    assert plan_name("") == ""


# ---------------------------------------------------------------------------
# ACTIVATING_PHASES
# ---------------------------------------------------------------------------


def test_activating_phases_is_alerta_and_emergencia() -> None:
    assert frozenset({Phase.ALERTA, Phase.EMERGENCIA}) == ACTIVATING_PHASES
    assert Phase.PREALERTA not in ACTIVATING_PHASES
    assert Phase.UNRECOGNIZED not in ACTIVATING_PHASES


# ---------------------------------------------------------------------------
# CecatState: dedup by key, canonical order, cycle comparison
# ---------------------------------------------------------------------------


def test_cecat_state_empty_is_empty() -> None:
    state = CecatState.from_rows([])
    assert state.is_empty
    assert state.activations == ()
    assert state.by_key == {}


def test_cecat_state_dedup_by_acronym_phase_key() -> None:
    """``dos_procicat_SYNTHETIC`` is two rows, same acronym, different phase.

    They must survive as two distinct entries keyed by ``(acronym, phase)``,
    not collapse into one (criterion: count is 2).
    """
    rows = load_fixture("dos_procicat_SYNTHETIC")
    state = CecatState.from_rows(rows)
    assert len(state.activations) == 2
    keys = {plan.key for plan in state.activations}
    assert keys == {("PROCICAT", Phase.PREALERTA), ("PROCICAT", Phase.ALERTA)}


def test_cecat_state_canonical_order_is_deterministic() -> None:
    """Order is ``(acronym, phase)``: INUNCAT before NEUCAT regardless of feed order."""
    rows = load_fixture("dos_plans_2026_01_19")
    state = CecatState.from_rows(rows)
    acronyms = [plan.acronym for plan in state.activations]
    assert acronyms == ["INUNCAT", "NEUCAT"]


def test_cecat_state_compares_equal_regardless_of_row_order() -> None:
    """Two states built from the same rows in different order compare equal."""
    rows = load_fixture("dos_plans_2026_01_19")
    reversed_rows = list(reversed(rows))
    assert CecatState.from_rows(rows) == CecatState.from_rows(reversed_rows)


def test_cecat_state_compares_different_when_content_differs() -> None:
    rows = load_fixture("dos_plans_2026_01_19")
    a = CecatState.from_rows(rows)
    b = CecatState.from_rows(rows[:1])
    assert a != b
    assert len(b.activations) == 1


def test_cecat_state_skips_non_dict_rows() -> None:
    state = CecatState.from_rows(
        [None, "x", {"plaacronim": "INUNCAT", "plafase": "ALERTA"}]
    )
    assert len(state.activations) == 1


def test_cecat_state_last_modified_round_trips() -> None:
    state = CecatState.from_rows([], last_modified="Wed, 06 Aug 2026 11:49:00 GMT")
    assert state.last_modified == "Wed, 06 Aug 2026 11:49:00 GMT"


def test_all_eleven_fixtures_parse_without_exception() -> None:
    """Every fixture parses to activations (or empty) without raising."""
    for name in [
        "alerta_2026_08_06",
        "camps_sistema_2026_08_06",
        "prealerta_2024_12_02",
        "buit_2026_06_16",
        "dos_plans_2026_01_19",
        "pdf_url_accents_2026_07_03",
        "emergencia_SYNTHETIC",
        "emergencia_plaactivat_rar_SYNTHETIC",
        "fase_desconeguda_SYNTHETIC",
        "camps_absents_SYNTHETIC",
        "dos_procicat_SYNTHETIC",
    ]:
        rows = load_fixture(name)
        state = CecatState.from_rows(rows)
        assert isinstance(state, CecatState)
        if name == "buit_2026_06_16":
            assert state.is_empty
