# Feature spec: `ha-cecat`

Especificació funcional de la v1. Deliberadament petita: **quatre entitats i una família
d'events**. Cada decisió apunta a l'evidència de [`01-data-sources.md`](01-data-sources.md) o al
precedent de [`02-existing-integrations.md`](02-existing-integrations.md).

Identificadors, claus de traducció i noms d'event en **anglès** (convenció dels germans); les
cadenes de cara a l'usuari surten de `translations/{ca,es,en}.json`, amb el català com a llengua
de referència.

---

## 1. Visió general

| | |
| --- | --- |
| Domini | `cecat` |
| Nom | Protecció Civil Catalunya |
| `integration_type` | `service` |
| `iot_class` | `cloud_polling` |
| `single_config_entry` | **`true`** |
| `requirements` | `[]` |
| Plataformes | `sensor`, `binary_sensor` |
| Entitats | **4** (3 + 1 de diagnòstic) |
| Events | **4** (3 de domini + 1 de degradació) |
| Accions de servei | **cap** |
| Objectiu `quality_scale` | 🥈 silver |

La pregunta que la integració respon és una i concreta: **hi ha algun pla de Protecció Civil
activat ara mateix a Catalunya, i en quina fase?**

`single_config_entry: true` no és una preferència: la font declara "Sense informació
geogràfica" i **no existeix cap dataset amb el territori afectat per activació**
([`01`](01-data-sources.md) §5). Sense eix territorial, una segona entrada seria una còpia
idèntica de la primera amb `unique_id` diferents i events duplicats.

---

## 2. Config flow

### 2.1 Setup inicial

**Un sol pas, sense res obligatori.** No hi ha clau d'API, ni quota, ni comarca, ni radi: no hi
ha res que l'usuari hagi de saber.

| Camp | Tipus | Per defecte | Rang |
| --- | --- | --- | --- |
| `scan_interval` | minuts (`NumberSelector`) | **5** | 1 a 60 |

Abans de crear l'entrada, el flow fa **una petició de prova** a l'endpoint (regla 🥉
`test_before_configure`):

| Resultat de la prova | Comportament |
| --- | --- |
| HTTP 200 amb JSON que és una llista (inclosa `[]`) | Crea l'entrada |
| HTTP 200 amb JSON que **no** és una llista | `cannot_connect`, missatge de format inesperat |
| Timeout, error de xarxa, 5xx | `cannot_connect` |
| 4xx | `cannot_connect` (no hi ha autenticació, per tant un 4xx és un canvi de contracte) |

`[]` **és un èxit**, no un error: és l'estat de normalitat i és el més probable en qualsevol
instant donat ([`01`](01-data-sources.md) §4, trap 2). Un flow que exigís almenys una fila
fallaria la majoria dels dies.

`async_set_unique_id(DOMAIN)` + `_abort_if_unique_id_configured()`, redundant amb
`single_config_entry` però barat.

### 2.2 Options flow

Reconfigurable després del setup: **només `scan_interval`**. Un canvi reprograma el
coordinator sense recarregar l'entrada.

### 2.3 Sense YAML

Integració config-flow-only. No es dona suport a `configuration.yaml`, igual que els germans.

---

## 3. Entitats

### 3.1 `sensor.cecat_max_phase` ⭐ l'entitat principal

La fase més alta activa a Catalunya. És la que va al dashboard i a les automacions.

| | |
| --- | --- |
| `translation_key` | `max_phase` |
| `device_class` | `SensorDeviceClass.ENUM` |
| `options` | `["none", "prealerta", "alerta", "emergencia", "unknown"]` |
| Estat quan la resposta és `[]` | **`none`** |
| Icona | `mdi:shield-alert-outline` (fixa; **no** `plaicona`, vegeu [`01`](01-data-sources.md) §11.3) |

Ordre de severitat: `none` < `prealerta` < `alerta` < `emergencia`. `unknown` és la vàlvula
d'escapament: si `plafase` porta un literal que no reconeixem, l'estat és `unknown` i s'emet un
`warning` **una sola vegada** per literal (patró de `nina`, [`02`](02-existing-integrations.md) §2).

