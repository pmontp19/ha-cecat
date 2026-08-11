# Fonts de dades: activacions dels plans de Protecció Civil (CECAT)

Recerca feta el **2026-08-06**. Continua la investigació parcial que
[`ha-avisoscat/docs/01-data-sources.md`](https://github.com/pmontp19/ha-avisoscat/blob/main/docs/01-data-sources.md)
§5 va deixar oberta, i respon les quatre preguntes que bloquejaven el disseny.

Convenció d'aquest document, igual que als repositoris germans:

| Marca | Significat |
| :---: | --- |
| ✅ | **Verificat en viu** contra el servei real, amb data i captura desada a [`captures/`](captures/) |
| 🗄️ | **Verificat sobre una captura d'arxiu** (Wayback Machine o llistat del contenidor de comunicats), amb data d'origen |
| 📄 | **Documentat** per la font oficial (descripció del dataset, comunicat del CECAT, registre oficial) |
| 🔶 | **Inferència** meva a partir de dades observades. Explicito l'evidència i el nivell de confiança |
| ❓ | **No verificat.** No ho he pogut observar ni trobar documentat |

---

## 1. Endpoint principal

```
GET https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json
```

Dataset Socrata **"Plans de protecció civil en fase de prealerta, alerta o emergència"**
al portal de Transparència de la Generalitat. Verificat en viu el 2026-08-06 ✅.

| Propietat | Valor | Evidència |
| --- | --- | --- |
| Identificador Socrata | `wj9c-j6vf` | ✅ |
| Autenticació | **Cap.** Sense API key, sense quota, sense `X-App-Token` | ✅ |
| Backend | Socrata NBE (`newBackend: true`) | ✅ metadata |
| Regió | `aws-eu-west-1-prod` | ✅ capçalera `X-Socrata-Region` |
| Autoria | Direcció General de Protecció Civil, Departament d'Interior i Seguretat Pública | ✅ metadata |
| Creat | 2024-07-08, publicat 2024-07-12 | ✅ metadata |
| Freqüència declarada | "Variable" | 📄 metadata `custom_fields` |
| Àmbit geogràfic declarat | Catalunya, **"Sense informació geogràfica"** | 📄 metadata `custom_fields` |
| Files vistes simultàniament | 1 (2026-08-06), 2 (2026-01-19), 0 (2026-06-16) | ✅ 🗄️ |
| `viewCount` / `downloadCount` | 22.462 / 677 | ✅ metadata |

### Variants d'endpoint (totes verificades ✅)

| Forma | Ús | Nota |
| --- | --- | --- |
| `/resource/wj9c-j6vf.json` | La que farem servir | Retorna només els camps de negoci |
| `/resource/wj9c-j6vf.json?$select=:*,*` | Afegeix `:id`, `:created_at`, `:updated_at`, `:version` | **Clau per detectar l'inici de fase** (§7) |
| `/api/v3/views/wj9c-j6vf/query.json?accessType=DOWNLOAD` | Equivalent, inclou els camps de sistema per defecte | La que fa servir el consumidor de tercers de [`02`](02-existing-integrations.md) §6.1 |
| `/api/views/wj9c-j6vf.json` | Metadata completa: descripció, llicència, `rowsUpdatedAt`, `columns[].cachedContents` | No cal en runtime |

### Capçaleres i GET condicional ✅

Captura completa a [`captures/http-headers-2026-08-06.txt`](captures/http-headers-2026-08-06.txt).

```
X-SODA2-Fields: ["plaicona","plaacronim","planom","plafase","plaactivat","fasedatahora","comunicatpdf","descripcio"]
X-SODA2-Types:  ["url","text","text","text","text","text","url","text"]
X-SODA2-Truth-Last-Modified: Thu, 06 Aug 2026 09:20:17 GMT
Last-Modified:               Thu, 06 Aug 2026 09:20:17 GMT
ETag: "YnJhdm8u…---gzipFV3yYjLqxnXzyd1M5Hh_3x-37Eg--gzip--gzip"
```

| Prova | Resultat | Conseqüència de disseny |
| --- | --- | --- |
| `If-Modified-Since: <Last-Modified>` | **HTTP 304**, cos buit ✅ | **Fer-lo servir sempre.** Un cicle sense canvis costa una capçalera |
| `If-None-Match: <ETag>` | **HTTP 200** amb cos sencer ✅ | L'ETag **no** es honora. A més arriba amb el sufix `--gzip` duplicat, senyal que està trencat pel middleware de compressió. **No fer-lo servir** |
| `X-SODA2-Types` | Tots els camps són `text` o `url` | **No hi ha cap columna de data tipada.** No es pot filtrar ni ordenar per data al servidor |
| `Content-Encoding: gzip` | Suportat | Payload real < 500 bytes; irrelevant, però gratis |

---

## 2. Esquema de camps

Totes les descripcions són literals de la metadata oficial (📄). La columna "Observat" recull
els valors reals de les **cinc files** observades a [`captures/`](captures/) (2024-12-02,
2026-01-19 ×2, 2026-07-03 i 2026-08-06; la captura de camps de sistema és una segona
projecció d'aquesta última, no una sisena fila).

| Camp | Tipus SODA | Descripció oficial | Observat |
| --- | --- | --- | --- |
| `plaicona` | `url` | "Icona representativa del pla (URL a icona corresponent de DocumentsOberts)" | Objecte `{"url": "…/cecat/docs/ico_INUNCAT.png"}`. **El nom del fitxer no es deriva de l'acrònim** (§6.3) |
| `plaacronim` ⭐ | `text` | "Acrònim Pla (ex: PLASEQTA)" | `INUNCAT`, `NEUCAT`, `INFOCAT`, `PROCICAT`. Part de la clau natural, juntament amb `plafase` |
| `planom` | `text` | "Nom complet del Pla (ex: Pla especial d'emergència exterior del sector químic de Tarragona)" | **Sempre idèntic a `plaacronim`** a les 5 files observades. La descripció oficial no es compleix |
| `plafase` ⭐ | `text` | "Fase actual del Pla" | `PREALERTA`, `ALERTA`. `EMERGÈNCIA` documentat però no observat |
| `plaactivat` ⭐ | `text` | "Indica si el Pla està activat o no. (Si/No)" | `SI` amb `ALERTA`; **`NO` amb `PREALERTA`** 🗄️. Majúscules, no `Si`/`No`. **La descripció oficial i l'observació no coincideixen** (§3.3) |
| `fasedatahora` ⭐ | `text` | "Data/hora de l'inici de la fase" | `DD/MM/YYYY HH:MM`, **hora local d'Europe/Madrid** (§8) |
| `comunicatpdf` | `url` | "Comunicat del Centre de Coordinació Operativa de Catalunya (CECAT) (URL a Documents Oberts)" | Objecte `{"url": …}`. **Pot contenir caràcters no segurs per a URL** (§6.2) |
| `descripcio` | `text` | "Descripció addicional (opcional)" | Sempre present a les 5 files observades, però **brut**: espais dobles, sufix `" - "`, salts de línia (§9) |

Els camps `url` són **objectes amb una clau `url`**, no cadenes. Poden faltar del tot: el
`cachedContents` de la metadata no reporta ni `non_null` ni `null` per a `plaicona` i
`comunicatpdf`, mentre que sí ho fa per a tots els camps `text` ✅.

### Camps de sistema (només amb `$select=:*,*`) ✅

Resposta sencera desada a
[`captures/wj9c-j6vf-camps-sistema-2026-08-06.json`](captures/wj9c-j6vf-camps-sistema-2026-08-06.json),
capturada en viu el **2026-08-06 12:31 UTC** amb la mateixa fila de l'INUNCAT que la captura de
projecció pelada. Els quatre camps que afegeix `$select=:*,*`:

```json
{ ":id": "row-vb4t-m2s8~23fg",
  ":version": "rv-szy2-7t4a_a4hr",
  ":created_at": "2026-08-05T11:18:09.349Z",
  ":updated_at": "2026-08-06T09:20:17.588Z" }
```

`:created_at` **2026-08-05T11:18:09Z** contra `fasedatahora` **05/08/2026 13:18**: la mateixa
instant (CEST = UTC+2), al minut. La precisió és de mil·lisegons (`.349Z`) i es trunca a
segons en arribar a `started_at`. Vegeu §7 i §8.

---

## 3. Pregunta 1: vocabulari complet

### 3.1 Fases: `PREALERTA` / `ALERTA` / `EMERGÈNCIA`, i res més

**El conjunt és tancat i està documentat oficialment** 📄. La descripció del dataset
(1.995 caràcters, desada a
[`captures/wj9c-j6vf-metadata-2026-08-06.json`](captures/wj9c-j6vf-metadata-2026-08-06.json))
enumera exactament tres fases i les defineix. Literals:

> Les fases són les següents:
>
> **PREALERTA**: La prealerta es produeix, en general, davant de les situacions següents: Quan és
> previsible un fenomen que pot produir situacions de risc per a la població a mitjà termini. […]
> **La prealerta no implica l'activació del pla.**
>
> **ALERTA**: El pla s'activa en fase d'alerta, en general, davant de les situacions següents: Quan
> hi ha paràmetres objectius que fan preveure una situació d'emergència important per a la població
> a curt termini. […]
>
> **EMERGÈNCIA**: El pla s'activa en fase d'emergència, en general, davant de les situacions
> següents: Quan s'informa de l'activació en fase d'emergència d'un pla especial de la Generalitat
> per afectació a la zona on es troba el municipi, la comarca o el territori. […]

| Fase | `plaactivat` | Evidència |
| --- | :---: | --- |
| `PREALERTA` | **`NO`** | 🗄️ observat 2024-12-02 ([captura](captures/wj9c-j6vf-prealerta-2024-12-02.json)) + 📄 "la prealerta no implica l'activació del pla" + 📄 comunicat oficial: "Cal recordar que la situació de Prealerta no comporta l'activació del Pla" ([captura](captures/comunicat-prealerta-inuncat-2026-08-02.txt)) |
| `ALERTA` | `SI` | ✅ 2026-08-06, 🗄️ 2026-01-19 ×2, 🗄️ 2026-07-03 ([captura](captures/wj9c-j6vf-infocat-2026-07-03.json)) |
| `EMERGÈNCIA` | `SI` 🔶 | 📄 definida a la descripció. **Mai observada** ❓. Confiança alta que és `SI`: la definició diu explícitament "el pla s'activa en fase d'emergència" |

**No hi ha fase de normalitat ni de desactivació.** Ho confirmen tres coses independents:

1. El títol del dataset delimita l'abast: "*en fase de prealerta, alerta o emergència*".
2. La descripció oficial: "Quan no hi ha cap pla d'emergència activat, el conjunt de dades és
   buit, presenta 0 files" 📄.
3. Del catàleg de 1.146 comunicats del CECAT (§7) només **1** és de tipus `DESACTIVACIO` en
   623 dies 🗄️. El comunicat de prealerta n'explica el motiu: "La situació de risc contemplada
   en aquest comunicat es donarà per finalitzada, **sense necessitat d'una comunicació de
   tancament per part del CECAT**, un cop acabi el període meteorològic especificat" 📄.

**Verificació per agregació** ✅. `$select=plaacronim,plafase,plaactivat,count(*)&$group=…`
funciona (HTTP 200), però amb el dataset a 1 fila només retorna l'estat actual. **L'agregació
sobre aquest dataset no pot descobrir el vocabulari**, perquè el dataset no té història (§7).
Per això les fonts d'aquesta secció són la descripció oficial i les captures d'arxiu, no una
agregació.

**Subnivells que el dataset no exposa** 🔶. Els plans especials tenen internament situacions
graduades dins de l'emergència (l'INFOCAT en té 0/1/2/3). `plafase` les aplana a un sol
literal `EMERGÈNCIA`: cap capítol de la metadata les esmenta i el camp és `text` lliure.
Confiança mitjana; no ho he pogut comprovar amb una activació real d'emergència.

### 3.2 Plans: 18 identitats conegudes, i el conjunt no és tancat

Quatre fonts independents, cap d'elles completa per si sola:

| Font | Què aporta | Marca |
| --- | --- | --- |
| **A.** `xqqe-tgav` "Registre general de plans de protecció civil de Catalunya", filtrat `ambit='Generalitat'` | **17 plans de nivell Generalitat**, amb risc, estat d'homologació i enllaç oficial. Registre autoritatiu, `rowsUpdatedAt` 2026-07-14 | 📄 ✅ |
| **B.** `wfei-fjk5` "Nombre d'avisos i activacions…" 2017-2022 | 13 acrònims amb la tipologia d'emergència de cadascun i el volum d'activacions | 📄 ✅ |
| **C.** Contenidor de comunicats del CECAT (§7) | Els **tokens de pla que el CECAT escriu de veritat** als noms dels 1.146 comunicats, i les 18 icones publicades | 🗄️ |
| **D.** Llista d'acrònims que un consumidor de tercers sondeja | 21 acrònims esperats "a la natura" | 🗄️ |

Taula unificada. "Comunicats" és el recompte de comunicats del CECAT entre 2024-11-20 i
2026-08-06 (§7); "Activ. 17-22" és prealertes + alertes + emergències de `wfei-fjk5`, que només
desglossa **13 plans** i no té cap fila per pla d'actuació: les seves files de tipologia
"Ferrocarril" van sota `pla = PROCICAT`. Per això els quatre PA del PROCICAT hi consten com a
`n/a` i no com a zero.

| Acrònim | Risc / pla | Comunicats | Activ. 17-22 | Icona pròpia | Al registre |
| --- | --- | ---: | ---: | :---: | :---: |
| `INUNCAT` | Inundacions | 314 | 256 | ✅ | ✅ |
| `PROCICAT` | Territorial multirisc | 267 | 992 | ✅ | ✅ (`T`) |
| `VENTCAT` | Ventades | 135 | 115 | ❌ 404 | ✅ |
| `INFOCAT` | Incendis forestals | 104 | 69 | ✅ | ✅ |
| `AEROCAT` | Aeronàutic | 100 | 263 | ✅ | ✅ |
| `TRANSCAT` | Transport de mercaderies perilloses | 57 | 81 | ✅ | ✅ |
| `NEUCAT` | Nevades | 55 | 39 | ✅ | ✅ |
| `PLASEQTA` | Químic, sector de Tarragona | 32 | (dins PLASEQCAT) | ❌ 404 | ✅ |
| `PLASEQCAT` | Químic en instal·lacions | 30 | 141 | ✅ | ✅ |
| `ALLAUCAT` | Allaus | 29 | 26 | ✅ | ✅ |
| `CAMCAT` | Contaminació marina | 12 | 53 | ✅ | ✅ |
| `RADCAT` | Radiològic | 6 | 3 | ✅ | ✅ |
| `PENTA` | Nuclear (Tarragona) | 3 | 1 | ✅ | ❌ pla estatal |
| `NOPLA` | Comunicat sense pla associat | 2 | n/a | ❌ | ❌ |
| `SISMICAT` | Sísmic | 0 | 11 | ✅ | ✅ |
| Pla per **Pandèmies** | Pandèmies | 0 | n/a | ✅ `ico_PROCICAT_PANDEMIA.png` | ✅ (nom llarg, sense acrònim) |
| PA PROCICAT **Ferrocarril** | Transport de viatgers per ferrocarril | 0 | n/a | ✅ `ico_PROCICAT_FERROCARRIL.png` | ✅ |
| PA PROCICAT **Contaminació a l'Ebre (Flix)** | Contaminació de l'Ebre | 0 | n/a | ✅ `ico_PROCICAT_CONTAMINACIÓ.png` | ✅ |
| PA PROCICAT **Subsidència, barri de l'Estació de Sallent** | Territorial multirisc | 0 | n/a | ❌ | ✅ |

Tres avisos importants sobre aquesta taula:

1. **El conjunt no és tancat.** El registre `xqqe-tgav` té **5.806 files** i creix (última
   modificació 2026-07-14); els 17 de nivell Generalitat en són una tallada. `PENTA` demostra
   que el CECAT publica activacions de plans que **no** són al registre de la Generalitat
   (és un pla nuclear de competència estatal). `NOPLA` demostra que hi ha comunicats sense pla.
   **Cap disseny pot dependre d'una llista blanca d'acrònims.**
2. **Els acrònims dels PA del PROCICAT són desconeguts** ❓. El registre els anomena
   "PA PROCICAT - Transport de viatgers per Ferrocarril", el dataset `92sv-nckr` els anomena
   `PROCICAT - Ferrocarril`, `eqag-gzjs` els anomena `PA PROCICAT - Transport Viatgers
   Ferrocarril`, i el consumidor de tercers sondeja `FERROCAT`, `PROCICAT-FERROCARRIL`,
   `PROCICAT-CALOR`, `PROCICAT-FRED`, `PROCICAT-ONATGE`, `PANDEMIA` i `QUALITATAIRE`. **Quatre
   grafies per al mateix pla i cap font diu quina apareix a `plaacronim`.** Als 267 comunicats
   de PROCICAT el token és sempre `PROCICAT` pelat 🗄️, i les úniques icones que distingeixen
   subplans són `ico_PROCICAT_*` 🗄️: per tant la meva hipòtesi és que `plaacronim` diu
   `PROCICAT` i el subpla només es distingeix per `plaicona` i `descripcio` 🔶 (confiança
   mitjana-alta).
3. **`QUALITATAIRE`** és l'únic acrònim sondejat per tercers que no apareix a cap registre
   ni a cap comunicat ni a cap icona ❓. No el puc confirmar.

Detall de la font A a
[`captures/registre-plans-generalitat-2026-08-06.json`](captures/registre-plans-generalitat-2026-08-06.json),
de la font B a
[`captures/wfei-fjk5-activacions-2017-2022.json`](captures/wfei-fjk5-activacions-2017-2022.json).

### 3.3 `plaactivat`: el domini documentat no és el domini observat

La descripció oficial escriu el domini com a **"(Si/No)"** 📄, en minúscules amb inicial. Totes
les observacions donen **`SI`** i **`NO`** en majúscules ✅ 🗄️. Les dues grafies conviuen a la
mateixa font: una a la documentació del camp i l'altra a les dades.

**Per això la comparació no pot ser estricta.** `plaactivat == "SI"` falla amb `Si`, amb ` SI `
i amb el camp absent, i el cas on falla és precisament el que més importa: una fila
d'`EMERGÈNCIA`, que **mai s'ha observat** (§3.1) i de la qual per tant no sabem la grafia.

Regla, la mateixa tolerància que `plafase` (trap 14) i coherent amb AD-6 "`plafase` mana,
`plaactivat` és derivat":

| Valor de `plaactivat` (normalitzat: `strip` + `casefold` + sense diacrítics) | `activated` |
| --- | --- |
| `no` | **`False`** |
| `si` | `True` |
| Absent, buit, o qualsevol altre literal | **Es deriva de la fase**: `True` si la fase és `ALERTA` o `EMERGÈNCIA`, `False` altrament (una pertinença, no una comparació d'ordre, per tant una fase irreconeixible hi dona `False` sense poder llançar). `warning` una sola vegada per literal, i **el camp absent també avisa**: hi entra amb un sentinel explícit perquè un canvi d'esquema sobre el camp que governa el sensor `SAFETY` no pugui passar en silenci ([`04`](04-architecture.md) §4) |

`activated = False` **només** quan el valor normalitzat és exactament `no`. Un literal que no
reconeixem no pot llegir-se mai com a "no passa res": el que fa és cedir la decisió a `plafase`,
que és el camp autoritatiu. Si la fase també és desconeguda (`Phase.UNRECOGNIZED`, que queda fora de
`PHASE_ORDER` per AD-8) no hi ha res amb què comparar i `activated` és `False`, amb els dos
literals registrats als diagnostics.

---

## 4. Pregunta 2: comportament amb zero plans actius

**Retorna `[]`, un array JSON buit.** Establert per tres vies convergents:

| Via | Evidència |
| --- | --- |
| Observació directa d'un instant buit | 🗄️ Snapshot de la Wayback Machine del **2026-06-16 18:15:46 UTC** de l'endpoint sense filtres: cos exacte `[]`. Desat a [`captures/wj9c-j6vf-buit-2026-06-16.json`](captures/wj9c-j6vf-buit-2026-06-16.json) |
| Documentació oficial | 📄 Descripció del dataset: "Quan no hi ha cap pla d'emergència activat, el conjunt de dades és buit, **presenta 0 files**" |
| 19 consultes filtrades buides | 🗄️ El 2026-01-19 11:07 UTC, 19 dels 21 acrònims sondejats retornaven `[]`; només `INUNCAT` i `NEUCAT` tenien fila |

**Però la resposta ingènua a la pregunta és una trampa**, i és la troballa més important
d'aquesta recerca:

> El dataset **sí** conté files amb `plaactivat: "NO"`. Corresponen a la fase `PREALERTA`,
> que per definició oficial no activa el pla. `[]` i `plaactivat: "NO"` **no** són la mateixa
> cosa i no s'exclouen.

Fila real de prealerta, 🗄️ arxivada el **2024-12-02 09:18:52 UTC**
([captura](captures/wj9c-j6vf-prealerta-2024-12-02.json)):

```json
[{ "plaicona": { "url": "https://documents.dadesobertes.gencat.cat/cecat/docs/ico_PROCICAT.png" },
   "plaacronim": "PROCICAT",
   "planom": "PROCICAT",
   "plafase": "PREALERTA",
   "plaactivat": "NO",
   "fasedatahora": "01/12/2024 19:18",
   "comunicatpdf": { "url": "https://documents.dadesobertes.gencat.cat/cecat/docs/I-109233_ACTUALITZACIO--NOACTIVAT_PROCICAT_202412020353.pdf" },
   "descripcio": "Accident autocar. N-320 Porte-Puymorens   (Porta, Dep. Pirineus Orientals)\nRuta L'Hospitalet de Llobregat <-> Andorra  - " }]
```

I no és un cas marginal: dels 1.146 comunicats del CECAT, **589 (51,4%) porten el token
`NOACTIVAT`** i els altres **557 (48,6%) el token `ACTIVAT`** 🗄️ (589 + 557 = 1.146; un dels 557
és l'únic comunicat de `DESACTIVACIO`, que també porta `--ACTIVAT` al nom). **Filtrar per
`plaactivat='SI'` amaga la meitat del senyal**, que és exactament l'error que comet el
consumidor de tercers que va deixar les consultes arxivades
([`02`](02-existing-integrations.md) §6.2).

Contracte de parseig resultant, dues dimensions ortogonals:

| El que veus | Significat |
| --- | --- |
| `[]` | Cap pla en cap de les tres fases. Estat de normalitat |
| Fila amb `plafase: PREALERTA`, `plaactivat: NO` | Vigilància activa, pla **no** activat |
| Fila amb `plafase: ALERTA` o `EMERGÈNCIA`, `plaactivat: SI` | Pla **activat** |

---

## 5. Pregunta 3: granularitat territorial

**No existeix cap dataset que doni el territori afectat per activació.** He recorregut el
catàleg del portal amb `GET /api/catalog/v1?q=protecció civil&limit=100` (27 resultats) i he
inspeccionat la metadata de tots els candidats ✅.

| Dataset | Nom | Territori? | Per activació? | Veredicte |
| --- | --- | --- | --- | --- |
| `wj9c-j6vf` | Plans en fase de prealerta, alerta o emergència | **No.** Metadata: "Sense informació geogràfica" | (és el feed) | Catalunya sencera |
| `eqag-gzjs` | Obligacions i vigències dels plans municipals | **Sí**: `ine5`, `municipi`, `comarca`, `vegueria`, `sstt`, `província` | **No.** Mapa de risc **estàtic** | Enriquiment estàtic possible, vegeu avall |
| `xqqe-tgav` | Registre general de plans | Sí, per al pla municipal | No | Registre administratiu |
| `92sv-nckr` | Evolució d'activacions dels plans | No | No, agregat anual | Estadística |
| `wfei-fjk5` | Nombre d'avisos i activacions | No | No, agregat anual | Estadística |
| `9gu7-iwci` | Refugis climàtics dels municipis | Sí | Irrellevant | Fora d'abast |
| 12 recursos `type: href` | "Mapa de Protecció Civil: Risc X" | Visors, no APIs | No | Mapes de risc estàtics |

El territori afectat existeix, però **només com a prosa dins del PDF del comunicat**. Ho diu
la descripció oficial del dataset 📄: "[els comunicats] poden contenir consells
d'autoprotecció, **comarques afectades** o restriccions per a la població". I es confirma
llegint-ne un ✅ ([captura](captures/comunicat-prealerta-inuncat-2026-08-02.txt)):

> Segons informa el SMC, demà dilluns 3 d'agost a partir del migdia pot ploure amb intensitat
> superior a 20 mm / 30 minuts a **comarques de Terres de l'Ebre, Ponent, Prepirineu i
> Pirineu**.

Ni tan sols són comarques: són **zones meteorològiques** del SMC, en text lliure, dins d'un
PDF. Extreure-ho requeriria un parser de PDF i un mapatge de zones a comarques, amb dues
capes d'heurística sobre text extern.

**Conseqüència: `single_config_entry: true`.** No hi ha res a configurar per entrada perquè no
hi ha eix territorial: quan s'activa l'INUNCAT, s'activa per a tot Catalunya. Dues entrades
serien dues còpies idèntiques del mateix estat, amb `unique_id` diferents i events duplicats.
És el mateix argument que fa que `nina` (nacional) el declari i `dwd_weather_warnings`
(regional) no ([`ha-avisoscat/docs/02`](https://github.com/pmontp19/ha-avisoscat/blob/main/docs/02-existing-integrations.md)
§5 i §8.1).

**L'enriquiment estàtic amb `eqag-gzjs` queda fora de la v1**, tot i ser temptador (947
municipis × pla, amb `ine5`). El motiu no és cost sinó correcció: aquest dataset diu "el teu
municipi està exposat al risc d'inundacions i s'integra a l'INUNCAT", **no** "el teu municipi
està afectat ara". Un `binary_sensor.el_meu_municipi_afectat` construït sobre un mapa estàtic
diria "sí" cada vegada que s'activa l'INUNCAT en qualsevol punt de Catalunya, perquè els 947
municipis hi consten. Seria un senyal fals amb aparença de precisió. Vegeu
[`03-feature-spec.md`](03-feature-spec.md) §7.

---

## 6. `comunicatpdf`, `plaicona`: estabilitat i forma

### 6.1 Les URL dels PDF són estables i permanents ✅

Provat el 2026-08-06 amb dues versions del mateix comunicat, la vigent i la que
`ha-avisoscat` va capturar el dia abans:

| URL | HTTP | `content-length` | `content-md5` | `last-modified` |
| --- | :---: | ---: | --- | --- |
| `…_INUNCAT_202608061114.pdf` (vigent) | **200** | 1.041.711 | `8fUxN68WG+5yAjnzpvA43A==` | 2026-08-06 09:20:17 GMT |
| `…_INUNCAT_202608051838.pdf` (anterior) | **200** | 537.838 | `dHqmdZpMHUcHxpRYVKylPQ==` | 2026-08-05 16:39:47 GMT |

Els dos resolen, amb mides i hash diferents. El magatzem és Azure Blob Storage
(`x-ms-version`, `x-ms-meta-ctime`; el contenidor real és
`https://tdoprostg.blob.core.windows.net/cecat`). El patró és **append-only**: cada
actualització publica un fitxer nou amb una URL nova i **les antigues no s'esborren**.

Per tant: una URL de `comunicatpdf` és un enllaç permanent segur d'emmagatzemar i mostrar,
però **el valor del camp canvia sovint** dins d'una mateixa fase (§7). Si el guardem com a
atribut, cada actualització del comunicat provoca un canvi d'atribut sense canvi d'estat.

### 6.2 Els noms de fitxer no són un contracte 🗄️

El contenidor té 1.224 blobs: **1.146 PDF amb nom canònic**

```
I-<num_incident>_<ACCIO>--<ESTAT>_<PLA>_<YYYYMMDDHHMM>.pdf
```

**36 PDF amb nom lliure**, 18 icones de pla, 23 entrades sota `icones/` (icones ADR), i un
`test.txt`.
Exemples reals dels 36:

```
InstruccionsalapoblacióincendilaBisbald'Empordà4tconfinament.pdf   ← accents i apòstrof, dins d'una URL
InstruccionsalapoblacióRemolins,bítem,jesúsiRoquetes.pdf           ← coma
20260710_14_55_recomanacionsBisbalPenedès.pdf
ResolucióINUNCATrestriccions13_10_2025-1.pdf
Instruccionsalapoblació.pdf                                        ← 2,2 MB
test.txt                                                           ← no és un PDF
```

El primer d'aquests és el valor real de `comunicatpdf.url` a la captura del 2026-07-03 🗄️
([`captures/wj9c-j6vf-infocat-2026-07-03.json`](captures/wj9c-j6vf-infocat-2026-07-03.json): el
nom és al llistat del contenidor **i** la fila demostra que era el valor del camp).
**Una URL amb `ó`, `à`, `é` i `'` sense codificar no és RFC 3986.** Qualsevol client HTTP
que la reconstrueixi o la validi estrictament pot petar; el codi ha de tractar el camp com a
cadena opaca que només mostra, no com a URL que valida.

### 6.3 `plaicona` no es deriva de l'acrònim 🗄️

Hi ha **18 icones** al contenidor, publicades totes el 2024-08-20:

```
ico_AEROCAT ico_ALLAUCAT ico_CAMCAT ico_INFOCAT ico_INUNCAT ico_NEUCAT ico_PENTA
ico_PLASEQCAT ico_PROCICAT ico_RADCAT ico_SISMICAT ico_TRANSCAT
ico_PROCICAT_CONTAMINACIÓ ico_PROCICAT_FERROCARRIL ico_PROCICAT_ONADA_CALOR
ico_PROCICAT_ONADA_FRED ico_PROCICAT_PANDEMIA ico_PROCICAT_VENT
```

Dos forats verificats amb sondeig HTTP ✅: **`ico_VENTCAT.png` retorna 404** tot i que VENTCAT
té 135 comunicats, i **`ico_PLASEQTA.png` retorna 404** tot i que PLASEQTA en té 32. Existeix
en canvi `ico_PROCICAT_VENT.png`, que és el nom històric del VENTCAT quan era un pla
d'actuació del PROCICAT.

Hipòtesi 🔶 (confiança mitjana-alta): les files de VENTCAT porten
`plaicona = ico_PROCICAT_VENT.png`, i les de PLASEQTA alguna altra icona o cap. Sigui com
sigui, la conclusió de disseny és ferma: **mai construir la URL de la icona a partir de
`plaacronim`, i mai assumir que `plaicona` existeix o resol**. Fer servir les icones pròpies
de Home Assistant i, si de cas, exposar `plaicona` com a atribut informatiu.

---

## 7. Pregunta 4: història i cadència

### 7.1 El dataset no té història ✅

Tres evidències independents:

1. **Nom oficial en anglès** 📄: "Civil protection plans **currently** in the pre-alert, alert
   or emergency phase".
2. **`$select=count(*)` = 1** ✅ el 2026-08-06, i `= 1` també 🗄️ el 2024-12-02. Amb 537
   activacions en 623 dies (§7.3), un dataset històric no tindria 1 fila.
3. **Les files es muten al lloc.** El 2026-01-19, la fila de l'INUNCAT tenia
   `fasedatahora = 16/01/2026 19:54` i `comunicatpdf = …_202601182204.pdf`, és a dir un
   comunicat de **dos dies més tard** 🗄️. La fila havia sobreviscut i s'havia actualitzat.

### 7.2 `:created_at` és l'inici de fase, i és millor que `fasedatahora` 🔶

L'episodi de l'INUNCAT en curs (incident `I-125912`) permet reconstruir-ho 🗄️:

| Comunicat | Hora local | Token |
| --- | --- | --- |
| `I-125912_INICI--NOACTIVAT_INUNCAT_202608021847.pdf` | 02/08 18:47 | inici de **prealerta** |
| `I-125912_ACTUALITZACIO--NOACTIVAT_INUNCAT_202608021903.pdf` | 02/08 19:03 | actualització en prealerta |
| `I-125912_ACTUALITZACIO--NOACTIVAT_INUNCAT_202608031100.pdf` | 03/08 11:00 | actualització en prealerta |
| `I-125912_ACTUALITZACIO--ACTIVAT_INUNCAT_202608031851.pdf` | 03/08 18:51 | ja **activat** |
| … 4 actualitzacions més … | | |
| `I-125912_ACTUALITZACIO--ACTIVAT_INUNCAT_202608061114.pdf` | 06/08 11:14 | l'actual ✅ |

I la fila viva d'aquest mateix incident ✅
([`camps-sistema-2026-08-06`](captures/wj9c-j6vf-camps-sistema-2026-08-06.json)) té
`:created_at = 2026-08-05T11:18:09.349Z`
(= 05/08 13:18 local) i `fasedatahora = 05/08/2026 13:18`: **coincideixen al minut**, i són
posteriors al primer comunicat `ACTIVAT` del 03/08. Interpretació 🔶: quan canvia la fase el
publicador **substitueix la fila** (nou `:id`, nou `:created_at`) en lloc d'editar-la, i
mentre la fase es manté només n'actualitza `comunicatpdf` i `descripcio`.

Conseqüència pràctica: `:created_at` és un **ISO-8601 en UTC** que dona el mateix instant que
`fasedatahora` sense haver de parsejar `DD/MM/YYYY HH:MM` ni endevinar el fus. Val la pena
demanar-lo (`$select=:*,*`) i fer-lo servir com a font primària, amb `fasedatahora` de
reserva. Confiança mitjana: una sola transició observada.

### 7.3 Cadència real, mesurada sobre 1.146 comunicats 🗄️

El contenidor de comunicats és **públic i llistable**
(`GET https://documents.dadesobertes.gencat.cat/cecat?restype=container&comp=list&prefix=docs/`),
cosa que dona una traça completa de l'activitat del CECAT. Llistat sencer desat a
[`captures/cecat-comunicats-blobs-2026-08-06.json`](captures/cecat-comunicats-blobs-2026-08-06.json)
(1.224 blobs), anàlisi a
[`captures/analisi-cadencia-comunicats-2026-08-06.txt`](captures/analisi-cadencia-comunicats-2026-08-06.txt).

| Mètrica | Valor |
| --- | --- |
| Període cobert | 2024-11-20 a 2026-08-06 (**623 dies**) |
| Comunicats amb nom canònic | **1.146** |
| Ritme mitjà | **1,84 comunicats/dia** |
| Incidents distints (`I-<num>`) | **537**, és a dir **0,86 episodis/dia** |
| Episodis amb un sol comunicat | 335 (62%) |
| Comunicats per episodi | mediana 1, màxim **34** |
| Durada publicada d'un episodi | mediana 0 h, p90 **50,5 h**, màxim 77,8 dies |
| Mes més tranquil / més actiu | 2025-02 (16) / **2026-01 (106)** |

Interval entre comunicats consecutius:

| p05 | p25 | mediana | p75 | p95 | màx |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **14,0 min** | 105 min | **357,6 min** (6 h) | 960 min | 3.055 min | 11.214 min (7,8 dies) |

Només **5,4%** dels intervals són inferiors a 15 minuts i **1,0%** inferiors a 5 minuts
(mínim absolut: 5 segons). Amb `rowsUpdatedAt` ✅ = 2026-08-06 09:20:17 UTC coincidint
exactament amb el `last-modified` del PDF vigent, el dataset es refresca al mateix instant que
es publica el comunicat.

**Interval de sondeig recomanat: 5 minuts** (per defecte), configurable. Justificació: cobreix
el p05 de 14 min amb marge, un cicle sense canvis costa un 304 amb cos buit (§1), i és el
mateix valor que fan servir `nina` i `ha-incendiscat`. Pujar a 15 min faria coalescir
actualitzacions al 5% dels casos, que és precisament durant els episodis greus.

### 7.4 Senyal de "recentment desactivat": possible, però només per absència 🗄️

**Sí que és possible**, amb una limitació estructural. El CECAT gairebé no publica comunicats
de tancament: **1 sol `DESACTIVACIO` en 623 dies**, i el comunicat de prealerta ho diu per
escrit 📄 ("es donarà per finalitzada, sense necessitat d'una comunicació de tancament").

Per tant l'única manera de detectar una desactivació és **reconciliar**: recordar les parelles
**`(plaacronim, plafase)`** del cicle anterior i, si una desapareix, emetre l'event. La clau ha
de ser la parella sencera i no `plaacronim` sol, perquè dues files simultànies del mateix pla en
fases diferents col·lapsarien i la que es perdés no emetria mai el seu event: és el trap 3, i és
la mateixa clau que fa servir l'estat del coordinator
([`04`](04-architecture.md) §5, AD-5). Cada clau que desapareix emet **sempre** el seu event de
tancament, amb la durada; **a més**, si al mateix cicle hi ha una sola alta i una sola baixa per
a l'acrònim i **les dues fases són reconegudes**, s'hi afegeix un event de canvi de fase. Aquell
event addicional no en substitueix cap: el tancament hi és igualment. El patró és el `_prune_vanished` que
`ha-incendiscat` ja fa servir per als incendis que s'esvaeixen de la vista ArcGIS
([`ha-incendiscat/docs/01`](https://github.com/pmontp19/ha-incendiscat/blob/main/docs/01-data-sources.md)
§2).

El que **no** es pot fer és distingir "s'ha desactivat" de "el publicador ha esborrat la fila
per error" ni saber *quan* s'ha desactivat més enllà de "entre el cicle anterior i aquest".
Tampoc es pot fer història retroactiva: si Home Assistant està aturat quan un pla s'activa i
es desactiva, l'episodi no ha existit.

---

## 8. `fasedatahora`: format i fus, demostrat amb 1.146 punts

Format `DD/MM/YYYY HH:MM` ✅, sense segons, sense offset, sense indicador de fus. Cinc valors
observats: `01/12/2024 19:18`, `16/01/2026 19:12`, `16/01/2026 19:54`, `03/07/2026 10:20`,
`05/08/2026 13:18`.

**El fus és Europe/Madrid** (CET/CEST amb canvi d'horari), no UTC. Demostració quantitativa
🗄️: els noms canònics dels comunicats contenen un segell `YYYYMMDDHHMM`, i el blob té un
`Last-Modified` en UTC. Interpretant el segell com a Europe/Madrid i restant:

| n | mín | p05 | mediana | p95 | màx | negatius |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1.146 | 0 min | 1 min | **2,4 min** | 8 min | 993 min | **0** |

**99,5% dels segells cauen dins dels 30 minuts anteriors a la pujada del fitxer, i cap és
posterior.** Si el segell fos UTC, tots els retards a l'estiu serien de 120 minuts negatius.
Amb una mostra de 1.146 això no és una coincidència.

Ho corrobora el propi comunicat 📄, que ocupa dues pàgines i està capturat en dos fitxers, un
per pàgina. El peu de pàgina 1
([`comunicat-…-2026-08-02.txt`](captures/comunicat-prealerta-inuncat-2026-08-02.txt)) diu "Reus,
diumenge 2 d'agost 2026 **18:45 h**" en un fitxer segellat `202608021847`. La pàgina 2
([`comunicat-…-2026-08-02-pagina2.txt`](captures/comunicat-prealerta-inuncat-2026-08-02-pagina2.txt))
és la que porta la nota que **només** els mapes van en UTC, literal: "S'adjunten a continuació
els mapes de risc per aquest episodi (Hores expressades en UTC (cal sumar 2 hores en horari
d'estiu i 1 en horari d'hivern: UTC+2h / UTC+1h))".

I ho tanca la fila viva ✅
([`camps-sistema-2026-08-06`](captures/wj9c-j6vf-camps-sistema-2026-08-06.json)):
`:created_at = 2026-08-05T11:18:09Z` amb `fasedatahora = 05/08/2026 13:18`, que és exactament
UTC+2.

Regla de parseig: `datetime.strptime(v, "%d/%m/%Y %H:%M")` amb
`ZoneInfo("Europe/Madrid")`, dins d'un `try` que retorna `None`. Preferir `:created_at` quan
hi sigui (§7.2).

---

## 9. `descripcio`: sempre present a la mostra, sempre bruta

Declarada "(opcional)" 📄. A les 5 files observades és **no buida 5/5**, però cap valor és net:

| Captura | Valor literal |
| --- | --- |
| 2024-12-02 | `"Accident autocar. N-320 Porte-Puymorens   (Porta, Dep. Pirineus Orientals)\nRuta L'Hospitalet de Llobregat <-> Andorra  - "` |
| 2026-01-19 (INUNCAT) | `"Alerta INUNCAT"` |
| 2026-01-19 (NEUCAT) | `"Alerta NEUCAT 17 i 18 de gener "` |
| [2026-07-03](captures/wj9c-j6vf-infocat-2026-07-03.json) | `"Incendi vegetació - "` |
| 2026-08-06 | `"Avís intensitat pluja fins al 04/08  - "` |

Patologies observades ✅ 🗄️: sufix `" - "` en 3/5 (residu d'una plantilla que concatena un
segon camp buit), espais dobles i triples, espai final, **salt de línia literal `\n`**, i
`<->` (que en un context HTML seria interpretable). El contingut semàntic és útil (descriu el
fenomen o l'incident) però és **text lliure escrit per un operador**.

Regla: `(row.get("descripcio") or "").strip()`, tractar la cadena buida com a absent, no
normalitzar mai el contingut més enllà de retallar espais, i **mai `allow_html` ni
interpolació HTML directa** (regla heretada de `CLAUDE.md` i dels dos germans).

---

## 10. Datasets relacionats: el mapa complet

Cerca ✅ `GET https://analisi.transparenciacatalunya.cat/api/catalog/v1?q=protecció civil&limit=100`,
27 resultats, tots inspeccionats.

| Id | Nom | Última actualització | Ús per a `ha-cecat` |
| --- | --- | --- | --- |
| `wj9c-j6vf` | Plans en fase de prealerta, alerta o emergència | **2026-08-06** ✅ | **Font única de la v1** |
| `xqqe-tgav` | Registre general de plans de protecció civil | 2026-07-14 | Vocabulari de plans (§3.2). No en runtime |
| `eqag-gzjs` | Obligacions i vigències dels plans municipals | 2026-07-08 | Fora de la v1 (§5) |
| `92sv-nckr` | Evolució d'activacions dels plans | **2023-08-14** (2017-2022) | Context històric. Obsolet |
| `wfei-fjk5` | Nombre d'avisos i activacions dels plans | **2023-08-14** (2017-2022) | Vocabulari i volums (§3.2). Obsolet |
| `49us-rifk` | Evolució anual de simulacres | | Fora d'abast |
| `pyz5-d9i2` | Associacions de voluntaris de protecció civil | | Fora d'abast |
| `aqri-5sbe` | Establiments afectats per accidents greus | | Fora d'abast |
| `9gu7-iwci` | Refugis climàtics dels municipis | | Fora d'abast |
| `ta3b-27fw`, `y64e-ui2e`, `p85t-x8r5`, `ht6d-rcs4`, `vvr8-anww`, `cywt-i78c` | Informes urbanístics, PAU, personal | | Fora d'abast |
| 12 recursos `type: href` | "Mapa de Protecció Civil: Risc X" | | Visors, no APIs |

Cap dels dos datasets estadístics s'ha actualitzat des del 2023-08-14: **no hi ha una font
oberta d'històric d'activacions viva**. El contenidor de comunicats (§7.3) és, de facto, el
millor històric disponible, i no està documentat com a API.

---

## 11. Llicència i atribució

| | |
| --- | --- |
| `licenseId` a la metadata | `SEE_TERMS_OF_USE` ✅ |
| `attribution` | "Direcció General de Protecció Civil" ✅ |
| `attributionLink` | `https://administraciodigital.gencat.cat/ca/dades/dades-obertes/informacio-practica/llicencies/` (redirigeix 301 a `web.gencat.cat/ca/generalitat/dades-indicadors/dades-obertes/llicencies`) ✅ |
| Llicència | **Llicència oberta d'ús d'informació de Catalunya** 📄 |

Condicions rellevants 📄: permet reutilització, distribució i obres derivades sense límit
temporal ni territorial; exigeix **citar la font i la data d'actualització**; prohibeix
alterar o desnaturalitzar la informació i **fer servir logotips, marques i símbols** de la
Generalitat sense autorització; prohibeix la subllicència.

Conseqüències concretes per a la integració:

1. Atribució obligatòria al README i a `DeviceInfo`: "Generalitat de Catalunya. Departament
   d'Interior i Seguretat Pública. Direcció General de Protecció Civil".
2. Exposar la data d'actualització (`Last-Modified` / `rowsUpdatedAt`) com a atribut, no només
   internament: forma part de la condició de la llicència.
3. **No fer servir `plaicona`** com a icona de marca de les entitats. Són els símbols oficials
   dels plans i la llicència en restringeix l'ús; el propi camp remet a un document titulat
   "Icones **només per a ús i identificació dels plans** de Protecció Civil" 📄. Icones pròpies
   de Home Assistant (`mdi:`), i `plaicona` com a atribut informatiu si de cas.
4. El repositori ha de mantenir el descàrrec de "no oficial, no afiliat" que ja té el README.

---

## 12. Traps de tolerància obligatoris

Cada trap ve d'una cosa que **he observat**, amb la captura que ho demostra. Cap és imaginat.

| # | Trap | Evidència | Regla |
| :---: | --- | --- | --- |
| 1 | **`plaactivat: "NO"` existeix** i correspon a `PREALERTA`. `[]` i `"NO"` són coses diferents. A més la descripció oficial escriu el domini com a "(Si/No)" i les dades donen `SI`/`NO` | 🗄️ [`prealerta-2024-12-02`](captures/wj9c-j6vf-prealerta-2024-12-02.json); 589/1.146 comunicats amb token `NOACTIVAT`; 📄 descripció del camp | **Mai filtrar per `plaactivat='SI'`** i **mai comparar-lo estrictament**. Normalitzar-lo com `plafase` (`strip` + `casefold` + sense diacrítics); `activated = False` **només** amb el literal `no`; absent o irreconeixible, derivar-lo de `plafase`, que és l'autoritatiu (§3.3) |
| 2 | La resposta pot ser **`[]`** | 🗄️ [`buit-2026-06-16`](captures/wj9c-j6vf-buit-2026-06-16.json) + 📄 descripció oficial | Llista buida és estat vàlid, no error. Zero plans, entitats a `0`/`off`, mai `unavailable` |
| 3 | Hi pot haver **més d'una fila**, i **dues poden compartir `plaacronim`**: als 267 comunicats del PROCICAT el token és sempre `PROCICAT` pelat, tot i que el registre hi té quatre plans d'actuació distints | 🗄️ [`dos-plans-2026-01-19`](captures/wj9c-j6vf-dos-plans-2026-01-19.json): INUNCAT i NEUCAT alhora; 🔶 §3.2 nota 2 per als PA del PROCICAT | Modelar una col·lecció indexada per **`(plaacronim, plafase)`**, no per `plaacronim` sol i no un objecte únic. Indexar per l'acrònim sol perdria silenciosament una de dues files simultànies del mateix pla. En reconciliar, cada clau que apareix i cada clau que desapareix emeten **sempre** el seu event; **a més**, una baixa i una alta del mateix acrònim afegeixen un event de canvi de fase només si **totes dues fases són reconegudes** ([`04`](04-architecture.md) §5) |
| 4 | `planom` **no** és el nom complet: és igual a `plaacronim` a 5/5 files observades, contra la seva pròpia descripció | ✅ 🗄️ les 5 files | No fer-lo servir per al nom de l'entitat. Mapatge propi acrònim → nom llarg, amb fallback a l'acrònim |
| 5 | `plaacronim` pot ser un valor **fora de qualsevol llista coneguda** (`PENTA` no és al registre de la Generalitat; `NOPLA` no és un pla) | 🗄️ 3 comunicats `PENTA`, 2 `NOPLA` | Acrònim desconegut → `warning` una sola vegada + entitat genèrica. **Mai `KeyError`, mai descartar la fila** |
| 6 | `plaicona` i `comunicatpdf` són **objectes** `{"url": …}`, poden faltar sencers, i `plaicona` pot apuntar a un 404 | ✅ `ico_VENTCAT.png` → 404 amb 135 comunicats de VENTCAT; `cachedContents` no reporta nuls per als camps `url` | `(row.get("comunicatpdf") or {}).get("url")`. Mai construir la URL de la icona des de l'acrònim |
| 7 | La URL de `comunicatpdf` pot contenir **accents, apòstrofs i comes sense codificar** | 🗄️ `…/InstruccionsalapoblacióincendilaBisbald'Empordà4tconfinament.pdf` a [`infocat-2026-07-03`](captures/wj9c-j6vf-infocat-2026-07-03.json) | Tractar com a cadena opaca. No validar-la, no reconstruir-la, no passar-la per cap client HTTP |
| 8 | El nom del PDF **no és un contracte**: 36 PDF de nom lliure conviuen amb els 1.146 canònics, i el contenidor té fins i tot un `test.txt` | 🗄️ [`cecat-comunicats-blobs`](captures/cecat-comunicats-blobs-2026-08-06.json) | No parsejar mai el nom del fitxer per obtenir pla, acció o data |
| 9 | `fasedatahora` és `DD/MM/YYYY HH:MM` en **hora local d'Europe/Madrid**, no ISO, no UTC | ✅ `:created_at` UTC+2 exacte; 🗄️ 1.146 segells amb 0 retards negatius | `strptime` explícit amb `ZoneInfo("Europe/Madrid")` dins d'un `try`; `None` si falla. Preferir `:created_at` |
| 10 | `descripcio` porta espais dobles, sufix `" - "` i **salts de línia literals** | ✅ 🗄️ 5/5 files brutes | `.strip()`, buit tractat com a absent, mai `allow_html` ni interpolació HTML |
| 11 | `comunicatpdf` **canvia dins de la mateixa fase**, sense que canviï `fasedatahora` | 🗄️ 2026-01-19: fase del 16/01 19:54 amb PDF del 18/01 22:04; ✅ incident `I-125912` amb 5 PDF en la mateixa fase | El canvi de PDF **no** és un canvi de fase. Els events s'han de disparar per `(plaacronim, plafase)`, no pel hash de la fila |
| 12 | L'**`ETag` està trencat** (sufix `--gzip` duplicat) i no genera 304; `If-Modified-Since` sí | ✅ [`http-headers`](captures/http-headers-2026-08-06.txt) | Cachejar amb `Last-Modified` + `If-Modified-Since`. Un 304 ha de conservar l'estat anterior, no buidar-lo |
| 13 | **Cap camp és de tipus data** al servidor (`X-SODA2-Types` són tots `text`/`url`) | ✅ capçalera | No intentar `$where`/`$order` per data. Descarregar-ho tot cada cicle (mai passa de desenes de bytes) |
| 14 | `EMERGÈNCIA` mai s'ha observat en un payload real, i **tampoc la grafia del seu `plaactivat`** | ❓ 15 emergències en 6 anys segons `wfei-fjk5`; 📄 domini documentat "(Si/No)" contra `SI`/`NO` observat | El camí de codi de la fase màxima ha d'existir i estar cobert per un fixture **sintètic marcat com a tal**, i el codi no ha de dependre de l'accent ni de la caixa: `casefold()` i sense diacrítics **tant a `plafase` com a `plaactivat`** (§3.3). Un accent o una `Si` no poden fer perdre la fase més greu |
| 15 | La desactivació **no es publica**: 1 sol comunicat `DESACTIVACIO` en 623 dies | 🗄️ anàlisi de tokens | La desaparició de la fila és l'únic senyal de tancament. Cal reconciliació amb l'estat anterior |

---

## 13. Índex de captures

| Fitxer | Origen | Instant |
| --- | --- | --- |
| [`wj9c-j6vf-alerta-2026-08-06.json`](captures/wj9c-j6vf-alerta-2026-08-06.json) | ✅ endpoint en viu, **projecció pelada** (només els 8 camps de negoci) | 2026-08-06 11:49 UTC |
| [`wj9c-j6vf-camps-sistema-2026-08-06.json`](captures/wj9c-j6vf-camps-sistema-2026-08-06.json) | ✅ endpoint en viu amb `$select=:*,*`. **L'única captura amb `:created_at`**: sosté l'inici de fase (§7.2), la corroboració UTC contra local (§8) i AD-3 | 2026-08-06 12:31 UTC |
| [`wj9c-j6vf-prealerta-2024-12-02.json`](captures/wj9c-j6vf-prealerta-2024-12-02.json) | 🗄️ Wayback, projecció `SELECT` desaliassada | 2024-12-02 09:18:52 UTC |
| [`wj9c-j6vf-buit-2026-06-16.json`](captures/wj9c-j6vf-buit-2026-06-16.json) | 🗄️ Wayback, endpoint sense filtres | 2026-06-16 18:15:46 UTC |
| [`wj9c-j6vf-dos-plans-2026-01-19.json`](captures/wj9c-j6vf-dos-plans-2026-01-19.json) | 🗄️ Wayback, **unió de dues consultes filtrades** (INUNCAT + NEUCAT) del mateix segon | 2026-01-19 11:07:48 UTC |
| [`wj9c-j6vf-infocat-2026-07-03.json`](captures/wj9c-j6vf-infocat-2026-07-03.json) | 🗄️ Wayback, `$where=plaactivat='SI' AND upper(plaacronim)='INFOCAT'`. La fila que demostra que la URL amb accents i apòstrof era el valor real del camp (§6.2, trap 7) | 2026-07-03 14:37:31 UTC |
| [`wj9c-j6vf-metadata-2026-08-06.json`](captures/wj9c-j6vf-metadata-2026-08-06.json) | ✅ `/api/views/wj9c-j6vf.json`, **subconjunt documentat** de claus (vegeu [`captures/README.md`](captures/README.md)) | 2026-08-06 |
| [`http-headers-2026-08-06.txt`](captures/http-headers-2026-08-06.txt) | ✅ capçaleres + proves de GET condicional | 2026-08-06 11:49 UTC |
| [`comunicat-prealerta-inuncat-2026-08-02.txt`](captures/comunicat-prealerta-inuncat-2026-08-02.txt) | ✅ `pdftotext -layout` de `I-125912_INICI--NOACTIVAT_INUNCAT_202608021847.pdf`, **pàgina 1 de 2** | doc. 2026-08-02 18:47 local |
| [`comunicat-prealerta-inuncat-2026-08-02-pagina2.txt`](captures/comunicat-prealerta-inuncat-2026-08-02-pagina2.txt) | ✅ **pàgina 2 de 2** del mateix PDF. És la que porta la nota "Hores expressades en UTC" que sosté §8 | doc. 2026-08-02 18:47 local |
| [`cecat-comunicats-blobs-2026-08-06.json`](captures/cecat-comunicats-blobs-2026-08-06.json) | 🗄️ llistat del contenidor Azure, 1.224 blobs | 2026-08-06 |
| [`analisi-cadencia-comunicats-2026-08-06.txt`](captures/analisi-cadencia-comunicats-2026-08-06.txt) | ✅ sortida de l'anàlisi de §7.3 i §8 | 2026-08-06 |
| [`registre-plans-generalitat-2026-08-06.json`](captures/registre-plans-generalitat-2026-08-06.json) | ✅ `xqqe-tgav` amb `ambit='Generalitat'`, 17 files | 2026-08-06 |
| [`wfei-fjk5-activacions-2017-2022.json`](captures/wfei-fjk5-activacions-2017-2022.json) | ✅ `wfei-fjk5` sencer, 102 files | 2026-08-06 |
| [`cdx-wj9c-j6vf-2026-08-06.txt`](captures/cdx-wj9c-j6vf-2026-08-06.txt) | ✅ índex CDX de la Wayback Machine per a l'endpoint, 26 entrades. Sosté el recompte i el desglossament per data d'aquesta mateixa secció | 2026-08-06 |

⚠️ La captura de dos plans és una **reconstrucció**: la Wayback Machine va arxivar dues
consultes filtrades del mateix segon, no una resposta sense filtres amb dues files. La forma
és fidel (les files són literals), l'ordre no està observat. Marcat com a tal al fitxer i als
tests que en derivin.

Nota metodològica: **cap dels snapshots arxivats és meu.** L'índex CDX de la Wayback Machine per
a aquest endpoint té 26 entrades, desades literalment a
[`captures/cdx-wj9c-j6vf-2026-08-06.txt`](captures/cdx-wj9c-j6vf-2026-08-06.txt) ✅ (26 línies,
una per entrada, amb `timestamp`, URL, codi i mida). El desglossament per data suma 26:

| Data | Entrades | Qui sembla que és |
| --- | ---: | --- |
| 2024-12-02 | 2 | La graella web de Socrata: una projecció `SELECT … as __select_alias__` i un `count('*')`, que és exactament el que emet el portal quan algú obre la pàgina del dataset |
| 2026-01-19 | 21 | Un consumidor **automatitzat**: `$where=plaactivat='SI' AND upper(plaacronim)='<ACRONIM>'`, una consulta per acrònim, totes dins de 7 segons |
| 2026-06-16 | 1 | L'endpoint pelat, que va retornar `[]` |
| 2026-07-03 | 2 | El mateix consumidor automatitzat, dos acrònims |

Les 23 consultes filtrades són **evidència de tercers** sobre quins acrònims s'esperen a la
natura (§3.2), i el seu filtre `plaactivat='SI'` és el trap núm. 1 d'aquest document.

---

## 14. Veredicte

> ### ✅ Sí, hi ha prou font per construir una integració útil, i és petita.
>
> Les quatre preguntes que bloquejaven el disseny estan **respostes amb evidència**, no amb
> conjectura:
>
> 1. **Vocabulari**: les fases són exactament `PREALERTA` / `ALERTA` / `EMERGÈNCIA`, definides
>    per la font oficial, sense normalitat ni desactivació. Els plans són 18 identitats
>    conegudes a partir del registre oficial i de 1.146 comunicats reals, però **el conjunt no
>    és tancat** i el disseny no en pot dependre.
> 2. **Estat buit**: `[]`, observat directament en un instant arxivat i documentat per la font.
>    Amb la correcció crítica que **`plaactivat: "NO"` també existeix** (és la prealerta) i que
>    filtrar per `'SI'` amaga la meitat del senyal.
> 3. **Territori**: **no existeix** cap font estructurada de territori per activació. Les
>    comarques només són prosa dins del PDF. Això **confirma `single_config_entry: true`** en
>    lloc de deixar-ho obert.
> 4. **Història i cadència**: el dataset és **només estat actual**, es muta al lloc, i canvia
>    **1,84 vegades al dia** amb un p05 de 14 minuts entre canvis. Sondeig de 5 minuts amb
>    `If-Modified-Since` (verificat: retorna 304). El senyal de "recentment desactivat" **és
>    possible** però només per reconciliació de l'absència de la fila.
>
> El que fa que això valgui la pena és que és un senyal que **no existeix a cap altre lloc de
> Home Assistant**: un avís del Meteocat diu què preveu el meteoròleg, això diu si Protecció
> Civil ha activat el pla. És oficial, obert, sense clau, sense quota, amb un payload de menys
> de 500 bytes i **zero dependències de PyPI**. Quatre entitats i una família d'events, no
> quinze.
>
> ### Què queda sense resoldre
>
> | # | Obert | Impacte | Mitigació a la v1 |
> | :---: | --- | --- | --- |
> | 1 | **La grafia de `plaacronim` per als PA del PROCICAT** (`PROCICAT`? `FERROCAT`? `PROCICAT-CALOR`?). Quatre grafies a quatre fonts, cap observada al feed | Baix. Afecta el nom mostrat, no la lògica | Acrònim desconegut → entitat genèrica + `warning` una vegada (trap 5). Es resol amb la primera activació observada |
> | 2 | **`EMERGÈNCIA` mai observada** en un payload real (15 en 6 anys), i amb ella la grafia real del seu `plaactivat` | Mitjà. És la fase que més importa | Fixture sintètic **marcat com a tal**; comparació sense diacrítics i amb `casefold()` a `plafase` **i** a `plaactivat`, i `plaactivat` irreconeixible derivat de la fase (traps 1 i 14, §3.3) |
> | 3 | **Si un canvi de fase substitueix la fila o l'edita.** Una sola transició observada | Mitjà. Decideix si `:created_at` és fiable com a inici de fase | Fer servir `:created_at` amb `fasedatahora` de reserva, i disparar events per `(plaacronim, plafase)` mai per `:id` (trap 11) |
> | 4 | **`plaicona` de VENTCAT i PLASEQTA** (les seves icones donen 404) | Nul. Ja hem decidit no fer servir `plaicona` (§11, punt 3) | Cap |
> | 5 | **El contenidor Azure de comunicats no és una API documentada.** L'he fet servir per fer arqueologia, no en runtime | Nul mentre no en depenguem | **No consumir-lo des de la integració.** Si algun dia es vol històric, cal negociar-ho amb la font |
> | 6 | **Dos plans d'actuació distints sota el mateix `plaacronim` poden generar un event de canvi de fase que no s'ha produït.** Si el PROCICAT reporta l'acrònim pelat (obert 1), un cicle on un PA s'acaba i un altre comença dona una alta i una baixa, i **s'hi afegeix** un `cecat_plan_phase_changed` amb `escalation: true` que afirma una escalada que no ha passat | Baix i **estret**: els events de començament i de tancament d'aquell cicle són individualment correctes, i el blueprint, que només escolta `phase_started`, no se'n veu afectat. Només ho pateix qui filtri per `escalation: true` | **Limitació acceptada i documentada**, no mitigada: corroborar amb `plaicona` o `descripcio` seria construir una porta de correcció sobre dos camps poc fiables (§6.3, §9). Detall i alternatives rebutjades a [`04`](04-architecture.md) §5. Es tanca sola si l'obert 1 resol que els PA porten acrònims distints |
>
> **Què reobriria l'obert 6, i com de lluny és de tancar-se.** La premissa que el sosté, §3.2
> nota 2 (que tots els plans d'actuació del PROCICAT reporten `PROCICAT` pelat a `plaacronim`), és
> una **inferència 🔶 de confiança mitjana-alta**, no una observació: cap captura mostra dues files
> de PROCICAT alhora. En sentit contrari, el consumidor de tercers que la mateixa §3.2 nota 2
> documenta (i que [`02`](02-existing-integrations.md) §6.2 detalla) sondeja explícitament
> `PROCICAT-CALOR` i `PROCICAT-FERROCARRIL` entre els 21 acrònims que consulta, cosa que suggereix
> que algú esperava que la font distingís els sub-plans. **Si resulta que `plaacronim` els
> distingeix, l'obert 6 desapareix sol** i la decisió de no afirmar mai un origen a
> `cecat_plan_phase_started` ([`03`](03-feature-spec.md) §4.1) es pot revisar. La primera
> observació real d'un PROCICAT amb dues files simultànies, o d'un acrònim amb sufix, ho resol.
>
> Cap dels sis bloqueja començar. Els dos que importen (2 i 3) es tanquen sols la primera
> vegada que hi hagi una emergència o una transició de fase reals, el 6 depèn del mateix que
> l'1, i el disseny de [`03-feature-spec.md`](03-feature-spec.md) està construït per no petar
> mentrestant.
