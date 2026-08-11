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
    UNRECOGNIZED = "unrecognized"

PHASE_ORDER = (Phase.NONE, Phase.PREALERTA, Phase.ALERTA, Phase.EMERGENCIA)
ACTIVATING_PHASES = frozenset({Phase.ALERTA, Phase.EMERGENCIA})
```

`PHASE_ORDER` serveix per **ordenar** (quina fase és més greu) i `ACTIVATING_PHASES` per
**classificar** (quina fase activa el pla). Són preguntes diferents i es responen amb eines
diferents: la segona és una pertinença, i per tant no pot llançar amb cap valor, ni tan sols amb
`UNRECOGNIZED`.

`UNRECOGNIZED` **queda fora de `PHASE_ORDER`** deliberadament: no se sap on col·locar un literal
desconegut a l'escala de severitat, i inventar-ho seria pitjor que no ordenar-lo. Regla:
`max_phase` és `UNRECOGNIZED` només si **cap** fila té una fase reconeguda; si n'hi ha alguna, mana la
màxima reconeguda i el literal desconegut queda visible a `phase_raw` i als diagnostics.

L'agregació **filtra abans d'ordenar**, i l'ordre dels dos passos és tota la substància:

```python
def max_phase(fases: Iterable[Phase]) -> Phase:
    """La fase agregada. Filtra a les fases ordenables ABANS d'ordenar."""
    fases = list(fases)
    ordenables = [f for f in fases if f in PHASE_ORDER]
    if ordenables:
        return max(ordenables, key=_severity)
    return Phase.UNRECOGNIZED if fases else Phase.NONE
```

Amb el filtre, la semàntica documentada surt d'una **pertinença** i no del valor numèric de cap
sentinel: `[]` dona `NONE`, un conjunt on totes les fases són irreconeixibles dona `UNRECOGNIZED`, i
qualsevol barreja dona la màxima reconeguda ([`05`](05-implementation-plan.md) T6). `max()` no veu
mai `UNRECOGNIZED`, per tant aquí ni tan sols un `PHASE_ORDER.index()` pelat no podria llançar.

### Severitat: `_severity`, i per què no es compara mai amb `UNRECOGNIZED` (AD-8)

```python
def _severity(phase: Phase) -> int:
    """Posició a l'escala de severitat. Mai llança: fora de PHASE_ORDER dona -1."""
    return PHASE_ORDER.index(phase) if phase in PHASE_ORDER else -1