Normalització del literal: `casefold()` **i sense diacrítics**, perquè el valor documentat és
`EMERGÈNCIA` amb accent obert i mai s'ha observat en viu ([`01`](01-data-sources.md) trap 14).
`EMERGÈNCIA`, `EMERGENCIA` i `emergència` han de donar el mateix estat.

Atributs:

| Atribut | Contingut |
| --- | --- |
| `plans` | Llista d'acrònims que estan en aquesta fase màxima (p. ex. `["INUNCAT"]`) |
| `total_plans` | Nombre total de files, en qualsevol fase |

### 3.2 `sensor.cecat_active_plans`

Recompte de plans presents al feed, amb el detall complet als atributs. És l'única entitat que
transporta la informació per pla, i és el que evita haver de crear entitats dinàmiques.

| | |
| --- | --- |
| `translation_key` | `active_plans` |
| Estat | Enter. **`0`** quan la resposta és `[]` |
| `state_class` | `MEASUREMENT` |
| Unitat | `plans` (via `translations`) |

Atributs:

| Atribut | Contingut |
| --- | --- |
| `plans` | Llista d'objectes, un per fila. Vegeu l'esquema avall |
| `activated` | Recompte de files amb `plaactivat == "SI"` |
| `prealerta` | Recompte de files en fase `prealerta` |

Esquema de cada element de `plans`:

```jsonc
{ "acronym": "INUNCAT",          // plaacronim, cru, majúscules
  "name": "INUNCAT",             // nom llarg del mapatge propi; fallback a l'acrònim
  "phase": "alerta",             // normalitzat: prealerta|alerta|emergencia|unknown
  "phase_raw": "ALERTA",         // literal original, sempre present
  "activated": true,             // plaactivat == "SI"
  "started_at": "2026-08-05T11:18:09+00:00",  // :created_at, o fasedatahora, o null
  "started_at_source": "created_at",          // created_at|fasedatahora|null
  "description": "Avís intensitat pluja fins al 04/08  -",  // només .strip(); buit → null
  "communique_url": "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_…pdf" }
```

Decisions de l'esquema, cada una amb la seva raó:

| Decisió | Motiu |
| --- | --- |
| `name` surt d'un mapatge propi, **no** de `planom` | `planom` és idèntic a `plaacronim` a 5/5 captures, contra la seva pròpia documentació ([`01`](01-data-sources.md) trap 4) |
| `phase_raw` sempre present al costat de `phase` | Un literal nou ha de ser visible a l'usuari i als diagnostics sense esperar una release |
| `started_at` prefereix `:created_at` | És ISO-8601 en UTC i coincideix al minut amb `fasedatahora` ([`01`](01-data-sources.md) §7.2). Evita parsejar `DD/MM/YYYY HH:MM` i endevinar el fus |
| `started_at_source` explícit | Fa auditable quina de les dues fonts s'ha fet servir, i fa visible el dia que `:created_at` desaparegui |
| `communique_url` és una cadena opaca | Pot contenir accents i apòstrofs sense codificar ([`01`](01-data-sources.md) trap 7). No es valida ni es reconstrueix |
| Cap camp de territori | No existeix ([`01`](01-data-sources.md) §5) |

### 3.3 `binary_sensor.cecat_plan_activated`

La pregunta binària: **hi ha algun pla realment activat?**

| | |
| --- | --- |
| `translation_key` | `plan_activated` |
| `device_class` | `BinarySensorDeviceClass.SAFETY` |
| `on` | Almenys una fila amb `plaactivat == "SI"` |
| `off` | Cap fila activada, incloent-hi el cas de només prealertes i el cas `[]` |

