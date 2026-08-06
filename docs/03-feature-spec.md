# Feature spec: `ha-cecat`

Especificació funcional de la v1. Deliberadament petita: **quatre entitats i una família
d'events**. Cada decisió apunta a l'evidència de [`01-data-sources.md`](01-data-sources.md) o al
precedent de [`02-existing-integrations.md`](02-existing-integrations.md).

Identificadors, claus de traducció i noms d'event en **anglès** (convenció dels germans); les
cadenes de cara a l'usuari surten de `translations/{ca,es,en}.json`, amb el català com a llengua
de referència.

> ⚠️ **Sobre els `entity_id` que apareixen en aquest document.** Amb
> `_attr_has_entity_name = True` i `DeviceInfo(name="Protecció Civil Catalunya")`, Home Assistant
> construeix l'`entity_id` com a **slug del nom del dispositiu + nom traduït de l'entitat**, no a
> partir del domini ni de la `translation_key`. Els identificadors que es documenten aquí
> (`sensor.proteccio_civil_catalunya_fase_maxima` i companyia) són doncs els d'una instància **en
> català**, i una instància en castellà o en anglès en generarà uns altres, perquè el nom es
> resol amb l'idioma del sistema en el moment de crear l'entitat. Les `translation_key`
> (`max_phase`, `plans`, `plan_activated`, `last_updated`) i els noms d'event **no** depenen de
> l'idioma. És exactament la convenció i l'advertiment que ja documenta `ha-incendiscat`
> (`sensor.incendis_catalunya_darrera_actualitzacio`), i els exemples copiables s'han d'adaptar
> comprovant l'`entity_id` real a **Eines de desenvolupament → Estats**.

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

### 3.1 `sensor.proteccio_civil_catalunya_fase_maxima` ⭐ l'entitat principal

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

### 3.2 `sensor.proteccio_civil_catalunya_plans`

Recompte de plans presents al feed, amb el detall complet als atributs. És l'única entitat que
transporta la informació per pla, i és el que evita haver de crear entitats dinàmiques.

| | |
| --- | --- |
| `translation_key` | `plans` |
| Estat | Enter: el nombre d'entrades de l'estat del coordinator, és a dir de parells `(acronym, phase)` distints. **`0`** quan la resposta és `[]` |
| `state_class` | `MEASUREMENT` |
| Unitat | `plans` (via `translations`) |

**No es diu `active_plans`**: compta files en qualsevol fase, prealerta inclosa, i una prealerta
no és un pla actiu. Qui vol el recompte d'activats té l'atribut `activated` o el binary sensor.

Dues files simultànies del mateix acrònim en fases diferents (p. ex. dos PA del PROCICAT, cosa
que §3.2 nota 2 de [`01`](01-data-sources.md) fa plausible) compten com a **2**, no com a 1.

Atributs:

| Atribut | Contingut |
| --- | --- |
| `plans` | Llista d'objectes, un per fila, ordenada per `(acronym, phase)`. Vegeu l'esquema avall |
| `activated` | Recompte de files amb `activated` cert (§3.3 de [`01`](01-data-sources.md)) |
| `prealerta` | Recompte de files en fase `prealerta` |

Esquema de cada element de `plans`:

```jsonc
{ "acronym": "INUNCAT",          // plaacronim, cru, majúscules
  "name": "INUNCAT",             // nom llarg del mapatge propi; fallback a l'acrònim
  "phase": "alerta",             // normalitzat: prealerta|alerta|emergencia|unknown
  "phase_raw": "ALERTA",         // literal original, sempre present
  "activated": true,             // plaactivat normalitzat; derivat de la fase si no es reconeix
  "started_at": "2026-08-05T11:18:09+00:00",  // :created_at, o fasedatahora, o null
  "started_at_source": "created_at",          // created_at|fasedatahora|null
  "description": "Avís intensitat pluja fins al 04/08  -",  // només .strip(); buit → null
  "communique_url": "https://documents.dadesobertes.gencat.cat/cecat/docs/I-125912_…pdf" }
```

Decisions de l'esquema, cada una amb la seva raó:

