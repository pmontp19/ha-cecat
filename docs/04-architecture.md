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

### Severitat: `_severity`, i per què no pot llançar mai (AD-8)

```python
def _severity(phase: Phase) -> int:
    """Posició a l'escala de severitat. Mai llança: fora de PHASE_ORDER dona -1."""
    return PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1


def _is_escalation(new: Phase, old: Phase) -> bool:
    if new not in PHASE_ORDER or old not in PHASE_ORDER:
        return False          # cap costat comparable: es reporta, no s'escala
    return _severity(new) > _severity(old)
```

`PHASE_ORDER.index(phase)` **pelat llançaria `ValueError` amb `Phase.UNKNOWN`**, i el camí que hi
arriba no és hipotètic: si l'estat previ és `{(INUNCAT, ALERTA)}` i el cicle següent el
publicador escriu un `plafase` irreconeixible, `normalise_phase` dona `UNKNOWN`, hi ha
exactament una alta i una baixa per a `INUNCAT`, i la regla d'aparellament de §5 entra a la
branca de `phase_changed` i compara les dues severitats. Una excepció allà avortaria **tot** el
cicle d'actualització, que és exactament el contrari del criteri 6 de
[`03`](03-feature-spec.md) ("cap excepció") i de la fila de `plafase` desconeguda de §8. El
conjunt de plans no és tancat ([`01`](01-data-sources.md) §3.2, trap 5): un literal desconegut
és **esperable**, no excepcional, i ha de degradar de manera segura i sorollosa, mai tombar el
coordinator.

Dues regles separades, i totes dues calen:

1. **`_severity` mai llança.** El sentinel `-1` queda per sota de qualsevol fase real, amb el
   mateix estil de guard que ja fa servir `resolve_activated`.
2. **`escalation` és `false` si qualsevol dels dos costats no és a `PHASE_ORDER`.** El sentinel
   sol no n'hi hauria prou: `_severity(ALERTA) > _severity(UNKNOWN)` seria `2 > -1`, cert, i
   afirmaria una escalada en sortir d'un literal desconegut. Una transició cap a `UNKNOWN` o des
   d'`UNKNOWN` **es reporta**, però no es qualifica mai d'escalada.

Això no posa `UNKNOWN` a `PHASE_ORDER` i per tant no toca AD-8: li dona una posició definida i
no comparable, que és el que AD-8 volia dir.

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

### Normalització de `plaactivat`

```python
ACTIVAT_ABSENT = "<absent>"   # sentinel: el camp no venia a la fila

def resolve_activated(raw: str | None, phase: Phase) -> tuple[bool, str | None]:
    """Retorna (activated, literal_a_registrar).

    El segon element és None quan el literal s'ha reconegut i no cal cap warning.
    """
    if raw is not None:
        key = _strip_diacritics(raw).strip().casefold()   # " SI " → "si", "Si" → "si"
        if key == "no":
            return False, None
        if key == "si":
            return True, None
    # Absent, buit o irreconeixible: mana la fase (AD-6).
    derived = _severity(phase) >= _severity(Phase.ALERTA)
    return derived, ACTIVAT_ABSENT if raw is None else raw
```

Mateixa tolerància que `normalise_phase`, i pel mateix motiu. `binary_sensor.proteccio_civil_catalunya_pla_activat`
és un sensor `SAFETY`: que es quedi a `off` durant una emergència real és el pitjor error
possible de la integració, i `plaactivat == "SI"` el fa possible perquè la descripció oficial
escriu el domini com a "(Si/No)" mentre les dades donen `SI`/`NO`, i la fase `EMERGÈNCIA` **mai
s'ha observat** ([`01`](01-data-sources.md) §3.3, traps 1 i 14).

Tres propietats que cal preservar:

1. **`False` només amb el literal `no`.** Qualsevol altra cosa no pot llegir-se com a "no passa
   res".
2. **El fallback és la fase, no un `True` incondicional.** És literalment el que diu AD-6:
   `plafase` mana, `plaactivat` és derivat. Una prealerta amb un `plaactivat` corrupte segueix
   donant `off`, que és correcte.
