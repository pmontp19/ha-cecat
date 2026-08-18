"""Tests for `blueprints/automation/cecat/plan_notification.yaml` (T12).

Every acceptance criterion of docs/05-implementation-plan.md T12 (lines
310-323) has an assertion here. Three layers:

1. Structural: a permissive YAML parse inspects `input:`, the single
   `phase_started` trigger, the automation-level `variables:` block that binds
   the `!input` values, and the guard-before-index() shape of the condition.
2. Schema: the blueprint is loaded through Home Assistant's real blueprint
   machinery and substituted with concrete inputs into a valid automation.
3. Behavioural + rendering: the substituted condition and message templates
   are rendered exactly the way a running automation renders them, with
   `min_phase`/`plans` reaching the templates ONLY through the blueprint's own
   `variables:` block (the substituted config's resolved variables), never by
   injecting `min_phase` directly into the render context, because that would
   pass even if the real blueprint were broken (T12, criterion on line 317).
   The blueprint is also installed as a live automation and exercised by
   firing `cecat_plan_phase_started` on `hass.bus`.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml as pyyaml
from custom_components.cecat.const import (
    EVENT_PHASE_CHANGED,
    EVENT_PHASE_ENDED,
    EVENT_PHASE_STARTED,
)
from custom_components.cecat.models import PLAN_NAMES
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    PLATFORM_SCHEMA,
)
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.helpers import condition
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util import yaml as yaml_util
from pytest_homeassistant_custom_component.common import async_mock_service

BLUEPRINT_PATH = str(
    Path(__file__).resolve().parent.parent
    / "blueprints"
    / "automation"
    / "cecat"
    / "plan_notification.yaml"
)

# The three inputs feature-spec §5 documents, and no others.
EXPECTED_INPUTS = {"notify_target", "min_phase", "plans"}

MIN_PHASES = ["prealerta", "alerta", "emergencia"]

# The four phases an event can carry: the three `plafase` literals plus the
# escape valve. `none` never appears in an event payload (`normalise_phase`
# never returns Phase.NONE; it only exists as the aggregate of an empty feed),
# so it is deliberately absent from this list.
EVENT_PHASES = ["prealerta", "alerta", "emergencia", "unrecognized"]

# The condition of docs/03-feature-spec.md §5.1, verbatim modulo whitespace.
EXPECTED_PHASE_CONDITION = """
{% set ordre = ['prealerta', 'alerta', 'emergencia'] %}
{{ trigger.event.data.phase == 'unrecognized'
   or ordre.index(trigger.event.data.phase) >= ordre.index(min_phase) }}