| Decisió | Motiu |
| --- | --- |
| `name` surt d'un mapatge propi, **no** de `planom` | `planom` és idèntic a `plaacronim` a 5/5 files observades, contra la seva pròpia documentació ([`01`](01-data-sources.md) trap 4) |
| `phase_raw` sempre present al costat de `phase` | Un literal nou ha de ser visible a l'usuari i als diagnostics sense esperar una release |
| `started_at` prefereix `:created_at` | És ISO-8601 en UTC i coincideix al minut amb `fasedatahora` ([`01`](01-data-sources.md) §7.2). Evita parsejar `DD/MM/YYYY HH:MM` i endevinar el fus |
| `started_at_source` explícit | Fa auditable quina de les dues fonts s'ha fet servir, i fa visible el dia que `:created_at` desaparegui |
| `communique_url` és una cadena opaca | Pot contenir accents i apòstrofs sense codificar ([`01`](01-data-sources.md) trap 7). No es valida ni es reconstrueix |
| Cap camp de territori | No existeix ([`01`](01-data-sources.md) §5) |

### 3.3 `binary_sensor.proteccio_civil_catalunya_pla_activat`

La pregunta binària: **hi ha algun pla realment activat?**

| | |
| --- | --- |
| `translation_key` | `plan_activated` |
| `device_class` | `BinarySensorDeviceClass.SAFETY` |
| `on` | Almenys una fila amb `activated` cert |
| `off` | Cap fila activada, incloent-hi el cas de només prealertes i el cas `[]` |

**Aquesta entitat és el motiu pel qual la prealerta es modela com a estat de primera classe.**
Una prealerta deixa `binary_sensor` a `off` (el pla no està activat: ho diu la font, "la
prealerta no implica l'activació del pla") però deixa `sensor.proteccio_civil_catalunya_fase_maxima` a `prealerta`.
Les dues coses són certes alhora i cap consumidor conegut d'aquesta font les distingeix
([`02`](02-existing-integrations.md) §6).

#### Com es calcula `activated`, i per què no és `plaactivat == "SI"`

Aquest és un sensor `SAFETY`. Que es quedi a `off` durant una emergència real és el pitjor
error possible de tota la integració, i una comparació estricta el fa possible: la descripció
oficial escriu el domini com a "(Si/No)" mentre les dades donen `SI`/`NO`, i la fase
`EMERGÈNCIA` **mai s'ha observat**, per tant ningú sap com hi ve escrit el camp
([`01`](01-data-sources.md) §3.3, traps 1 i 14).

Regla, idèntica a la de `plafase`, normalitzant amb `strip` + `casefold` + sense diacrítics:

| `plaactivat` normalitzat | `activated` |
| --- | --- |
| `no` | **`False`** |
| `si` | `True` |
| Absent, buit o qualsevol altre literal | **Es deriva de la fase**: `True` si la fase és `ALERTA` o superior a `PHASE_ORDER`. `warning` una sola vegada per literal |

`activated` és `False` **només** amb el literal `no`. Un valor irreconeixible mai no pot
llegir-se com a "no passa res": cedeix la decisió a `plafase`, que és el camp autoritatiu
(AD-6). Si la fase també és desconeguda no hi ha res amb què comparar i `activated` és `False`,
amb els dos literals visibles a `phase_raw` i als diagnostics.

Conseqüència pràctica: una fila d'`EMERGÈNCIA` amb `Si`, amb ` SI `, o **sense el camp**, deixa
el binary sensor a `on`. Una prealerta amb `NO` el deixa a `off`, com abans.

Atributs: `plans` amb els acrònims activats.

### 3.4 `sensor.proteccio_civil_catalunya_darrera_actualitzacio` (diagnòstic)

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
perquè el text és brut), `Last-Modified`, els literals de `plafase`, `plaacronim` i `plaactivat`
no reconeguts acumulats, i el recompte de cicles fallits consecutius. No hi ha dades personals ni coordenades
a redactar: la font no en té.

---

## 4. Events

Una sola família, `cecat_plan_phase_*`, més un event de degradació del servei. Mateix patró que
`ha-incendiscat` ([`02`](02-existing-integrations.md) §5), que és el que fa que un blueprint de
notificació sigui trivial.