3. **`Phase.UNKNOWN` queda fora de `PHASE_ORDER`** (AD-8), per tant `_severity` hi dona `-1` i el
   derivat és `False`. Fase desconeguda **i** `plaactivat` desconegut és l'únic cas sense cap
   senyal utilitzable; els dos literals van als diagnostics.

**El camp absent no pot ser silenciós.** Que `plaactivat` desaparegui de la resposta és un canvi
d'esquema sobre el camp que governa un sensor `SAFETY`: la integració passaria a derivar
l'activació de la fase sense que ningú se n'assabentés. Per això l'absència no retorna `None`
sinó el sentinel `ACTIVAT_ABSENT`, que viatja pel mateix camí que qualsevol altre literal
irreconeixible: entra a `_unknown_activated`, emet el `warning` **una sola vegada** i surt als
diagnostics.

Resum del contracte del segon element, que és el que el coordinator mira:

| `plaactivat` a la fila | `activated` | Segon element |
| --- | --- | --- |
| `SI`, `si`, ` SI `, `Si` | `True` | `None`, cap `warning` |
| `NO`, `no`, ` No ` | `False` | `None`, cap `warning` |
| Qualsevol altre literal (`true`, `Activat`, `""`) | Derivat de la fase | El literal cru, `warning` una vegada |
| **Camp absent** | Derivat de la fase | `"<absent>"`, `warning` una vegada |

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

Mapatge propi, **mai `planom`**: és idèntic a `plaacronim` a 5/5 files observades, contra la seva pròpia
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
| `_previous: dict[tuple[str, Phase], PlanActivation]` | Indexat per **`(acronym, phase)`**, la identitat que declara AD-5. Base de la reconciliació i dels events |
| `_last_modified: str \| None` | Per al `If-Modified-Since` del cicle següent |
| `_unknown_phases: set[str]`, `_unknown_acronyms: set[str]`, `_unknown_activated: set[str]` | Per emetre el `warning` **una sola vegada** per literal, i per als diagnostics |
| `_consecutive_failures: int` | Llindar de `cecat_service_degraded` |
| `_degraded: bool` | Per emetre l'event de recuperació una sola vegada |

**Per què la clau és la parella i no l'acrònim sol.** Als 267 comunicats del PROCICAT el token
sempre és `PROCICAT` pelat, mentre el registre hi té quatre plans d'actuació distints: la
hipòtesi de [`01`](01-data-sources.md) §3.2 nota 2 és que tots reporten `plaacronim = PROCICAT`
i només es distingeixen per `plaicona` i `descripcio`. Un `dict[str, …]` col·lapsaria dues files
simultànies de PROCICAT en una: el recompte diria 1 en lloc de 2, la fila perduda no dispararia
mai el seu event, i com que la font **no garanteix cap ordre de files** (§6), quina de les dues
sobreviu podria alternar entre cicles i emetre un canvi de fase espuri a cada sondeig. Indexar
per `(acronym, phase)` fa desaparèixer les tres coses alhora i és el que AD-5 ja deia.

Queden **dues limitacions acceptades**, totes dues inherents a la identitat declarada i no
resolubles amb el que la font publica:

1. **Dues files amb el mateix acrònim i la mateixa fase col·lapsen en una entrada.** Sota la
   identitat declarada són indistingibles i no hi ha res a la font que permeti separar-les.
2. **L'aparellament 1-a-1 no sap si les dues claus són el mateix pla.** Sota la premissa de
   [`01`](01-data-sources.md) §3.2 nota 2, on cada pla d'actuació del PROCICAT reporta
   `PROCICAT` pelat a `plaacronim`, un cicle en què el pla d'actuació d'onada de calor deixa de
   seguir-se mentre el pla d'actuació de ferrocarril apareix en `ALERTA` produeix exactament una
   alta i una baixa per a `PROCICAT`, i per tant la regla d'aparellament emet un sol
   `cecat_plan_phase_changed` amb `escalation: true`, afirmant que un pla ha escalat quan de fet
   un s'ha acabat i n'ha començat un altre de diferent. El blueprint escolta precisament
   `escalation: true` ([`03`](03-feature-spec.md) §5), de manera que l'usuari rep una
   notificació d'escalada per un episodi que no ha escalat.

La segona **no** està coberta pel paràgraf d'ambigüitat de més avall, que només parla del cas de
més d'una alta o més d'una baixa: aquest és estrictament 1-a-1 i entra a la branca
d'aparellament.