"""

# The message fragment of docs/03-feature-spec.md §5.2, the only copyable
# message in the whole doc set. Compared whitespace-normalized, so the line
# breaks below (kept to stay under the line-length limit) do not matter.
EXPECTED_MESSAGE_FRAGMENT = (
    "{% if trigger.event.data.phase == 'unrecognized' %}\n"
    "  {{ trigger.event.data.acronym }}: fase NO RECONEGUDA "
    '("{{ trigger.event.data.phase_raw }}")\n'
    "{% else %}\n"
    "  {{ trigger.event.data.acronym }}: ara en fase "
    "{{ trigger.event.data.phase | upper }}\n"
    "{% endif %}\n"
)

NOTIFY_INPUT = ["test-device-id"]

DESCRIPTION = "Avís intensitat pluja fins al 04/08  -"
COMMUNIQUE_URL = (
    "https://documents.dadesobertes.gencat.cat/cecat/docs/"
    "I-125912_INUNCAT_202608061114.pdf"
)


def started_payload(**overrides: Any) -> dict[str, Any]:
    """A `cecat_plan_phase_started` payload with the exact eight §4.1 fields."""
    payload: dict[str, Any] = {
        "acronym": "INUNCAT",
        "name": "Inundacions",
        "phase": "alerta",
        "phase_raw": "ALERTA",
        "activated": True,
        "started_at": "2026-08-05T11:18:09+00:00",
        "description": DESCRIPTION,
        "communique_url": COMMUNIQUE_URL,
    }
    payload.update(overrides)
    return payload


def _norm(text: str) -> str:
    """Collapse all whitespace runs, so YAML folding cannot break comparisons."""
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# 1. Structural checks (permissive YAML parse, no HA runtime)
# ---------------------------------------------------------------------------


def _load_raw() -> dict[str, Any]:
    """Parse the blueprint with a loader that tolerates the `!input` tag."""

    class _TolerantLoader(pyyaml.SafeLoader):
        pass

    def _construct_unknown(
        loader: pyyaml.SafeLoader, tag_suffix: str, node: Any
    ) -> Any:
        if isinstance(node, pyyaml.ScalarNode):
            return loader.construct_scalar(node)
        if isinstance(node, pyyaml.SequenceNode):
            return loader.construct_sequence(node)
        return loader.construct_mapping(node)

    _TolerantLoader.add_multi_constructor("!", _construct_unknown)
    with open(BLUEPRINT_PATH, encoding="utf-8") as handle:
        return pyyaml.load(handle, Loader=_TolerantLoader)


def test_blueprint_metadata() -> None:
    """The blueprint declares the domain/name/source_url/min_version."""
    meta = _load_raw()["blueprint"]
    assert meta["domain"] == "automation"
    assert "Protecció Civil Catalunya" in meta["name"]
    assert meta["source_url"].startswith(
        "https://github.com/pmontp19/ha-cecat/blob/main/blueprints/"
    )
    assert "min_version" in meta["homeassistant"]


def test_blueprint_declares_exactly_three_inputs() -> None:
    """`notify_target`, `min_phase` (default alerta) and `plans` (empty = all)."""
    inputs = _load_raw()["blueprint"]["input"]
    assert set(inputs.keys()) == EXPECTED_INPUTS

    device_selector = inputs["notify_target"]["selector"]["device"]
    assert device_selector["integration"] == "mobile_app"
    assert device_selector["multiple"] is True

    min_phase = inputs["min_phase"]
    assert min_phase["default"] == "alerta"
    options = min_phase["selector"]["select"]["options"]
    assert [opt["value"] for opt in options] == MIN_PHASES

    plans = inputs["plans"]
    assert plans["default"] == []
    plans_selector = plans["selector"]["select"]
    assert plans_selector["multiple"] is True
    # The offered acronyms are exactly the integration's known plans, in the
    # same order as PLAN_NAMES, so the two lists cannot drift apart.
    assert [opt["value"] for opt in plans_selector["options"]] == list(PLAN_NAMES)


def test_single_trigger_is_phase_started() -> None:
    """One and only one trigger: `cecat_plan_phase_started`, never `changed`."""
    triggers = _load_raw()["triggers"]
    assert len(triggers) == 1
    assert triggers[0]["event_type"] == EVENT_PHASE_STARTED
    # The `phase_changed` lane is named in the description (deliberately), so
    # the check must be about triggers, not about the raw text.
    assert EVENT_PHASE_CHANGED not in {t["event_type"] for t in triggers}


def test_description_documents_the_single_event_choice() -> None:
    """The description explains why `phase_changed` is not listened to."""
    description = _load_raw()["blueprint"]["description"]
    assert EVENT_PHASE_STARTED in description
    assert EVENT_PHASE_CHANGED in description
    # ...and the two documented reasons: the double-notification cost, and the
    # open-6 false positive that the escalation lane inherits (T12, line 315).
    assert "DUES notificacions" in description
    assert "fals positiu" in description


def test_variables_block_binds_the_two_inputs() -> None:
    """The automation-level `variables:` block binds exactly min_phase/plans.

    With the tolerant loader `!input min_phase` stringifies to `min_phase`, so
    this asserts the binding shape of docs/03-feature-spec.md §5.1: the
    condition templates resolve `min_phase` and `plans` through this block,
    because `!input` never substitutes inside a Jinja string.
    """
    raw = _load_raw()
    assert raw["variables"] == {"min_phase": "min_phase", "plans": "plans"}


def test_phase_condition_is_the_documented_form_with_guard_first() -> None:
    """The condition is §5.1 verbatim; `unrecognized` precedes any index()."""
    phase_condition = _load_raw()["conditions"][0]["value_template"]
    assert _norm(phase_condition) == _norm(EXPECTED_PHASE_CONDITION)
    # The order of the operands is the whole point: with `phase ==
    # 'unrecognized'` first, the short-circuiting `or` keeps the order-less
    # value away from index() (a ValueError that kills the template).
    assert phase_condition.index("unrecognized") < phase_condition.index(".index(")


def test_plans_condition_empty_means_all() -> None:
    """The second condition: empty `plans` list means every plan passes."""
    plans_condition = _load_raw()["conditions"][1]["value_template"]
    assert _norm(plans_condition) == _norm(
        "{{ plans | length == 0 or trigger.event.data.acronym in plans }}"
    )


def test_message_fragment_is_the_only_copyable_one() -> None:
    """The action implements the §5.2 fragment verbatim, and only that."""
    raw = _load_raw()
    notify_message = raw["actions"][0]["variables"]["notify_message"]
    assert _norm(notify_message) == _norm(EXPECTED_MESSAGE_FRAGMENT)
    # The composed message reuses the rendered fragment (trim), then appends
    # the description and the communique link when present (feature-spec §5).
    message = raw["actions"][1]["data"]["message"]
    assert "notify_message | trim" in message
    assert "trigger.event.data.description" in message
    assert "trigger.event.data.communique_url" in message
    assert raw["actions"][1]["data"]["title"] == "Protecció Civil Catalunya"
    # The notification goes to the user-picked devices via notify.send_message
    # with a device_id target (feature-spec §5: `device` selector).
    assert raw["actions"][1]["action"] == "notify.send_message"
    assert raw["actions"][1]["target"] == {"device_id": "notify_target"}


def test_no_unqualified_template_names() -> None:
    """Every event field is reached as `trigger.event.data.*`, never bare.

    A bare `{{ acronym }}` would not raise: Jinja renders it as an empty
    string (the name is not bound by the `variables:` block), silently
    stripping the plan from the notification (feature-spec §5.2).
    """
    raw_text = Path(BLUEPRINT_PATH).read_text(encoding="utf-8")
    for name in (
        "acronym",
        "name",
        "phase",
        "phase_raw",
        "description",
        "communique_url",
        "started_at",
        "activated",
    ):
        assert f"{{{{ {name} }}}}" not in raw_text


# ---------------------------------------------------------------------------
# 2. Schema: real blueprint machinery substitution
# ---------------------------------------------------------------------------


def _substitute(user_inputs: dict[str, Any]) -> dict[str, Any]:
    """Run the blueprint through HA's real loader/substitution pipeline."""
    data = yaml_util.load_yaml(BLUEPRINT_PATH)
    blueprint = Blueprint(
        data,
        path=BLUEPRINT_PATH,
        expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    inputs = BlueprintInputs(
        blueprint,
        {"use_blueprint": {"path": BLUEPRINT_PATH, "input": user_inputs}},
    )
    inputs.validate()
    return inputs.async_substitute()


@pytest.mark.parametrize(
    "user_inputs",
    [
        {"notify_target": NOTIFY_INPUT},
        {"notify_target": NOTIFY_INPUT, "min_phase": "prealerta"},
        {
            "notify_target": NOTIFY_INPUT,
            "min_phase": "emergencia",
            "plans": ["INUNCAT", "NEUCAT"],
        },
    ],
)
async def test_blueprint_produces_valid_automation_config(
    hass: HomeAssistant, user_inputs: dict[str, Any]
) -> None:
    """The substituted blueprint is a valid automation config."""
    config = _substitute(user_inputs)
    validated = PLATFORM_SCHEMA(config)
    assert validated["triggers"]
    assert validated["conditions"]
    assert validated["actions"]


@pytest.mark.parametrize("min_phase", MIN_PHASES)
async def test_substitution_resolves_inputs_through_variables_block(
    hass: HomeAssistant, min_phase: str
) -> None:
    """The `!input` values land in the automation's `variables:` block.

    This is the real resolution path the conditions rely on: the substituted
    config carries `min_phase`/`plans` as automation variables (bound from the
    inputs), while the condition template still references the bare names,
    which only resolve through that block. Direct injection into the render
    context is what the render tests below deliberately never do.
    """
    config = _substitute({"notify_target": NOTIFY_INPUT, "min_phase": min_phase})
    assert config["variables"] == {"min_phase": min_phase, "plans": []}
    condition_template = config["conditions"][0]["value_template"]
    assert "ordre.index(min_phase)" in condition_template


# ---------------------------------------------------------------------------
# 3a. Rendering: the substituted condition, 4 phases x 3 min_phase = 12 combos
# ---------------------------------------------------------------------------


def _render_context(
    variables: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """The context a running automation gives to condition/action templates."""
    return {**variables, "trigger": {"event": {"data": payload}}}


def _phase_condition_of(config: dict[str, Any]) -> str:
    return config["conditions"][0]["value_template"]


def _message_template_of(config: dict[str, Any]) -> str:
    return config["actions"][0]["variables"]["notify_message"]


def _composed_message_template_of(config: dict[str, Any]) -> str:
    return config["actions"][1]["data"]["message"]


async def _condition_result(
    hass: HomeAssistant,
    condition_template: str,
    variables: dict[str, Any],
    payload: dict[str, Any],
) -> bool:
    """Render a condition exactly as HA's template condition does."""
    template = Template(condition_template, hass)
    return condition.async_template(
        hass, template, variables=_render_context(variables, payload)
    )


# The full 4 x 3 truth table, keyed (phase, min_phase). `unrecognized` passes
# every min_phase; the remaining rows are the severity order
# prealerta < alerta < emergencia.
TRUTH_TABLE = {
    ("prealerta", "prealerta"): True,
    ("prealerta", "alerta"): False,
    ("prealerta", "emergencia"): False,
    ("alerta", "prealerta"): True,
    ("alerta", "alerta"): True,
    ("alerta", "emergencia"): False,
    ("emergencia", "prealerta"): True,
    ("emergencia", "alerta"): True,
    ("emergencia", "emergencia"): True,
    ("unrecognized", "prealerta"): True,
    ("unrecognized", "alerta"): True,
    ("unrecognized", "emergencia"): True,
}


@pytest.mark.parametrize("phase", EVENT_PHASES)
@pytest.mark.parametrize("min_phase", MIN_PHASES)
async def test_phase_condition_renders_all_twelve_combinations(
    hass: HomeAssistant, phase: str, min_phase: str
) -> None:
    """No combination raises; each renders the documented truth value."""
    config = _substitute({"notify_target": NOTIFY_INPUT, "min_phase": min_phase})
    # min_phase reaches the template only via the substituted variables block.
    variables = config["variables"]
    raw_by_phase = {
        "prealerta": "PREALERTA",
        "alerta": "ALERTA",
        "emergencia": "EMERGÈNCIA",
        "unrecognized": "VIGILÀNCIA PERPETUA",
    }
    payload = started_payload(phase=phase, phase_raw=raw_by_phase[phase])
    result = await _condition_result(
        hass, _phase_condition_of(config), variables, payload
    )
    assert result is TRUTH_TABLE[(phase, min_phase)]


async def test_plans_condition_rendering(hass: HomeAssistant) -> None:
    """Empty `plans` lets any acronym through; a list filters by acronym."""
    config = _substitute({"notify_target": NOTIFY_INPUT})
    plans_condition = config["conditions"][1]["value_template"]

    empty = config["variables"]["plans"]
    assert empty == []
    assert await _condition_result(
        hass, plans_condition, config["variables"], started_payload(acronym="PENTA")
    )

    narrowed = _substitute({"notify_target": NOTIFY_INPUT, "plans": ["INUNCAT"]})
    assert await _condition_result(
        hass,
        plans_condition,
        narrowed["variables"],
        started_payload(acronym="INUNCAT"),
    )
    assert not await _condition_result(
        hass,
        plans_condition,
        narrowed["variables"],
        started_payload(acronym="PROCICAT"),
    )


# ---------------------------------------------------------------------------
# 3b. Rendering: the message, all four phases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("phase", "phase_raw"),
    [
        ("prealerta", "PREALERTA"),
        ("alerta", "ALERTA"),
        ("emergencia", "EMERGÈNCIA"),
        ("unrecognized", "VIGILÀNCIA PERPETUA"),
    ],
)
async def test_message_renders_all_four_phases(
    hass: HomeAssistant, phase: str, phase_raw: str
) -> None:
    """No phase raises, and the two §5.2 cases come out verbatim."""
    config = _substitute({"notify_target": NOTIFY_INPUT})
    context = _render_context(
        config["variables"], started_payload(phase=phase, phase_raw=phase_raw)
    )
    # The variables step renders the fragment first, exactly as the script
    # would; then the composed message template consumes that result.
    fragment = Template(_message_template_of(config), hass).async_render(
        variables=context
    )
    assert isinstance(fragment, str)

    composed = Template(_composed_message_template_of(config), hass).async_render(
        variables={**context, "notify_message": fragment}
    )

    if phase == "unrecognized":
        # Says the phase was NOT recognized and shows the raw literal.
        assert "NO RECONEGUDA" in composed
        assert phase_raw in composed
    else:
        assert composed.startswith(f"INUNCAT: ara en fase {phase.upper()}")
        # The unrecognized wording must not leak into the recognized branch.
        assert "NO RECONEGUDA" not in composed
    # The acronym is always present: it is reached through
    # trigger.event.data.acronym, so it renders instead of an empty string.
    assert "INUNCAT" in composed
    assert DESCRIPTION in composed
    assert COMMUNIQUE_URL in composed


async def test_message_without_description_or_url_is_the_bare_state(
    hass: HomeAssistant,
) -> None:
    """Null description/url collapse to the neutral state line alone."""
    config = _substitute({"notify_target": NOTIFY_INPUT})
    context = _render_context(
        config["variables"],
        started_payload(description=None, communique_url=None),
    )
    fragment = Template(_message_template_of(config), hass).async_render(
        variables=context
    )
    composed = Template(_composed_message_template_of(config), hass).async_render(
        variables={**context, "notify_message": fragment}
    )
    assert composed == "INUNCAT: ara en fase ALERTA"


async def test_message_claims_no_direction(hass: HomeAssistant) -> None:
    """A de-escalation renders exactly like a fresh alerta: neutral state.

    `phase_started` carries no origin (§4.1), so any direction wording would
    be an unhonest inference. The rendered text has none of it, whichever way
    the plan actually moved.
    """
    config = _substitute({"notify_target": NOTIFY_INPUT})
    for phase, phase_raw in (("alerta", "ALERTA"), ("emergencia", "EMERGÈNCIA")):
        context = _render_context(
            config["variables"], started_payload(phase=phase, phase_raw=phase_raw)
        )
        fragment = Template(_message_template_of(config), hass).async_render(
            variables=context
        )
        composed = Template(_composed_message_template_of(config), hass).async_render(
            variables={**context, "notify_message": fragment}
        )
        for forbidden in (
            "pujat",
            "puja",
            "baixat",
            "baixa",
            "escalat",
            "escalada",
            "entrat",
            "transici",
            "origen",
            "abans",
            "des de",
        ):
            assert forbidden not in composed.lower()


# ---------------------------------------------------------------------------
# 3c. Behavioural: live automation + mocked notify service
# ---------------------------------------------------------------------------


async def _install_automation(
    hass: HomeAssistant, *, alias: str, user_inputs: dict[str, Any]
) -> list[Any]:
    """Install the blueprint as a live automation and return captured calls."""

    def _copy_blueprint() -> None:
        blueprint_dir = Path(hass.config.path("blueprints", "automation", "cecat"))
        blueprint_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BLUEPRINT_PATH, blueprint_dir / "plan_notification.yaml")

    await hass.async_add_executor_job(_copy_blueprint)
    calls = async_mock_service(hass, "notify", "send_message")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": alias,
                    "use_blueprint": {
                        "path": "cecat/plan_notification.yaml",
                        "input": user_inputs,
                    },
                }
            ]
        },
    )
    await hass.async_block_till_done()
    return calls


