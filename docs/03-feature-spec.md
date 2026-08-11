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
| `options` | `["none", "prealerta", "alerta", "emergencia", "unrecognized"]` |
| Estat quan la resposta és `[]` | **`none`** |
| Icona | `mdi:shield-alert-outline` (fixa; **no** `plaicona`, vegeu [`01`](01-data-sources.md) §11.3) |

Ordre de severitat: `none` < `prealerta` < `alerta` < `emergencia`. `unrecognized` és la vàlvula
d'escapament: si `plafase` porta un literal que no reconeixem, l'estat és `unrecognized` i s'emet un
`warning` **una sola vegada** per literal (patró de `nina`, [`02`](02-existing-integrations.md) §2).

> ⚠️ **Per què el valor és `unrecognized` i no `unknown`, i no s'ha de revertir.** `unknown` és
> el `STATE_UNKNOWN` reservat de Home Assistant, el que una entitat mostra quan no té estat.
> Fer-lo servir aquí faria **indistingible** "la font ha publicat un `plafase` que no reconeixem"
> de "aquesta entitat encara no té estat", a la màquina d'estats, a les plantilles, a l'historial
> i a la interfície. Dues conseqüències concretes: el guard gairebé universal
> `states('sensor.…') not in ['unknown', 'unavailable']` s'empassaria precisament el senyal que
> tota la vàlvula d'escapament existeix per fer visible, i una automació que dispari en entrar a
> l'estat saltaria a **cada reinici** de Home Assistant, abans del primer refresc. Amb un valor
> propi, cap de les dues coses passa.
>
> S'escriu en **anglès americà** (`unrecognized`, no `unrecognised`) perquè aquesta cadena viu a
> la màquina d'estats de Home Assistant, que fa servir anglès americà a tot arreu; l'etiqueta que
> veu l'usuari surt de `translations/{ca,es,en}.json` i en català és "Desconeguda". `unavailable`
> continua sent exclusiu del guard de dades velles ([`04`](04-architecture.md) §5), i `none` el
> de la resposta buida: els tres conceptes queden separats.
>
> Les claus de diagnòstic `unknown_phases`, `unknown_acronyms` i `unknown_activated` **no** es
> renombren: nomenen el concepte intern de literal no reconegut i no creuen mai cap a la màquina
> d'estats, per tant canviar-les seria soroll sense cap benefici per a l'usuari.

Normalització del literal: `casefold()` **i sense diacrítics**, perquè el valor documentat és
`EMERGÈNCIA` amb accent obert i mai s'ha observat en viu ([`01`](01-data-sources.md) trap 14).
`EMERGÈNCIA`, `EMERGENCIA` i `emergència` han de donar el mateix estat.

Atributs:

| Atribut | Contingut |
| --- | --- |
| `acronyms` | Llista d'**acrònims** (cadenes) que estan en aquesta fase màxima, p. ex. `["INUNCAT"]`. **No** es diu `plans`: aquest nom queda reservat per a la llista d'objectes de §3.2, de manera que el nom digui la forma |
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
  "phase": "alerta",             // normalitzat: prealerta|alerta|emergencia|unrecognized
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
| Absent, buit o qualsevol altre literal | **Es deriva de la fase**: `True` si la fase és `ALERTA` o `EMERGÈNCIA`, i `False` per a qualsevol altra, la irreconeixible inclosa. `warning` una sola vegada per literal |

`activated` és `False` **només** amb el literal `no`. Un valor irreconeixible mai no pot
llegir-se com a "no passa res": cedeix la decisió a `plafase`, que és el camp autoritatiu
(AD-6). Si la fase també és desconeguda no hi ha res amb què comparar i `activated` és `False`,
amb els dos literals visibles a `phase_raw` i als diagnostics.

Conseqüència pràctica: una fila d'`EMERGÈNCIA` amb `Si`, amb ` SI `, o **sense el camp**, deixa
el binary sensor a `on`. Una prealerta amb `NO` el deixa a `off`, com abans.