```

`PHASE_ORDER.index(phase)` **pelat llançaria `ValueError` amb `Phase.UNRECOGNIZED`**, i el conjunt de
plans no és tancat ([`01`](01-data-sources.md) §3.2, trap 5): un literal desconegut és
**esperable**, no excepcional, i ha de degradar de manera segura i sorollosa, mai tombar el
coordinator. Una excepció dins del cicle el avortaria sencer, que és exactament el contrari del
criteri 6 de [`03`](03-feature-spec.md) ("cap excepció") i de la fila de `plafase` desconeguda
de §8.

**La correcció de fons, però, no és el sentinel: és no fer la comparació.** `escalation` només
té sentit entre dues fases que **totes dues** tenen posició a `PHASE_ORDER`. Comparar a través
d'un valor que no en té era el defecte real, i intentar salvar-lo amb un sentinel només movia el
problema: `_severity(ALERTA) > _severity(UNRECOGNIZED)` és `2 > -1`, cert, i afirmaria una escalada
en sortir d'un literal desconegut. Per això la regla d'aparellament de §5 **exclou `UNRECOGNIZED` de
la branca de `phase_changed`**, i la comparació de severitats no hi arriba mai amb un valor
sense ordre.

Conseqüència sobre aquest codi, i **enumerada per cridant en lloc d'afirmada en absolut**, perquè
una afirmació absoluta sobre llocs de crida ja ha resultat falsa diverses vegades mentre una
enumeració incompleta com a mínim es veu:

| Cridant | El sentinel `-1` hi és portant? | Per què |
| --- | --- | --- |
| La branca additiva de `phase_changed` (§5) | **No** | La tercera condició ja garanteix que les dues fases són a `PHASE_ORDER`, per tant la comparació no hi arriba mai amb un valor sense ordre. Aquí el sentinel és defensa en profunditat |
| L'agregació de `max_phase` (§4, regla de dalt) | **No** | El filtre previ treu `UNRECOGNIZED` **abans** d'ordenar, per tant `max()` només rep fases amb posició. Sense el filtre sí que hi era portant: la semàntica documentada depenia de `-1` ordenant per sota de qualsevol fase real, i un `index()` pelat hi feia petar la fixture `fase_desconeguda_SYNTHETIC` i el cas mixt de desconeguda més `ALERTA` ([`05`](05-implementation-plan.md) T6) |
| `resolve_activated` (§4) | **No hi crida** | Deriva per pertinença a `ACTIVATING_PHASES`: una fase irreconeixible hi dona `False` sense tocar cap ordre |

Dit tal com queda: **cap dels cridants enumerats no depèn del sentinel**, i cadascun hi arriba per
una via diferent (la tercera condició de §5, el filtre previ de l'agregació, la pertinença a
`ACTIVATING_PHASES`). `_severity` es manté **no-llançant igualment**, però com a defensa en
profunditat i no com la peça que fa funcionar res: si algun dia hi arriba un quart cridant amb una
fase irreconeixible, degradarà en lloc d'avortar el cicle. L'enumeració és per cridant justament
perquè, si aquell quart apareix, es vegi que la taula no el cobreix.

La lliçó, que és la que ha costat més rondes: un sentinel la feina del qual és deixar que un valor
sense ordre sobrevisqui a una comparació ordenada és el senyal que la comparació no s'hauria de fer
amb aquell valor. La correcció no és refinar el sentinel, és **treure el valor de la comparació**, i
es fa amb la mateixa eina als dos llocs: una condició prèvia a §5 i un filtre previ a l'agregació.

Això no posa `UNRECOGNIZED` a `PHASE_ORDER` i per tant no toca AD-8: el sentinel li dona una posició
definida i no comparable, que és el que AD-8 volia dir, i ara ja no hi ha cap cridant que en depengui.

### Normalització de la fase

```python
def normalise_phase(raw: str | None) -> Phase:
    if not raw:
        return Phase.UNRECOGNIZED
    key = _strip_diacritics(raw).strip().casefold()   # "EMERGÈNCIA" → "emergencia"
    return _PHASE_BY_KEY.get(key, Phase.UNRECOGNIZED)
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
    derived = phase in ACTIVATING_PHASES
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
3. **La derivació és una pertinença, no una comparació d'ordre.** `ACTIVATING_PHASES` és el
   `frozenset({Phase.ALERTA, Phase.EMERGENCIA})`, i `Phase.UNRECOGNIZED` simplement no hi és, per
   tant el derivat és `False` **sense cap comparació de severitat i sense cap possibilitat de
   llançar**. Fase desconeguda **i** `plaactivat` desconegut és l'únic cas sense cap senyal
   utilitzable; els dos literals van als diagnostics. Aquesta forma és deliberada: una pertinença
   expressa exactament la pregunta ("aquesta fase activa el pla?") i no arrossega l'ordre, que
   aquí no fa falta.

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
   alta i una baixa per a `PROCICAT`, i per tant s'hi **afegeix** un
   `cecat_plan_phase_changed` amb `escalation: true`, afirmant que un pla ha escalat quan de fet
   un s'ha acabat i n'ha començat un altre de diferent.

La segona és ara **més estreta del que era**, i val la pena dir exactament què hi falla i què
no. Els events `phase_ended(PROCICAT, PREALERTA)` i `phase_started(PROCICAT, ALERTA)` són
**individualment correctes**: un pla d'actuació realment ha deixat de seguir-se i un altre
realment ha començat en alerta. **L'únic que informa malament és el `phase_changed` additiu**,
que els lliga com si fossin el mateix episodi. Un consumidor del carril `phase_started` o del
carril `phase_ended` ([`03`](03-feature-spec.md) §6) no en pateix res; només el carril
`phase_changed` amb `escalation: true` veu una escalada que no ha passat.

No la resol cap dels dos casos que no afegeixen `phase_changed`: no és ambigüitat de cardinalitat
(és estrictament 1-a-1) i cap dels dos costats no és `UNRECOGNIZED` (`PREALERTA` i `ALERTA` són
totes dues a `PHASE_ORDER`). Compleix les tres condicions i per tant el `phase_changed` s'hi
afegeix.

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

Amb la clau composta, la detecció és una diferència de conjunts de claus. **Cap event no en
suprimeix cap altre**: `phase_started` i `phase_ended` s'emeten sempre, i `phase_changed` és
purament **additiu**.

