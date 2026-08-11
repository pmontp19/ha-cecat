# Pla d'implementació: `ha-cecat`

Descomposició derivada de [`03-feature-spec.md`](03-feature-spec.md) i
[`04-architecture.md`](04-architecture.md). Cada tasca és S/M (1 a 5 fitxers), deixa el
repositori en verd i té criteris d'acceptació verificables.

**Tretze tasques** (T1 a T13). És una integració d'un sol endpoint, quatre entitats i quatre
events, i el pla ho reflecteix: cap tasca passa de M. Comparació: `ha-incendiscat` en va
necessitar 16, i les seves són més grosses, perquè té dues fonts, geometria i entitats
dinàmiques.

---

## Graf de dependències

```
T1 Scaffold + CI
 ├── T2 Fixtures des de docs/captures/        (pur fitxers, cap codi)
 │    └── T3 Models + normalització           (pur Python, sense HA)
 │         └── T4 Client + caché condicional   ⚠️ únic contacte extern
 │              └── T5 Coordinator + reconciliació
 │                   ├── T6 Sensors (3)
 │                   ├── T7 Binary sensor (1)
 │                   ├── T8 Events (4)
 │                   └── T10 Diagnostics + resiliència
 └── T9 Config flow + options flow            (només depèn de T1 i T4)

T11 Traduccions + icons        ← (T6, T7, T9)
T12 Blueprint                  ← (T8)
T13 README + AGENTS + v0.1.0   ← (tot)
```

**Ordre de risc.** T2 va abans que tot el codi: les fixtures són **captures reals** que ja
existeixen a [`captures/`](captures/), i tenir-les al repositori converteix cada tasca posterior
en TDD contra dades verdaderes. T4 és l'única tasca amb contacte extern i va tan aviat com pot:
si el contracte de `$select=:*,*` o el 304 no es comporten com s'ha mesurat, ho sabem abans
d'escriure una sola entitat.

---

## Fase 1: Fonament (sense runtime de HA)

### T1: Scaffold del repositori i CI

