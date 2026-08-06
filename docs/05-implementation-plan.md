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
(sense `UNKNOWN`), `normalise_phase()` amb `casefold()` i sense diacrítics,
`resolve_activated()` amb la mateixa normalització i fallback a la fase,
`resolve_started_at()` amb `:created_at` primer i `fasedatahora` de reserva,
`PlanActivation.from_row()` tolerant, `PLAN_NAMES` des del registre oficial, `CecatState`. Cap
import de Home Assistant.

**Criteris d'acceptació.**
- [ ] `camps_sistema_2026_08_06.json` → `phase = ALERTA`, `activated = True`, `started_at = 2026-08-05T11:18:09+00:00` (el `.349Z` truncat a segons), `started_at_source = "created_at"`
- [ ] `alerta_2026_08_06.json`, que és la **mateixa fila sense camps de sistema** → `started_at = 2026-08-05T11:18:00+00:00`, `started_at_source = "fasedatahora"`. Els dos camins donen el mateix minut sobre dades reals
- [ ] `prealerta_2024_12_02.json` → `phase = PREALERTA`, **`activated = False`**, `description` amb el `\n` conservat
- [ ] `EMERGÈNCIA`, `EMERGENCIA`, `emergència` i ` Emergencia ` donen tots `Phase.EMERGENCIA`
- [ ] `plaactivat` = `SI`, `si`, ` SI ` → `activated = True`; `NO`, `no`, ` No ` → **`activated = False`**
- [ ] `plaactivat` **absent**, buit, o amb un literal inesperat (`true`, `Activat`), sobre una fila d'`EMERGÈNCIA` o d'`ALERTA` → **`activated = True`**, i el literal cru queda exposat perquè el coordinator hi pugui fer el `warning`
- [ ] Els mateixos valors irreconeixibles sobre una fila de `PREALERTA` → `activated = False` (mana la fase, AD-6)
- [ ] `plaactivat` irreconeixible **i** `plafase` irreconeixible → `activated = False`, cap excepció, els dos literals conservats
- [ ] Fase desconeguda → `Phase.UNKNOWN`, i `phase_raw` conserva el literal
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
- [ ] L'entitat de recompte és `sensor.cecat_plans` amb `translation_key = "plans"`, **no** `active_plans`: compta files en qualsevol fase, prealerta inclosa
- [ ] `buit` → `max_phase = "none"`, `plans = 0`. **Cap entitat a `unavailable`**
- [ ] `prealerta_2024_12_02` → `max_phase = "prealerta"`, `plans = 1`, atribut `activated = 0`, `prealerta = 1`
- [ ] `alerta_2026_08_06` → `max_phase = "alerta"`; l'element de `plans` té els 9 camps del §3.2 de [`03`](03-feature-spec.md)
- [ ] `dos_plans_2026_01_19` → `plans = 2`, atribut `plans` **ordenat per `(acronym, phase)`** (INUNCAT abans que NEUCAT)
- [ ] `dos_procicat_SYNTHETIC` (mateix acrònim, fases diferents) → `plans = **2**`, **les dues** files a l'atribut `plans`, en ordre determinista per `(acronym, phase)`. És el criteri que falla si l'estat s'indexa per l'acrònim sol
- [ ] `emergencia_SYNTHETIC` → `max_phase = "emergencia"`
- [ ] `fase_desconeguda_SYNTHETIC` → `max_phase = "unknown"` i `phase_raw` visible a `plans`
- [ ] Una fila desconeguda i una `ALERTA` alhora → `max_phase = "alerta"` (la desconeguda no guanya)
- [ ] `last_updated` parseja el `Last-Modified` a `datetime` amb tz; `None` si falta la capçalera
- [ ] `options` de `max_phase` inclou `"unknown"`; `entity_category` de `last_updated` és `DIAGNOSTIC`

**Verificació.** `pytest tests/test_sensor.py` verd.
**Dependències.** T5. **Mida.** M

### T7: Binary sensor

**Descripció.** `binary_sensor.py` amb `plan_activated`, `device_class = SAFETY`.

**Criteris d'acceptació.**
- [ ] `alerta_2026_08_06` → `on`, atribut `plans = ["INUNCAT"]`
- [ ] `prealerta_2024_12_02` → **`off`** (el pla no està activat), mentre `max_phase` és `prealerta`
- [ ] `buit` → `off`
- [ ] `emergencia_SYNTHETIC` → `on`
- [ ] `emergencia_plaactivat_rar_SYNTHETIC` → **`on`** amb `plaactivat` = `Si`, amb ` SI `, i **amb el camp absent**. Cap dels tres pot deixar un sensor `SAFETY` a `off` durant una emergència (§3.3 de [`03`](03-feature-spec.md), criteri 5b)
- [ ] Cap comparació literal `== "SI"` al mòdul: `is_on` llegeix `activated`, que ja ve normalitzat de `models.py`

**Verificació.** `pytest tests/test_binary_sensor.py` verd. El segon criteri és la prova que la
prealerta es modela com a estat de primera classe i no com a "no activat"; el cinquè és la
prova que la tolerància de la trap 14 arriba també a `plaactivat` i no només a `plafase`.
**Dependències.** T5. **Mida.** S

