# Captures

Evidència en cru de la recerca de [`../01-data-sources.md`](../01-data-sources.md). Tot el que hi
ha aquí és **observat**, mai generat. Els fixtures sintètics que faran falta per als tests viuen
a `tests/fixtures/` amb el sufix `_SYNTHETIC`, mai aquí.

| Fitxer | Origen | Instant | Sosté |
| --- | --- | --- | --- |
| `wj9c-j6vf-alerta-2026-08-06.json` | Endpoint en viu, **projecció pelada** (només els 8 camps de negoci, sense camps de sistema) | 2026-08-06 11:49 UTC | Cas base: `ALERTA` amb `plaactivat: SI`. **No conté `:created_at`**: per a això hi ha la captura de camps de sistema |
| `wj9c-j6vf-camps-sistema-2026-08-06.json` | Endpoint en viu amb `$select=:*,*` | 2026-08-06 12:31 UTC | **L'única captura amb `:id`, `:created_at`, `:updated_at` i `:version`.** Sosté `:created_at` com a font de l'inici de fase (§7.2), la corroboració UTC contra hora local (§8) i AD-3 |
| `wj9c-j6vf-prealerta-2024-12-02.json` | Wayback Machine, projecció `SELECT` desaliassada | 2024-12-02 09:18:52 UTC | **`plaactivat: "NO"` amb `PREALERTA`**, i `descripcio` amb un `\n` literal |
| `wj9c-j6vf-buit-2026-06-16.json` | Wayback Machine, endpoint sense filtres | 2026-06-16 18:15:46 UTC | **L'estat buit és `[]`** |
| `wj9c-j6vf-dos-plans-2026-01-19.json` | Wayback Machine, **unió de dues consultes filtrades** del mateix segon | 2026-01-19 11:07:48 UTC | Hi pot haver més d'una fila (INUNCAT + NEUCAT). ⚠️ **Reconstrucció**: les files són literals, l'ordre no està observat |
| `wj9c-j6vf-infocat-2026-07-03.json` | Wayback Machine, `$where=plaactivat='SI' AND upper(plaacronim)='INFOCAT'` | 2026-07-03 14:37:31 UTC | La fila que demostra que `comunicatpdf.url` **era de veritat** `…/InstruccionsalapoblacióincendilaBisbald'Empordà4tconfinament.pdf`, amb accents i apòstrof sense codificar (§6.2, trap 7). També `planom == plaacronim` i `descripcio` amb el sufix `" - "` |
| `wj9c-j6vf-metadata-2026-08-06.json` | `/api/views/wj9c-j6vf.json`, **subconjunt documentat de claus** (vegeu avall) | 2026-08-06 | Descripció oficial de les tres fases, l'estat buit, llicència, atribució, `rowsUpdatedAt`, `newBackend`, `viewCount` / `downloadCount` |
| `http-headers-2026-08-06.txt` | Capçaleres + proves de GET condicional | 2026-08-06 11:49 UTC | `If-Modified-Since` dona 304; l'`ETag` està trencat i dona 200; tots els camps són `text`/`url` |
| `comunicat-prealerta-inuncat-2026-08-02.txt` | `pdftotext -layout` de `I-125912_INICI--NOACTIVAT_INUNCAT_202608021847.pdf`, **pàgina 1 de 2** | doc. 2026-08-02 18:47 local | "La prealerta no comporta l'activació del Pla"; les comarques són prosa; no hi ha comunicat de tancament; el peu de pàgina dona l'hora local |
| `comunicat-prealerta-inuncat-2026-08-02-pagina2.txt` | **Pàgina 2 de 2** del mateix PDF | doc. 2026-08-02 18:47 local | **La nota que només els mapes van en UTC**: "Hores expressades en UTC (cal sumar 2 hores en horari d'estiu i 1 en horari d'hivern: UTC+2h / UTC+1h)". És a la pàgina 2 i no a la 1, per això el document està capturat en dos fitxers |
| `cecat-comunicats-blobs-2026-08-06.json` | Llistat del contenidor Azure públic, 1.224 blobs | 2026-08-06 | Cadència real, tokens `ACTIVAT`/`NOACTIVAT`/`DESACTIVACIO`, les 18 icones, els 36 noms de fitxer no canònics |
| `analisi-cadencia-comunicats-2026-08-06.txt` | Sortida de l'anàlisi del llistat anterior | 2026-08-06 | Les xifres de §7.3 i §8: 1,84 comunicats/dia, p05 de 14 min, i els 1.146 punts que demostren el fus Europe/Madrid |
| `registre-plans-generalitat-2026-08-06.json` | `xqqe-tgav` amb `ambit='Generalitat'`, 17 files | 2026-08-06 | El vocabulari autoritatiu de plans de nivell Generalitat |
| `wfei-fjk5-activacions-2017-2022.json` | `wfei-fjk5` sencer, 102 files | 2026-08-06 | Acrònims amb la seva tipologia i el volum d'activacions 2017-2022 |
| `cdx-wj9c-j6vf-2026-08-06.txt` | Índex CDX de la Wayback Machine per a l'endpoint, resposta crua de 26 línies | 2026-08-06 | Que l'índex té **26 entrades** i el seu desglossament per data (2 + 21 + 1 + 2), que és d'on surten les observacions arxivades de §4, §7.1 i §13 de [`../01-data-sources.md`](../01-data-sources.md) |