```python
added   = current.keys() - previous.keys()
removed = previous.keys() - current.keys()

def fire(event_type: str, **data) -> None:
    """El payload és EXACTAMENT els kwargs. fire() no hi afegeix ni hi treu res."""
    hass.bus.async_fire(event_type, data)

# 1. Sempre, sense excepcions ni supressió.
for key in removed:
    old = previous[key]
    fire(EVENT_PLAN_PHASE_ENDED,                      # 5 camps, 03 §4.3
         acronym=old.acronym, name=old.name,
         previous_phase=old.phase, previous_phase_raw=old.phase_raw,
         duration_minutes=_duration(old))
for key in added:
    new = current[key]
    if new.phase is not Phase.NONE:
        fire(EVENT_PLAN_PHASE_STARTED,                # 8 camps, 03 §4.1
             acronym=new.acronym, name=new.name,
             phase=new.phase, phase_raw=new.phase_raw,
             activated=new.activated, started_at=new.started_at,
             description=new.description, communique_url=new.communique_url)

# 2. A MÉS, quan es donen les tres condicions, un event de canvi.
for acronym in {a for a, _ in added | removed}:
    adds    = [k for k in added   if k[0] == acronym]
    removes = [k for k in removed if k[0] == acronym]

    pairs = (
        len(adds) == 1
        and len(removes) == 1
        and adds[0][1] in PHASE_ORDER           # cap costat pot ser Phase.UNRECOGNIZED
        and removes[0][1] in PHASE_ORDER
    )
    if pairs:
        new, old = current[adds[0]], previous[removes[0]]
        fire(EVENT_PLAN_PHASE_CHANGED,                # 9 camps, 03 §4.2
             acronym=new.acronym, name=new.name,
             previous_phase=old.phase, previous_phase_raw=old.phase_raw,
             phase=new.phase, phase_raw=new.phase_raw,
             escalation=_severity(new.phase) > _severity(old.phase),
             activated=new.activated, started_at=new.started_at)
```

**Cada payload s'escriu sencer a la seva crida**, i això és deliberat: `fire()` no completa res a
partir del `PlanActivation`, per tant els tres payloads es llegeixen directament de les tres crides
i es poden comparar camp per camp amb §4.1, §4.2 i §4.3 de [`03`](03-feature-spec.md). Passar el
`PlanActivation` sencer i deixar que els camps hi entressin sols era el que feia que `phase_ended`
sortís amb `phase` i sense `previous_phase`, és a dir amb la fase de la clau desapareguda etiquetada
com si fos la fase actual del pla. `phase_ended` és el payload més curt a propòsit: **no porta
`phase` ni `phase_raw`**, perquè la fase de la clau que ha desaparegut ja hi viatja com a
`previous_phase`, i portar-la dues vegades amb dos noms convida a llegir-la com la fase d'ara.

**`phase_started` no porta cap origen, i això és una decisió, no un oblit.** El payload diu en
quina fase ha entrat la clau i prou. La raó és el resultat central de la recerca: **`plaacronim`
no identifica un pla** ([`01`](01-data-sources.md) §3.2 nota 2), de manera que relacionar una clau
que apareix amb una que desapareix és una **inferència** sobre continuïtat, no una observació.
`phase_ended` sí que porta `previous_phase` i `previous_phase_raw`, i la diferència no és
arbitrària: allà la clau `(acronym, phase)` **ha desaparegut** i la seva fase és un fet sobre la
clau mateixa. La regla, dita una vegada perquè no calgui redescobrir-la: **la continuïtat al llarg
d'un acrònim no és derivable d'aquesta font, per tant cap event no afirma un origen**, i
l'aparellament s'intenta només al `phase_changed` additiu, amb el residu de l'obert 6 assumit.

**Una transició del mateix acrònim emet tres events**, no un: `phase_ended` de la fase que
s'acaba (amb la seva durada), `phase_started` de la que comença, i `phase_changed` que descriu
el parell. Tres és el recompte honest: una fase **s'ha** acabat, una altra **ha** començat, i el
parell **és** un canvi.

**Per què s'ha eliminat la supressió.** Amb el disseny anterior, un `phase_changed` reemplaçava
el parell, i per tant qualsevol consumidor que escoltés només `phase_started` no rebia res quan
un pla escalava a `EMERGÈNCIA`, que és exactament la transició que més importa. Aquell disseny
va produir el mateix defecte tres rondes seguides, en camins diferents. Ara **un consumidor d'un
sol event no pot equivocar-se**, i aquest és tot el propòsit del canvi.