Atributs: `acronyms` amb els **acrònims** (cadenes) activats. Igual que a §3.1, **no** es diu `plans`: el nom `plans` és exclusiu de la llista d'objectes de §3.2.

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

### Cap event no en suprimeix cap altre, i què costa això

**`phase_started` s'emet per a cada clau que apareix i `phase_ended` per a cada clau que
desapareix, sempre.** `phase_changed` és **additiu**: s'emet **a més** del parell, mai en lloc
seu, i només quan es compleixen les tres condicions de §4.2.

Per tant una transició del mateix acrònim, per exemple `ALERTA` cap a `EMERGÈNCIA`, emet **tres**
events: `phase_ended(ALERTA)` amb la seva durada, `phase_started(EMERGÈNCIA)` i
`phase_changed` amb `escalation: true`. Tres és el recompte honest: una fase s'ha acabat, una
altra ha començat, i el parell és un canvi.

La conseqüència que importa és que **un consumidor d'un sol event no pot equivocar-se**. Qui
escolta només `phase_started` rep la fase nova tant si la fila apareix de zero com si escala; qui
escolta només `phase_ended` rep totes les fases que s'acaben, amb `duration_minutes`, també les
intermèdies d'un episodi.

> ⚠️ **El cost, dit clarament: qui escolti `phase_started` i `phase_changed` alhora rebrà DUES
> notificacions per una sola transició.** No és un error, és la contrapartida de no suprimir res.
> Per això cada recepta de §6 declara **un sol carril** i el blueprint també (§5), i els carrils
> no s'han de combinar tret que es vulgui expressament la notificació doble.

### 4.1 `cecat_plan_phase_started`

Es dispara **sempre** que apareix un parell `(acronym, phase)` que el cicle anterior no tenia i
la fase no és `none`. Sense excepcions i sense supressió: tant si la fila apareix de zero com si
és el costat nou d'una transició, aquest event s'emet.

És el carril que cobreix "avisa'm quan un pla arribi a la fase X" sense casos especials, i el que
fa servir el blueprint (§5). Una fila que entra en `unrecognized` també el dispara.

**Es dispara per QUALSEVOL entrada en una fase**, i les tres maneres compten igual: una fila que
apareix de nou, una que puja de fase, i una que baixa de fase. Una baixada és una entrada en la
fase nova tant com ho és una pujada, i per això arriba pel mateix carril.

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

Vuit camps, i **cap d'origen**: aquest event diu en quina fase ha entrat el pla, i no diu d'on
venia.

`phase_raw` hi és **sempre**, mai `null`, també quan `phase` és `unrecognized` i també quan la fase
s'ha reconegut sense cap problema. No és decoració ni un camp de depuració: és l'únic lloc on una
automació pot veure el literal que ha arribat de veritat, i és el carril que llegeix el blueprint
(§5.1 regla 3), per tant ometre'l quan la fase parseja bé deixaria el missatge de fase no reconeguda
sense res a mostrar. La mateixa garantia val per a l'atribut `plans` (§3.2), per a `phase_changed`
(§4.2) i per a `phase_ended` (§4.3).

#### Per què `phase_started` NO porta cap origen, i `phase_ended` sí

L'asimetria és deliberada i no s'ha d'aplanar. Es deriva directament del resultat central de la
recerca: **`plaacronim` no identifica un pla** ([`01`](01-data-sources.md) §3.2 nota 2). Sota
aquesta premissa, quan una clau apareix i una altra del mateix acrònim desapareix al mateix cicle,
**no és coneixible** si es tracta del mateix pla que ha canviat de fase o de dos plans distints.
Per tant:

| Event | Porta origen? | Per què |
| --- | --- | --- |
| `cecat_plan_phase_started` | **No** | L'origen d'una clau que apareix seria una **inferència** sobre continuïtat, i amb un acrònim que pot contenir diversos plans aquesta inferència és exactament el fals positiu de l'obert 6 |
| `cecat_plan_phase_ended` | **Sí**, `previous_phase` i `previous_phase_raw` | Aquí no hi ha inferència: la clau `(acronym, phase)` **ha desaparegut**, i la seva fase és un fet sobre la clau mateixa, no una conjectura sobre què ha passat després |

