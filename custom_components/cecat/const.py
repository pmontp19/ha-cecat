"""Constants for the Protecció Civil Catalunya (cecat) integration.

Endpoint and polling defaults come from docs/01-data-sources.md §1 and §7;
event names follow the rule in docs/03-feature-spec.md §4: the event family
speaks of *phases* that start, change and end, while the binary_sensor is the
only place that speaks of *activation*. The attribution string is mandated
verbatim by the open-data licence (docs/01-data-sources.md §11).
"""

DOMAIN = "cecat"

# ---------------------------------------------------------------------------
# Data source (docs/01-data-sources.md §1, §7)
#
# A single Socrata dataset on the Catalan transparency portal. No API key,
# no quota. `$select=:*,*` pulls the four Socrata metadata columns
# (`:id`, `:version`, `:created_at`, `:updated_at`) alongside every dataset
# column; `:created_at` is the primary source for phase start time
# (docs/04-architecture.md §3).
# ---------------------------------------------------------------------------

BASE_URL = "https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json"
PARAMS = {"$select": ":*,*"}

# ---------------------------------------------------------------------------
# Polling interval (docs/03-feature-spec.md §6, docs/05 §T1)
#
# 5 min default: 1.84 communications/day measured over 623 days with a p05 of
# 14 min between consecutive ones (docs/01-data-sources.md §14), so 5 min
# catches a new phase within one polling cycle on average without pressing the
# source. Conditional caching via `If-Modified-Since` (verified to return 304,
# docs/01-data-sources.md §12 trap 12) keeps the cost of an idle poll at a
# 304 with an empty body.
# ---------------------------------------------------------------------------

DEFAULT_SCAN_INTERVAL_MIN = 5
MIN_SCAN_INTERVAL_MIN = 1
MAX_SCAN_INTERVAL_MIN = 60

# ---------------------------------------------------------------------------
# Bus event types (docs/03-feature-spec.md §4)
#
# Fired on `hass.bus` for `trigger: event` automations. Each phase key
# `(acronym, phase)` that appears emits `phase_started` and each one that
# disappears emits `phase_ended`, always; `phase_changed` is *additive* and
# requires three conditions (docs/04-architecture.md §5). `service_degraded`
# fires once when the source has failed persistently
# (docs/04-architecture.md §10). No event is named `activated`: that word is
# reserved for the binary_sensor, whose truth condition is the opposite for
# prealerta (docs/03-feature-spec.md §4).
# ---------------------------------------------------------------------------

EVENT_PHASE_STARTED = "cecat_plan_phase_started"
EVENT_PHASE_CHANGED = "cecat_plan_phase_changed"
EVENT_PHASE_ENDED = "cecat_plan_phase_ended"
EVENT_SERVICE_DEGRADED = "cecat_service_degraded"

# ---------------------------------------------------------------------------
# Attribution (docs/01-data-sources.md §11)
#
# The open-data licence of the Generalitat mandates citing the source. This
# exact string is the official attribution and appears on every entity via
# `_attr_attribution` (docs/03-feature-spec.md §3.5).
# ---------------------------------------------------------------------------

ATTRIBUTION = (
    "Generalitat de Catalunya. Departament d'Interior i Seguretat Pública. "
    "Direcció General de Protecció Civil"
)
