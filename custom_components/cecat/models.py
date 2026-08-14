"""Data model and tolerant parser for the CECAT civil-protection feed.

No Home Assistant import lives here on purpose: this module is pure Python and
testable in complete isolation (``docs/04-architecture.md`` §4). It takes already
decoded JSON rows and returns typed objects. No network, no I/O.

The source is free text from a public service that can change without notice
(``docs/01-data-sources.md`` §12), so every field is read with ``.get()`` plus a
default and no conversion raises. The traps this module codifies, each with a
test in ``tests/test_models.py``:

- Episode identity is ``(acronym, phase)``, never Socrata's ``:id`` nor a hash of
  the row. ``comunicatpdf`` changes several times within one phase and ``:id``
  changes on a phase change (trap 11), so any other key duplicates or loses
  events. ``PlanActivation.key`` is that pair.
- ``plafase`` is authoritative; ``plaactivat`` is derived (AD-6). ``plaactivat``
  ``"NO"`` is the ``PREALERTA`` phase and is 51.4% of the signal, so filtering on
  ``"SI"`` hides half the source. ``resolve_activated`` returns ``False`` only on
  the literal ``no`` and falls back to the phase otherwise.
- Phase matching strips diacritics and casefolds: ``EMERGÈNCIA`` is documented
  with an accent but has never been observed live (trap 14), so an accent
  variation must not lose the most severe phase.
- ``resolve_started_at`` tries ``:created_at`` (ISO-8601 UTC) first and falls back
  to ``fasedatahora`` (``DD/MM/YYYY HH:MM`` in CET/CEST via ``Europe/Madrid``).
  ``started_at_source`` makes the degradation observable (AD-3).
- A missing ``plaactivat`` is not silent: it returns the ``"<absent>"`` sentinel
  so the coordinator can warn once, because a field that governs a ``SAFETY``
  sensor vanishing is a schema change worth noticing.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

__all__ = [
    "ACTIVATING_PHASES",
    "ACTIVAT_ABSENT",
    "PHASE_ORDER",
    "PLAN_NAMES",
    "CecatState",
    "Phase",
    "PlanActivation",
    "max_phase",
    "normalise_phase",
    "plan_name",
    "resolve_activated",
    "resolve_started_at",
]


# ---------------------------------------------------------------------------
# Phase vocabulary
# ---------------------------------------------------------------------------


class Phase(StrEnum):
    """Civil-protection phase of a plan activation.

    ``NONE`` is the aggregated state of an empty response (``max_phase([])``);
    a single row never carries it. ``UNRECOGNIZED`` stands for a literal the
    source sent that is not one of the three known phases (trap 5: the set of
    phases is not closed). ``UNRECOGNIZED`` is deliberately excluded from
    ``PHASE_ORDER`` because its position on the severity scale is unknown
    (AD-8): ordering compares only members that have one.
    """

    NONE = "none"
    PREALERTA = "prealerta"
    ALERTA = "alerta"
    EMERGENCIA = "emergencia"
    UNRECOGNIZED = "unrecognized"


# Used to *order* phases by severity. ``UNRECOGNIZED`` is absent on purpose
# (AD-8): ``max_phase`` filters to these before ordering, and the pairing rule
# of the coordinator (§5) only compares severities when both sides are members.
PHASE_ORDER: tuple[Phase, ...] = (
    Phase.NONE,
    Phase.PREALERTA,
    Phase.ALERTA,
    Phase.EMERGENCIA,
)

# Used to *classify* whether a phase activates the plan. This is a membership
# question, not an ordering one, so it cannot raise on any value: ``UNRECOGNIZED``
# simply is not a member and derives ``False`` (AD-6).
ACTIVATING_PHASES = frozenset({Phase.ALERTA, Phase.EMERGENCIA})

# Sentinel for a ``plaactivat`` field that vanished from the row entirely. It
# travels the same path as any other unrecognised literal: into the coordinator's
# ``_unknown_activated`` set, one ``warning``, and the diagnostics export. A
# missing field on a ``SAFETY`` sensor must never be silent (§4).
ACTIVAT_ABSENT = "<absent>"


# Casefolded, accent-stripped keys for the three known phases. Built from the
# enum values themselves so the table cannot drift away from them.
_PHASE_BY_KEY: dict[str, Phase] = {
    "prealerta": Phase.PREALERTA,
    "alerta": Phase.ALERTA,
    "emergencia": Phase.EMERGENCIA,
}


# ---------------------------------------------------------------------------
# Plan acronym → display name
# ---------------------------------------------------------------------------

# The 13 plans with observed communications (``docs/01-data-sources.md`` §3.2),
# mapped to the ``risc`` label of the official registry ``xqqe-tgav``. Notably
# absent are ``PENTA`` (a state plan, not in the Generalitat registry) and
# ``NOPLA`` (a communique with no plan): both are the canonical examples of
# unknown acronyms that fall back to the acronym itself (trap 5), and keeping
# them out is what makes that fallback exercisable. The map is a dict, not a
# set, because ``plan_name`` resolves a display name from it.
PLAN_NAMES: dict[str, str] = {
    "INUNCAT": "Inundacions",
    "PROCICAT": "Territorial - Multirisc",
    "VENTCAT": "Ventades",
    "INFOCAT": "Incendis Forestals",
    "AEROCAT": "Aeronàutic",
    "TRANSCAT": "Transport de mercaderies perilloses",
    "NEUCAT": "Nevades",
    "PLASEQTA": "Químic",
    "PLASEQCAT": "Químic",
    "ALLAUCAT": "Allaus",
    "CAMCAT": "Contaminació marina",
    "RADCAT": "Radiològic",
    "SISMICAT": "Sísmic",
}


def plan_name(acronym: str) -> str:
    """Resolve a display name for an acronym, falling back to the acronym.

    The fallback is not degradation (§4): ``PENTA`` and ``NOPLA`` survive it,
    and an acronym that joins the feed later shows verbatim until the map is
    updated. The lookup never reads ``planom``, which is identical to
    ``plaacronim`` on 5/5 observed rows (trap 4).
    """
    return PLAN_NAMES.get(acronym.upper(), acronym)


# ---------------------------------------------------------------------------
# Severity and aggregation
# ---------------------------------------------------------------------------


def _severity(phase: Phase) -> int:
    """Position of a phase on the severity scale, or ``-1`` when it has none.

    Never raises: ``UNRECOGNIZED`` is not in ``PHASE_ORDER`` and returns ``-1``.
    The ``-1`` is defence in depth only: no enumerated caller depends on it,
    each is protected by a membership filter or condition beforehand (AD-8).
    """
    return PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1


def max_phase(phases: Iterable[Phase]) -> Phase:
    """The most severe phase among ``phases``, filtering before it orders.

    ``[]`` gives ``NONE``; a set where every phase is unrecognised gives
    ``UNRECOGNIZED``; any mixture gives the maximum *recognised* one. The
    filter is the substance: ``max()`` never receives a value without a
    severity position, so an ``index()`` could not raise here.
    """
    as_list = list(phases)
    orderable = [phase for phase in as_list if phase in PHASE_ORDER]
    if orderable:
        return max(orderable, key=_severity)
    return Phase.UNRECOGNIZED if as_list else Phase.NONE


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------


def _strip_diacritics(value: str) -> str:
    """Fold accents away so ``EMERGÈNCIA`` reads as ``EMERGENCIA``.

    NFKD decomposition followed by combining-mark removal. ``casefold`` and
    ``strip`` are applied by the callers, who keep the raw literal separately.
    """
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalise_phase(raw: str | None) -> tuple[Phase, str]:
    """Resolve a ``plafase`` literal to a ``(Phase, raw_literal)`` pair.

    Matching is casefolded and accent-stripped so that ``EMERGÈNCIA``,
    ``EMERGENCIA``, ``emergència`` and ``" Emergencia "`` all resolve to
    ``Phase.EMERGENCIA`` (trap 14). The raw literal is returned unchanged so
    the coordinator and diagnostics can show exactly what the source sent,
    including for an unrecognised value (``MÀXIMA`` → ``UNRECOGNIZED``).
    """
    if raw is None:
        return Phase.UNRECOGNIZED, ""
    key = _strip_diacritics(raw).strip().casefold()
    return _PHASE_BY_KEY.get(key, Phase.UNRECOGNIZED), raw


def resolve_activated(raw: str | None, phase: Phase) -> tuple[bool, str | None]:
    """Resolve ``plaactivat`` to ``(activated, literal_to_register)``.

    The second element is ``None`` when the literal was recognised (``SI`` or
    ``NO`` in any tolerated casing) and no warning is needed. Otherwise the
    activation is derived from the phase via ``ACTIVATING_PHASES`` (AD-6:
    ``plafase`` governs, ``plaactivat`` is derived), and the second element
    carries either the raw literal (for an unexpected value or the empty
    string) or the ``ACTIVAT_ABSENT`` sentinel (for a field that vanished), so
    the coordinator can warn exactly once per literal.

    Properties this preserves:
    - ``False`` only on the literal ``no``. Nothing else reads as "nothing".
    - The fallback is the phase, not unconditional ``True``: a ``PREALERTA``
      with a corrupt ``plaactivat`` still gives ``off``, which is correct.
    - The derivation is a membership, never an ordering comparison, so it
      cannot raise on ``UNRECOGNIZED``.
    """
    if isinstance(raw, str):
        key = _strip_diacritics(raw).strip().casefold()
        if key == "no":
            return False, None
        if key == "si":
            return True, None
    derived = phase in ACTIVATING_PHASES
    if raw is None:
        return derived, ACTIVAT_ABSENT
    return derived, raw if isinstance(raw, str) else str(raw)


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------


def _parse_iso(raw: Any) -> datetime | None:
    """Parse an ISO-8601 ``:created_at`` (already UTC, ends with ``Z``).

    Truncated to whole seconds: the sub-second fraction (``.349Z``) is source
    bookkeeping, not signal, and keeping it would make two captures of the same
    row compare unequal. Unparseable input degrades to ``None``.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.replace(microsecond=0)