Dues sortides considerades i rebutjades, perquè ningú les reobri:

| Alternativa | Per què no |
| --- | --- |
| Corroborar la identitat amb `plaicona` o `descripcio` | Recolzaria una porta de correcció sobre dos camps que aquesta mateixa recerca ha trobat poc fiables: `plaicona` dona 404 per a VENTCAT i PLASEQTA ([`01`](01-data-sources.md) §6.3) i `descripcio` és text lliure sense validar (§9). Pitjor que una limitació honesta |
| Suprimir `phase_changed` per als acrònims que poden tenir més d'un pla | Descarta senyal real precisament a l'únic acrònim que en pot tenir diversos alhora |

Es tanca sola el dia que s'observi la grafia real de `plaacronim` per als PA del PROCICAT, que
és l'obert 1 del veredicte ([`01`](01-data-sources.md) §14): si resulta que porten acrònims
distints, la confusió desapareix sense tocar res.

### Cicle

```
1. api.fetch()
2. si 304  → retorna self.data intacta. Cap event. FI.
3. si error → _consecutive_failures += 1; potser emet degraded; raise UpdateFailed.
              Cap event. L'estat anterior es conserva.
4. normalitza les files → dict[(acronym, phase), PlanActivation]
5. _emit_events(previous=self._previous, current=current)
6. self._previous = current; _consecutive_failures = 0; potser emet recuperació
7. retorna CecatState(plans=current, last_modified=…)
```

**El pas 3 és el més important de tota la integració.** Un cicle fallit **no** pot generar
`cecat_plan_phase_ended`: si ho fes, cada glitch de xarxa notificaria a l'usuari que
l'emergència s'ha acabat. Només un `[]` **vàlid** és una desactivació
([`03`](03-feature-spec.md) §4.3, criteri 14).

Si l'últim cicle amb èxit té més de `max(6 × interval, 1 h)`, les entitats passen a
`available = False`. Amb `[]` com a estat normal, una font congelada és indistingible d'una font
sana: sense aquest guard, l'usuari veuria `max_phase = none` per sempre i creuria que no hi ha
cap emergència. `sensor.proteccio_civil_catalunya_darrera_actualitzacio` és el senyal complementari
([`03`](03-feature-spec.md) §3.4).

### Detecció d'events (`_emit_events`)

Amb la clau composta, la detecció és una diferència de conjunts de claus més **una sola regla
d'aparellament**, i aquesta regla és tota la que hi ha:

```python
added   = current.keys() - previous.keys()      # candidats a "started"
removed = previous.keys() - current.keys()      # candidats a "ended"

for acronym in {a for a, _ in added | removed}:
    adds    = [k for k in added   if k[0] == acronym]
    removes = [k for k in removed if k[0] == acronym]

    if len(adds) == 1 and len(removes) == 1:
        # Exactament una alta i una baixa del mateix acrònim: és un canvi de fase.
        # S'emet un sol event i el parell started/ended queda suprimit.
        new, old = current[adds[0]], previous[removes[0]]
        fire(EVENT_PLAN_PHASE_CHANGED, new,
             previous_phase=old.phase, previous_phase_raw=old.phase_raw,
             escalation=_is_escalation(new.phase, old.phase))
        continue

    # Qualsevol altra combinació: no s'endevina res.
    for key in adds:
        if current[key].phase is not Phase.NONE:
            fire(EVENT_PLAN_PHASE_STARTED, current[key])
    for key in removes:
        fire(EVENT_PLAN_PHASE_ENDED, previous[key], duration_minutes=_duration(previous[key]))
```

**Quan un acrònim té més d'una alta o més d'una baixa al mateix cicle, la correspondència és
ambigua i no s'intenta resoldre.** Si dues files de PROCICAT desapareixen i n'apareix una, no hi
ha cap manera honesta de dir quina de les dues "ha canviat de fase" i quina "s'ha acabat":
s'emeten els `started` i els `ended` plans i s'acaba. Això està escrit aquí explícitament perquè
ningú no hi dedueixi una heurística d'aparellament per severitat, per ordre o per `started_at`.
Un event de més és soroll; un aparellament inventat és una mentida sobre què ha passat.