## Sobre el subconjunt de `wj9c-j6vf-metadata-2026-08-06.json`

La resposta real de `/api/views/wj9c-j6vf.json` té 43 claus de primer nivell, la majoria
irrellevants (`approvals`, `grants`, `owner`, `flags`, comptadors de comentaris i valoracions).
El fitxer desat n'és un **subconjunt retallat a mà**, no la resposta sencera. Conserva
exactament aquestes 19 claus, i cap altra, amb els valors literals de la resposta:

```
id  name  description  attribution  attributionLink  licenseId  license  category  tags
provenance  newBackend  createdAt  publicationDate  rowsUpdatedAt  viewLastModified
viewCount  downloadCount  metadata  columns
```

Els valors són literals, sense retocar: `description` són els 1.995 caràcters sencers de la
descripció oficial, i `columns[].cachedContents` conserva els recomptes tal com van arribar.
Tota afirmació de [`../01-data-sources.md`](../01-data-sources.md) marcada "✅ metadata" ha de
ser comprovable en aquestes claus; si algun dia se'n cita una que no hi és, o s'afegeix aquí o
es baixa la marca.

## Com reproduir-les

```bash
# Estat actual, amb camps de sistema
curl 'https://analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json?$select=:*,*'

# Metadata (descripció oficial, llicència, rowsUpdatedAt)
curl 'https://analisi.transparenciacatalunya.cat/api/views/wj9c-j6vf.json'

# Registre oficial de plans de nivell Generalitat
curl -G 'https://analisi.transparenciacatalunya.cat/resource/xqqe-tgav.json' \
  --data-urlencode "\$where=ambit='Generalitat'" --data-urlencode '$limit=200'

# Instantànies històriques de l'endpoint
curl 'https://web.archive.org/cdx/search/cdx?url=analisi.transparenciacatalunya.cat/resource/wj9c-j6vf.json*&fl=timestamp,original,statuscode,length'
```

El llistat del contenidor de comunicats està documentat a
[`../01-data-sources.md` §7.3](../01-data-sources.md). **No es consumeix des de la integració**:
no és una API documentada, i dependre'n en runtime seria construir sobre un detall
d'implementació (decisió AD-14 de [`../04-architecture.md`](../04-architecture.md)).

Totes les peticions d'aquesta recerca van ser de només lectura i espaiades. És un servei públic
d'una administració pública.
