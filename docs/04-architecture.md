# Arquitectura tècnica: `ha-cecat`

Com es construeix el que descriu [`03-feature-spec.md`](03-feature-spec.md). Les convencions
d'enginyeria són les d'`ha-incendiscat`, verificades ✅ 2026-08-06 contra el checkout local; el
que és específic d'aquesta integració està justificat amb l'evidència de
[`01-data-sources.md`](01-data-sources.md).

Regla que travessa tot el document: **la font és text lliure d'un servei públic que pot canviar
sense avís.** Accés amb `.get()` i valor per defecte, mai indexació directa; cap `raise` per un
literal inesperat.

---

## 1. Layout del repositori

```
ha-cecat/
├── custom_components/cecat/
│   ├── __init__.py            # setup/unload, runtime_data, PLATFORMS
│   ├── api.py                 # client HTTP + caché condicional (~90 línies)
│   ├── binary_sensor.py       # 1 entitat
│   ├── config_flow.py         # 1 pas + options flow
│   ├── const.py               # DOMAIN, events, fases, mapatge d'acrònims
│   ├── coordinator.py         # DataUpdateCoordinator + reconciliació + events
│   ├── diagnostics.py
│   ├── entity.py              # CecatEntity: DeviceInfo, attribution, available
│   ├── models.py              # PlanActivation, CecatState (frozen dataclasses)
│   ├── sensor.py              # 3 entitats
│   ├── manifest.json
│   ├── quality_scale.yaml
│   ├── strings.json
│   ├── icons.json
│   ├── brand/{icon.png,icon@2x.png}
│   └── translations/{ca,es,en}.json
├── blueprints/automation/cecat/plan_notification.yaml
├── docs/                      # 01..05 + captures/
├── tests/
│   ├── conftest.py            # fixtures + FakeClock
│   ├── fixtures/              # còpies de docs/captures/ + sintètics marcats
│   └── test_*.py
├── .github/workflows/{ci.yml,validate.yml,release-please.yml}
├── .github/dependabot.yml
├── AGENTS.md  (+ CLAUDE.md → symlink)
├── CONTRIBUTING.md
├── hacs.json
├── pyproject.toml
├── requirements_dev.txt
├── release-please-config.json
└── .release-please-manifest.json
```

Un mòdul menys que `ha-incendiscat`: no hi ha `geo.py` (cap coordenada) ni un segon client (una
sola font).

---

## 2. `manifest.json`

```jsonc
{
  "domain": "cecat",
  "name": "Protecció Civil Catalunya",
  "codeowners": ["@pmontp19"],
  "config_flow": true,
  "documentation": "https://github.com/pmontp19/ha-cecat",
  "integration_type": "service",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/pmontp19/ha-cecat/issues",
  "requirements": [],
  "single_config_entry": true,
  "version": "0.0.0"     // ← només release-please el toca
}
```

`requirements: []` com els dos germans i com `dpc`. El client són ~90 línies sobre
`aiohttp_client.async_get_clientsession(hass)`: un `GET`, un `json.loads`, vuit camps
([`02`](02-existing-integrations.md) §2).

---

## 3. Client (`api.py`)

### Responsabilitats

1. Un `GET` a l'endpoint amb `$select=:*,*`.
2. Caché condicional amb `If-Modified-Since`.
3. Validar que el cos és una **llista** i res més.
4. Retornar `(rows, last_modified, not_modified)`.

**No** normalitza, **no** parseja dates, **no** decideix fases. Això és de `models.py`.

### Endpoint i paràmetres

```python
BASE_URL = "https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json"
PARAMS = {"$select": ":*,*"}
```

`$select=:*,*` afegeix `:id`, `:version`, `:created_at` i `:updated_at`. `:created_at` és la
font primària de l'inici de fase ([`01`](01-data-sources.md) §7.2): és ISO-8601 en UTC i estalvia
parsejar `DD/MM/YYYY HH:MM` amb el fus endevinat.