Quatre propietats que es deriven directament de les traps:

1. **La clau és `(acronym, phase)`, mai `:id` ni el hash de la fila**, i és la mateixa clau que
   indexa `_previous`. `comunicatpdf` canvia diverses vegades dins de la mateixa fase (l'incident
   `I-125912` en va tenir 5) i `:id` canvia quan el publicador substitueix la fila en un canvi de
   fase ([`01`](01-data-sources.md) trap 11, §7.2). Qualsevol altra clau duplica events o els
   perd. És l'error exacte que comet un consumidor de tercers d'aquesta font
   ([`02`](02-existing-integrations.md) §6.1).
2. **Un canvi de fase emet `phase_changed`, no `phase_started` + `phase_ended`.** L'`acronym` és
   el mateix i l'episodi és continu, com demostra el rastre de `I-125912`.
3. **`phase_ended` és per absència.** El CECAT gairebé no publica tancaments: 1 sol
   `DESACTIVACIO` en 623 dies ([`01`](01-data-sources.md) §7.4). Mateix patró `_prune_vanished`
   que `ha-incendiscat` va necessitar per a la vista ArcGIS.
4. **Dues files simultànies del mateix acrònim en fases diferents generen dos `phase_started`,
   un per cadascuna**, i cap no es perd. És el cas que la clau composta existeix per cobrir.
5. **La branca d'aparellament no pot llançar.** Compara amb `_is_escalation`, que dona `false`
   quan qualsevol dels dos costats no és a `PHASE_ORDER` (§4). Una fila que passa a un `plafase`
   irreconeixible emet el seu `phase_changed` amb `escalation: false` i el literal cru viatja al
   payload a `phase_raw`; no hi ha cap `ValueError` que avorti el cicle.

### Literals desconeguts

```python
if plan.phase is Phase.UNKNOWN and plan.phase_raw not in self._unknown_phases:
    self._unknown_phases.add(plan.phase_raw)
    LOGGER.warning("Fase de pla no reconeguda: %r (pla %s)", plan.phase_raw, acronym)

if plan.activated_raw is not None and plan.activated_raw not in self._unknown_activated:
    self._unknown_activated.add(plan.activated_raw)
    LOGGER.warning(
        "Valor de plaactivat no reconegut: %r (pla %s). S'ha derivat de la fase %s",
        plan.activated_raw, acronym, plan.phase,
    )
```

Un `warning` per literal i prou, per als tres conjunts (`plafase`, `plaacronim`, `plaactivat`).
Un `warning` per cicle amb un sondeig de 5 min ompliria el log amb 288 línies al dia.

`activated_raw` és no-`None` exactament quan `activated` **s'ha hagut de derivar de la fase**, i
això inclou tres casos: un literal irreconeixible (hi arriba tal qual), la cadena buida (hi
arriba com a `""`) i **el camp absent** (hi arriba com a `"<absent>"`). Quan el literal és `SI` o
`NO` en qualsevol grafia tolerada, `activated_raw` és `None` i no hi ha `warning`, perquè no s'ha
derivat res: és el cas normal (§4).

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
| `sensor.py` | `plans` | `state_class = MEASUREMENT`. L'estat és `len(state.plans)`, és a dir el nombre de parells `(acronym, phase)`. L'atribut `plans` es serialitza des dels `dataclasses` amb `asdict` i ordre estable per `(acronym, phase)` |
| `sensor.py` | `last_updated` | `SensorDeviceClass.TIMESTAMP`, `entity_category = DIAGNOSTIC`. Parseig del `Last-Modified` amb `email.utils.parsedate_to_datetime` |
| `binary_sensor.py` | `plan_activated` | `BinarySensorDeviceClass.SAFETY`. `is_on` = qualsevol fila amb `activated`, calculat segons §4 i **mai** amb `plaactivat == "SI"` |

Cap entitat retorna `None` com a estat quan la resposta és `[]`: són `none`, `0` i `off`
([`03`](03-feature-spec.md) criteri 1). `unavailable` queda reservat al guard de dades velles.