**El cost, dit clarament:** qui escolti `phase_started` **i** `phase_changed` alhora rep **dues**
notificacions per una sola transició. Per això cada recepta de [`03`](03-feature-spec.md) §6 tria
un carril explícit, i el blueprint també.

**Les tres condicions de `phase_changed`, i cap més.** Una alta per a l'acrònim, una baixa per a
l'acrònim, i **les dues fases a `PHASE_ORDER`**. Si en falla qualsevol, simplement no hi ha
`phase_changed`; el parell `phase_ended` + `phase_started` ja s'ha emès igualment.

Dos casos no afegeixen `phase_changed`, i per motius diferents:

1. **Ambigüitat de cardinalitat**: més d'una alta o més d'una baixa per al mateix acrònim. Si
   dues files de PROCICAT desapareixen i n'apareix una, no hi ha cap manera honesta de dir quina
   de les dues "ha canviat de fase" i quina "s'ha acabat". Això està escrit explícitament perquè
   ningú no hi dedueixi una heurística d'aparellament per severitat, per ordre o per
   `started_at`. Un aparellament inventat és una mentida sobre què ha passat.
2. **Un costat és `UNRECOGNIZED`**: la fase d'entrada o la de sortida no té posició a l'escala.
   Un `phase_changed` afirma implícitament que sabem entre quines dues fases s'ha mogut
   l'episodi, i amb un literal irreconeixible no ho sabem.

En tots dos casos el senyal no es perd: el parell `phase_ended` + `phase_started` sempre hi és, i
és individualment correcte. L'únic que falta és l'afirmació que no podem sostenir.

Amb això, `escalation` només es calcula entre dues fases que totes dues tenen posició a
`PHASE_ORDER`, que és l'únic cas on "changed" vol dir alguna cosa (§4).

#### Exemple treballat: `ALERTA` cap a `UNRECOGNIZED` cap a `EMERGÈNCIA`

| Cicle | Estat | Events emesos |
| --- | --- | --- |
| N | `{(INUNCAT, ALERTA)}` | (cap canvi) |
| N+1 | `{(INUNCAT, UNRECOGNIZED)}`, el publicador escriu un `plafase` irreconeixible | `phase_ended(INUNCAT, ALERTA)` **+** `phase_started(INUNCAT, UNRECOGNIZED)`. **Cap `phase_changed`**: un costat no és a `PHASE_ORDER` |
| N+2 | `{(INUNCAT, EMERGÈNCIA)}` | `phase_ended(INUNCAT, UNRECOGNIZED)` **+** `phase_started(INUNCAT, EMERGÈNCIA)`. **Cap `phase_changed`** |

I la transició directa, per contrast:

| Cicle | Estat | Events emesos |
| --- | --- | --- |
| N | `{(INUNCAT, ALERTA)}` | (cap canvi) |
| N+1 | `{(INUNCAT, EMERGÈNCIA)}` | `phase_ended(INUNCAT, ALERTA)` amb `duration_minutes` **+** `phase_started(INUNCAT, EMERGÈNCIA)` **+** `phase_changed` amb `escalation: true` |

En tots dos casos **el blueprint notifica**, perquè escolta `phase_started` i la fase nova hi
arriba sempre. Aquesta és la propietat que la supressió trencava.

Cinc propietats que es deriven directament de les traps:

1. **La clau és `(acronym, phase)`, mai `:id` ni el hash de la fila**, i és la mateixa clau que
   indexa `_previous`. `comunicatpdf` canvia diverses vegades dins de la mateixa fase (l'incident
   `I-125912` en va tenir 5) i `:id` canvia quan el publicador substitueix la fila en un canvi de
   fase ([`01`](01-data-sources.md) trap 11, §7.2). Qualsevol altra clau duplica events o els
   perd. És l'error exacte que comet un consumidor de tercers d'aquesta font
   ([`02`](02-existing-integrations.md) §6.1).
2. **Un canvi de fase emet `phase_changed` a més del parell, no en lloc del parell.** L'`acronym`
   és el mateix i l'episodi és continu, com demostra el rastre de `I-125912`, i `phase_changed`
   és la manera de dir-ho; però la fase antiga realment s'ha acabat i la nova realment ha
   començat, i suprimir aquells dos events amagava la transició als consumidors que només
   n'escolten un.
