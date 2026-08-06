# Integracions existents: què copiar i què evitar

Recerca feta el **2026-08-06**. Objectiu: no reinventar el que ja funciona i no repetir el que
ja s'ha demostrat que molesta. Tots els fets d'aquest document estan verificats contra el codi
real de cada integració (manifest, `const.py`, arbre de fitxers), amb la data de comprovació.

---

## 1. Resum executiu

| Integració | Rol | Què en copiem | Què evitem |
| --- | --- | --- | --- |
| `nina` (HA core, 🥈 silver) | Protecció civil nacional, Alemanya | `single_config_entry`, `integration_type: service`, `cloud_polling`, sondeig de 5 min | La dependència de PyPI (`pynina`) i els "message slots" |
| `caiosweet/DPC-Alert` (HACS) | Protecció civil, Itàlia | `requirements: []`, `entity.py` compartit, diagnostics, atribució explícita | Els atributs `today`/`tomorrow`/`aftertomorrow` i el sondeig de 30 min |
| `ha-incendiscat` (germà) | Incendis forestals i Pla Alfa, Catalunya | Tot l'esquelet d'enginyeria: layout, `runtime_data`, events al bus, `quality_scale.yaml`, CI, `release-please`, traduccions ca/es/en | Res. És la referència |
| `ha-avisoscat` (germà) | Avisos SMP del Meteocat | La disciplina de traps i el patró d'events | La multi-entrada per comarca: aquí no aplica |
| `dwd_weather_warnings` (HA core) | Avisos meteo, Alemanya | Res directament | És el contraexemple deliberat (§3) |

**No existeix cap integració de Home Assistant per a Protecció Civil de Catalunya ni
d'Espanya.** Cerca ✅ 2026-08-06 sobre GitHub (`search/repositories` amb `proteccion civil`,
`proteccio civil`, `cecat`, `transparenciacatalunya`, `meteocat`): cap resultat rellevant més
enllà d'aquest mateix repositori i dels dos germans. `aemet` a HA core cobreix predicció
meteorològica estatal, no activacions de plans. **Aquesta integració és la primera.**

---

## 2. `nina` (HA core): el model estructural

Verificat ✅ 2026-08-06 contra `home-assistant/core@dev`.

```jsonc
// homeassistant/components/nina/manifest.json
{ "domain": "nina", "name": "NINA", "config_flow": true,
  "integration_type": "service", "iot_class": "cloud_polling",
  "quality_scale": "silver",
  "requirements": ["pynina==1.0.2"],
  "single_config_entry": true }
```

```python
# homeassistant/components/nina/const.py
SCAN_INTERVAL: timedelta = timedelta(minutes=5)
SEVERITY_VALUES: list[str] = ["extreme", "severe", "moderate", "minor", "unknown"]
SERVICE_GET_DETAILS: str = "get_details"
```

### Què copiem, literalment

| Decisió de `nina` | Per què aplica al CECAT |
| --- | --- |
| **`single_config_entry: true`** | El CECAT és per a tot Catalunya i no hi ha eix territorial per activació ([`01`](01-data-sources.md) §5). Igual que NINA és nacional |
| **`integration_type: "service"`** | És un servei al núvol, no un dispositiu. `DeviceInfo.entry_type = SERVICE` |
| **`iot_class: "cloud_polling"`** | No hi ha push ni webhook |
| **`SCAN_INTERVAL = 5 min`** | Coincideix independentment amb el que la mesura de cadència recomana ([`01`](01-data-sources.md) §7.3: p05 de 14 min entre canvis). Dos camins diferents, la mateixa xifra |
| **`SEVERITY_VALUES` amb `"unknown"` al final** | Un vocabulari tancat **sempre** necessita la vàlvula d'escapament. El nostre `plafase` en necessita una perquè `plaacronim` no és un conjunt tancat ([`01`](01-data-sources.md) trap 5) |
| **Objectiu 🥈 silver** | Fita realista per a una integració d'un sol endpoint. `ha-incendiscat` ja hi apunta amb `quality_scale.yaml` |