L'atribut `plans` s'ordena per la clau sencera **`(acronym, phase)`**, no per `acronym` sol,
perquè un canvi d'ordre a la resposta no ha de produir un canvi d'atribut espuri i perquè dues
files del mateix acrònim han de quedar en un ordre determinista. El recorregut de la font no
garanteix cap ordre: la captura de dos plans és fins i tot una reconstrucció de dues consultes
separades ([`01`](01-data-sources.md) §13).

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
| `plafase` desconeguda | `Phase.UNKNOWN` + `warning` una vegada per literal. **Cap excepció**: `_severity` hi dona `-1` en lloc de llançar, i un `phase_changed` cap a `UNKNOWN` o des d'`UNKNOWN` surt amb `escalation: false` (§4) |
| `plaacronim` desconegut | Fila ingerida, `name` = acrònim, `warning` una vegada |
| `plaactivat` amb una grafia tolerada (`SI`, `si`, ` SI `, `Si`, `NO`, `no`) | Es normalitza i es fa servir **tal qual**. Cap derivació i **cap `warning`**: és el cas normal, i tolerar la grafia és justament el punt (§4) |
| `plaactivat` absent, buit o amb un literal irreconeixible (`true`, `Activat`…) | **`activated` es deriva de `plafase`**: cert si la fase és `ALERTA` o superior. Mai es llegeix com a "no activat". `warning` una vegada per literal; l'absència s'hi registra com a `"<absent>"` (§4) |
| Dues files amb el **mateix `plaacronim`** en fases diferents | Dues entrades a l'estat, dos `phase_started`, recompte 2. La clau és `(acronym, phase)` (§5) |
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
| `alerta_2026_08_06.json` | ✅ endpoint en viu, **projecció pelada** | Cas base amb `plaactivat: SI` i **sense camps de sistema**: obliga el camí de `fasedatahora` (`started_at_source = "fasedatahora"`) |
| `camps_sistema_2026_08_06.json` | ✅ endpoint en viu amb `$select=:*,*` | **L'únic fixture amb `:created_at`**: `started_at = 2026-08-05T11:18:09+00:00`, `started_at_source = "created_at"` |
| `prealerta_2024_12_02.json` | 🗄️ Wayback | `plaactivat: NO`, `descripcio` amb `\n` |
| `buit_2026_06_16.json` | 🗄️ Wayback | `[]` |
| `dos_plans_2026_01_19.json` | 🗄️ Wayback (**reconstrucció**) | Múltiples files amb acrònims diferents |
| `pdf_url_accents_2026_07_03.json` | 🗄️ Wayback | URL amb `ó`, `à`, `'` |
| `emergencia_SYNTHETIC.json` | **sintètic** | `EMERGÈNCIA`, mai observada |
| `emergencia_plaactivat_rar_SYNTHETIC.json` | **sintètic** | Tres files d'`EMERGÈNCIA` amb `plaactivat` = `Si`, ` SI ` i **el camp absent**: els tres han de donar `activated = True` (§4). Cada fila porta un `plaacronim` **distint** (`INUNCAT`, `INFOCAT`, `NEUCAT`) perquè les tres claus `(acronym, phase)` siguin distintes; amb l'acrònim repetit col·lapsarien en una entrada (§5) i dues de les tres variants no s'avaluarien mai |
| `fase_desconeguda_SYNTHETIC.json` | **sintètic** | Vàlvula `unknown` |
| `camps_absents_SYNTHETIC.json` | **sintètic** | `comunicatpdf`/`plaicona`/`descripcio` absents |
| `dos_procicat_SYNTHETIC.json` | **sintètic** | Dues files del **mateix acrònim** en fases diferents. Sintètic perquè la forma és una inferència de [`01`](01-data-sources.md) §3.2 nota 2, mai observada |

Els sis primers són còpies literals de [`docs/captures/`](captures/); els cinc `_SYNTHETIC` no
ho són i no ho poden semblar. `alerta_2026_08_06.json` i `camps_sistema_2026_08_06.json` són la
**mateixa fila amb dues projeccions diferents**, capturades el mateix dia amb 42 minuts de
diferència (11:49 i 12:31 UTC) i amb el mateix `comunicatpdf`, `fasedatahora` i `descripcio`.
Tenir-les totes dues és el que fa comprovables els dos camins de `resolve_started_at` amb dades
reals en lloc d'un fixture retocat a mà.