3. **`phase_ended` és per absència, i s'emet sempre.** El CECAT gairebé no publica tancaments: 1
   sol `DESACTIVACIO` en 623 dies ([`01`](01-data-sources.md) §7.4). Mateix patró
   `_prune_vanished` que `ha-incendiscat` va necessitar per a la vista ArcGIS. Com que ja no se
   suprimeix mai, **sempre porta `duration_minutes`**, també per a les fases intermèdies d'un
   episodi, que amb la supressió no s'emetien enlloc. L'exactitud de la xifra en una fase
   intermèdia, però, depèn de l'obert 3 ([`01`](01-data-sources.md) §14): amb edició de fila en
   lloc de substitució, `started_at` es queda a l'inici de l'episodi i la durada surt inflada
   ([`03`](03-feature-spec.md) §4.3).
4. **Dues files simultànies del mateix acrònim en fases diferents generen dos `phase_started`,
   un per cadascuna**, i cap no es perd. És el cas que la clau composta existeix per cobrir.
5. **El càlcul de `escalation` no pot llançar, i per construcció.** La tercera condició
   garanteix que `_severity` només rep fases que són a `PHASE_ORDER`, per tant la comparació no
   pot arribar mai a un valor sense ordre. Una fila que passa a un `plafase` irreconeixible surt
   amb `phase_ended` + `phase_started` i sense `phase_changed`, i el literal cru viatja als dos
   payloads (`previous_phase_raw` i `phase_raw`); no hi ha cap `ValueError` que avorti el cicle
   (criteri 6 de [`03`](03-feature-spec.md)).

### Literals desconeguts