def _parse_local(raw: Any) -> datetime | None:
    """Parse ``fasedatahora`` as ``DD/MM/YYYY HH:MM`` in CET/CEST.

    ``ZoneInfo("Europe/Madrid")`` resolves DST from the date itself, so the
    offset is never wired: a January stamp reads UTC+1 and an August one
    UTC+2. Verified against 1,146 data points (``docs/01-data-sources.md`` §8).
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        naive = datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=ZoneInfo("Europe/Madrid")).astimezone(UTC)


def resolve_started_at(row: dict[str, Any]) -> tuple[datetime | None, str | None]:
    """Resolve the phase start timestamp, ``:created_at`` first (AD-3).

    Returns ``(datetime, source)`` where source is ``"created_at"`` or
    ``"fasedatahora"``, making the degradation observable. When neither field
    yields a timestamp, returns ``(None, None)`` rather than raising: a row
    with no usable start is still a valid activation.
    """
    created = row.get(":created_at")
    if created:
        parsed = _parse_iso(created)
        if parsed:
            return parsed, "created_at"
    parsed = _parse_local(row.get("fasedatahora"))
    return (parsed, "fasedatahora") if parsed else (None, None)


# ---------------------------------------------------------------------------
# Optional field readers
# ---------------------------------------------------------------------------


def _url(value: Any) -> str | None:
    """Read ``url`` from a ``comunicatpdf``/``plaicona`` object; ``None`` otherwise.

    Both fields are objects ``{"url": ...}`` that can be missing wholesale
    (trap 6). A non-dict value (a stray string, ``null``) reads as ``None``
    without raising. The URL is treated as an opaque string: never validated,
    normalised or fetched, so an unescaped ``ó`` or ``'`` passes through
    verbatim (trap 7).
    """
    return value.get("url") if isinstance(value, dict) else None


def _text(value: Any) -> str | None:
    """Read a free-text field with ``.strip()`` only; ``None`` when absent/empty.

    ``descripcio`` carries double spaces, a ``" - "`` suffix and literal
    newlines (trap 10): only leading/trailing whitespace is removed. The
    suffix is content the licence forbids altering (``docs/01-data-sources.md``
    §11), so it is kept, and the internal ``\\n`` survives ``strip``.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _as_str(value: Any) -> str:
    """Return external text verbatim; anything non-textual becomes empty."""
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------------------
# PlanActivation
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanActivation:
    """One row of the CECAT feed, parsed and normalised.

    The fields are exactly those the event payloads and the ``plans`` sensor
    attribute need (``docs/03-feature-spec.md`` §4.1, §3.2): ``acronym`` and
    ``phase`` form the identity key (AD-5), ``phase_raw`` and ``activated_raw``
    carry the unrecognised literals for diagnostics, and ``started_at_source``
    records which timestamp path won. Frozen so snapshots compare by value.
    """

    acronym: str
    name: str
    phase: Phase
    phase_raw: str
    activated: bool
    activated_raw: str | None
    started_at: datetime | None
    started_at_source: str | None
    description: str | None
    communique_url: str | None

    @property
    def key(self) -> tuple[str, Phase]:
        """The ``(acronym, phase)`` identity (AD-5), also the state-dict key."""
        return (self.acronym, self.phase)

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PlanActivation | None:
        """Build a ``PlanActivation`` from one decoded JSON row.

        Tolerant to every trap of §4: missing optional fields, unrecognised
        phases and acronyms, absent ``plaactivat``, and either timestamp path.
        Returns ``None`` only when the row is not a dict (the API client
        discards those); every dict row yields an activation, even a degenerate
        one, so a single bad field never drops a real plan.
        """
        if not isinstance(row, dict):
            return None
        acronym = _as_str(row.get("plaacronim"))
        phase, phase_raw = normalise_phase(row.get("plafase"))
        activated, activated_raw = resolve_activated(row.get("plaactivat"), phase)
        started_at, started_at_source = resolve_started_at(row)
        return cls(
            acronym=acronym,
            name=plan_name(acronym),
            phase=phase,
            phase_raw=phase_raw,
            activated=activated,
            activated_raw=activated_raw,
            started_at=started_at,
            started_at_source=started_at_source,
            description=_text(row.get("descripcio")),
            communique_url=_url(row.get("comunicatpdf")),
        )


