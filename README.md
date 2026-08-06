# Protecció Civil Catalunya (`ha-cecat`)

Integració de Home Assistant per a les **activacions dels plans de Protecció Civil de
Catalunya** (CECAT): INUNCAT, VENTCAT, NEUCAT, PROCICAT, SISMICAT, TRANSCAT i la resta.

> 🚧 **En recerca, amb el disseny tancat.** La font està verificada i **els cinc documents de
> disseny estan escrits**. El codi encara no hi és. Recerca feta el 2026-08-06; el que queda
> obert està llistat més avall, sense endolcir.

Un avís del Meteocat diu què preveu el meteoròleg; això diu si Protecció Civil ha activat
realment un pla, i en quina fase.

Els noms segueixen una regla: la família d'events parla de **fases** que comencen, canvien i
acaben (`cecat_plan_phase_started` / `_changed` / `_ended`), i el `binary_sensor` és l'únic que
parla d'**activació**. No és el mateix: una prealerta és una fase que comença, però la font diu
explícitament que "la prealerta no implica l'activació del pla".

## Veredicte de la recerca

**Sí, hi ha prou font per construir una integració útil, i és petita.** Les quatre preguntes que
bloquejaven el disseny estan respostes amb evidència, no amb conjectura. Detall complet i
matisos a [`docs/01-data-sources.md` §14](docs/01-data-sources.md#14-veredicte).

| Pregunta | Resposta |
| --- | --- |
| **Vocabulari** | Fases: exactament `PREALERTA` / `ALERTA` / `EMERGÈNCIA`, definides per la font oficial. Sense normalitat ni desactivació. Plans: 18 identitats conegudes, però **el conjunt no és tancat** |
| **Estat buit** | `[]`, observat directament i documentat. **Amb una correcció crítica**: `plaactivat: "NO"` també existeix, és la prealerta, i filtrar per `'SI'` amaga el 51,4% del senyal |
| **Territori** | **No existeix** cap font estructurada de territori per activació. Les comarques només són prosa dins del PDF del comunicat. Això confirma `single_config_entry: true` |
| **Història i cadència** | Només estat actual, mutat al lloc. **1,84 comunicats/dia** mesurats sobre 623 dies, p05 de 14 min entre comunicats consecutius. Sondeig de 5 min amb `If-Modified-Since` (verificat: retorna 304). "Recentment desactivat" és possible, però només per reconciliació de l'absència |

## Estat

| | |
| --- | --- |
| Domini de Home Assistant | `cecat` |
| Distribució | HACS (repositori personalitzat, de moment) |
| Font | [Dades obertes de la Generalitat](https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf), sense clau ni quota |
| Entitats previstes | 4 (3 + 1 de diagnòstic): `sensor.proteccio_civil_catalunya_fase_maxima`, `sensor.proteccio_civil_catalunya_plans`, `binary_sensor.proteccio_civil_catalunya_pla_activat`, `sensor.proteccio_civil_catalunya_darrera_actualitzacio` |
| Events previstos | 4: `cecat_plan_phase_started`, `cecat_plan_phase_changed`, `cecat_plan_phase_ended`, `cecat_service_degraded` |
| Dependències de PyPI | cap (`requirements: []`) |

> ⚠️ **Els `entity_id` d'aquesta taula corresponen a una instància de Home Assistant configurada
> en català.** Home Assistant genera l'`entity_id` inicial a partir del **nom traduït** de
> l'entitat, no de la clau de traducció interna, i el resol amb l'idioma del sistema en el moment
> de crear l'entitat: en una instància en castellà o en anglès seran diferents (p. ex.
> `sensor.proteccio_civil_catalunya_max_phase` en anglès en lloc de
> `sensor.proteccio_civil_catalunya_fase_maxima`). Si un exemple d'automació no troba l'entitat,
> comprova l'`entity_id` real a **Eines de desenvolupament → Estats**. És la mateixa convenció i
> el mateix advertiment que documenta
> [`ha-incendiscat`](https://github.com/pmontp19/ha-incendiscat#entitats).

## Documentació de disseny

| Document | Contingut |
| --- | --- |
| [`01-data-sources.md`](docs/01-data-sources.md) | Endpoint, esquema, vocabulari complet, estat buit, cadència, llicència, **15 traps de tolerància** i el **veredicte** |
| [`02-existing-integrations.md`](docs/02-existing-integrations.md) | `nina`, `dpc`, els germans, i dos consumidors reals d'aquesta mateixa font amb els seus errors |
| [`03-feature-spec.md`](docs/03-feature-spec.md) | Entitats, estats, atributs, events, config flow, criteris d'acceptació |
| [`04-architecture.md`](docs/04-architecture.md) | Layout, models, coordinator, resiliència, tests, CI, 14 decisions arquitecturals |
| [`05-implementation-plan.md`](docs/05-implementation-plan.md) | 13 tasques S/M amb criteris verificables i graf de dependències |
| [`captures/`](docs/captures/) | Les captures reals que sostenen cada afirmació |

## Què encara no se sap

El veredicte llista **sis** punts oberts en total
([`docs/01-data-sources.md` §14](docs/01-data-sources.md#14-veredicte)). Cap no bloqueja començar
a construir, i el disseny està fet per no petar mentrestant. Aquí hi ha **els quatre que tenen
una conseqüència visible per a l'usuari**; els oberts 4 i 5 s'ometen perquè §14 en qualifica
l'impacte de "Nul" i ja estan resolts al disseny. Si algun dia el veredicte en llista set,
aquest recompte ha de deixar de quadrar i s'ha d'actualitzar.

1. **La fase `EMERGÈNCIA` no s'ha observat mai** en un payload real (n'hi va haver 15 en 6 anys).
   És la fase que més importa i està coberta només amb un fixture sintètic marcat com a tal.
   (Obert 2.)
2. **La grafia de `plaacronim` per als plans d'actuació del PROCICAT** és desconeguda: quatre
   fonts oficials en donen quatre grafies diferents (`PROCICAT`, `FERROCAT`,
   `PROCICAT - Ferrocarril`, `PA PROCICAT - Transport Viatgers Ferrocarril`) i cap s'ha observat
   al feed. (Obert 1.)
3. **Si un canvi de fase substitueix la fila o l'edita.** Només s'ha observat una transició.
   Decideix si `:created_at` és fiable com a inici de fase. (Obert 3.)
4. **El blueprint pot notificar una escalada que no ha passat.** Si dos plans d'actuació distints
   comparteixen `plaacronim`, cosa que l'obert 1 fa plausible per al PROCICAT, un cicle en què un
   acaba i un altre comença es veu com una escalada d'un sol pla. És una limitació acceptada, amb
   les alternatives rebutjades documentades. (Obert 6.)

I tres limitacions que **no** es resoldran perquè són de la font, no de la recerca:

- **No hi ha territori afectat.** La integració no pot dir si el teu municipi està afectat, i
  qualsevol cosa que ho pretengui estarà mentint.
- **No hi ha històric.** Si Home Assistant està aturat quan un pla s'activa i es desactiva,
  l'episodi no ha existit.
- **La desactivació es detecta per absència**, amb la resolució de l'interval de sondeig. El
  CECAT gairebé no publica comunicats de tancament: 1 en 623 dies.

## Integracions germanes

- [`ha-avisoscat`](https://github.com/pmontp19/ha-avisoscat): avisos de temps sever del Meteocat.
- [`ha-incendiscat`](https://github.com/pmontp19/ha-incendiscat): incendis forestals i Pla Alfa.

Per què això va separat d'`ha-avisoscat`:
[`docs/02-existing-integrations.md` §3](docs/02-existing-integrations.md#3-dwd_weather_warnings-vs-nina-el-precedent-de-la-separació).

## Avís legal

Projecte no oficial, **no afiliat ni aprovat** pel CECAT ni per la Generalitat de
Catalunya.

Dades: **Generalitat de Catalunya. Departament d'Interior i Seguretat Pública. Direcció General
de Protecció Civil.** Publicades sota la
[Llicència oberta d'ús d'informació de Catalunya](https://web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies),
que exigeix citar la font i la data d'actualització.

Llicència del codi: [MIT](LICENSE).