async def test_alerta_notifies_with_neutral_state(
    hass: HomeAssistant,
) -> None:
    """Default inputs: an alerta notification carries the §5.2 message."""
    calls = await _install_automation(
        hass, alias="alerta_default", user_inputs={"notify_target": NOTIFY_INPUT}
    )
    hass.bus.async_fire(EVENT_PHASE_STARTED, started_payload())
    await hass.async_block_till_done()

    assert len(calls) == 1
    data = calls[0].data
    assert data["title"] == "Protecció Civil Catalunya"
    assert data["message"].startswith("INUNCAT: ara en fase ALERTA")
    assert DESCRIPTION in data["message"]
    assert COMMUNIQUE_URL in data["message"]


async def test_prealerta_filtered_by_default(hass: HomeAssistant) -> None:
    """Default min_phase is alerta: a prealerta produces no notification."""
    calls = await _install_automation(
        hass, alias="prealerta_default", user_inputs={"notify_target": NOTIFY_INPUT}
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED, started_payload(phase="prealerta", phase_raw="PREALERTA")
    )
    await hass.async_block_till_done()
    assert calls == []


async def test_min_phase_prealerta_notifies_prealerta(
    hass: HomeAssistant,
) -> None:
    """Opting into prealertas (min_phase=prealerta) notifies them."""
    calls = await _install_automation(
        hass,
        alias="prealerta_optin",
        user_inputs={
            "notify_target": NOTIFY_INPUT,
            "min_phase": "prealerta",
        },
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED, started_payload(phase="prealerta", phase_raw="PREALERTA")
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert "INUNCAT: ara en fase PREALERTA" in calls[0].data["message"]


async def test_min_phase_emergencia_filters_alerta(
    hass: HomeAssistant,
) -> None:
    """min_phase=emergencia: alerta is dropped, emergencia passes."""
    calls = await _install_automation(
        hass,
        alias="only_emergencies",
        user_inputs={
            "notify_target": NOTIFY_INPUT,
            "min_phase": "emergencia",
        },
    )
    hass.bus.async_fire(EVENT_PHASE_STARTED, started_payload())
    await hass.async_block_till_done()
    assert calls == []

    hass.bus.async_fire(
        EVENT_PHASE_STARTED,
        started_payload(phase="emergencia", phase_raw="EMERGÈNCIA"),
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert "INUNCAT: ara en fase EMERGENCIA" in calls[0].data["message"]


@pytest.mark.parametrize("min_phase", MIN_PHASES)
async def test_unrecognized_passes_every_min_phase(
    hass: HomeAssistant, min_phase: str
) -> None:
    """Criterion 15b: unrecognized notifies with any min_phase, saying so."""
    calls = await _install_automation(
        hass,
        alias=f"unrecognized_{min_phase}",
        user_inputs={
            "notify_target": NOTIFY_INPUT,
            "min_phase": min_phase,
        },
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED,
        started_payload(phase="unrecognized", phase_raw="VIGILÀNCIA PERPETUA"),
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    message = calls[0].data["message"]
    assert "NO RECONEGUDA" in message
    assert "VIGILÀNCIA PERPETUA" in message
    assert "INUNCAT" in message


async def test_alerta_to_emergencia_produces_one_notification(
    hass: HomeAssistant,
) -> None:
    """A transition emits ended+started+changed; the blueprint notifies once.

    This is the regression the single-lane rule guards (T12, line 314): the
    coordinator fires THREE events for `alerta -> emergencia`, and listening
    to anything beyond `phase_started` would duplicate the notification.
    """
    calls = await _install_automation(
        hass, alias="single_lane", user_inputs={"notify_target": NOTIFY_INPUT}
    )
    # What the coordinator actually fires for that transition (§4).
    hass.bus.async_fire(
        EVENT_PHASE_ENDED,
        {
            "acronym": "INUNCAT",
            "name": "Inundacions",
            "previous_phase": "alerta",
            "previous_phase_raw": "ALERTA",
            "duration_minutes": 1471,
        },
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED,
        started_payload(phase="emergencia", phase_raw="EMERGÈNCIA"),
    )
    hass.bus.async_fire(
        EVENT_PHASE_CHANGED,
        {
            "acronym": "INUNCAT",
            "name": "Inundacions",
            "previous_phase": "alerta",
            "previous_phase_raw": "ALERTA",
            "phase": "emergencia",
            "phase_raw": "EMERGÈNCIA",
            "escalation": True,
            "activated": True,
            "started_at": "2026-08-05T11:18:09+00:00",
        },
    )
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert "INUNCAT: ara en fase EMERGENCIA" in calls[0].data["message"]


async def test_phase_changed_alone_never_notifies(hass: HomeAssistant) -> None:
    """The blueprint has no trigger on the escalation lane at all."""
    calls = await _install_automation(
        hass, alias="no_changed_lane", user_inputs={"notify_target": NOTIFY_INPUT}
    )
    hass.bus.async_fire(
        EVENT_PHASE_CHANGED,
        {
            "acronym": "INUNCAT",
            "name": "Inundacions",
            "previous_phase": "prealerta",
            "previous_phase_raw": "PREALERTA",
            "phase": "alerta",
            "phase_raw": "ALERTA",
            "escalation": True,
            "activated": True,
            "started_at": "2026-08-05T11:18:09+00:00",
        },
    )
    await hass.async_block_till_done()
    assert calls == []


async def test_empty_plans_means_all(hass: HomeAssistant) -> None:
    """Default plans=[]: an acronym outside the known list still notifies."""
    calls = await _install_automation(
        hass, alias="plans_all", user_inputs={"notify_target": NOTIFY_INPUT}
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED,
        started_payload(
            acronym="PENTA", name="PENTA", description=None, communique_url=None
        ),
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert "PENTA: ara en fase ALERTA" in calls[0].data["message"]


async def test_plans_filter_excludes_unselected_plans(
    hass: HomeAssistant,
) -> None:
    """plans=[INUNCAT]: a PROCICAT phase start produces no notification."""
    calls = await _install_automation(
        hass,
        alias="plans_narrow",
        user_inputs={
            "notify_target": NOTIFY_INPUT,
            "plans": ["INUNCAT"],
        },
    )
    hass.bus.async_fire(
        EVENT_PHASE_STARTED,
        started_payload(acronym="PROCICAT", name="Territorial - Multirisc"),
    )
    await hass.async_block_till_done()
    assert calls == []

    hass.bus.async_fire(EVENT_PHASE_STARTED, started_payload())
    await hass.async_block_till_done()
    assert len(calls) == 1
