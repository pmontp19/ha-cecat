# Protecció Civil Catalunya (`ha-cecat`)

> Integració de Home Assistant per a les **activacions dels plans de Protecció Civil de
> Catalunya** (CECAT): INUNCAT, VENTCAT, NEUCAT, PROCICAT, SISMICAT, TRANSCAT i la resta.
> Converteix el feed oficial de dades obertes de la Generalitat en entitats i events per a
> automatitzacions.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/pmontp19/ha-cecat)
![CI](https://github.com/pmontp19/ha-cecat/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/github/license/pmontp19/ha-cecat)

> 📌 **Instal·lació via repositori personalitzat.** Aquesta integració s'instal·la
> afegint-la com a *repositori personalitzat* a HACS (instruccions a sota). La inclusió al
> repositori *default* de HACS queda com a possible futur; el repositori personalitzat és
> la via primària avui.

Un avís del Meteocat diu què preveu el meteoròleg; això diu si Protecció Civil ha activat
realment un pla, i en quina fase. Les dues integracions estan fetes per conviure i creuar-se
(vegeu [Automatitzacions](#automatitzacions)).

## Fases i activació: dues coses diferents

El CECAT publica cada comunicat amb una **fase** (`PREALERTA`, `ALERTA`, `EMERGÈNCIA`) i un
indicador d'**activació** del pla (`plaactivat`). La integració manté la distinció, perquè la
font la manté: el comunicat de prealerta diu explícitament que "la prealerta no implica
l'activació del pla".

La regla de noms, i és l'única que cal recordar: la família d'events parla de **fases** que
comencen, canvien i acaben (`cecat_plan_phase_started` / `_changed` / `_ended`), i el
`binary_sensor` és l'únic que parla d'**activació**. No és el mateix: una prealerta que
apareix **sí** que dispara `cecat_plan_phase_started` (una fase ha començat) i **no** encén el
binary sensor (el pla no està activat).

| Fase | Què significa | `binary_sensor…_pla_activat` |
| --- | --- | --- |
| `prealerta` | El pla es prepara; no implica activació | `off` |
| `alerta` | El pla s'ha activat | `on` |
| `emergencia` | Situació d'emergència declarada | `on` |
| `unrecognized` | La font ha publicat un literal de fase que la integració no reconeix | depèn de la fila |

## Instal·lació

### Via HACS (repositori personalitzat)

1. Obriu **HACS** al panell lateral de Home Assistant.
2. Aneu a **Settings** → **Custom repositories** (en versions anteriors de HACS: menú ⋮
   → **Custom repositories**).
3. Al camp de text, enganxeu `https://github.com/pmontp19/ha-cecat`.
4. Al desplegable **Category**, seleccioneu **Integration**.
5. Premeu **Add**.
6. Torneu a la pestanya d'integracions de HACS, cerqueu **"Protecció Civil Catalunya"** i
   premeu **Install**.
7. **Reinicieu** Home Assistant.
8. Aneu a **Configuració → Dispositius i serveis → Afegeix integració**, cerqueu
   **"Plans de Protecció Civil"** i seguiu el flux de configuració.

### Manual

1. Copieu `custom_components/cecat/` d'aquest repositori dins la carpeta `custom_components/`
   de la vostra instal·lació de Home Assistant.
2. Reinicieu Home Assistant.
3. Afegiu la integració des de **Configuració → Dispositius i serveis**.

## Configuració

Integració **config-flow-only**: no es configura via `configuration.yaml`. Només es pot crear
**una instància** (el servei és únic a Catalunya; l'intent d'una segona entrada s'avorta).

El flux de configuració fa una petició de prova a la font abans de crear l'entrada: si la font
no respon, veureu l'error i no una entrada trencada. Una resposta buida `[]` és un èxit, no un
error: la majoria de dies no hi ha cap pla actiu.

| Camp | Tipus | Default | Notes |
| --- | --- | --- | --- |
| `scan_interval` | 1–60 min | **5** | Interval de sondeig. Des de **Configuració → Dispositius i serveis → Plans de Protecció Civil → Configurar** es pot canviar sense reiniciar ni recarregar. |

El valor per defecte de 5 min ve de la cadència mesurada de la font (1,84 comunicats/dia en
623 dies, amb un percentil 5 de 14 min entre comunicats consecutius). Cada cicle s'envia
`If-Modified-Since` i la font respon `304` quan res no ha canviat, de manera que el sondeig
freqüent és barat per a tothom.

## Entitats

Totes pengen d'un únic dispositiu de servei anomenat **"Protecció Civil Catalunya"**.

> ℹ️ Els `entity_id` d'aquesta taula corresponen a una instància de Home Assistant configurada
> **en català**. Home Assistant genera l'`entity_id` inicial a partir del nom traduït de
> l'entitat, i el resol amb l'idioma del sistema en el moment de crear-la: en una instància en
> castellà o en anglès seran diferents (p. ex. `sensor.proteccio_civil_catalunya_max_phase` en
> anglès). Si una automatització no troba l'entitat, comprova l'`entity_id` real a **Eines de
> desenvolupament → Estats**.

| Entitat | Descripció |
| --- | --- |
| `sensor.proteccio_civil_catalunya_fase_maxima` | La fase més alta activa a Catalunya: `none` / `prealerta` / `alerta` / `emergencia` / `unrecognized`. Amb el feed buit, `none`. Atributs: `acronyms` (els que són en aquesta fase màxima), `total_plans`. |
| `sensor.proteccio_civil_catalunya_plans` | Nombre de plans presents al feed (qualsevol fase, prealerta inclosa). `0` amb el feed buit. Atributs: `plans` (llista d'objectes, un per fila, amb el detall complet), `activated` (recompte d'activats), `prealerta` (recompte de prealertes). |
| `binary_sensor.proteccio_civil_catalunya_pla_activat` | `on` si hi ha **cap pla realment activat** (`device_class: safety`). Una prealerta sola el deixa a `off`, perquè la prealerta no implica activació. Atribut `acronyms`: els activats. |
| `sensor.proteccio_civil_catalunya_darrera_actualitzacio` | Diagnòstic. La data d'actualització de les dades (capçalera `Last-Modified` de la darrera resposta). Exigida per la llicència de dades obertes, i fa visible una font congelada. |

Esquema de cada element de l'atribut `plans`:

```jsonc
{ "acronym": "INUNCAT",          // plaacronim, cru, majúscules
  "name": "INUNCAT",             // nom llarg del mapatge propi; fallback a l'acrònim
  "phase": "alerta",             // normalitzat: prealerta|alerta|emergencia|unrecognized
  "phase_raw": "ALERTA",         // literal original, sempre present
  "activated": true,             // plaactivat normalitzat; derivat de la fase si no es reconeix
  "started_at": "2026-08-05T11:18:09+00:00",  // :created_at, o fasedatahora, o null
  "started_at_source": "created_at",          // created_at|fasedatahora|null
  "description": "Avís intensitat pluja fins al 04/08  -",  // només .strip(); buit → null
  "communique_url": "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_…pdf" }
```

No hi ha una entitat per pla: el conjunt d'acrònims no és tancat (la font ha publicat
`PENTA`, que no és al registre oficial) i una llista blanca quedaria obsoleta sense avís.
L'atribut `plans` més un template cobreix el cas (vegeu
[Un pla concret](#un-pla-concret-per-exemple-linuncat)).

Amb el feed buit `[]`: `fase_maxima = none`, `plans = 0`, `pla_activat = off`. **Cap entitat
no passa a `unavailable`** per una resposta buida: és l'estat normal de la font.

## Events

Es disparen al bus d'events de Home Assistant per fer-los servir en automatitzacions
(`trigger: event`).

| Event | Quan es dispara |
| --- | --- |
| `cecat_plan_phase_started` | **Sempre** que apareix un parell (pla, fase) que el cicle anterior no tenia: una fila nova de zero, una que hi puja i una que **hi baixa**. Vuit camps, cap d'origen. |
| `cecat_plan_phase_changed` | **A més** del parell anterior, quan un acrònim té exactament una baixa i una alta al mateix cicle i totes dues fases són conegudes. Únic lloc amb semàntica de transició. |
| `cecat_plan_phase_ended` | **Sempre** que un parell (pla, fase) que seguíem desapareix: finals d'episodi i fases intermèdies, amb `duration_minutes`. |
| `cecat_service_degraded` | Un cop quan la font falla de forma persistent, i un altre cop quan es recupera. |

**Cap event no en suprimeix cap altre.** Una transició `ALERTA` → `EMERGÈNCIA` del mateix pla
emet **tres** events: `phase_ended(ALERTA)`, `phase_started(EMERGÈNCIA)` i `phase_changed`
amb `escalation: true`. Tres és el recompte honest: una fase s'ha acabat, una altra ha
començat, i el parell és un canvi. La conseqüència pràctica: **cada automatització ha
d'escoltar un sol carril**; escoltar `phase_started` i `phase_changed` alhora dona dues
notificacions per una sola transició.

> ⚠️ `description` i `communique_url` són **text extern** que prové del servei del CECAT.
> Mai no els renderitzis amb `allow_html: true` (p. ex. Markdown card): tracta'ls com a text
> pla.

Payload de `cecat_plan_phase_started`:

```yaml
event_type: cecat_plan_phase_started
data:
  acronym: INUNCAT
  name: INUNCAT
  phase: alerta              # normalitzat
  phase_raw: ALERTA          # literal original, sempre present
  activated: true
  started_at: "2026-08-05T11:18:09+00:00"
  description: "Avís intensitat pluja fins al 04/08  -"
  communique_url: "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_…pdf"
```

Payload de `cecat_plan_phase_changed`:

```yaml
event_type: cecat_plan_phase_changed
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: prealerta
  previous_phase_raw: PREALERTA
  phase: alerta
  phase_raw: ALERTA
  escalation: true           # només si la fase nova és més greu
  activated: true
  started_at: "2026-08-05T11:18:09+00:00"
```

Payload de `cecat_plan_phase_ended`:

```yaml
event_type: cecat_plan_phase_ended
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: alerta
  previous_phase_raw: ALERTA
  duration_minutes: 4126     # des de started_at fins ara; null si started_at era null
```

Payload de `cecat_service_degraded`:

```yaml
event_type: cecat_service_degraded
data:
  consecutive_failures: 3
  last_error: "TimeoutError"
  recovered: false
```

Dues limitacions documentades d'aquests events:

- **`escalation: true` no garanteix que hagi escalat el mateix pla.** Diversos plans
  d'actuació del PROCICAT reporten el mateix `plaacronim` pelat, i un cicle en què un pla
  s'acaba i un altre comença pot semblar una escalada d'un de sol. És una limitació acceptada
  i inherent a la font; els carrils `phase_started` i `phase_ended` no en pateixen res.
- **`duration_minutes` d'una fase intermèdia pot sortir inflada** si el publicador edita la
  fila en lloc de substituir-la: `started_at` es quedaria a l'inici de l'episodi sencer. Per
  això el payload de l'atribut `plans` porta `started_at_source`. La durada de la fase
  terminal no en depèn.

## Automatitzacions

### Blueprint de notificació (recomanat)

La integració inclou un blueprint de notificació a
[`blueprints/automation/cecat/plan_notification.yaml`](blueprints/automation/cecat/plan_notification.yaml).

[![Open your Home Assistant instance and show the blueprint import dialog.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fpmontp19%2Fha-cecat%2Fmain%2Fblueprints%2Fautomation%2Fcecat%2Fplan_notification.yaml)

Manualment: **Configuració → Automacions i escenes → Blueprints → Importa un blueprint** i
enganxeu l'URL del fitxer anterior.

Escolta **un sol event**, `cecat_plan_phase_started`, i per cada pla que entra en una fase
suficientment greu envia una notificació amb l'acrònim, la fase, la descripció i l'enllaç al
comunicat:

| Camp | Descripció |
| --- | --- |
| `notify_target` | Dispositius de l'app de Home Assistant que rebran la notificació (més d'un possible). |
| `min_phase` | Fase mínima per notificar: `prealerta` / `alerta` / `emergencia`. Per defecte **`alerta`**: amb 589 prealertes en 623 dies, notificar-les totes seria soroll. Una fase `unrecognized` **sempre passa el filtre**: en protecció civil, un desconegut silenciós és pitjor que una notificació de més, i el missatge mostra el literal cru. |
| `plans` | Quins plans notificar, per acrònim. Buit (per defecte) vol dir tots. |

El missatge és un **estat neutre** ("INUNCAT: ara en fase ALERTA") i no afirma cap direcció:
`phase_started` no porta origen i aquesta font no permet inferir-lo honestament.

### El mateix sense blueprint (qualsevol canal de notificació)

Si el teu canal no és un dispositiu de l'app (un grup `notify`, el Telegram, ...), rèplica el
blueprint així. Les condicions i el missatge són els del blueprint:

```yaml
automation:
  - mode: queued
    max: 10
    triggers:
      - trigger: event
        event_type: cecat_plan_phase_started
    variables:
      min_phase: alerta
      plans: []            # buit = tots
    conditions:
      - condition: template
        value_template: >-
          {% set ordre = ['prealerta', 'alerta', 'emergencia'] %}
          {{ trigger.event.data.phase == 'unrecognized'
             or ordre.index(trigger.event.data.phase) >= ordre.index(min_phase) }}
      - condition: template
        value_template: >-
          {{ plans | length == 0 or trigger.event.data.acronym in plans }}
    actions:
      - action: notify.notify
        data:
          title: Protecció Civil Catalunya
          message: >-
            {% if trigger.event.data.phase == 'unrecognized' %}
            {{ trigger.event.data.acronym }}: fase NO RECONEGUDA ("{{ trigger.event.data.phase_raw }}")
            {% else %}
            {{ trigger.event.data.acronym }}: ara en fase {{ trigger.event.data.phase | upper }}
            {% endif %}
```

> ⚠️ L'ordre dels operands de la primera condició importa: el guard `unrecognized` ha d'anar
> **abans** de l'`index()`, perquè Jinja avalua l'`or` amb curtcircuit i un valor sense ordre
> faria petar la plantilla.

### Només emergències

```yaml
automation:
  - triggers:
      - trigger: event
        event_type: cecat_plan_phase_started
        event_data:
          phase: emergencia
    actions:
      - action: notify.mobile_app_telefon_mobil
        data:
          message: "EMERGÈNCIA declarada: {{ trigger.event.data.acronym }}"
```

### Un pla concret, per exemple l'INUNCAT

Sobre l'atribut `plans`, sense cap event: cert quan l'INUNCAT és en alerta o emergència.

```yaml
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.proteccio_civil_catalunya_plans', 'plans')
         | selectattr('acronym', 'eq', 'INUNCAT')
         | selectattr('phase', 'in', ['alerta', 'emergencia'])
         | list | count > 0 }}
```

### Registrar la durada dels episodis

El carril `phase_ended` arriba per a **totes** les fases que s'acaben, també les intermèdies:

```yaml
automation:
  - triggers:
      - trigger: event
        event_type: cecat_plan_phase_ended
    actions:
      - action: logbook.log
        data:
          name: "{{ trigger.event.data.acronym }}"
          message: >-
            La fase {{ trigger.event.data.previous_phase }} s'ha acabat
            ({{ trigger.event.data.duration_minutes }} minuts)
```

### Creuar amb el Meteocat: avís greu i INUNCAT en alerta

Dues integracions a la mateixa instància, cap acoblament. Amb la germana
[`ha-avisoscat`](https://github.com/pmontp19/ha-avisoscat):

```yaml
condition:
  - condition: state
    entity_id: binary_sensor.avisos_meteocat_osona_avis_greu
    state: "on"
  - condition: template
    value_template: >
      {{ state_attr('sensor.proteccio_civil_catalunya_plans', 'plans')
         | selectattr('acronym', 'eq', 'INUNCAT')
         | selectattr('phase', 'in', ['alerta', 'emergencia'])
         | list | count > 0 }}
```

## Font de dades i sondeig

| | |
| --- | --- |
| Font | [Activacions dels plans de protecció civil](https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf), Dades Obertes de la Generalitat de Catalunya |
| Clau API | No en fa falta: font pública, sense clau ni quota |
| Peticions | `GET` amb `If-Modified-Since`; `304` quan res no ha canviat |
| Diagnòstic | **Configuració → Dispositius i serveis → Plans de Protecció Civil → Descarrega la diagnosi**: última resposta crua, `Last-Modified`, literals no reconeguts acumulats i recompte de cicles fallits |

Quan la font falla (xarxa, timeout, cos que no és una llista):

- Les entitats **conserven l'últim estat bo**; no es buiden ni passen a `unavailable`.
- **Cap event no es dispara en un cicle fallit**: un `[]` vàlid sí que és una desactivació,
  un error no.
- En arribar a 3 cicles fallits seguits es dispara `cecat_service_degraded` (i un altre cop,
  amb `recovered: true`, en recuperar-se).

## Limitacions conegudes

Tres limitacions **estructurals**, de la font mateixa; no es resoldran:

1. **Cap territori afectat.** La integració no pot dir si el teu municipi està afectat, i
   qualsevol cosa que ho pretengui estarà mentint: la font no publica territori per
   activació, i les comarques només són prosa dins del PDF del comunicat.
2. **Cap històric.** La font és només estat actual, mutat al lloc. Si Home Assistant està
   aturat quan un pla s'activa i es desactiva, l'episodi no ha existit i no es pot recuperar.
3. **La desactivació es detecta per absència**, amb la resolució de l'interval de sondeig (5
   minuts per defecte). El CECAT gairebé no publica comunicats de tancament: 1 en 623 dies.
   L'instant exacte de desactivació no es pot conèixer.

I dues d'operatives, assumides i documentades amb el detall a
[`docs/01-data-sources.md`](docs/01-data-sources.md):

- La fase `EMERGÈNCIA` mai s'ha observat en un payload real (n'hi va haver 15 en 6 anys, segons
  el dataset estadístic): el seu camí de codi està cobert per un fixture sintètic marcat com a
  tal.
- El fals positiu d'`escalation: true` amb el PROCICAT descrit a la secció [Events](#events).

## Eliminació

1. Esborreu l'entrada: **Configuració → Dispositius i serveis → Plans de Protecció Civil →
   Suprimeix l'entrada**. Això elimina el dispositiu i totes les entitats.
2. Si voleu treure la integració del tot, desinstal·leu-la des de **HACS** (o esborreu
   `custom_components/cecat/` si la vau instal·lar manualment) i reinicieu Home Assistant.
3. Opcionalment, esborreu les automatitzacions creades des del blueprint i el blueprint
   importat (**Configuració → Automacions i escenes → Blueprints**).

No hi ha dades personals ni ubicacions emmagatzemades: la font no en té, i la diagnosi no
n'exporta.

## Desenvolupament

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements_dev.txt

.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/python -m pytest tests/ --cov=custom_components/cecat --cov-fail-under=95
```

Documentació de disseny i recerca a [`docs/`](docs/): [fonts de dades](docs/01-data-sources.md),
[integracions existents](docs/02-existing-integrations.md), [especificació
funcional](docs/03-feature-spec.md), [arquitectura](docs/04-architecture.md), [pla
d'implementació](docs/05-implementation-plan.md).

Voleu contribuir? Mireu [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Integracions germanes

- [`ha-avisoscat`](https://github.com/pmontp19/ha-avisoscat): avisos de temps sever del
  Meteocat. L'encaix natural per creuar "avís greu" amb "fase d'activació del pla".
- [`ha-incendiscat`](https://github.com/pmontp19/ha-incendiscat): incendis forestals i Pla
  Alfa (Agents Rurals). Comparteix convencions d'enginyeria amb aquesta integració.

## Avís legal i atribució

Projecte **no oficial, no afiliat ni aprovat** pel CECAT ni per la Generalitat de Catalunya.
Aquesta integració **no substitueix mai** els canals oficials de Protecció Civil.

Dades: **Generalitat de Catalunya. Departament d'Interior i Seguretat Pública. Direcció
General de Protecció Civil.** Publicades al portal de Dades Obertes sota la
[Llicència oberta d'ús d'informació de Catalunya](https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies),
que exigeix citar la font i la data d'actualització. La data d'actualització de les dades
reutilitzades queda exposada en tot moment per l'entitat
`sensor.proteccio_civil_catalunya_darrera_actualitzacio` (capçalera `Last-Modified` de la
darrera resposta rebuda). Font i documentació verificades per darrera vegada el 2026-08-06.

Llicència del codi: [MIT](LICENSE).