Els sintètics porten `_SYNTHETIC` al nom i una capçalera `_comment` que ho diu, perquè ningú els
confongui amb evidència. És la distinció que fa creïbles els documents dels germans. Els dos que
porten `EMERGÈNCIA` són sintètics precisament perquè **aquesta fase no s'ha observat mai en un
payload real** ([`01`](01-data-sources.md) §3.1, trap 14): el fixture prova el camí de codi, no
documenta cap observació.

Un avís sobre el fixture de les variants de `plaactivat`: la cobertura per variant viu als
criteris de `resolve_activated` de T3 ([`05`](05-implementation-plan.md)), que asserten fila a
fila. El criteri agregat de T7 (`plan_activated = on`) el satisfaria **qualsevol** de les tres
files essent certa, per tant no és cobertura de les tres i no s'hi ha de confiar com si ho fos.

### Fitxers de test

| Fitxer | Què cobreix |
| --- | --- |
| `test_api.py` | 200, 304, timeout, 4xx, 5xx, cos no-JSON, cos no-llista, `If-Modified-Since` enviat |
| `test_models.py` | Normalització de fase amb i sense diacrítics, `resolve_activated` amb `SI`/`NO`/`Si`/` SI `/absent/irreconeixible, `resolve_started_at` amb les dues fonts i cap, camps absents, `descripcio` bruta |
| `test_coordinator.py` | Reconciliació amb la clau `(acronym, phase)`, dues files del mateix acrònim, `available` per dades velles, `warning` una sola vegada, 304 conserva estat |
| `test_events.py` | Els 4 events, l'aparellament 1-a-1 que dona `phase_changed`, el cas ambigu que dona `started`/`ended` plans, el no-event del PDF canviat, el no-event del cicle fallit, `escalation` |
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
| AD-5 | Identitat de l'episodi = `(acronym, phase)`, **i és també la clau del `dict` d'estat** | `:id` de Socrata, hash de la fila, o indexar per `plaacronim` sol | `comunicatpdf` canvia dins de la mateixa fase i `:id` canvia en un canvi de fase ([`01`](01-data-sources.md) trap 11). Indexar per l'acrònim sol perdria una de dues files simultànies de PROCICAT, que §3.2 nota 2 fa plausible (§5) |
| AD-6 | `plafase` mana, `plaactivat` és derivat: normalitzat com `plafase`, `False` només amb `no`, i derivat de la fase si no es reconeix | Filtrar o comparar per `plaactivat == 'SI'` | `plaactivat: "NO"` és la prealerta, el 51,4% dels comunicats: filtrar amaga mitja font. I la descripció oficial escriu "(Si/No)" mentre les dades donen `SI`/`NO`, per tant una comparació estricta pot deixar un sensor `SAFETY` a `off` durant una emergència ([`01`](01-data-sources.md) traps 1 i 14, §3.3) |
| AD-7 | Un atribut `plans` en lloc de N entitats per pla | 13-18 binary sensors | `plaacronim` no és un conjunt tancat (`PENTA`, `NOPLA`). Una llista blanca quedaria obsoleta sense avís ([`03`](03-feature-spec.md) §7) |
| AD-8 | `Phase.UNKNOWN` fora de `PHASE_ORDER`, amb `_severity` que hi dona `-1` en lloc de llançar i `escalation: false` sempre que un costat no sigui comparable | Col·locar-la a dalt o a baix de l'escala, o cridar `PHASE_ORDER.index()` pelat | No se sap on va un literal desconegut i inventar-ho és pitjor que no ordenar-lo. Però `index()` pelat llançaria `ValueError` a la branca d'aparellament i avortaria el cicle sencer, contra el criteri 6 de [`03`](03-feature-spec.md): un literal desconegut és esperable, no excepcional (§4) |
| AD-9 | Normalització de fase sense diacrítics | Comparació exacta amb `"EMERGÈNCIA"` | La fase més greu mai s'ha observat en viu; un accent no pot fer-la perdre ([`01`](01-data-sources.md) trap 14) |
| AD-10 | Mapatge propi acrònim → nom, amb fallback a l'acrònim | `planom` | `planom` és igual a `plaacronim` a 5/5 files observades ([`01`](01-data-sources.md) trap 4) |
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