Dit d'una altra manera: `phase_ended` informa d'una clau que existia i ja no existeix, cosa
observada; `phase_started` informaria d'una relació entre dues claus, cosa no observada.

**La lliçó, escrita una vegada perquè no es torni a redescobrir:** la continuïtat al llarg d'un
acrònim **no és derivable** d'aquesta font. Per tant **cap event no afirma un origen**, i
l'aparellament només s'intenta en un sol lloc, el `phase_changed` additiu de §4.2, que és opcional
i que porta la seva limitació documentada com a residu acceptat (obert 6). S'ha intentat portar
l'origen al carril `phase_started` i ha fallat sempre al mateix lloc: el PROCICAT.

### 4.2 `cecat_plan_phase_changed`

Es dispara quan un `acronym` que ja seguíem canvia **entre dues fases conegudes**, en qualsevol
direcció: una clau `(acronym, phase)` desapareix i una altra del **mateix acrònim** apareix al
mateix cicle. **S'emet a més del parell `phase_ended` + `phase_started`, mai en lloc seu.**

Demana **tres** condicions alhora, i totes tres han de ser certes:

1. Exactament **una alta** per a aquell acrònim.
2. Exactament **una baixa** per a aquell acrònim.
3. **Les dues fases són a `PHASE_ORDER`**, és a dir cap costat no és `unrecognized`.

Si en falla qualsevol, simplement no hi ha `phase_changed`; el parell `phase_ended` +
`phase_started` ja s'ha emès igualment i el senyal no es perd. La regla sencera, amb el motiu de
cada condició i els exemples treballats, és a [`04`](04-architecture.md) §5.

És l'**únic** lloc del disseny on s'intenta un aparellament, i per tant l'únic que pot afirmar una
transició. No es pot derivar de `phase_started`, perquè aquell event no porta cap origen (§4.1):
qui vulgui semàntica de transició ha d'escoltar aquest event i acceptar-ne la limitació.

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

`phase_raw` i `previous_phase_raw` hi són **sempre**, i la garantia val per a **tots** els llocs on
apareix un literal cru, sense excepcions: `phase_started` (§4.1), l'atribut `plans` (§3.2),
`phase_ended` (§4.3) i aquest event. No són decoració: són l'únic lloc on una automació pot veure el
literal que ha arribat de veritat.

`escalation` es calcula **només** entre dues fases que totes dues tenen posició a `PHASE_ORDER`,
perquè la tercera condició de l'aparellament garanteix que aquest event no s'emet mai amb un
costat `unrecognized`. Una transició que hi entra o en surt no arriba aquí: surt com a `phase_ended`
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
`PROCICAT`, i s'hi **afegeix** un `cecat_plan_phase_changed` amb `escalation: true` que afirma
una escalada quan de fet un pla s'ha acabat i n'ha començat un altre de diferent.

La limitació és **només d'aquest event**: el `phase_ended(PROCICAT, prealerta)` i el
`phase_started(PROCICAT, alerta)` del mateix cicle són **individualment correctes**, perquè un
pla realment s'ha acabat i un altre realment ha començat. Qui fa servir el carril `phase_started`
o el carril `phase_ended` (§6) no en pateix res. És una limitació acceptada i inherent a la
identitat declarada, amb les alternatives rebutjades documentades a
[`04`](04-architecture.md) §5 i llistada com a obert 6 del veredicte
([`01`](01-data-sources.md) §14).

### 4.3 `cecat_plan_phase_ended`

Es dispara **sempre** que una clau `(acronym, phase)` que seguíem desapareix de la resposta.
Sense excepcions i sense supressió: tant si l'episodi s'acaba del tot com si la fase és
intermèdia i el pla continua en una altra, aquest event s'emet.