Si algun dia `$select` fallés, el fallback és l'URL pelada i `fasedatahora`. El model ja
distingeix les dues fonts amb `started_at_source`, per tant la degradació és observable.

### Caché condicional

```python
headers = {}
if self._last_modified:
    headers["If-Modified-Since"] = self._last_modified
# ...
if response.status == HTTPStatus.NOT_MODIFIED:      # 304
    return CecatResponse(rows=None, last_modified=self._last_modified, not_modified=True)
```

Mesurat ✅ ([`01`](01-data-sources.md) §1): `If-Modified-Since` retorna **304 amb cos buit**;
`If-None-Match` retorna **200** amb el cos sencer perquè l'`ETag` arriba trencat (sufix `--gzip`
duplicat). **No es fa servir l'`ETag`.**

La font publica 1,84 comunicats/dia, i el `rowsUpdatedAt` del dataset coincideix al segon amb el
`last-modified` del PDF ✅, per tant es pot esperar de l'ordre d'una actualització cada ~13 hores
de mitjana. Amb un sondeig de 5 min, això vol dir que **la gran majoria de cicles són un 304**.
És el que fa que 5 minuts sigui poc agressiu contra un servei públic.

### Validació i errors

| Situació | Excepció | Tractament al coordinator |
| --- | --- | --- |
| Timeout, error de connexió | `CecatConnectionError` | `UpdateFailed`, conserva l'estat |
| HTTP 5xx | `CecatConnectionError` | idem |
| HTTP 4xx | `CecatConnectionError` | idem. No hi ha auth: un 4xx és canvi de contracte |
| Cos no JSON | `CecatFormatError` | `UpdateFailed`, conserva l'estat |
| JSON que **no** és una llista | `CecatFormatError` | idem |
| `[]` | **cap** | Estat vàlid: zero plans |
| Element de la llista que no és un `dict` | **cap** | Es descarta amb `debug`, la resta es processa |

`[]` no és mai un error. És l'estat de normalitat i és el més probable en un instant qualsevol
([`01`](01-data-sources.md) §4, trap 2).

### Timeout i mida

`async_timeout.timeout(15)`. El payload real és de ~400 bytes amb una fila; el pitjor cas
realista amb un grapat de plans no arriba a 4 KB. No hi ha paginació: `count(*)` ha estat 0, 1 o
2 en totes les observacions.

---

## 4. Models (`models.py`)

`frozen dataclasses`, sense dependències.

```python
class Phase(StrEnum):
    NONE = "none"
    PREALERTA = "prealerta"
    ALERTA = "alerta"
    EMERGENCIA = "emergencia"
    UNKNOWN = "unknown"

PHASE_ORDER = (Phase.NONE, Phase.PREALERTA, Phase.ALERTA, Phase.EMERGENCIA)
```

`UNKNOWN` **queda fora de `PHASE_ORDER`** deliberadament: no se sap on col·locar un literal
desconegut a l'escala de severitat, i inventar-ho seria pitjor que no ordenar-lo. Regla:
`max_phase` és `UNKNOWN` només si **cap** fila té una fase reconeguda; si n'hi ha alguna, mana la
màxima reconeguda i el literal desconegut queda visible a `phase_raw` i als diagnostics.

### Normalització de la fase

```python
def normalise_phase(raw: str | None) -> Phase:
    if not raw:
        return Phase.UNKNOWN
    key = _strip_diacritics(raw).strip().casefold()   # "EMERGÈNCIA" → "emergencia"
    return _PHASE_BY_KEY.get(key, Phase.UNKNOWN)
```

`casefold()` **i** eliminació de diacrítics amb `unicodedata.normalize("NFKD", …)`. Motiu:
`EMERGÈNCIA` està documentada amb accent obert però **mai s'ha observat en viu**
([`01`](01-data-sources.md) trap 14); una variació d'accent o de codificació no pot fer perdre
la fase més greu del sistema.

### Inici de fase