### T8: Events

**Descripció.** `_emit_events()` al coordinator: `cecat_plan_phase_started`,
`cecat_plan_phase_changed`, `cecat_plan_phase_ended`, `cecat_service_degraded`. Diferència de
claus `(acronym, phase)` més la regla d'aparellament del §5 de [`04`](04-architecture.md).

**Criteris d'acceptació.**
- [ ] Els noms d'event són `cecat_plan_phase_started` / `_changed` / `_ended`. **Cap event no es diu `activated`**: aquest nom és exclusiu del binary sensor, que té la condició de veritat contrària per a la prealerta (§4 de [`03`](03-feature-spec.md))
- [ ] `{}` → `{(INUNCAT, alerta)}` dispara **un** `cecat_plan_phase_started` amb els 8 camps del §4.1 de [`03`](03-feature-spec.md)
- [ ] `{(INUNCAT, prealerta)}` → `{(INUNCAT, alerta)}` dispara **un** `cecat_plan_phase_changed` amb `escalation: true` i **cap** `phase_started` ni `phase_ended`
- [ ] `{(INUNCAT, alerta)}` → `{(INUNCAT, prealerta)}` dispara `cecat_plan_phase_changed` amb `escalation: false`
- [ ] `{}` → `{(PROCICAT, prealerta), (PROCICAT, alerta)}` dispara **dos** `cecat_plan_phase_started`, un per fase. Cap dels dos es perd i no es col·lapsen
- [ ] Cas ambigu: `{(PROCICAT, prealerta), (PROCICAT, alerta)}` → `{(PROCICAT, emergencia)}` dispara **dos** `phase_ended` i **un** `phase_started`, i **cap** `phase_changed`. No s'aparella res quan hi ha més d'una alta o més d'una baixa per acrònim
- [ ] `{(INUNCAT, alerta)}` → `{}` en un cicle **vàlid** dispara `cecat_plan_phase_ended` amb `duration_minutes` calculat
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
- [ ] L'export conté: config entry, **resposta crua** de l'últim cicle, `Last-Modified`, `unknown_phases`, `unknown_acronyms`, `consecutive_failures`
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
- [ ] `icons.json` assigna icones `mdi:` fixes. **Cap referència a `plaicona`** (§11.3 de [`01`](01-data-sources.md))
- [ ] `test_translations.py` compara les claus dels tres fitxers i falla si divergeixen

**Verificació.** `validate.yml` verd + `pytest tests/test_translations.py`.
**Dependències.** T6, T7, T9. **Mida.** S

### T12: Blueprint de notificació

**Descripció.** `blueprints/automation/cecat/plan_notification.yaml` del §5 de
[`03`](03-feature-spec.md), amb `min_phase` per defecte a `alerta`.

**Criteris d'acceptació.**
- [ ] `min_phase` per defecte és **`alerta`**, no `prealerta` (589 prealertes en 623 dies)
- [ ] El filtre per `plans` buit vol dir "tots"
- [ ] Escolta `cecat_plan_phase_started` i `cecat_plan_phase_changed` amb `escalation: true`
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

- [ ] Tots els criteris d'acceptació del §8 de [`03-feature-spec.md`](03-feature-spec.md) marcats: els 18 numerats més 3b, 4b i 5b
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
| **Un canvi de fase no substitueix la fila sinó que l'edita**, i `:created_at` es queda enganxat a la fase antiga | Mitjà | Els events van per `(acronym, phase)`, no per `started_at` (T8): el canvi es detecta igualment. Només l'atribut `started_at` seria vell, i `started_at_source` ho fa visible |
| **El servei canvia de forma sense avís** (és una font pública sense SLA) | Alt | Tolerància amb `.get()` a tota la cadena, `CecatFormatError` que conserva l'estat, `cecat_service_degraded`, i diagnostics amb la resposta crua (T10) |
| **Pocs canvis durant el desenvolupament** i el soak no observa cap event real | Baix | El ritme mesurat és de 0,86 episodis/dia ([`01`](01-data-sources.md) §7.3): 48 h de soak en veuen algun amb alta probabilitat. Si no, els tests amb fixtures reals ja cobreixen tots els camins |
| **Sobrecàrrega d'un servei públic** | Alt reputacionalment | `If-Modified-Since` a cada petició, un sol `GET` per cicle, mínim d'1 min per contracte, per defecte 5 min. El cas normal és un 304 amb cos buit |

---

## Qüestions obertes

Cap bloqueja començar. Les **cinc primeres** són exactament les cinc que llista el veredicte del
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
| 6 | Entitat per pla (13-18 binary sensors) | Decisió de disseny, fora del veredicte | Cap | ✅ Resolt: **no**. `plaacronim` no és un conjunt tancat (§7 de [`03`](03-feature-spec.md)) |
| 7 | Filtre per municipi amb `eqag-gzjs` | Decisió de disseny, fora del veredicte | Cap | ✅ Resolt: **no** a la v1. És un mapa de risc estàtic i donaria un fals positiu per als 947 municipis (§5 de [`01`](01-data-sources.md)) |