**Aquesta entitat és el motiu pel qual la prealerta es modela com a estat de primera classe.**
Una prealerta deixa `binary_sensor` a `off` (el pla no està activat: ho diu la font, "la
prealerta no implica l'activació del pla") però deixa `sensor.cecat_max_phase` a `prealerta`.
Les dues coses són certes alhora i cap consumidor conegut d'aquesta font les distingeix
([`02`](02-existing-integrations.md) §6).

Atributs: `plans` amb els acrònims activats.

### 3.4 `sensor.cecat_last_updated` (diagnòstic)

| | |
| --- | --- |
| `translation_key` | `last_updated` |
| `device_class` | `SensorDeviceClass.TIMESTAMP` |
| `entity_category` | `DIAGNOSTIC` |
| Valor | El `Last-Modified` de la resposta (equival a `rowsUpdatedAt` i a `X-SODA2-Truth-Last-Modified`) |
| Si no hi ha capçalera | `None` |

No és decoració: **la llicència de dades obertes de la Generalitat exigeix publicar la data
d'actualització** de la informació reutilitzada ([`01`](01-data-sources.md) §11). Exposar-la com
a entitat és la manera de complir-ho dins de Home Assistant. A més fa immediatament visible una
font congelada, que amb `[]` com a estat normal és indistingible d'una font sana.

### 3.5 Dispositiu i atribució

Un únic dispositiu per entrada, `DeviceInfo(entry_type=SERVICE)`:

| Camp | Valor |
| --- | --- |
| `name` | Protecció Civil Catalunya |
| `manufacturer` | Generalitat de Catalunya |
| `model` | CECAT, Direcció General de Protecció Civil |
| `configuration_url` | `https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf` |

`_attr_attribution` a totes les entitats: *"Generalitat de Catalunya. Departament d'Interior i
Seguretat Pública. Direcció General de Protecció Civil."*

### 3.6 Diagnostics

`diagnostics.py` exporta: config entry redactada, l'última resposta **crua** (útil precisament
perquè el text és brut), `Last-Modified`, els literals de `plafase` i `plaacronim` no reconeguts
acumulats, i el recompte de cicles fallits consecutius. No hi ha dades personals ni coordenades
a redactar: la font no en té.

---

## 4. Events

Una sola família, `cecat_plan_*`, més un event de degradació del servei. Mateix patró que
`ha-incendiscat` ([`02`](02-existing-integrations.md) §5), que és el que fa que un blueprint de
notificació sigui trivial.