```python
def resolve_started_at(row: dict) -> tuple[datetime | None, str | None]:
    created = row.get(":created_at")
    if created:
        parsed = _parse_iso(created)          # ja és UTC, acaba amb "Z"
        if parsed:
            return parsed, "created_at"
    parsed = _parse_local(row.get("fasedatahora"))
    return (parsed, "fasedatahora") if parsed else (None, None)


def _parse_local(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        naive = datetime.strptime(raw.strip(), "%d/%m/%Y %H:%M")
    except (ValueError, TypeError):
        return None
    return naive.replace(tzinfo=ZoneInfo("Europe/Madrid")).astimezone(UTC)
```

`ZoneInfo("Europe/Madrid")` no és una suposició: està demostrat amb 1.146 punts de dades
([`01`](01-data-sources.md) §8). Interpretant els segells dels comunicats com a hora local, el
99,5% cauen dins dels 30 min anteriors a la pujada del fitxer i **cap** és posterior; si fossin
UTC, tots els d'estiu tindrien 120 minuts de retard negatiu. Ho corrobora la fila viva
(`:created_at` = `fasedatahora` + 2 h exactes) i el peu del comunicat oficial.

### Camps opcionals

```python
def _url(value: object) -> str | None:
    return value.get("url") if isinstance(value, dict) else None

def _text(value: object) -> str | None:
    return stripped or None if isinstance(value, str) and (stripped := value.strip()) else None
```

`plaicona` i `comunicatpdf` són **objectes** `{"url": …}` que poden faltar sencers
([`01`](01-data-sources.md) trap 6). `descripcio` porta espais dobles, sufix `" - "` i salts de
línia literals (trap 10): només `.strip()`, res més. El sufix `" - "` **no** es neteja: és
contingut de la font i tocar-lo seria "desnaturalitzar la informació", cosa que la llicència
prohibeix explícitament ([`01`](01-data-sources.md) §11).

`communique_url` es tracta com a **cadena opaca**: no es valida, no es normalitza, no es passa
per cap client HTTP. Pot contenir `ó`, `à`, `é` i `'` sense codificar (trap 7).

### Nom del pla

```python
PLAN_NAMES: dict[str, str] = {
    "INUNCAT": "Inundacions",
    "VENTCAT": "Ventades",
    ...
}

def plan_name(acronym: str) -> str:
    return PLAN_NAMES.get(acronym.upper(), acronym)
```

Mapatge propi, **mai `planom`**: és idèntic a `plaacronim` a 5/5 captures, contra la seva pròpia
documentació ([`01`](01-data-sources.md) trap 4). El mapatge surt del registre oficial
`xqqe-tgav` ([`captures/registre-plans-generalitat-2026-08-06.json`](captures/registre-plans-generalitat-2026-08-06.json)).
El fallback a l'acrònim cru **no és degradació**: és la manera de sobreviure a `PENTA` i a
`NOPLA`, que no són a cap registre (trap 5).

---

## 5. Coordinator (`coordinator.py`)

`DataUpdateCoordinator[CecatState]`, interval de `entry.options["scan_interval"]`, per defecte 5
minuts.

### Estat que manté entre cicles

| Camp | Per a què |
| --- | --- |
| `_previous: dict[str, PlanActivation]` | Indexat per `acronym`. Base de la reconciliació i dels events |
| `_last_modified: str \| None` | Per al `If-Modified-Since` del cicle següent |
| `_unknown_phases: set[str]`, `_unknown_acronyms: set[str]` | Per emetre el `warning` **una sola vegada** per literal, i per als diagnostics |
| `_consecutive_failures: int` | Llindar de `cecat_service_degraded` |
| `_degraded: bool` | Per emetre l'event de recuperació una sola vegada |

### Cicle

```
1. api.fetch()
2. si 304  → retorna self.data intacta. Cap event. FI.
3. si error → _consecutive_failures += 1; potser emet degraded; raise UpdateFailed.
              Cap event. L'estat anterior es conserva.
4. normalitza les files → dict[acronym, PlanActivation]
5. _emit_events(previous=self._previous, current=current)
6. self._previous = current; _consecutive_failures = 0; potser emet recuperació
7. retorna CecatState(plans=current, last_modified=…)
```