**Descripció.** Esquelet del §1 de [`04`](04-architecture.md): `custom_components/cecat/` amb
`manifest.json` (§2), `const.py` (domini, URL, paràmetres, noms d'events, defaults),
`hacs.json`, `pyproject.toml` (ruff + pytest, còpia del germà), `requirements_dev.txt`,
`release-please-config.json`, `.release-please-manifest.json`, i els tres workflows
(`ci.yml`, `validate.yml`, `release-please.yml`) amb els SHA pinats. `CONTRIBUTING.md`.

**Criteris d'acceptació.**
- [ ] `manifest.json` amb `domain: cecat`, `integration_type: service`, `iot_class: cloud_polling`, `requirements: []`, `config_flow: true`, **`single_config_entry: true`**
- [ ] `const.py` conté `BASE_URL`, `PARAMS = {"$select": ":*,*"}`, `DEFAULT_SCAN_INTERVAL_MIN = 5`, `MIN/MAX = 1/60`, els 4 noms d'event i `ATTRIBUTION`
- [ ] `ruff` amb el mateix conjunt de regles que `ha-incendiscat` (`E,W,F,I,UP,B,SIM,RUF,ASYNC,PL`, `line-length = 88`, `py313`)
- [ ] `validate.yml` amb `hassfest` i `hacs/action` (`category: integration`), amb cron diari

**Verificació.** `ruff check .` net; `validate.yml` verd en el primer push.
**Dependències.** Cap. **Mida.** M

### T2: Fixtures reals des de `docs/captures/`

**Descripció.** Copiar les captures de [`captures/`](captures/) a `tests/fixtures/` amb els noms
de la taula del §9 de [`04`](04-architecture.md), i escriure els **cinc** fixtures sintètics
(`emergencia_SYNTHETIC.json`, `emergencia_plaactivat_rar_SYNTHETIC.json`,
`fase_desconeguda_SYNTHETIC.json`, `camps_absents_SYNTHETIC.json`,
`dos_procicat_SYNTHETIC.json`). `tests/conftest.py` amb el carregador de fixtures i el
`FakeClock`.

**Criteris d'acceptació.**
- [ ] **6** fixtures són **còpies literals** de captures reals, amb el fitxer d'origen documentat a `tests/fixtures/README.md`: `alerta_2026_08_06`, `camps_sistema_2026_08_06`, `prealerta_2024_12_02`, `buit_2026_06_16`, `dos_plans_2026_01_19`, `pdf_url_accents_2026_07_03` (des de `wj9c-j6vf-infocat-2026-07-03.json`)
- [ ] Els **5** sintètics porten `_SYNTHETIC` al nom **i** una clau `_comment` al JSON que ho declara
- [ ] `alerta_2026_08_06.json` **no** té camps de sistema i `camps_sistema_2026_08_06.json` **sí**: són la mateixa fila amb dues projeccions, i cap dels dos s'edita per fer-los coincidir
- [ ] `buit_2026_06_16.json` conté exactament `[]`
- [ ] `pdf_url_accents_2026_07_03.json` conserva `ó`, `à` i `'` sense escapar-los

**Verificació.** Un test paramètric carrega els 11 fixtures i comprova que tots són llistes.
**Dependències.** T1. **Mida.** S

### T3: Models i normalització

**Descripció.** `models.py` del §4 de [`04`](04-architecture.md): enum `Phase`, `PHASE_ORDER`
(sense `UNRECOGNIZED`), `normalise_phase()` amb `casefold()` i sense diacrítics,
`resolve_activated()` amb la mateixa normalització i fallback a la fase,
`resolve_started_at()` amb `:created_at` primer i `fasedatahora` de reserva,
`PlanActivation.from_row()` tolerant, `PLAN_NAMES` des del registre oficial, `CecatState`. Cap
import de Home Assistant.

**Criteris d'acceptació.**
- [ ] `camps_sistema_2026_08_06.json` → `phase = ALERTA`, `activated = True`, `started_at = 2026-08-05T11:18:09+00:00` (el `.349Z` truncat a segons), `started_at_source = "created_at"`
- [ ] `alerta_2026_08_06.json`, que és la **mateixa fila sense camps de sistema** → `started_at = 2026-08-05T11:18:00+00:00`, `started_at_source = "fasedatahora"`. Els dos camins donen el mateix minut sobre dades reals
- [ ] `prealerta_2024_12_02.json` → `phase = PREALERTA`, **`activated = False`**, `description` amb el `\n` conservat
- [ ] `EMERGÈNCIA`, `EMERGENCIA`, `emergència` i ` Emergencia ` donen tots `Phase.EMERGENCIA`
- [ ] `plaactivat` = `SI`, `si`, ` SI ` → `activated = True`; `NO`, `no`, ` No ` → **`activated = False`**. En tots sis casos el segon element de `resolve_activated` és `None`: són literals reconeguts i **no** han de generar cap `warning`
- [ ] `plaactivat` amb un literal inesperat (`true`, `Activat`) o buit (`""`), sobre una fila d'`EMERGÈNCIA` o d'`ALERTA` → **`activated = True`**, i el segon element és **el literal cru**, perquè el coordinator hi pugui fer el `warning`
- [ ] `plaactivat` **absent** sobre una fila d'`EMERGÈNCIA` o d'`ALERTA` → **`activated = True`** i el segon element és el sentinel **`"<absent>"`**, no `None`: un camp que desapareix no pot ser silenciós
- [ ] `emergencia_plaactivat_rar_SYNTHETIC` → les **tres** files donen `activated = True`, assertat **fila a fila** i no amb l'agregat de T7. Les tres claus `(acronym, phase)` són distintes perquè els acrònims ho són
- [ ] Els mateixos valors irreconeixibles sobre una fila de `PREALERTA` → `activated = False` (mana la fase, AD-6)
- [ ] `plaactivat` irreconeixible **i** `plafase` irreconeixible → `activated = False`, cap excepció, els dos literals conservats
- [ ] `_severity(Phase.UNRECOGNIZED)` retorna `-1` i **no llança**; `_severity` de les quatre fases de `PHASE_ORDER` retorna la seva posició
- [ ] Fase desconeguda → `Phase.UNRECOGNIZED`, i `phase_raw` conserva el literal
- [ ] `plaacronim` desconegut (`PENTA`, `NOPLA`) → fila vàlida amb `name` = l'acrònim
- [ ] `comunicatpdf`/`plaicona` absents o no-`dict` → `None`, sense excepció
- [ ] Sense `:created_at` i amb `fasedatahora = "16/01/2026 19:54"` → `2026-01-16T18:54:00+00:00` (CET, UTC+1) i `started_at_source = "fasedatahora"`
- [ ] Sense `:created_at` i amb `fasedatahora = "05/08/2026 13:18"` → `2026-08-05T11:18:00+00:00` (CEST, UTC+2)
- [ ] `fasedatahora` il·legible o buida i sense `:created_at` → `(None, None)`
- [ ] `PLAN_NAMES` conté les 13 sigles amb comunicats observats i cap entrada inventada

**Verificació.** `pytest tests/test_models.py` verd. El parell CET/CEST és el test que demostra
que el fus no està cablejat a un offset fix.
**Dependències.** T2. **Mida.** M

### T4: Client HTTP i caché condicional ⚠️ únic contacte extern

**Descripció.** `api.py` del §3 de [`04`](04-architecture.md): `fetch()` amb
`async_get_clientsession`, `$select=:*,*`, `If-Modified-Since`, timeout de 15 s, i les excepcions
`CecatConnectionError` / `CecatFormatError`.

**Criteris d'acceptació.**
- [ ] Amb `aioresponses`: 200 retorna les files i desa `Last-Modified`
- [ ] Segona crida envia la capçalera `If-Modified-Since` amb el valor desat
- [ ] 304 retorna `not_modified = True` i `rows = None`, sense tocar `Last-Modified`
- [ ] Timeout, 500 i 404 llancen `CecatConnectionError`
- [ ] Cos `{"error": true}` (objecte, no llista) llança `CecatFormatError`
- [ ] Cos `[]` retorna llista buida **sense excepció**
- [ ] Un element no-`dict` dins la llista es descarta amb `debug`; la resta es processa
- [ ] **No** s'envia mai `If-None-Match`

**Verificació.** `pytest tests/test_api.py` verd + **una comprovació manual en viu** documentada
al PR: `curl -I` amb `If-Modified-Since` retorna 304, tal com registra
[`captures/http-headers-2026-08-06.txt`](captures/http-headers-2026-08-06.txt). Si el servei ja
no es comporta així, això és un canvi de contracte i cal aturar-se abans de T5.
**Dependències.** T3. **Mida.** M

---

### Checkpoint 1: Fonament

- [ ] `ruff check .` i `ruff format --check .` nets
- [ ] `pytest` verd amb cobertura ≥ 95% sobre `api.py` i `models.py`
- [ ] Les 11 fixtures parsegen a `PlanActivation` sense excepcions
- [ ] `If-Modified-Since` confirmat en viu contra el servei real

---

## Fase 2: Slice vertical (de la font a l'entitat)

### T5: Coordinator i reconciliació

**Descripció.** `coordinator.py` del §5 de [`04`](04-architecture.md): `DataUpdateCoordinator`,
estat entre cicles (`_previous`, `_last_modified`, `_unknown_*`, `_consecutive_failures`,
`_degraded`), guard de dades velles, `warning` una sola vegada per literal. `__init__.py` amb
`runtime_data` i `PLATFORMS`.

**Criteris d'acceptació.**
- [ ] `_previous` està indexat per **`(acronym, phase)`**, no per `acronym`
- [ ] `dos_procicat_SYNTHETIC` → **2 entrades** a l'estat, no 1. Cap de les dues files es perd
- [ ] 304 retorna `self.data` intacta sense recalcular res
- [ ] Cicle fallit llança `UpdateFailed` i **conserva `_previous` sencer**
- [ ] Cicle vàlid amb `[]` **substitueix** `_previous` per un dict buit
- [ ] Dades més velles que `max(6 × interval, 1 h)` → `available = False`
- [ ] Una fase desconeguda genera **un** `warning`, no un per cicle. Idem per a un `plaacronim` i per a un `plaactivat` desconeguts, amb tres conjunts separats
- [ ] `entry.runtime_data` conté el coordinator; res a `hass.data[DOMAIN]`

**Verificació.** `pytest tests/test_coordinator.py` verd, amb la fixture `clock` per al guard de
dades velles.
**Dependències.** T4. **Mida.** M

### T6: Sensors

**Descripció.** `sensor.py` i `entity.py`: `CecatEntity` amb `DeviceInfo(entry_type=SERVICE)` i
`ATTRIBUTION`, i les tres entitats `max_phase`, `plans`, `last_updated`.

**Criteris d'acceptació.**
- [ ] L'entitat de recompte és `sensor.proteccio_civil_catalunya_plans` amb `translation_key = "plans"`, **no** `active_plans`: compta files en qualsevol fase, prealerta inclosa
- [ ] `buit` → `max_phase = "none"`, `plans = 0`. **Cap entitat a `unavailable`**
- [ ] `prealerta_2024_12_02` → `max_phase = "prealerta"`, `plans = 1`, atribut `activated = 0`, `prealerta = 1`
- [ ] `alerta_2026_08_06` → `max_phase = "alerta"`; l'element de `plans` té els 9 camps del §3.2 de [`03`](03-feature-spec.md)
- [ ] `dos_plans_2026_01_19` → `plans = 2`, atribut `plans` **ordenat per `(acronym, phase)`** (INUNCAT abans que NEUCAT)
- [ ] `dos_procicat_SYNTHETIC` (mateix acrònim, fases diferents) → `plans = **2**`, **les dues** files a l'atribut `plans`, en ordre determinista per `(acronym, phase)`. És el criteri que falla si l'estat s'indexa per l'acrònim sol
- [ ] `emergencia_SYNTHETIC` → `max_phase = "emergencia"`
- [ ] `fase_desconeguda_SYNTHETIC` → `max_phase = "unrecognized"` i `phase_raw` visible a `plans`
- [ ] Una fila desconeguda i una `ALERTA` alhora → `max_phase = "alerta"` (la desconeguda no guanya), **i cap excepció**: l'agregació filtra a les fases de `PHASE_ORDER` abans d'ordenar, per tant `max()` no rep mai `unrecognized` (§4 de [`04`](04-architecture.md))
- [ ] `last_updated` parseja el `Last-Modified` a `datetime` amb tz; `None` si falta la capçalera
- [ ] `options` de `max_phase` inclou `"unrecognized"`; `entity_category` de `last_updated` és `DIAGNOSTIC`
- [ ] L'estat de `max_phase` llegit de la màquina d'estats **mai no és la cadena reservada `"unknown"`**, en cap dels fixtures, ni tan sols amb `fase_desconeguda_SYNTHETIC` (criteri 6a de [`03`](03-feature-spec.md))

**Verificació.** `pytest tests/test_sensor.py` verd.
**Dependències.** T5. **Mida.** M

### T7: Binary sensor

**Descripció.** `binary_sensor.py` amb `plan_activated`, `device_class = SAFETY`.

**Criteris d'acceptació.**
- [ ] `alerta_2026_08_06` → `on`, atribut **`acronyms`** `= ["INUNCAT"]`. L'atribut **no** es diu `plans`: aquest nom és exclusiu de la llista d'objectes de `sensor.…_plans` (§3.1 i §3.3 de [`03`](03-feature-spec.md))
- [ ] `prealerta_2024_12_02` → **`off`** (el pla no està activat), mentre `max_phase` és `prealerta`
- [ ] `buit` → `off`
- [ ] `emergencia_SYNTHETIC` → `on`
- [ ] `emergencia_plaactivat_rar_SYNTHETIC` → **`on`**. ⚠️ Aquest criteri és **agregat**: el satisfaria qualsevol de les tres files essent certa, per tant **no** és la cobertura de les tres variants. Aquesta viu als criteris per fila de T3, i aquí només es comprova que l'agregació no perdi el senyal (§3.3 de [`03`](03-feature-spec.md), criteri 5b)
- [ ] Una fila d'`EMERGÈNCIA` amb `plaactivat` = `Si`, amb ` SI `, o **amb el camp absent** dona `on` en els tres casos, comprovat carregant cada variant per separat. És la conducta que una comparació literal `== "SI"` trencaria

**Verificació.** `pytest tests/test_binary_sensor.py` verd. El segon criteri és la prova que la
prealerta es modela com a estat de primera classe i no com a "no activat"; el cinquè és la
prova que la tolerància de la trap 14 arriba també a `plaactivat` i no només a `plafase`.
**Dependències.** T5. **Mida.** S

### T8: Events

**Descripció.** `_emit_events()` al coordinator: `cecat_plan_phase_started`,
`cecat_plan_phase_changed`, `cecat_plan_phase_ended`, `cecat_service_degraded`. Diferència de
claus `(acronym, phase)`: `phase_started` i `phase_ended` sempre, i `phase_changed` **additiu**
segons la regla de tres condicions del §5 de [`04`](04-architecture.md).

**Criteris d'acceptació.**
- [ ] Els noms d'event són `cecat_plan_phase_started` / `_changed` / `_ended`. **Cap event no es diu `activated`**: aquest nom és exclusiu del binary sensor, que té la condició de veritat contrària per a la prealerta (§4 de [`03`](03-feature-spec.md))
- [ ] `{}` → `{(INUNCAT, alerta)}` dispara **un** `cecat_plan_phase_started` amb **exactament aquests vuit camps** del §4.1 de [`03`](03-feature-spec.md): `acronym`, `name`, `phase`, `phase_raw`, `activated`, `started_at`, `description`, `communique_url`. **Cap camp d'origen**: ni `previous_phase` ni `previous_phase_raw`, perquè la continuïtat al llarg d'un acrònim no és derivable
- [ ] `{(INUNCAT, prealerta)}` → `{(INUNCAT, alerta)}` dispara **tres** events: `phase_ended` (`previous_phase = prealerta`, amb `duration_minutes`), `phase_started` (`phase = alerta`) i `phase_changed` amb `escalation: true`. **Cap event no en suprimeix cap altre** (criteri 11 de [`03`](03-feature-spec.md))
- [ ] La mateixa transició cap a `emergencia` emet igualment el `phase_started`, per tant un listener de `phase_started` amb `phase == emergencia` es dispara. És la regressió que la supressió causava (criteri 11b)
- [ ] `{(INUNCAT, alerta)}` → `{(INUNCAT, prealerta)}` dispara els tres events igualment, amb `escalation: false` al `phase_changed`
- [ ] `{}` → `{(PROCICAT, prealerta), (PROCICAT, alerta)}` dispara **dos** `cecat_plan_phase_started`, un per fase. Cap dels dos es perd i no es col·lapsen
- [ ] Cas ambigu: `{(PROCICAT, prealerta), (PROCICAT, alerta)}` → `{(PROCICAT, emergencia)}` dispara **dos** `phase_ended` i **un** `phase_started`, i **cap** `phase_changed`. No s'aparella res quan hi ha més d'una alta o més d'una baixa per acrònim
- [ ] La cardinalitat inversa: `{(PROCICAT, prealerta)}` → `{(PROCICAT, alerta), (PROCICAT, emergencia)}` dispara **un** `phase_ended`, **dos** `phase_started` i **cap** `phase_changed`. Cap dels dos `phase_started` no afirma un origen, que és exactament el cas on una inferència d'origen seria falsa per a almenys un dels dos (criteri 11e de [`03`](03-feature-spec.md))
- [ ] `phase_changed` és **additiu** i demana **tres** condicions: una alta per a l'acrònim, una baixa, **i les dues fases a `PHASE_ORDER`**. Un test comprova que amb un costat `unrecognized` **no** s'emet cap `phase_changed`, i que el parell `phase_ended` + `phase_started` s'emet igualment
- [ ] `{(INUNCAT, alerta)}` → el mateix acrònim amb un `plafase` **irreconeixible** dispara **un** `cecat_plan_phase_ended` (`previous_phase_raw = ALERTA`, amb `duration_minutes`) **i un** `cecat_plan_phase_started` (`phase = unrecognized`, `phase_raw` amb el literal cru), **cap** `phase_changed`, i cap excepció (criteri 6b de [`03`](03-feature-spec.md))
- [ ] **Exemple treballat de dos cicles**, seguint el criteri 6c de [`03`](03-feature-spec.md): partint de l'estat anterior, la fila arriba com a `EMERGÈNCIA` i dispara un `phase_ended` (`previous_phase = unrecognized`, `previous_phase_raw` amb el literal cru) i un `phase_started` (`phase = emergencia`), **cap** `phase_changed`. És el camí que fa que l'escalada a la fase més greu arribi al blueprint sense tocar-lo
- [ ] `_severity` no rep mai una fase fora de `PHASE_ORDER` des de la branca d'aparellament: un test amb un doble o una asserció ho comprova
- [ ] Tot `phase_changed` porta `phase_raw` i `previous_phase_raw`, tot `phase_ended` porta `previous_phase_raw` i tot `phase_started` porta `phase_raw`, també quan les fases són reconegudes (§4.1 de [`03`](03-feature-spec.md))
- [ ] El payload de `phase_ended` té **exactament aquests cinc camps** del §4.3 de [`03`](03-feature-spec.md): `acronym`, `name`, `previous_phase`, `previous_phase_raw`, `duration_minutes`. **No porta `phase` ni `phase_raw`**: la fase de la clau desapareguda hi viatja com a `previous_phase` i no s'ha de poder llegir com la fase actual del pla
- [ ] `{(INUNCAT, alerta)}` → `{(INUNCAT, unrecognized)}`: el `phase_started` **no porta cap camp d'origen**, i el `phase_ended` d'aquell mateix cicle **sí** porta `previous_phase = alerta` i `previous_phase_raw` amb el literal cru. És l'asimetria de §4.1, i el test l'ha de comprovar en tots dos events del mateix cicle
- [ ] Transició `emergencia → alerta`: el `phase_started` porta `phase = alerta` i **cap origen**; el `phase_ended` porta `previous_phase = emergencia`; i el `phase_changed` additiu porta `escalation: false`
- [ ] `{(INUNCAT, alerta)}` → `{}` en un cicle **vàlid** dispara `cecat_plan_phase_ended` amb `duration_minutes` calculat
- [ ] `duration_minutes` hi és **també per a una fase intermèdia**: a la transició `prealerta → alerta`, el `phase_ended` de la prealerta el porta. Amb la supressió era irrecuperable
- [ ] `{(INUNCAT, alerta)}` → cicle **fallit** dispara **cap** event
- [ ] Només canvia `comunicatpdf` (mateix acrònim, mateixa fase) → **cap** event
- [ ] 3 fallides consecutives → `cecat_service_degraded` amb `recovered: false`; el cicle bo següent, un amb `recovered: true`
- [ ] `duration_minutes = None` si `started_at` era `None`

**Verificació.** `pytest tests/test_events.py` verd. Els criteris del cicle fallit i del PDF
canviat són els que eviten els dos errors observats en consumidors reals d'aquesta font
([`02`](02-existing-integrations.md) §6); el criteri del cas ambigu és el que impedeix que algú
hi afegeixi una heurística d'aparellament més endavant.
**Dependències.** T5. **Mida.** M

### T9: Config flow i options flow

**Descripció.** `config_flow.py` del §7 de [`04`](04-architecture.md): un pas amb
`scan_interval`, petició de prova, `OptionsFlow` que reprograma el coordinator.

**Criteris d'acceptació.**
- [ ] Prova que retorna `[]` → **`async_create_entry`** amb `scan_interval = 5`
- [ ] Prova que retorna una fila → entrada creada igualment
- [ ] Timeout o 500 → `errors["base"] = "cannot_connect"`, formulari reenviat
- [ ] Cos que no és una llista → `cannot_connect`
- [ ] Segona entrada → `abort` (`single_config_entry` + `unique_id`)
- [ ] Options flow amb `scan_interval = 15` → `coordinator.update_interval` a 15 min sense recarregar l'entrada
- [ ] `scan_interval` fora de 1..60 → rebutjat pel selector

**Verificació.** `pytest tests/test_config_flow.py` verd, cobertura 100% del mòdul (regla 🥉
`config_flow_test_coverage`).
**Dependències.** T4 (per la prova). **Mida.** M

---

### Checkpoint 2: Slice vertical end-to-end

- [ ] Tots els criteris de T5 a T9 marcats
- [ ] Instal·lació manual en una instància real de HA: entrada creada, 4 entitats presents, estats coherents amb el que el dataset diu en aquell moment
- [ ] Amb el dataset a `[]`: `max_phase = none`, `plans = 0`, `plan_activated = off`, cap entitat `unavailable`
- [ ] Cobertura global ≥ 95%

---

## Fase 3: Poliment i release

### T10: Diagnostics i resiliència completa

**Descripció.** `diagnostics.py` del §3.6 de [`03`](03-feature-spec.md) i la taula sencera de
resiliència del §8 de [`04`](04-architecture.md).

**Criteris d'acceptació.**
- [ ] L'export conté: config entry, **resposta crua** de l'últim cicle, `Last-Modified`, `unknown_phases`, `unknown_acronyms`, **`unknown_activated`**, `consecutive_failures`. Els **tres** conjunts de literals irreconeguts, com diu el §3.6 de [`03`](03-feature-spec.md): sense `unknown_activated` no hi ha cap canal per veure un `plaactivat` inesperat al camp, que és el cas per al qual existeix el criteri 5b
- [ ] Una fila amb `plaactivat` absent deixa `"<absent>"` a `unknown_activated` de l'export
- [ ] `camps_absents_SYNTHETIC` no genera cap `KeyError` en cap capa
- [ ] `pdf_url_accents_2026_07_03` es propaga fins a l'atribut **sense recodificar ni validar** la URL
- [ ] Cada fila de la taula de §8 de [`04`](04-architecture.md) té un test a `test_resilience.py`

**Verificació.** `pytest tests/test_diagnostics.py tests/test_resilience.py` verd.
**Dependències.** T5. **Mida.** M

### T11: Traduccions i icones

**Descripció.** `strings.json`, `icons.json`, `translations/{ca,es,en}.json`. Català com a
llengua de referència. `brand/icon.png` i `icon@2x.png`.

**Criteris d'acceptació.**
- [ ] Les 4 entitats i tots els camps del config flow tenen clau als **tres** idiomes
- [ ] Els 5 valors de `max_phase` tenen etiqueta traduïda als tres idiomes
- [ ] `hassfest` passa
- [ ] `icons.json`, **parsejat com a JSON i no grepat**, assigna a cada entitat una icona `mdi:` fixa i cap valor no prové de `plaicona` (§11.3 de [`01`](01-data-sources.md))
- [ ] `test_translations.py` compara les claus dels tres fitxers i falla si divergeixen

**Verificació.** `validate.yml` verd + `pytest tests/test_translations.py`.
**Dependències.** T6, T7, T9. **Mida.** S

### T12: Blueprint de notificació

**Descripció.** `blueprints/automation/cecat/plan_notification.yaml` del §5 de
[`03`](03-feature-spec.md), amb `min_phase` per defecte a `alerta`.

**Criteris d'acceptació.**
- [ ] `min_phase` per defecte és **`alerta`**, no `prealerta` (589 prealertes en 623 dies)
- [ ] El blueprint declara un bloc `variables:` a nivell d'automatització que lliga `min_phase: !input min_phase` i `plans: !input plans`, de manera que `ordre.index(min_phase)` i el filtre per `plans` resolen dins de les plantilles (§5.1 de [`03`](03-feature-spec.md))
- [ ] El filtre per `plans` buit vol dir "tots"
- [ ] **Escolta un sol event, `cecat_plan_phase_started`**, i **no** té cap trigger de `phase_changed`. Un test comprova que una transició `alerta → emergencia` produeix **una sola** notificació, no dues (§5 de [`03`](03-feature-spec.md))
- [ ] La descripció del blueprint documenta que escolta només `phase_started` i que `cecat_plan_phase_changed` queda per a qui vulgui semàntica d'escalada estrictament, amb el fals positiu de l'obert 6 que aquell carril hereta (§5 i §6 de [`03`](03-feature-spec.md))
- [ ] **`phase: unrecognized` passa el filtre amb els tres valors de `min_phase`** (`prealerta`, `alerta`, `emergencia`), sense excepció (§5.1 de [`03`](03-feature-spec.md), criteri 15b)
- [ ] **Cap error de plantilla amb cap valor de `phase`**, `unrecognized` inclòs: un test renderitza la **condició del blueprint substituït** (el YAML real amb `!input` resolt a través del bloc `variables:` de §5.1 de [`03`](03-feature-spec.md), no `min_phase` injectat directament al context de renderització, perquè això passaria tot i que el blueprint real petaria) amb **les quatre fases que un event pot portar** (`prealerta`, `alerta`, `emergencia`, `unrecognized`) × els tres `min_phase`, i cap de les dotze combinacions peta. `none` no hi entra perquè cap payload d'event no el pot portar: `normalise_phase` no retorna mai `Phase.NONE` i `none` només existeix com a estat agregat de `max_phase`. La condició comprova `unrecognized` abans de qualsevol `index()`, i el curtcircuit de l'`or` és el que ho garanteix
- [ ] El missatge renderitzat per a `phase: unrecognized` **diu que la fase no s'ha reconegut i mostra `phase_raw`**, en lloc de presentar `unrecognized` com si fos una fase coneguda
- [ ] El missatge implementa **els dos casos** de §5.2 de [`03`](03-feature-spec.md) i cap més: l'estat neutre per a una fase reconeguda ("INUNCAT: ara en fase ALERTA") i el text de fase no reconeguda. **No afirma cap direcció ni cap origen**: una transició `emergencia → alerta` renderitza el mateix estat neutre que una entrada en alerta des de zero, perquè l'event no porta prou informació per distingir-les honestament
- [ ] **Cap error de plantilla en el missatge** amb cap de les quatre fases que un event pot portar (`prealerta`, `alerta`, `emergencia`, `unrecognized`): un test les renderitza totes. Aquí no hi ha cap `index()` a garantir, perquè el missatge és neutre i la branca de la fase reconeguda és el cas per defecte; la regla del guard abans de l'`index()` és del criteri anterior, que és el de la **condició** de `min_phase`
- [ ] El missatge renderitzat **conté l'acrònim del pla**: cap valor del missatge no és un nom pelat sense qualificar, perquè el bloc `variables:` de §5.1 de [`03`](03-feature-spec.md) només lliga `min_phase` i `plans`, i un `{{ acronym }}` sense `trigger.event.data.` no hi és i rendiria una cadena buida sense petar (§5.2 de [`03`](03-feature-spec.md))
- [ ] Hi ha **un sol** fragment de missatge copiable a tot el conjunt de documents, el de §5.2 de [`03`](03-feature-spec.md), i el blueprint implementa aquell
- [ ] `test_blueprint.py` valida l'esquema del YAML

**Verificació.** `pytest tests/test_blueprint.py` verd + importació manual a una instància real.
**Dependències.** T8. **Mida.** S

### T13: README, `AGENTS.md`, `quality_scale.yaml` i v0.1.0

**Descripció.** README amb instal·lació HACS, taula d'entitats, exemples d'automació (inclòs el
template per pla concret del §6 de [`03`](03-feature-spec.md)), atribució de la llicència,
descàrrec de "no oficial", i **la secció de limitacions conegudes**. `AGENTS.md` amb les
convencions. `quality_scale.yaml` amb cada regla marcada i les exempcions justificades.
Instruccions d'eliminació (regla 🥉 `docs_removal_instructions`).

**Criteris d'acceptació.**
- [ ] El README documenta explícitament les tres limitacions estructurals: **cap territori afectat**, **cap històric**, i **la desactivació es detecta per absència amb la resolució de l'interval de sondeig**
- [ ] Atribució literal: "Generalitat de Catalunya. Departament d'Interior i Seguretat Pública. Direcció General de Protecció Civil", **amb la data d'actualització** (exigència de la llicència, §11 de [`01`](01-data-sources.md))
- [ ] `quality_scale.yaml` amb totes les regles 🥉 bronze a `done` o `exempt` amb comentari
- [ ] `AGENTS.md` amb la secció `## Maintaining this file`
- [ ] Tag `v0.1.0` generat per `release-please`, mai a mà

**Verificació.** `validate.yml` (hassfest + HACS) verd; instal·lació des de zero via HACS com a
repositori personalitzat.
**Dependències.** Tot. **Mida.** M

---

### Checkpoint final: v1

- [ ] Tots els criteris d'acceptació del §8 de [`03-feature-spec.md`](03-feature-spec.md) marcats: els 18 numerats més 3b, 4b, 5b, 6a, 6b, 6c, 11b, 11c, 11d, 11e i 15b
- [ ] CI completa verda: `ruff check`, `ruff format --check`, `pytest --cov-fail-under=95`, `hassfest`, `hacs/action`
- [ ] Soak de 48 h en una instància real sense cap `ERROR` al log ni entitat encallada a `unavailable`
- [ ] Almenys **un** canvi real observat durant el soak (activació, canvi de fase o desactivació) amb l'event corresponent al bus

---

## Paral·lelització

| Bloc | Notes |
| --- | --- |
| **Seqüencial obligatori** | T1 → T2 → T3 → T4 → T5. És la columna vertebral i no es pot escurçar |
| **Paral·lelitzable després de T5** | T6, T7, T8, T10. Quatre fitxers independents sobre el mateix coordinator |
| **Paral·lelitzable després de T4** | T9, que no depèn del coordinator |
| **Al final** | T11, T12, T13 |

---

## Riscos i mitigacions

| Risc | Impacte | Mitigació |
| --- | --- | --- |
| **`EMERGÈNCIA` no s'observa mai durant el desenvolupament** (15 en 6 anys) | Mitjà. És la fase que més importa | Fixture sintètic marcat com a tal (T2) + normalització sense diacrítics (T3). El camí de codi existeix i està cobert abans de veure'l en viu |
| **`$select=:*,*` deixa de funcionar** o `:created_at` desapareix | Mitjà | `started_at_source` fa la degradació observable; el fallback a `fasedatahora` ja està implementat i testat (T3). Comprovació en viu obligatòria a T4 |
| **La grafia real de `plaacronim` per als PA del PROCICAT** no és cap de les 4 conegudes | Baix. Afecta el nom mostrat | Fallback a l'acrònim cru + `warning` una vegada (T3). Es resol amb la primera activació observada |
| **Un canvi de fase no substitueix la fila sinó que l'edita**, i `:created_at` es queda enganxat a la fase antiga | Mitjà | Els events van per `(acronym, phase)`, no per `started_at` (T8): el canvi es detecta igualment i **cap event es perd**. El que en surt afectat és tot el que deriva de `started_at`: l'atribut `started_at`, i també **`duration_minutes`** de `phase_ended`, que en una fase intermèdia comptaria l'episodi sencer en lloc de només aquella fase. `started_at_source` fa visible d'on surt la marca. És l'obert 3 de [`01`](01-data-sources.md) §14 |
| **El servei canvia de forma sense avís** (és una font pública sense SLA) | Alt | Tolerància amb `.get()` a tota la cadena, `CecatFormatError` que conserva l'estat, `cecat_service_degraded`, i diagnostics amb la resposta crua (T10) |
| **Pocs canvis durant el desenvolupament** i el soak no observa cap event real | Baix | El ritme mesurat és de 0,86 episodis/dia ([`01`](01-data-sources.md) §7.3): 48 h de soak en veuen algun amb alta probabilitat. Si no, els tests amb fixtures reals ja cobreixen tots els camins |
| **Sobrecàrrega d'un servei públic** | Alt reputacionalment | `If-Modified-Since` a cada petició, un sol `GET` per cicle, mínim d'1 min per contracte, per defecte 5 min. El cas normal és un 304 amb cos buit |

---

## Qüestions obertes

Cap bloqueja començar. Les **sis primeres** són exactament les sis que llista el veredicte del
§14 de [`01-data-sources.md`](01-data-sources.md), amb la tasca on es tocarien afegida. Les
**dues últimes no surten del veredicte**: són decisions de disseny que es podrien reobrir i que
es deixen tancades aquí perquè no es discuteixin dues vegades.

| # | Qüestió | Origen | Tasca afectada | Estat |
| :---: | --- | --- | --- | --- |
| 1 | Grafia de `plaacronim` per als PA del PROCICAT | Veredicte, obert 1 | T3 (`PLAN_NAMES`) | Obert. Mitigat amb fallback. Es tanca amb la primera activació observada |
| 2 | `EMERGÈNCIA` mai observada en viu, ni la grafia del seu `plaactivat` | Veredicte, obert 2 | T2 (fixtures sintètics), T3 (normalització), T7 | Obert. Mitigat |
| 3 | Un canvi de fase substitueix la fila o l'edita? | Veredicte, obert 3 | T3 (`resolve_started_at`), T8 (clau d'event) | Obert. Mitigat per la clau `(acronym, phase)` |
| 4 | `plaicona` de VENTCAT i PLASEQTA (404) | Veredicte, obert 4 | Cap | ✅ Resolt: no fem servir `plaicona` com a icona (§11.3 de [`01`](01-data-sources.md)) |
| 5 | Consumir el contenidor Azure de comunicats per a l'històric | Veredicte, obert 5 | Cap | ✅ Resolt: **no**. No és una API documentada (AD-14 de [`04`](04-architecture.md)) |
| 6 | Dos PA distints sota el mateix `plaacronim` es poden confondre en un sol `phase_changed` amb `escalation: true` | Veredicte, obert 6 | T8 (regla d'aparellament), T12 (blueprint) | Obert. **Limitació acceptada, no mitigada**: documentada a §5 de [`04`](04-architecture.md) i a §4.2 i §5 de [`03`](03-feature-spec.md). Depèn de l'obert 1 |
| 7 | Entitat per pla (13-18 binary sensors) | Decisió de disseny, fora del veredicte | Cap | ✅ Resolt: **no**. `plaacronim` no és un conjunt tancat (§7 de [`03`](03-feature-spec.md)) |
| 8 | Filtre per municipi amb `eqag-gzjs` | Decisió de disseny, fora del veredicte | Cap | ✅ Resolt: **no** a la v1. És un mapa de risc estàtic i donaria un fals positiu per als 947 municipis (§5 de [`01`](01-data-sources.md)) |