**La identitat d'un episodi és `(acronym, phase)`, mai `:id` ni el hash de la fila.** Motiu
mesurat: `comunicatpdf` canvia diverses vegades dins de la mateixa fase sense que canviï
`fasedatahora` (l'incident `I-125912` en va tenir 5) i `:id` canvia quan el publicador
substitueix la fila en un canvi de fase ([`01`](01-data-sources.md) traps 11 i §7.2). Qualsevol
altra clau genera events duplicats o els perd.

### 4.1 `cecat_plan_activated`

Es dispara quan apareix un parell `(acronym, phase)` que el cicle anterior no tenia, i la fase
no és `none`.

```yaml
event_type: cecat_plan_activated
data:
  acronym: INUNCAT
  name: INUNCAT
  phase: alerta
  phase_raw: ALERTA
  activated: true
  started_at: "2026-08-05T11:18:09+00:00"
  description: "Avís intensitat pluja fins al 04/08  -"
  communique_url: "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_…pdf"
```

### 4.2 `cecat_phase_change`

Es dispara quan un `acronym` que ja seguíem canvia de fase, en qualsevol direcció.

```yaml
event_type: cecat_phase_change
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: prealerta
  phase: alerta
  escalation: true          # phase > previous_phase en l'ordre de severitat
  activated: true
  started_at: "2026-08-05T11:18:09+00:00"
```

És l'event que captura la transició real observada a la font: `I-125912` va passar de prealerta
(02/08 18:47) a activat (03/08 18:51) mantenint el mateix número d'incident
([`01`](01-data-sources.md) §7.2).

### 4.3 `cecat_plan_deactivated`

Es dispara quan un `acronym` que seguíem **desapareix** de la resposta.

```yaml
event_type: cecat_plan_deactivated
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: alerta
  duration_minutes: 4126     # des de started_at fins ara; null si started_at era null
```

⚠️ **Aquest event és per absència, no per anunci.** El CECAT gairebé no publica comunicats de
tancament: 1 sol `DESACTIVACIO` en 623 dies, i el comunicat de prealerta diu explícitament que
la situació s'acaba "sense necessitat d'una comunicació de tancament"
([`01`](01-data-sources.md) §7.4). Conseqüències que cal documentar al README:

- L'instant de desactivació té la resolució de l'interval de sondeig, no és exacte.
- Si Home Assistant està aturat mentre un pla s'activa i es desactiva, l'episodi no existeix.
  La font no té història ([`01`](01-data-sources.md) §7.1) i no es pot recuperar.
- **No s'emet en cap cicle fallit.** Si la petició falla o el JSON no és una llista, l'estat
  anterior es manté intacte i no es dispara res. Un `[]` **vàlid** sí que és una desactivació;
  un error no.

### 4.4 `cecat_service_degraded`

Diagnòstic, mateix nom i semàntica que a `ha-incendiscat`. Es dispara en arribar al llindar de
cicles fallits consecutius, i un altre quan es recupera.

```yaml
event_type: cecat_service_degraded
data:
  consecutive_failures: 3
  last_error: "TimeoutError"
  recovered: false
```

---

## 5. Blueprint inclòs

Un sol blueprint, `blueprints/automation/cecat/plan_notification.yaml`, amb tres selectors:

| Entrada | Tipus | Per defecte |
| --- | --- | --- |
| `notify_target` | `selector: device` o `action` | (obligatori) |
| `min_phase` | `select`: `prealerta` / `alerta` / `emergencia` | `alerta` |
| `plans` | `select` múltiple d'acrònims coneguts, buit = tots | buit |

Escolta `cecat_plan_activated` i `cecat_phase_change` (només amb `escalation: true`), filtra per
`min_phase` i per `plans`, i envia el missatge amb `description` i l'enllaç al comunicat.

Per defecte `alerta` i **no** `prealerta`: amb 589 prealertes en 623 dies
([`01`](01-data-sources.md) §4) un blueprint que notifiqués prealertes seria soroll i faria que
l'usuari el silenciés, perdent també les alertes.

---

## 6. Patrons d'automació que suportem

| Vull… | Com |
| --- | --- |
| Avisar-me quan s'activi qualsevol pla | Trigger d'estat sobre `binary_sensor.cecat_plan_activated` a `on`, o el blueprint |
| Avisar-me només d'emergències | Trigger d'event `cecat_plan_activated` amb condició `phase == emergencia` |
| Saber si l'INUNCAT concretament està en alerta | Template sobre l'atribut `plans` de `sensor.cecat_active_plans`. Vegeu el README |
| Creuar amb el Meteocat: avís greu **i** INUNCAT en alerta | Condició que creua `ha-avisoscat` i `ha-cecat`. Dues integracions a la mateixa instància, cap acoblament ([`02`](02-existing-integrations.md) §3) |
| Registrar la durada dels episodis | Escoltar `cecat_plan_deactivated` i llegir `duration_minutes` |

Exemple del cas per pla concret, que va al README:

```yaml
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.cecat_active_plans', 'plans')
         | selectattr('acronym', 'eq', 'INUNCAT')
         | selectattr('phase', 'in', ['alerta', 'emergencia'])
         | list | count > 0 }}
```

---

## 7. Fora d'abast de la v1, amb el motiu

| No farem | Motiu |
| --- | --- |
| **Una entitat per pla** (13-18 binary sensors) | `plaacronim` **no és un conjunt tancat**: `PENTA` no és al registre de la Generalitat i `NOPLA` no és un pla ([`01`](01-data-sources.md) §3.2, trap 5). Una llista blanca quedaria obsoleta sense avís, i 18 entitats a `off` permanent per a un usuari que en vol una és soroll al registre. L'atribut `plans` més un template cobreix el cas |
| **Entitats dinàmiques** que apareixen i desapareixen amb l'activació | Trenca l'estabilitat del registre d'entitats i les gràfiques de l'historial. `nina` va resoldre això amb "message slots" i és pitjor que el problema ([`02`](02-existing-integrations.md) §2) |
| **Filtre o sensor per municipi/comarca** | La font no publica territori per activació. Construir-lo sobre `eqag-gzjs` (mapa de risc **estàtic**) donaria "el teu municipi està afectat" cada vegada que s'activa l'INUNCAT en qualsevol punt de Catalunya, perquè els 947 municipis hi consten. Un senyal fals amb aparença de precisió ([`01`](01-data-sources.md) §5) |
| **Parsejar el PDF del comunicat** per extreure comarques o restriccions | Dues capes d'heurística (extracció de PDF + mapatge de zones meteorològiques a comarques) sobre text lliure extern. I les "comarques" del comunicat sovint són **zones del SMC**, no comarques ([`01`](01-data-sources.md) §5) |
| **Històric d'activacions** | La font és només estat actual. Els dos datasets estadístics del portal estan aturats des del 2023-08-14 i acaben el 2022 ([`01`](01-data-sources.md) §10) |
| **Consumir el contenidor Azure de comunicats** | És llistable públicament i ha estat clau per a la recerca, però **no és una API documentada**. Dependre'n en runtime seria construir sobre un detall d'implementació ([`01`](01-data-sources.md) §14, obert 5) |
| **Fer servir `plaicona`** com a icona de les entitats | Són els símbols oficials dels plans i la llicència en restringeix l'ús ([`01`](01-data-sources.md) §11.3). A més `ico_VENTCAT.png` dona 404 |
| **`geo_location`** o qualsevol entitat amb coordenades | Cap geometria a la font |
| Accions de servei | Els events cobreixen el cas i el blueprint és la UX escollida, igual que als germans |

---

## 8. Criteris d'acceptació de la v1

| # | Criteri |
| :---: | --- |
| 1 | Amb `[]` a la resposta: `max_phase = none`, `active_plans = 0`, `plan_activated = off`. **Cap entitat a `unavailable`** |
| 2 | Amb la captura real de prealerta (2024-12-02): `max_phase = prealerta`, `active_plans = 1`, `plan_activated = **off**` |
| 3 | Amb la captura real d'alerta (2026-08-06): `max_phase = alerta`, `plan_activated = on`, `started_at` = `2026-08-05T11:18:09+00:00` amb `started_at_source = created_at` |
| 4 | Amb la captura real de dos plans (2026-01-19): `active_plans = 2` i `plans` amb INUNCAT i NEUCAT |
| 5 | Amb un fixture sintètic d'`EMERGÈNCIA` (marcat com a sintètic): `max_phase = emergencia`. També amb `EMERGENCIA` sense accent |
| 6 | `plafase` amb un literal desconegut: `max_phase = unknown`, `warning` una sola vegada, cap excepció |
| 7 | `plaacronim` desconegut (`PENTA`, `NOPLA`): fila ingerida, `name` = l'acrònim, `warning` una vegada |
| 8 | `comunicatpdf` absent, `plaicona` absent, `descripcio` buida: cap `KeyError`, atributs a `None` |
| 9 | `comunicatpdf.url` amb accents i apòstrof: es propaga tal qual sense petar ni recodificar |
| 10 | `fasedatahora` il·legible o absent i sense `:created_at`: `started_at = None`, `started_at_source = null`, cap excepció |
| 11 | Transició prealerta → alerta del mateix acrònim: **un** `cecat_phase_change` amb `escalation: true`, i **cap** `cecat_plan_activated` |
| 12 | `comunicatpdf` canvia sense canviar `plafase`: **cap** event. Només canvia l'atribut |
| 13 | Fila que desapareix en un cicle **vàlid**: un `cecat_plan_deactivated` amb `duration_minutes` |
| 14 | Fila que desapareix perquè la petició **falla**: cap event, estat anterior intacte |
| 15 | HTTP 304 a `If-Modified-Since`: estat anterior intacte, cap event, cap entitat a `unavailable` |
| 16 | Config flow: `[]` a la petició de prova crea l'entrada; timeout dona `cannot_connect` |
| 17 | Les quatre entitats tenen clau als tres `translations/{ca,es,en}.json` i `hassfest` passa |
| 18 | Cobertura ≥ 95%, `ruff check` i `ruff format --check` en verd |