**El pas 3 és el més important de tota la integració.** Un cicle fallit **no** pot generar
`cecat_plan_deactivated`: si ho fes, cada glitch de xarxa notificaria a l'usuari que
l'emergència s'ha acabat. Només un `[]` **vàlid** és una desactivació
([`03`](03-feature-spec.md) §4.3, criteri 14).

Si l'últim cicle amb èxit té més de `max(6 × interval, 1 h)`, les entitats passen a
`available = False`. Amb `[]` com a estat normal, una font congelada és indistingible d'una font
sana: sense aquest guard, l'usuari veuria `max_phase = none` per sempre i creuria que no hi ha
cap emergència. `sensor.cecat_last_updated` és el senyal complementari
([`03`](03-feature-spec.md) §3.4).

### Detecció d'events (`_emit_events`)

```python
for acronym, plan in current.items():
    old = previous.get(acronym)
    if old is None:
        if plan.phase is not Phase.NONE:
            fire(EVENT_PLAN_ACTIVATED, plan)
    elif old.phase != plan.phase:
        fire(EVENT_PHASE_CHANGE, plan, previous_phase=old.phase,
             escalation=_severity(plan.phase) > _severity(old.phase))

for acronym, old in previous.items():
    if acronym not in current:
        fire(EVENT_PLAN_DEACTIVATED, old, duration_minutes=_duration(old))
```

Tres propietats que es deriven directament de les traps:

1. **La clau és `(acronym, phase)`, mai `:id` ni el hash de la fila.** `comunicatpdf` canvia
   diverses vegades dins de la mateixa fase (l'incident `I-125912` en va tenir 5) i `:id` canvia
   quan el publicador substitueix la fila en un canvi de fase ([`01`](01-data-sources.md)
   trap 11, §7.2). Qualsevol altra clau duplica events o els perd. És l'error exacte que comet un
   consumidor de tercers d'aquesta font ([`02`](02-existing-integrations.md) §6.1).
2. **Un canvi de fase emet `phase_change`, no `activated` + `deactivated`.** L'`acronym` és el
   mateix i l'episodi és continu, com demostra el rastre de `I-125912`.
3. **`deactivated` és per absència.** El CECAT gairebé no publica tancaments: 1 sol
   `DESACTIVACIO` en 623 dies ([`01`](01-data-sources.md) §7.4). Mateix patró `_prune_vanished`
   que `ha-incendiscat` va necessitar per a la vista ArcGIS.

### Literals desconeguts

```python
if plan.phase is Phase.UNKNOWN and plan.phase_raw not in self._unknown_phases:
    self._unknown_phases.add(plan.phase_raw)
    LOGGER.warning("Fase de pla no reconeguda: %r (pla %s)", plan.phase_raw, acronym)
```

Un `warning` per literal i prou. Un `warning` per cicle amb un sondeig de 5 min ompliria el log
amb 288 línies al dia.

---

## 6. Entitats

### Patró comú (`entity.py`)

```python
class CecatEntity(CoordinatorEntity[CecatCoordinator]):
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name="Protecció Civil Catalunya",
            manufacturer="Generalitat de Catalunya",
            model="CECAT, Direcció General de Protecció Civil",
            configuration_url="https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf",
        )
```

`unique_id` amb `entry_id` de prefix tot i `single_config_entry: true`: costa zero i sobreviu a
un futur canvi d'àmbit.

### Les quatre entitats

| Fitxer | Entitat | Notes d'implementació |
| --- | --- | --- |
| `sensor.py` | `max_phase` | `SensorDeviceClass.ENUM` amb `options` incloent-hi `"unknown"`. Icona fixa `mdi:shield-alert-outline` via `icons.json` |
| `sensor.py` | `active_plans` | `state_class = MEASUREMENT`. L'atribut `plans` es serialitza des dels `dataclasses` amb `asdict` i ordre estable per `acronym` |
| `sensor.py` | `last_updated` | `SensorDeviceClass.TIMESTAMP`, `entity_category = DIAGNOSTIC`. Parseig del `Last-Modified` amb `email.utils.parsedate_to_datetime` |
| `binary_sensor.py` | `plan_activated` | `BinarySensorDeviceClass.SAFETY`. `is_on` = qualsevol fila amb `activated` |

Cap entitat retorna `None` com a estat quan la resposta és `[]`: són `none`, `0` i `off`
([`03`](03-feature-spec.md) criteri 1). `unavailable` queda reservat al guard de dades velles.

L'atribut `plans` s'ordena per `acronym` perquè un canvi d'ordre a la resposta no ha de produir
un canvi d'atribut espuri. El recorregut de la font no garanteix cap ordre: la captura de dos
plans és fins i tot una reconstrucció de dues consultes separades
([`01`](01-data-sources.md) §13).

---

## 7. Config flow (`config_flow.py`)

```
async_step_user
├── mostra el formulari amb scan_interval (per defecte 5)
├── prova: api.fetch()
│   ├── llista (inclosa buida) → async_create_entry
│   └── error o no-llista      → errors["base"] = "cannot_connect"
└── async_set_unique_id(DOMAIN) + _abort_if_unique_id_configured()
```

`OptionsFlow` amb el mateix camp; en desar, `coordinator.update_interval` es reprograma sense
recarregar l'entrada.

El detall que importa: **la prova ha d'acceptar `[]`**. La resposta buida és el cas més probable
en un instant qualsevol ([`01`](01-data-sources.md) §4). Un flow que exigís almenys una fila
fallaria la majoria dels dies i semblaria un error de connexió.

---

## 8. Resiliència

| Fallada | Comportament |
| --- | --- |
| Timeout / xarxa / 5xx | `UpdateFailed`. Entitats conserven el valor. `_consecutive_failures += 1` |
| 4xx | Igual. No hi ha auth, per tant és canvi de contracte, no credencials |
| JSON no vàlid o no-llista | Igual, amb `LOGGER.error` una vegada per canvi de forma |
| Element no-`dict` dins la llista | Es descarta amb `debug`; la resta es processa |
| Camp que falta o és `null` | `.get()` amb valor per defecte. Mai excepció |
| `plafase` desconeguda | `Phase.UNKNOWN` + `warning` una vegada per literal |
| `plaacronim` desconegut | Fila ingerida, `name` = acrònim, `warning` una vegada |
| 3 cicles fallits consecutius | `cecat_service_degraded`; un altre amb `recovered: true` al recuperar-se |
| Dades més velles que `max(6 × interval, 1 h)` | `available = False` a totes les entitats |
| HTTP 304 | Estat intacte, cap event, `available` es manté |

**Rate limit i cortesia.** Cap límit documentat i cap capçalera `X-RateLimit-*` observada ✅. Amb
tot: `scan_interval` mínim d'1 minut per contracte, per defecte 5, i `If-Modified-Since` a cada
petició, cosa que fa que el cas normal sigui un 304 amb cos buit. Un sol `GET` per cicle, sense
paral·lelisme. És un servei d'una administració pública i el disseny ho ha de reflectir.

**El contenidor Azure de comunicats no es consumeix mai des de la integració.** Ha estat
decisiu per a la recerca ([`01`](01-data-sources.md) §7.3) però no és una API documentada;
dependre'n en runtime seria construir sobre un detall d'implementació que ningú ens ha promès.

---

## 9. Tests

`pytest-homeassistant-custom-component` + `aioresponses`. **Zero xarxa real.**

### Fixtures

`tests/fixtures/` són còpies de [`docs/captures/`](captures/), és a dir **respostes reals
capturades**, no inventades (regla d'`AGENTS.md` heretada d'`ha-incendiscat`):

| Fixture | Origen | Cobreix |
| --- | --- | --- |
| `alerta_2026_08_06.json` | ✅ endpoint en viu | Cas base, `:created_at`, `plaactivat: SI` |
| `prealerta_2024_12_02.json` | 🗄️ Wayback | `plaactivat: NO`, `descripcio` amb `\n` |
| `buit_2026_06_16.json` | 🗄️ Wayback | `[]` |
| `dos_plans_2026_01_19.json` | 🗄️ Wayback (**reconstrucció**) | Múltiples files |
| `pdf_url_accents_2026_07_03.json` | 🗄️ Wayback | URL amb `ó`, `à`, `'` |
| `emergencia_SYNTHETIC.json` | **sintètic** | `EMERGÈNCIA`, mai observada |
| `fase_desconeguda_SYNTHETIC.json` | **sintètic** | Vàlvula `unknown` |
| `camps_absents_SYNTHETIC.json` | **sintètic** | `comunicatpdf`/`plaicona`/`descripcio` absents |

Els sintètics porten `_SYNTHETIC` al nom i una capçalera `_comment` que ho diu, perquè ningú els
confongui amb evidència. És la distinció que fa creïbles els documents dels germans.

### Fitxers de test

| Fitxer | Què cobreix |
| --- | --- |
| `test_api.py` | 200, 304, timeout, 4xx, 5xx, cos no-JSON, cos no-llista, `If-Modified-Since` enviat |
| `test_models.py` | Normalització de fase amb i sense diacrítics, `resolve_started_at` amb les dues fonts i cap, camps absents, `descripcio` bruta |
| `test_coordinator.py` | Reconciliació, `available` per dades velles, `warning` una sola vegada, 304 conserva estat |
| `test_events.py` | Els 4 events, el no-event del PDF canviat, el no-event del cicle fallit, `escalation` |
| `test_sensor.py`, `test_binary_sensor.py` | Estats i atributs contra cada fixture |
| `test_config_flow.py` | `[]` crea l'entrada, `cannot_connect`, options flow, `single_config_entry` |
| `test_diagnostics.py` | Forma de l'export |
| `test_resilience.py` | Les files de la taula de §8 |
| `test_translations.py` | Cada `translation_key` present als tres idiomes |
| `test_blueprint.py` | El YAML del blueprint valida |

Lògica dependent del rellotge amb la fixture `clock` (`FakeClock`), mai `sleep()` real ni
`freezegun`, igual que `ha-incendiscat`.

### Cobertura

**≥ 95%** (`--cov-fail-under=95`), la mateixa gate que la CI. Amb ~600 línies de codi és una
fita còmoda.

---

## 10. CI / CD

Tres workflows, còpia dels d'`ha-incendiscat` amb els SHA pinats:

| Workflow | Contingut |
| --- | --- |
| `ci.yml` | `uv venv --python 3.13`, `ruff check .`, `ruff format --check .`, `pytest --cov=custom_components/cecat --cov-fail-under=95` |
| `validate.yml` | `hassfest` + `hacs/action` amb `category: integration`. Push, PR, cron diari i `workflow_dispatch` |
| `release-please.yml` | Conventional Commits → versió, `CHANGELOG.md` i `manifest.json`. **Mai editar la versió a mà** |

`requirements_dev.txt` amb versions fixades (`pytest`, `pytest-cov`,
`pytest-homeassistant-custom-component`, `homeassistant`, `ruff`, `aioresponses`) i `dependabot`
per mantenir-les. `pyproject.toml` amb el mateix conjunt de regles de `ruff` que el germà
(`E,W,F,I,UP,B,SIM,RUF,ASYNC,PL`, `line-length = 88`, `target-version = "py313"`).

---

## 11. Decisions arquitecturals

| # | Decisió | Alternativa descartada | Motiu |
| :---: | --- | --- | --- |
| AD-1 | `single_config_entry: true` | Multi-entrada per comarca | No hi ha eix territorial per activació: la font declara "Sense informació geogràfica" i cap dataset del portal en té ([`01`](01-data-sources.md) §5) |
| AD-2 | `requirements: []` | Un paquet propi a PyPI | El client són ~90 línies. Mateixa política que `ha-incendiscat`, `ha-avisoscat` i `dpc` |
| AD-3 | `$select=:*,*` i `:created_at` com a font primària de l'inici de fase | Només `fasedatahora` | ISO-8601 en UTC contra `DD/MM/YYYY HH:MM` amb el fus implícit. `started_at_source` fa la degradació observable ([`01`](01-data-sources.md) §7.2) |
| AD-4 | `If-Modified-Since`, mai `ETag` | `ETag` condicional | Mesurat: l'`ETag` arriba amb el sufix `--gzip` duplicat i retorna 200; `If-Modified-Since` retorna 304 ([`01`](01-data-sources.md) §1) |
| AD-5 | Identitat de l'episodi = `(acronym, phase)` | `:id` de Socrata, o hash de la fila | `comunicatpdf` canvia dins de la mateixa fase i `:id` canvia en un canvi de fase ([`01`](01-data-sources.md) trap 11) |
| AD-6 | `plafase` mana, `plaactivat` és derivat | Filtrar per `plaactivat='SI'` | `plaactivat: "NO"` és la prealerta, el 51,4% dels comunicats. Filtrar amaga mitja font ([`01`](01-data-sources.md) trap 1) |
| AD-7 | Un atribut `plans` en lloc de N entitats per pla | 13-18 binary sensors | `plaacronim` no és un conjunt tancat (`PENTA`, `NOPLA`). Una llista blanca quedaria obsoleta sense avís ([`03`](03-feature-spec.md) §7) |
| AD-8 | `Phase.UNKNOWN` fora de `PHASE_ORDER` | Col·locar-la a dalt o a baix de l'escala | No se sap on va un literal desconegut. Inventar-ho és pitjor que no ordenar-lo |
| AD-9 | Normalització de fase sense diacrítics | Comparació exacta amb `"EMERGÈNCIA"` | La fase més greu mai s'ha observat en viu; un accent no pot fer-la perdre ([`01`](01-data-sources.md) trap 14) |
| AD-10 | Mapatge propi acrònim → nom, amb fallback a l'acrònim | `planom` | `planom` és igual a `plaacronim` a 5/5 captures ([`01`](01-data-sources.md) trap 4) |
| AD-11 | Icones `mdi:` fixes, `plaicona` només com a atribut | `plaicona` com a `entity_picture` | La llicència restringeix l'ús dels símbols oficials i `ico_VENTCAT.png` dona 404 ([`01`](01-data-sources.md) §11.3, §6.3) |
| AD-12 | Guard de dades velles (`available = False`) | Confiar només en `UpdateFailed` | Amb `[]` com a estat normal, una font congelada sembla una font sana |
| AD-13 | Events al bus, cap acció de servei | `get_details` com `nina` | Els germans ja tenen el patró i el blueprint |
| AD-14 | El contenidor Azure de comunicats no es consumeix en runtime | Fer-lo servir per a l'històric | No és una API documentada ([`01`](01-data-sources.md) §14) |

---

## 12. Roadmap post-v1

Res d'això entra a la v1, i tot depèn d'evidència que avui no tenim.

| Idea | Bloqueig actual |
| --- | --- |
| Nom llarg i subpla del PROCICAT correctes | Cal observar la grafia real de `plaacronim` per als PA del PROCICAT: hi ha 4 grafies a 4 fonts i cap observada al feed ([`01`](01-data-sources.md) §14, obert 1) |
| Sensor de durada de l'episodi en curs | Cal confirmar si un canvi de fase substitueix la fila o l'edita; avui és una sola transició observada ([`01`](01-data-sources.md) §14, obert 3) |
| Filtre per municipi | Caldria territori per activació. No existeix ([`01`](01-data-sources.md) §5) |
| Històric d'activacions | La font no en té i els datasets estadístics del portal estan aturats des del 2023-08-14 |
| Extreure comarques del PDF | Dues capes d'heurística sobre text lliure extern, i sovint són zones del SMC i no comarques |