Perquè ja no se suprimeix mai, **`duration_minutes` hi és sempre**, també per a les fases
intermèdies. Amb la supressió anterior, la durada de qualsevol fase que acabés transicionant no
s'emetia enlloc: aquest és el carril de "registrar la durada dels episodis" (§6) i ara hi arriba
per a totes les fases, no només per a les terminals.

⚠️ **Que l'event hi sigui i que la xifra sigui exacta són dues coses distintes.**
`duration_minutes` es calcula des de `started_at`, i per a una fase **intermèdia** la seva
exactitud depèn de l'obert 3 ([`01`](01-data-sources.md) §14, "si un canvi de fase substitueix la
fila o l'edita"): si el publicador edita la fila en lloc de substituir-la, `:created_at` es queda
enganxat a l'inici de l'episodi i la durada de la fase intermèdia surt inflada amb tot el que
l'ha precedida. La durada de la fase **terminal**, i la de qualsevol episodi d'una sola fase, no
en depèn. `started_at_source` fa visible d'on surt la marca.

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
`unrecognized` no és aparellable, aquest event és on aterra un episodi que va acabar amb un `plafase`
irreconeixible. Sense el literal cru, una automació que registri durades per fase anotaria
`unrecognized` sense cap manera de distingir dos literals dolents diferents, que sota la col·lisió
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

**Escolta un sol event: `cecat_plan_phase_started`.** Filtra per `min_phase` i per `plans`, i
envia el missatge amb `description` i l'enllaç al comunicat.

Un sol carril, i n'hi ha prou. Com que `phase_started` s'emet per a **cada** fase que comença,
sigui perquè la fila apareix de nou, perquè **puja** de fase o perquè **baixa** de fase (§4.1), la
fase nova hi arriba sempre i el filtre `min_phase` decideix si es notifica. Afegir-hi també `phase_changed` només
serviria per enviar **dues** notificacions per una mateixa escalada, que és exactament el cost
que §4 adverteix. `cecat_plan_phase_changed` queda disponible per a qui vulgui semàntica
d'**escalada estrictament**, que és la recepta corresponent de §6, però no és el que fa el
blueprint.

Per defecte `alerta` i **no** `prealerta`: amb 589 prealertes en 623 dies
([`01`](01-data-sources.md) §4) un blueprint que notifiqués prealertes seria soroll i faria que
l'usuari el silenciés, perdent també les alertes.

### 5.1 `phase: unrecognized` sempre passa el filtre, i el missatge ho ha de dir

`min_phase` només ofereix `prealerta` / `alerta` / `emergencia`, però §4.1 dispara
`phase_started` per a qualsevol fase que no sigui `none`, **inclosa `unrecognized`**. Un acrònim nou
que arribi amb un `plafase` irreconeixible entra directament al filtre. Tres regles, i cap és
opcional:

1. **`unrecognized` sempre passa**, sigui quin sigui el `min_phase` configurat. En una integració de
   protecció civil, un desconegut silenciós és pitjor que una notificació de més. És el mateix
   principi que al coordinator: un valor irreconeixible degrada de manera segura i sorollosa.
   El preu d'aquesta regla, per tenir-lo escrit: com que `unrecognized` esquiva `min_phase` del
   tot, si el publicador canviés el literal de fase a tota la font (un espai final, una
   recodificació, una fase rebatejada) cada fila de prealerta normalitzaria a `unrecognized` i
   dispararia un `phase_started` que cap valor de `min_phase` no podria filtrar, reproduint el
   flux de soroll d'aproximadament un per dia que el valor per defecte `alerta` existeix per
   evitar; queda diagnosticable pel `warning` una sola vegada per literal i pels
   `unknown_phases` dels diagnostics.
2. **Cap implementació no pot petar.** Un error de plantilla no és una tercera opció, és
   precisament la fallada que les altres dues eviten. Per això la condició ha de comprovar
   `unrecognized` **primer** i sortir, i només després buscar posicions a la llista ordenada, de
   manera que el valor sense ordre no arribi mai a un `index()`. És el mateix motiu i la mateixa
   forma que `_severity` a [`04`](04-architecture.md) §4.