```python
if plan.phase is Phase.UNRECOGNIZED and plan.phase_raw not in self._unknown_phases:
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
| `sensor.py` | `max_phase` | `SensorDeviceClass.ENUM` amb `options` incloent-hi `"unrecognized"`. Icona fixa `mdi:shield-alert-outline` via `icons.json`. Atributs `acronyms` (llista de cadenes) i `total_plans`: **`acronyms`, no `plans`**, perquè el nom digui la forma |
| `sensor.py` | `plans` | `state_class = MEASUREMENT`. L'estat és `len(state.plans)`, és a dir el nombre de parells `(acronym, phase)`. L'atribut `plans` es serialitza des dels `dataclasses` amb `asdict` i ordre estable per `(acronym, phase)` |
| `sensor.py` | `last_updated` | `SensorDeviceClass.TIMESTAMP`, `entity_category = DIAGNOSTIC`. Parseig del `Last-Modified` amb `email.utils.parsedate_to_datetime` |
| `binary_sensor.py` | `plan_activated` | `BinarySensorDeviceClass.SAFETY`. `is_on` = qualsevol fila amb `activated`, calculat segons §4 i **mai** amb `plaactivat == "SI"`. Atribut `acronyms` (llista de cadenes), **no `plans`** |

Cap entitat retorna `None` com a estat quan la resposta és `[]`: són `none`, `0` i `off`
([`03`](03-feature-spec.md) criteri 1). `unavailable` queda reservat al guard de dades velles.

**El nom `plans` designa una sola forma a tota la integració**: la llista d'objectes de
`sensor.…_plans`. Les dues llistes de cadenes (`max_phase` i `plan_activated`) es diuen
`acronyms`. Un mateix nom amb dues formes incompatibles fa que un `selectattr('acronym', …)`
apuntat per error a l'entitat equivocada peti, i amb `entity_id` dependents de l'idioma
([`03`](03-feature-spec.md) §3) apuntar-hi malament és fàcil.

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
| `plafase` desconeguda | `Phase.UNRECOGNIZED` + `warning` una vegada per literal. **Cap excepció.** Una transició cap a `UNRECOGNIZED` o des d'`UNRECOGNIZED` emet `phase_ended` + `phase_started`, amb el literal cru a `previous_phase_raw` i a `phase_raw` respectivament, i **cap `phase_changed`**: un costat no és a `PHASE_ORDER` (§5) |
| `plaacronim` desconegut | Fila ingerida, `name` = acrònim, `warning` una vegada |
| `plaactivat` amb una grafia tolerada (`SI`, `si`, ` SI `, `Si`, `NO`, `no`) | Es normalitza i es fa servir **tal qual**. Cap derivació i **cap `warning`**: és el cas normal, i tolerar la grafia és justament el punt (§4) |
| `plaactivat` absent, buit o amb un literal irreconeixible (`true`, `Activat`…) | **`activated` es deriva de `plafase`**: cert si la fase és a `ACTIVATING_PHASES`, és a dir `ALERTA` o `EMERGÈNCIA`. Mai es llegeix com a "no activat". `warning` una vegada per literal; l'absència s'hi registra com a `"<absent>"` (§4) |
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
| `fase_desconeguda_SYNTHETIC.json` | **sintètic** | Vàlvula `unrecognized` |
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
| `test_events.py` | Els 4 events. Que **cada clau afegida dona `phase_started` i cada clau retirada dona `phase_ended`, sempre**; que l'aparellament només hi **afegeix** `phase_changed` quan es compleixen les tres condicions; els dos casos que no l'afegeixen (més d'una alta o baixa per acrònim, i un costat fora de `PHASE_ORDER`); que `phase_started` **no porta cap camp d'origen**, que `phase_ended` **sí** porta `previous_phase` i `previous_phase_raw` i **no** porta `phase`; el no-event del PDF canviat; el no-event del cicle fallit; `escalation` |
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
| AD-5 | Identitat de l'episodi = `(acronym, phase)`, **i és també la clau del `dict` d'estat**. `phase_started` i `phase_ended` s'emeten **sempre**, per a cada clau afegida i retirada; `phase_changed` és **additiu** i demana **tres** condicions: una alta, una baixa, i **les dues fases a `PHASE_ORDER`**. `phase_started` **no porta cap origen**: la continuïtat al llarg d'un acrònim no és derivable (§5) | `:id` de Socrata, hash de la fila, indexar per `plaacronim` sol, o **suprimir** el parell quan s'emet `phase_changed` | `comunicatpdf` canvia dins de la mateixa fase i `:id` canvia en un canvi de fase ([`01`](01-data-sources.md) trap 11). Indexar per l'acrònim sol perdria una de dues files simultànies de PROCICAT, que §3.2 nota 2 fa plausible. I la supressió deixava sense senyal qualsevol consumidor d'un sol event precisament a la transició que més importa: amb ella, escalar a `EMERGÈNCIA` no emetia cap `phase_started` (§5) |
| AD-6 | `plafase` mana, `plaactivat` és derivat: normalitzat com `plafase`, `False` només amb `no`, i derivat de la fase si no es reconeix | Filtrar o comparar per `plaactivat == 'SI'` | `plaactivat: "NO"` és la prealerta, el 51,4% dels comunicats: filtrar amaga mitja font. I la descripció oficial escriu "(Si/No)" mentre les dades donen `SI`/`NO`, per tant una comparació estricta pot deixar un sensor `SAFETY` a `off` durant una emergència ([`01`](01-data-sources.md) traps 1 i 14, §3.3) |
| AD-7 | Un atribut `plans` en lloc de N entitats per pla | 13-18 binary sensors | `plaacronim` no és un conjunt tancat (`PENTA`, `NOPLA`). Una llista blanca quedaria obsoleta sense avís ([`03`](03-feature-spec.md) §7) |
| AD-8 | `Phase.UNRECOGNIZED` fora de `PHASE_ORDER`, i **`phase_changed` no s'afegeix mai quan un costat hi és fora**: la transició surt com a `phase_ended` + `phase_started` | Col·locar-la a dalt o a baix de l'escala, o comparar-la igualment recolzant-se en un sentinel | No se sap on va un literal desconegut i inventar-ho és pitjor que no ordenar-lo. La correcció no és fer que la comparació sobrevisqui a un valor sense ordre, és **no fer-la**: la tercera condició de §5 garanteix que `_severity` només rep fases ordenables. El sentinel `-1` no és el que fa segura cap de les crides enumerades a §4: l'escalada la protegeix la tercera condició de §5, i l'agregació de `max_phase` **filtra a les fases ordenables abans d'ordenar**, de manera que la seva semàntica no depèn del valor del sentinel. Es manté com a defensa en profunditat, no com la peça portant. `resolve_activated` ja no hi crida: deriva per pertinença a `ACTIVATING_PHASES` (§4). L'enumeració per cridant és a §4; s'evita expressament afirmar un nombre absolut de llocs de crida |
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