def _activation_sort_key(activation: PlanActivation) -> tuple[str, int]:
    """Total order over an activation's own fields, for canonical tuple order.

    The feed does not guarantee row order (``docs/01-data-sources.md`` §6), so
    activations are sorted canonically before they enter ``CecatState``: two
    snapshots of the same content then compare equal regardless of how the rows
    happened to arrive. The phase ranks by severity position; ``UNRECOGNIZED``
    ranks ``-1`` and sorts first for its acronym, deterministically.
    """
    return (activation.acronym, _severity(activation.phase))


# ---------------------------------------------------------------------------
# CecatState
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CecatState:
    """Everything one successful fetch produced, as a comparable snapshot.

    ``activations`` is a tuple in canonical ``(acronym, phase)`` order, deduplicated
    by that key: two rows sharing both (an accepted indistinguishability, §5)
    collapse to one entry. Frozenness plus the canonical order lets the
    coordinator compare cycle to cycle with ``always_update=False`` and skip
    downstream work when nothing changed, exactly like the sibling repos.
    """

    activations: tuple[PlanActivation, ...] = ()
    last_modified: str | None = None

    @classmethod
    def from_rows(
        cls,
        rows: Iterable[Any],
        *,
        last_modified: str | None = None,
    ) -> CecatState:
        """Parse decoded JSON rows into a deduplicated, canonically ordered state.

        Non-dict entries are skipped (the API client logs them at ``debug``).
        Duplicate ``(acronym, phase)`` keys keep the last row seen, which is
        arbitrary but stable for comparison since the identity makes the rows
        indistinguishable.
        """
        by_key: dict[tuple[str, Phase], PlanActivation] = {}
        for row in rows:
            parsed = PlanActivation.from_row(row)
            if parsed is not None:
                by_key[parsed.key] = parsed
        activations = tuple(sorted(by_key.values(), key=_activation_sort_key))
        return cls(activations=activations, last_modified=last_modified)

    @property
    def by_key(self) -> dict[tuple[str, Phase], PlanActivation]:
        """Index of activations by ``(acronym, phase)``, the reconciliation key."""
        return {activation.key: activation for activation in self.activations}

    @property
    def is_empty(self) -> bool:
        """Whether the snapshot carries no activation (the most likely state)."""
        return not self.activations