3. **El missatge ha de dir que la fase no s'ha reconegut**, i mostrar `phase_raw`. Notificar és
   correcte; presentar-ho com si fos una fase coneguda seria una altra mentida. `phase_raw` hi és
   sempre al payload que escolta el blueprint, que és `phase_started` (§4.1). Aquesta és la
   **regla**; el codi que la implementa viu a §5.2, que és l'**única** secció que conté el missatge
   copiable.

Forma exacta de la condició, perquè ningú no reintrodueixi el perill:

```jinja
{% set ordre = ['prealerta', 'alerta', 'emergencia'] %}
{{ trigger.event.data.phase == 'unrecognized'
   or ordre.index(trigger.event.data.phase) >= ordre.index(min_phase) }}
```

L'ordre dels operands importa: Jinja avalua `or` amb curtcircuit, per tant amb
`phase == 'unrecognized'` la crida a `index()` no s'executa mai. Escriure-ho al revés tornaria a
donar l'error de plantilla.

### 5.2 El missatge: estat neutre, sense afirmar direcció

**Aquesta secció és l'única propietària del missatge del blueprint.** És l'únic fragment copiable
de tot el conjunt de documents; §5.1 hi posa una regla, no codi.

El missatge diu **en quina fase és el pla ara**, i res més. No diu que hi hagi entrat, ni que hagi
pujat, ni que hagi baixat, perquè `phase_started` no porta cap origen (§4.1) i qualsevol direcció
seria una inferència sobre continuïtat que aquesta font no permet fer. Afirmar "ha pujat" quan de
fet un pla s'ha acabat i n'ha començat un altre seria dir una cosa falsa, en català pla, a una
persona i sobre una emergència de protecció civil.

Dos casos, i cap més:

| Cas | Missatge |
| --- | --- |
| Fase reconeguda | Estat neutre: "PROCICAT: ara en fase ALERTA" |
| Fase `unrecognized` | Diu que la fase **no s'ha reconegut** i mostra `phase_raw` (§5.1 regla 3) |

El missatge **no conté cap comparació d'ordre**: es comprova `unrecognized` i la branca de la fase
reconeguda és el cas per defecte, sense cap `index()` a la vista. Amb el missatge reduït a un estat
neutre, no queda cap posició a comparar. La regla d'ordenar el guard **abans** de qualsevol `index()`
segueix vigent, però pertany a un altre constructe: la **condició** de `min_phase` de §5.1, que sí
que en conté un.

Tot valor surt qualificat com a `trigger.event.data.*`: el blueprint només té les tres entrades de
§5 i no defineix cap `variables:`, per tant un nom pelat com `acronym` no existiria i Jinja el
renderitzaria com a cadena buida amb un avís al log, deixant la notificació sense el pla.

```jinja
{% if trigger.event.data.phase == 'unrecognized' %}
  {{ trigger.event.data.acronym }}: fase NO RECONEGUDA ("{{ trigger.event.data.phase_raw }}")
{% else %}
  {{ trigger.event.data.acronym }}: ara en fase {{ trigger.event.data.phase | upper }}
{% endif %}
```

Un usuari que vulgui saber la direcció té el carril `phase_changed` de §6, que és l'únic lloc on
s'intenta un aparellament, amb la limitació de l'obert 6 documentada i assumida.

⚠️ **El fals positiu de l'obert 6 no afecta aquest blueprint.** Com que escolta `phase_started` i
no `escalation: true`, la confusió de §4.2 entre dos plans d'actuació que comparteixen
`plaacronim` no hi arriba: el que rep és un `phase_started(PROCICAT, alerta)` que és cert, perquè
un pla d'actuació realment ha començat en alerta. Qui sí que hereta la limitació és la recepta
"notificar només escalades" de §6, que filtra per `escalation: true` deliberadament. No es
corregeix perquè corregir-ho requeriria corroborar la identitat amb `plaicona` o `descripcio`,
dos camps que aquesta mateixa recerca ha trobat poc fiables ([`01`](01-data-sources.md) §6.3 i
§9). Obert 6 del veredicte.