**Regla de noms, i és l'única que cal recordar: la família d'events parla de *fases* que
comencen, canvien i acaben; el `binary_sensor` és l'únic que parla d'*activació*.** Cap event no
es diu `activated`, i per tant cap no pot confondre's amb
`binary_sensor.proteccio_civil_catalunya_pla_activat`, que té la condició de veritat contrària per a la
prealerta: una prealerta que apareix **sí** que dispara `cecat_plan_phase_started` (una fase ha
començat) i **no** encén el binary sensor (el pla no està activat). `phase_ended` també és més
honest que "deactivated": una prealerta que desapareix no és cap desactivació, perquè el pla no
estava activat.

**La identitat d'un episodi és `(acronym, phase)`, mai `:id` ni el hash de la fila.** Motiu
mesurat: `comunicatpdf` canvia diverses vegades dins de la mateixa fase sense que canviï
`fasedatahora` (l'incident `I-125912` en va tenir 5) i `:id` canvia quan el publicador
substitueix la fila en un canvi de fase ([`01`](01-data-sources.md) traps 11 i §7.2). Qualsevol
altra clau genera events duplicats o els perd. L'estat del coordinator està indexat per aquesta
mateixa clau, no per l'acrònim sol ([`04`](04-architecture.md) §5, trap 3).

### 4.1 `cecat_plan_phase_started`

Es dispara quan apareix un parell `(acronym, phase)` que el cicle anterior no tenia, i la fase
no és `none`, **excepte** quan aquella alta s'aparella amb una baixa del mateix acrònim i es
col·lapsa en un `phase_changed` (§4.2). L'aparellament demana tres condicions alhora, i si en
falla qualsevol s'emeten els events plans: exactament una alta per a l'acrònim, exactament una
baixa, i **les dues fases a `PHASE_ORDER`** (és a dir, cap costat no és `unknown`). La regla
sencera és a [`04`](04-architecture.md) §5.

Conseqüència que val la pena tenir present: una fila que entra en `unknown` **sí** que dispara
`phase_started`, perquè `unknown` no és aparellable. És el que fa que una escalada que passa per
un literal irreconeixible segueixi arribant a les automacions.

```yaml
event_type: cecat_plan_phase_started
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

### 4.2 `cecat_plan_phase_changed`

Es dispara quan un `acronym` que ja seguíem canvia **entre dues fases conegudes**, en qualsevol
direcció: una clau `(acronym, phase)` desapareix i una altra del **mateix acrònim** apareix al
mateix cicle, i en lloc de dos events se n'emet un de sol.

L'aparellament demana **tres** condicions alhora, i totes tres han de ser certes:

1. Exactament **una alta** per a aquell acrònim.
2. Exactament **una baixa** per a aquell acrònim.
3. **Les dues fases són a `PHASE_ORDER`**, és a dir cap costat no és `unknown`.

Si en falla qualsevol, no hi ha `phase_changed`: s'emeten un `phase_ended` per clau retirada i un
`phase_started` per clau afegida. La regla sencera, amb el motiu de cada condició, és a
[`04`](04-architecture.md) §5.

```yaml
event_type: cecat_plan_phase_changed
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: prealerta
  previous_phase_raw: PREALERTA
  phase: alerta
  phase_raw: ALERTA
  escalation: true          # només si les dues fases són a PHASE_ORDER i phase > previous
  activated: true
  started_at: "2026-08-05T11:18:09+00:00"
```

`phase_raw` i `previous_phase_raw` hi són **sempre**, igual que a l'atribut `plans` (§3.2) i que
al payload de `phase_ended` (§4.3), i no són decoració: són l'únic lloc on una automació pot
veure el literal que ha arribat de veritat.

`escalation` es calcula **només** entre dues fases que totes dues tenen posició a `PHASE_ORDER`,
perquè la tercera condició de l'aparellament garanteix que aquest event no s'emet mai amb un
costat `unknown`. Una transició que hi entra o en surt no arriba aquí: surt com a `phase_ended`
+ `phase_started` (§4.1 i §4.3). Comparar severitats a través d'un valor sense ordre no és una
comparació que doni `false`, és una comparació que no s'hauria de fer
([`04`](04-architecture.md) §4).

És l'event que captura la transició real observada a la font: `I-125912` va passar de prealerta
(02/08 18:47) a activat (03/08 18:51) mantenint el mateix número d'incident
([`01`](01-data-sources.md) §7.2).

⚠️ **`escalation: true` no és garantia que hagi escalat el mateix pla.** Sota la premissa de
[`01`](01-data-sources.md) §3.2 nota 2, on cada pla d'actuació del PROCICAT reporta `PROCICAT`
pelat a `plaacronim`, un cicle en què el pla d'actuació d'onada de calor deixa de seguir-se
mentre el de ferrocarril apareix en `ALERTA` dona exactament una alta i una baixa per a
`PROCICAT`, i s'emet un sol `cecat_plan_phase_changed` amb `escalation: true` que afirma una
escalada quan de fet un pla s'ha acabat i n'ha començat un altre de diferent. És una limitació
acceptada i inherent a la identitat declarada, amb les alternatives rebutjades documentades a
[`04`](04-architecture.md) §5 i llistada com a obert 6 del veredicte
([`01`](01-data-sources.md) §14).

### 4.3 `cecat_plan_phase_ended`

Es dispara quan una clau `(acronym, phase)` que seguíem **desapareix** de la resposta i aquella
baixa **no** s'aparella en un `phase_changed`. L'aparellament demana les tres condicions de
§4.2: una alta, una baixa, i les dues fases a `PHASE_ORDER`. Per tant una clau que se'n va en
`unknown`, o que se'n va cap a `unknown`, acaba **sempre** aquí i no dins d'un `phase_changed`.

```yaml
event_type: cecat_plan_phase_ended
data:
  acronym: INUNCAT
  name: INUNCAT
  previous_phase: alerta
  previous_phase_raw: ALERTA
  duration_minutes: 4126     # des de started_at fins ara; null si started_at era null
```

`previous_phase_raw` hi és **sempre**, per la mateixa regla de §4.2 i amb més motiu aquí: com que
`unknown` no és aparellable, aquest event és on aterra un episodi que va acabar amb un `plafase`
irreconeixible. Sense el literal cru, una automació que registri durades per fase anotaria
`unknown` sense cap manera de distingir dos literals dolents diferents, que sota la col·lisió
residual de [`04`](04-architecture.md) §5 havien col·lapsat a la mateixa clau.

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

Escolta `cecat_plan_phase_started` i `cecat_plan_phase_changed` (només amb `escalation: true`),
filtra per `min_phase` i per `plans`, i envia el missatge amb `description` i l'enllaç al
comunicat.

Per defecte `alerta` i **no** `prealerta`: amb 589 prealertes en 623 dies
([`01`](01-data-sources.md) §4) un blueprint que notifiqués prealertes seria soroll i faria que
l'usuari el silenciés, perdent també les alertes.

### 5.1 `phase: unknown` sempre passa el filtre, i el missatge ho ha de dir

`min_phase` només ofereix `prealerta` / `alerta` / `emergencia`, però §4.1 dispara
`phase_started` per a qualsevol fase que no sigui `none`, **inclosa `unknown`**. Un acrònim nou
que arribi amb un `plafase` irreconeixible entra directament al filtre. Tres regles, i cap és
opcional:

1. **`unknown` sempre passa**, sigui quin sigui el `min_phase` configurat. En una integració de
   protecció civil, un desconegut silenciós és pitjor que una notificació de més. És el mateix
   principi que al coordinator: un valor irreconeixible degrada de manera segura i sorollosa.
2. **Cap implementació no pot petar.** Un error de plantilla no és una tercera opció, és
   precisament la fallada que les altres dues eviten. Per això la condició ha de comprovar
   `unknown` **primer** i sortir, i només després buscar posicions a la llista ordenada, de
   manera que el valor sense ordre no arribi mai a un `index()`. És el mateix motiu i la mateixa
   forma que `_severity` a [`04`](04-architecture.md) §4.
3. **El missatge ha de dir que la fase no s'ha reconegut**, i mostrar `phase_raw`. Notificar és
   correcte; presentar-ho com si fos una fase coneguda seria una altra mentida. `phase_raw` hi és
   sempre (§4.2).

Forma exacta de la condició, perquè ningú no reintrodueixi el perill:

```jinja
{% set ordre = ['prealerta', 'alerta', 'emergencia'] %}
{{ trigger.event.data.phase == 'unknown'
   or ordre.index(trigger.event.data.phase) >= ordre.index(min_phase) }}
```

L'ordre dels operands importa: Jinja avalua `or` amb curtcircuit, per tant amb
`phase == 'unknown'` la crida a `index()` no s'executa mai. Escriure-ho al revés tornaria a
donar l'error de plantilla.

I el missatge, quan la fase no es reconeix:

```jinja
{% if trigger.event.data.phase == 'unknown' %}
  {{ acronym }}: fase NO RECONEGUDA ("{{ trigger.event.data.phase_raw }}")
{% endif %}
```

⚠️ **Fals positiu conegut d'aquest blueprint.** Com que filtra per `escalation: true`, hereta la
limitació de §4.2: si dos plans d'actuació distints comparteixen `plaacronim` (el cas del
PROCICAT), un cicle en què un acaba i un altre comença es veu com una escalada i el blueprint
enviarà una notificació d'escalada per un episodi que no ha escalat. No es corregeix perquè
corregir-ho requeriria corroborar la identitat amb `plaicona` o `descripcio`, dos camps que
aquesta mateixa recerca ha trobat poc fiables ([`01`](01-data-sources.md) §6.3 i §9). Obert 6
del veredicte.

---

## 6. Patrons d'automació que suportem

| Vull… | Com |
| --- | --- |
| Avisar-me quan s'activi qualsevol pla | Trigger d'estat sobre `binary_sensor.proteccio_civil_catalunya_pla_activat` a `on`, o el blueprint. **No** l'event `phase_started`, que també salta amb una prealerta |
| Avisar-me només d'emergències | Trigger d'event `cecat_plan_phase_started` amb condició `phase == emergencia` |
| Saber si l'INUNCAT concretament està en alerta | Template sobre l'atribut `plans` de `sensor.proteccio_civil_catalunya_plans`. Vegeu el README |
| Creuar amb el Meteocat: avís greu **i** INUNCAT en alerta | Condició que creua `ha-avisoscat` i `ha-cecat`. Dues integracions a la mateixa instància, cap acoblament ([`02`](02-existing-integrations.md) §3) |
| Registrar la durada dels episodis | Escoltar `cecat_plan_phase_ended` i llegir `duration_minutes` |
| Notificar només escalades | Trigger d'event `cecat_plan_phase_changed` amb condició `escalation == true`, o el blueprint. **Amb el fals positiu de §4.2**: per a `PROCICAT`, dos plans d'actuació distints poden semblar una escalada d'un de sol |

Exemple del cas per pla concret, que va al README:

```yaml
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.proteccio_civil_catalunya_plans', 'plans')
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
| 1 | Amb `[]` a la resposta: `max_phase = none`, `plans = 0`, `plan_activated = off`. **Cap entitat a `unavailable`** |
| 2 | Amb la captura real de prealerta (2024-12-02): `max_phase = prealerta`, `plans = 1`, `plan_activated = **off**` |
| 3 | Amb la captura real de camps de sistema (2026-08-06, `$select=:*,*`): `max_phase = alerta`, `plan_activated = on`, `started_at` = `2026-08-05T11:18:09+00:00` amb `started_at_source = created_at` (el `.349Z` es trunca a segons) |
| 3b | Amb la captura real d'alerta de projecció pelada (2026-08-06, sense camps de sistema): mateixos estats, però `started_at` = `2026-08-05T11:18:00+00:00` amb `started_at_source = fasedatahora` |
| 4 | Amb la captura real de dos plans (2026-01-19): `plans = 2` i l'atribut `plans` amb INUNCAT i NEUCAT |
| 4b | Amb dues files del **mateix acrònim** en fases diferents (p. ex. PROCICAT en prealerta i PROCICAT en alerta): `plans = 2`, **les dues** a l'atribut `plans` ordenades per `(acronym, phase)`, i **dos** `cecat_plan_phase_started`. Cap de les dues es perd |
| 5 | Amb un fixture sintètic d'`EMERGÈNCIA` (marcat com a sintètic): `max_phase = emergencia`. També amb `EMERGENCIA` sense accent |
| 5b | Amb `emergencia_plaactivat_rar_SYNTHETIC` (tres files d'`EMERGÈNCIA`, `plaactivat` = `Si`, ` SI ` i **el camp absent**, amb acrònims distints perquè no col·lapsin): `plan_activated = on`. ⚠️ Criteri **agregat**: el satisfaria qualsevol de les tres files essent certa, per tant **no** és cobertura de les tres variants, només comprova que l'agregació no perdi el senyal. La cobertura per variant viu als criteris per fila de `resolve_activated` a T3 de [`05`](05-implementation-plan.md). El camp absent genera un `warning` una sola vegada, registrat com a `<absent>`; `Si` i ` SI ` es reconeixen i no en generen cap. Amb `plaactivat = NO` sobre una prealerta: `off` |
| 6 | `plafase` amb un literal desconegut: `max_phase = unknown`, `warning` una sola vegada, cap excepció |
| 6b | Estat previ `{(INUNCAT, alerta)}` i el cicle següent l'`INUNCAT` arriba amb un `plafase` irreconeixible: hi ha una alta i una baixa, però un costat és `unknown`, per tant **no s'aparella**. S'emeten **un `cecat_plan_phase_ended`** (`previous_phase = alerta`, `previous_phase_raw = ALERTA`) **i un `cecat_plan_phase_started`** (`phase = unknown`, `phase_raw` amb el literal cru), i **cap `cecat_plan_phase_changed`**. Cap excepció avorta el cicle |
| 6c | Continuant des de 6b, el cicle següent la fila arriba com a `EMERGÈNCIA`: **un `cecat_plan_phase_ended`** (`previous_phase = unknown`, `previous_phase_raw` amb el literal cru) **i un `cecat_plan_phase_started`** (`phase = emergencia`), i **cap `phase_changed`**. El blueprint, que escolta `phase_started`, **notifica l'escalada** sense cap canvi al blueprint |
| 7 | `plaacronim` desconegut (`PENTA`, `NOPLA`): fila ingerida, `name` = l'acrònim, `warning` una vegada |
| 8 | `comunicatpdf` absent, `plaicona` absent, `descripcio` buida: cap `KeyError`, atributs a `None` |
| 9 | `comunicatpdf.url` amb accents i apòstrof (captura 2026-07-03): es propaga tal qual sense petar ni recodificar |
| 10 | `fasedatahora` il·legible o absent i sense `:created_at`: `started_at = None`, `started_at_source = null`, cap excepció |
| 11 | Transició prealerta → alerta del mateix acrònim: **un** `cecat_plan_phase_changed` amb `escalation: true`, i **cap** `cecat_plan_phase_started` ni `cecat_plan_phase_ended` |
| 12 | `comunicatpdf` canvia sense canviar `plafase`: **cap** event. Només canvia l'atribut |
| 13 | Fila que desapareix en un cicle **vàlid**: un `cecat_plan_phase_ended` amb `duration_minutes` |
| 14 | Fila que desapareix perquè la petició **falla**: cap event, estat anterior intacte |
| 15 | HTTP 304 a `If-Modified-Since`: estat anterior intacte, cap event, cap entitat a `unavailable` |
| 15b | Blueprint: un event amb `phase: unknown` **passa** el filtre amb `min_phase` a `prealerta`, a `alerta` i a `emergencia`, sense cap error de plantilla, i el missatge diu que la fase **no s'ha reconegut** i mostra `phase_raw` (§5.1) |
| 16 | Config flow: `[]` a la petició de prova crea l'entrada; timeout dona `cannot_connect` |
| 17 | Les quatre entitats tenen clau als tres `translations/{ca,es,en}.json` i `hassfest` passa |
| 18 | Cobertura ≥ 95%, `ruff check` i `ruff format --check` en verd |