### Què **no** copiem

| Cosa de `nina` | Motiu |
| --- | --- |
| **`requirements: ["pynina==1.0.2"]`** | Els dos germans van amb **`requirements: []`** i aquí el client cap en 60 línies: un `GET`, un `json.loads`, vuit camps. Una dependència de PyPI per això és pes mort i una superfície de manteniment que no controlem |
| **"Message slots"** (`CONF_MESSAGE_SLOTS`, N entitats fixes preassignades) | És una solució al problema de NINA: desenes d'avisos simultanis per regió. Nosaltres tenim **1 o 2 files**, màxim un grapat. Un sensor de recompte més un atribut amb la llista és més honest i no deixa entitats buides al registre |
| `SERVICE_GET_DETAILS` (acció de servei per llegir detalls) | Els detalls caben als atributs. Els germans exposen **events al bus** en lloc d'accions, i és el patró que ja té blueprint |
| Els filtres per `headline` i per `area` amb regex | Amb 1-2 files no hi ha res a filtrar |

---

## 3. `dwd_weather_warnings` vs `nina`: el precedent de la separació

Aquest és l'argument pel qual `ha-cecat` existeix com a repositori independent i no com a
plataforma dins d'`ha-avisoscat`.

**No el repeteixo aquí.** Està desenvolupat, amb els sis arguments ordenats per pes, a
[`ha-avisoscat/docs/02-existing-integrations.md` §8](https://github.com/pmontp19/ha-avisoscat/blob/main/docs/02-existing-integrations.md#8-decisió-meteocat-i-protecció-civil-van-separats),
i el precedent alemany a
[§5](https://github.com/pmontp19/ha-avisoscat/blob/main/docs/02-existing-integrations.md#5-alemanya-dwd_weather_warnings--nina--el-precedent-per-a-la-pregunta-una-o-dues)
del mateix document.

Resum en tres línies, per si algú arriba aquí primer:

1. **L'àmbit territorial no encaixa.** El SMP del Meteocat és per comarca i la seva integració
   és multi-entrada; el CECAT és per a tot Catalunya. Barrejar-los duplicaria el mateix INUNCAT
   una vegada per entrada.
2. **L'abast del CECAT és molt més gran que el temps**: SISMICAT, TRANSCAT, RADCAT, PENTA,
   PLASEQTA. Ningú buscarà un sensor sísmic dins d'una integració que es diu "Avisos Meteocat".
3. **Autoritats i modes de fallada diferents**: Departament de Territori (SMC) contra
   Departament d'Interior (CECAT), i dos serveis tècnicament sense relació.

**La recerca d'aquest repositori confirma la decisió amb dades noves que `ha-avisoscat` no
tenia**: el dataset declara "Sense informació geogràfica" a la metadata i **no existeix cap
font estructurada de territori per activació** ([`01`](01-data-sources.md) §5). L'eix
territorial no és que sigui incòmode: **no hi és**. `single_config_entry: true` no és una
elecció de disseny, és el que la font permet.

---

## 4. `caiosweet/DPC-Alert` (Itàlia): l'equivalent més proper

Verificat ✅ 2026-08-06 contra `caiosweet/Home-Assistant-custom-components-DPC-Alert@master`.

```jsonc
{ "domain": "dpc", "name": "Dipartimento Protezione Civile",
  "config_flow": true, "iot_class": "cloud_polling",
  "requirements": [] }          // ← sense single_config_entry: és per municipi
```

Arbre: `__init__.py`, `api.py`, `binary_sensor.py`, `config_flow.py`, `const.py`,
`diagnostics.py`, `entity.py`, `geojson_utils.py`, `manifest.json`, `sensor.py`,
`strings.json`, `translations/`.

### Què copiem

| Cosa | Nota |
| --- | --- |
| **`requirements: []`** | Confirma que una integració de protecció civil no necessita cap dependència. Mateixa política que els dos germans |
| **`entity.py` amb la classe base compartida** | Un sol lloc per a `DeviceInfo`, `_attr_attribution` i `available`. És el que fa `ha-incendiscat` |
| **`ATTRIBUTION` explícita** al `const.py` (`"Data provided by Civil Protection Department"`) | La nostra llicència **exigeix** atribució i data d'actualització ([`01`](01-data-sources.md) §11) |
| **`diagnostics.py`** des del primer dia | Requisit 🥉 bronze i l'única manera raonable de depurar text extern brut |
| Dues plataformes, `sensor` + `binary_sensor` | Exactament el que necessitem, i res més |

### Què evitem

| Cosa de DPC-Alert | Motiu |
| --- | --- |
| **`ATTR_TODAY` / `ATTR_TOMORROW` / `ATTR_AFTERTOMORROW`** | El DPC publica un butlletí diari amb horitzó de 3 dies. **El CECAT no té horitzó**: publica l'estat actual i prou ([`01`](01-data-sources.md) §7.1). Inventar-nos "demà" seria fabricar dades |
| **`DEFAULT_SCAN_INTERVAL = 30` min** | Massa lent per a la nostra font: el p05 entre canvis és de 14 min i el mínim observat de 5 segons. Anem a 5 min, que és gratis gràcies a `If-Modified-Since` |
| `geojson_utils.py`, `CONF_MUNICIPALITY`, `DEFAULT_RADIUS = 50 km` | El DPC publica zones d'allerta amb geometria. **La nostra font no té geometria de cap mena** |
| `DEFAULT_WARNING_LEVEL = 2` com a llindar de config | Amb tres fases i sense territori, un llindar configurable no compra res que una condició d'automació no faci millor |
| `version.py` a mà i `"version": "0.0.0"` al manifest | `release-please` gestiona la versió als germans. Mai editar-la a mà (`AGENTS.md`) |

DPC-Alert **no** declara `single_config_entry` perquè és per municipi. És el mateix eix que
separa `nina` de `dwd_weather_warnings`, i confirma la regla: **protecció civil d'àmbit
nacional o autonòmic → entrada única; per zona → multi-entrada.** El CECAT és del primer tipus.

---

## 5. Els germans: `ha-incendiscat` i `ha-avisoscat`

Verificat ✅ 2026-08-06 contra el checkout local d'`ha-incendiscat`.

```jsonc
// custom_components/incendiscat/manifest.json
{ "domain": "incendiscat", "name": "Incendis Catalunya",
  "codeowners": ["@pmontp19"], "config_flow": true,
  "integration_type": "service", "iot_class": "cloud_polling",
  "requirements": [],
  "single_config_entry": true }
```

`ha-cecat` hereta **tot** l'esquelet, sense discussió. La llista completa és a
[`04-architecture.md`](04-architecture.md); el resum:

| Convenció | On viu a `ha-incendiscat` |
| --- | --- |
| `requirements: []`, `integration_type: service`, `single_config_entry: true` | `manifest.json` |
| Estat a `entry.runtime_data` amb alias tipat, mai `hass.data[DOMAIN]` | `__init__.py` |
| Events al bus amb prefix de domini (`incendiscat_fire_detected`, `incendiscat_phase_change`, `incendiscat_service_degraded`) en lloc d'accions de servei | `const.py` |
| `_attr_translation_key` + `translations/{ca,es,en}.json`, els tres o `hassfest` falla | `translations/` |
| `DeviceInfo.entry_type = SERVICE` | `entity.py` |
| `quality_scale.yaml` amb `status: exempt` justificat regla per regla | `custom_components/incendiscat/quality_scale.yaml` |
| Cobertura mínima **95%** (`--cov-fail-under=95`), `pytest-homeassistant-custom-component` + `aioresponses`, zero xarxa real | `.github/workflows/ci.yml` |
| Fixtures que han de ser **respostes reals capturades, no inventades** | `tests/fixtures/` |
| `ruff check` + `ruff format --check` com a gates de CI | `.github/workflows/ci.yml` |
| Conventional Commits estricte, versió només via `release-please` | `AGENTS.md`, `CONTRIBUTING.md` |
| `SCAN_INTERVAL` per defecte 5 min, mín. 1, màx. 60 | `const.py` |

Dos patrons d'`ha-incendiscat` que aquí són especialment rellevants:

1. **`_prune_vanished`**: reconciliar la col·lecció completa cada cicle i emetre l'event de
   tancament quan un element desapareix de la resposta. `ha-incendiscat` el va necessitar
   perquè la vista ArcGIS esborra files antigues sense estat terminal. **Nosaltres el
   necessitem pel mateix motiu**: el CECAT gairebé no publica desactivacions ([`01`](01-data-sources.md)
   §7.4).
2. **Accés amb `.get()` i valor per defecte, mai indexació directa**, perquè la font pot canviar
   sense avís. Aquí és igual de cert: `planom` ja contradiu la seva pròpia documentació
   ([`01`](01-data-sources.md) trap 4).

D'`ha-avisoscat` copiem la **disciplina de traps** ([`01`](01-data-sources.md) §12): una taula
numerada on cada regla apunta a una captura real. El seu trap 11 (`fasedatahora` és local, no
ISO) ja anticipava aquesta font; aquí queda demostrat amb 1.146 punts de dades
([`01`](01-data-sources.md) §8).

---

## 6. Consumidors de tercers d'aquesta mateixa font

Val la pena mirar-los perquè demostren errors concrets que podem evitar.

### 6.1 `PabloCalomardo/Incendis_Forestals` ✅ 2026-08-06

No és una integració de Home Assistant: és un backend (`apps/api`) amb un connector
`ProteccioCivilPlansConnector` que ingereix `wj9c-j6vf` i el persisteix com a `OfficialNotice`.

Coses que fa bé i que confirmen decisions nostres:

- Fa servir `/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD`, que **inclou els camps de
  sistema** (`:id`, `:created_at`). Bona pista: nosaltres arribem al mateix amb
  `$select=:*,*` ([`01`](01-data-sources.md) §7.2).
- Fa servir `row.get(":id")` com a identificador extern, amb fallback a un hash de la fila.
- `validate()` comprova explícitament que el payload sigui una llista i, si no, llança.
- La seva documentació diu, correctament, que **no crea zones d'evacuació ni de restricció
  "perquè la font pública no publica geometries exactes"**. Coincideix amb la nostra conclusió
  de [`01`](01-data-sources.md) §5, arribada per un camí independent.

Coses que **evitem**:

| Què fa | Per què no ho fem |
| --- | --- |
| `plan = row.get("plaacronim") or row.get("planom") or "Proteccio Civil"` | El fallback a `planom` no compra res: és **idèntic** a `plaacronim` a 5/5 captures ([`01`](01-data-sources.md) trap 4) |
| `deduplication_hash` calculat sobre **tota** la fila (inclou `comunicatpdf` i `descripcio`) | `comunicatpdf` canvia dins de la mateixa fase ([`01`](01-data-sources.md) trap 11): cada actualització del PDF compta com a avís nou. Nosaltres identifiquem per **`(plaacronim, plafase)`** |
| `"area_bbox": "0.15,40.5,3.35,42.9"` fixa per a tot Catalunya | És honest per al seu model de dades, però és un bbox inventat. Nosaltres no exposem geometria: no en tenim |
| `plaactivat` només com a text al cos de l'avís (`f"Pla activat: {active}"`) | És el camp que distingeix prealerta d'activació. Ha de ser estructural, no prosa |

### 6.2 El sondejador anònim de la Wayback Machine 🗄️

A la Wayback Machine hi ha **23 consultes filtrades** a aquest endpoint fetes per algú altre, 21
el 2026-01-19 (totes dins de 7 segons) i 2 el 2026-07-03, sempre de la forma

```
?$where=plaactivat='SI' AND upper(plaacronim)='<ACRONIM>'
```

una per acrònim, sobre 21 acrònims. No sé qui és ni què construeix. Ens serveix per dues coses:

1. **Evidència de tercers sobre el vocabulari d'acrònims** esperat a la natura, incloent-hi
   quatre grafies (`FERROCAT`, `PROCICAT-FERROCARRIL`, `PROCICAT-CALOR`, `QUALITATAIRE`) que no
   surten a cap registre oficial ([`01`](01-data-sources.md) §3.2).
2. **La demostració del pitjor error possible amb aquesta font.** El filtre `plaactivat='SI'`
   descarta silenciosament **totes les prealertes**, que són el 51,4% dels comunicats del CECAT
   ([`01`](01-data-sources.md) §4). Qui hagi construït això no veu mai una prealerta i no ho
   sap. És el trap número 1 del nostre document, i li devem el descobriment.

---

## 7. Buits que aquesta integració omple

| Buit | Qui el té avui |
| --- | --- |
| Activacions de plans de Protecció Civil de Catalunya a Home Assistant | **Ningú** ✅ |
| Un senyal de "l'autoritat ha activat el pla", diferent de "el meteoròleg preveu mal temps" | `nina` per a Alemanya, `dpc` per a Itàlia. Res per a Catalunya ni Espanya |
| Events al bus per a plans de protecció civil | Ni `nina` ni `dpc` en tenen: els dos van per entitats. Els dos germans catalans sí, i és el que fa que un blueprint de notificació sigui trivial |
| Prealerta com a estat de primera classe, distingible de l'activació | Cap dels consumidors coneguts d'aquesta font ho fa bé (§6) |

---

## 8. Decisions derivades

| Decisió | Origen |
| --- | --- |
| `single_config_entry: true` | `nina`; i sobretot [`01`](01-data-sources.md) §5: no hi ha eix territorial per activació |
| `integration_type: "service"`, `iot_class: "cloud_polling"` | `nina`, `dpc`, `ha-incendiscat` |
| `requirements: []` | `dpc`, `ha-incendiscat`, `ha-avisoscat`. Contra `nina` |
| Sondeig per defecte de **5 min**, configurable 1-60 | `nina` (5 min) i la mesura de cadència de [`01`](01-data-sources.md) §7.3. Contra `dpc` (30 min) |
| `If-Modified-Since` en lloc d'`ETag` | Mesurat a [`01`](01-data-sources.md) §1. Cap dels precedents ho fa |
| **Prealerta com a estat separat**, no com a "no activat" | Buit detectat a §6. `plafase` manda, `plaactivat` és derivat |
| Vocabulari amb vàlvula d'escapament (`unknown`) i `warning` una sola vegada | `nina` (`SEVERITY_VALUES` acaba amb `"unknown"`), `ha-avisoscat` (meteor desconegut) |
| Events al bus, no accions de servei | `ha-incendiscat`, `ha-avisoscat`. Contra `nina` (`get_details`) |
| Reconciliació per absència (`_prune_vanished`) per detectar desactivacions | `ha-incendiscat`; necessari per [`01`](01-data-sources.md) §7.4 |
| Identitat de l'episodi = `(plaacronim, plafase)`, mai `:id` ni el hash de la fila | Error observat a §6.1 + [`01`](01-data-sources.md) trap 11 |
| Sense geometria, sense bbox, sense territori | `dpc` en té perquè la seva font en té. La nostra no |
| `quality_scale.yaml` amb objectiu 🥈 silver | `nina` (silver), `ha-incendiscat` |
| `diagnostics.py` des del primer dia | `dpc`, `ha-incendiscat` |
| Sense `plaicona` com a icona d'entitat | [`01`](01-data-sources.md) §11.3 (restricció de llicència sobre símbols oficials) |