---

## 6. Patrons d'automació que suportem

**Cada recepta declara un sol carril**, i els carrils **no s'han de combinar** tret que es vulgui
expressament la notificació doble que adverteix §4: qui escolti `phase_started` i `phase_changed`
alhora rebrà dos avisos per una sola transició.

| Vull… | Carril | Com |
| --- | --- | --- |
| Avisar-me quan s'activi qualsevol pla | (estat, no event) | Trigger d'estat sobre `binary_sensor.proteccio_civil_catalunya_pla_activat` a `on`, o el blueprint. **No** l'event `phase_started`, que també salta amb una prealerta |
| Avisar-me quan un pla arribi a una fase concreta | `phase_started` | Trigger d'event `cecat_plan_phase_started` amb condició sobre `phase`. Correcte per a **qualsevol** entrada en la fase: una fila que apareix de nou, una que hi puja i una que **hi baixa**. L'event **no diu d'on venia** (§4.1): si vols la direcció, el carril és `phase_changed` |
| Avisar-me només d'emergències | `phase_started` | Trigger d'event `cecat_plan_phase_started` amb condició `phase == emergencia`. Cobreix l'escalada `alerta → emergencia`, que és com va passar l'única transició observada a la font (`I-125912`, [`01`](01-data-sources.md) §7.2) |
| Saber si l'INUNCAT concretament està en alerta | (atribut, no event) | Template sobre l'atribut `plans` de `sensor.proteccio_civil_catalunya_plans`. L'exemple és just sota d'aquesta taula |
| Creuar amb el Meteocat: avís greu **i** INUNCAT en alerta | (condició, no event) | Condició que creua `ha-avisoscat` i `ha-cecat`. Dues integracions a la mateixa instància, cap acoblament ([`02`](02-existing-integrations.md) §3) |
| Registrar la durada dels episodis | `phase_ended` | Escoltar `cecat_plan_phase_ended` i llegir `duration_minutes`. L'event arriba per a **totes** les fases, també les intermèdies, perquè ja no se suprimeix mai (§4.3). ⚠️ L'**exactitud** de la durada d'una fase intermèdia depèn de l'obert 3 ([`01`](01-data-sources.md) §14): si el publicador edita la fila en lloc de substituir-la, `started_at` es queda a l'inici de l'episodi i la durada surt inflada. `started_at_source` ho fa visible |
| Notificar només escalades | `phase_changed` | Trigger d'event `cecat_plan_phase_changed` amb condició `escalation == true`. **Amb el fals positiu de §4.2**: per a `PROCICAT`, dos plans d'actuació distints poden semblar una escalada d'un de sol. És l'únic carril que hereta l'obert 6 |

Exemple del cas per pla concret. Aquesta és la seva única còpia; quan la integració es publiqui, va
també al README:

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
| 6 | `plafase` amb un literal desconegut: `max_phase = unrecognized`, `warning` una sola vegada, cap excepció |
| 6a | L'estat de `max_phase` **mai no és la cadena reservada `unknown`**, llegit de la màquina d'estats de Home Assistant, ni per a un `plafase` irreconeixible ni en cap altre cas. Amb `[]` és `none`; `unavailable` només arriba pel guard de dades velles (§3.1) |
| 6b | Estat previ `{(INUNCAT, alerta)}` i el cicle següent l'`INUNCAT` arriba amb un `plafase` irreconeixible: s'emeten **un `cecat_plan_phase_ended`** (`previous_phase = alerta`, `previous_phase_raw = ALERTA`, amb `duration_minutes`) **i un `cecat_plan_phase_started`** (`phase = unrecognized`, `phase_raw` amb el literal cru). **Cap `cecat_plan_phase_changed`**, perquè un costat no és a `PHASE_ORDER`. Cap excepció avorta el cicle |
| 6c | Continuant des de 6b, el cicle següent la fila arriba com a `EMERGÈNCIA`: **un `cecat_plan_phase_ended`** (`previous_phase = unrecognized`, `previous_phase_raw` amb el literal cru) **i un `cecat_plan_phase_started`** (`phase = emergencia`), i **cap `phase_changed`**. El blueprint, que escolta `phase_started`, **notifica l'escalada** sense cap canvi al blueprint |
| 7 | `plaacronim` desconegut (`PENTA`, `NOPLA`): fila ingerida, `name` = l'acrònim, `warning` una vegada |
| 8 | `comunicatpdf` absent, `plaicona` absent, `descripcio` buida: cap `KeyError`, atributs a `None` |
| 9 | `comunicatpdf.url` amb accents i apòstrof (captura 2026-07-03): es propaga tal qual sense petar ni recodificar |
| 10 | `fasedatahora` il·legible o absent i sense `:created_at`: `started_at = None`, `started_at_source = null`, cap excepció |
| 11 | Transició prealerta → alerta del mateix acrònim: **tres** events, no un. `cecat_plan_phase_ended` (`previous_phase = prealerta`, `previous_phase_raw`, **amb `duration_minutes` calculat**), `cecat_plan_phase_started` (`phase = alerta`) i `cecat_plan_phase_changed` amb `escalation: true`. Cap dels tres no en suprimeix cap altre |
| 11b | La mateixa transició, però cap a `emergencia`: el `cecat_plan_phase_started` **s'emet igualment**, per tant una automació que escolti només `phase_started` amb `phase == emergencia` es dispara. És la regressió que la supressió causava |
| 11c | El payload de `cecat_plan_phase_started` té **exactament els vuit camps** de §4.1 (`acronym`, `name`, `phase`, `phase_raw`, `activated`, `started_at`, `description`, `communique_url`) i **cap camp d'origen**: ni `previous_phase` ni `previous_phase_raw`. L'origen d'una clau que apareix no és derivable d'aquesta font (§4.1) |
| 11d | Transició `emergencia → alerta` del mateix acrònim (la situació millorant): el `phase_started` porta `phase = alerta`, i el missatge renderitzat pel blueprint és l'**estat neutre** de §5.2 ("INUNCAT: ara en fase ALERTA"). La seqüència **notifica**, que era el propòsit, i **no afirma cap direcció** |
| 11e | Cicle amb **una baixa i dues altes** del mateix acrònim (p. ex. `{(PROCICAT, prealerta)}` cap a `{(PROCICAT, alerta), (PROCICAT, emergencia)}`): **dos** `phase_started`, **un** `phase_ended`, i **cap** `phase_changed` perquè falla la condició de cardinalitat. Cap dels dos `phase_started` no afirma un origen, que és precisament el cas on una inferència seria falsa per a almenys un dels dos |
| 12 | `comunicatpdf` canvia sense canviar `plafase`: **cap** event. Només canvia l'atribut |
| 13 | Fila que desapareix en un cicle **vàlid**: un `cecat_plan_phase_ended` amb `duration_minutes` |
| 14 | Fila que desapareix perquè la petició **falla**: cap event, estat anterior intacte |
| 15 | HTTP 304 a `If-Modified-Since`: estat anterior intacte, cap event, cap entitat a `unavailable` |
| 15b | Blueprint: un event amb `phase: unrecognized` **passa** el filtre amb `min_phase` a `prealerta`, a `alerta` i a `emergencia`, sense cap error de plantilla, i el missatge diu que la fase **no s'ha reconegut** i mostra `phase_raw` (§5.1) |
| 16 | Config flow: `[]` a la petició de prova crea l'entrada; timeout dona `cannot_connect` |
| 17 | Les quatre entitats tenen clau als tres `translations/{ca,es,en}.json` i `hassfest` passa |
| 18 | Cobertura ≥ 95%, `ruff check` i `ruff format --check` en verd |
