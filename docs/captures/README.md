# Captures

Evidència en cru de la recerca de [`../01-data-sources.md`](../01-data-sources.md). Tot el que hi
ha aquí és **observat**, mai generat. Els fixtures sintètics que faran falta per als tests viuen
a `tests/fixtures/` amb el sufix `_SYNTHETIC`, mai aquí.

| Fitxer | Origen | Instant | Sosté |
| --- | --- | --- | --- |
| `wj9c-j6vf-alerta-2026-08-06.json` | Endpoint en viu | 2026-08-06 11:49 UTC | Cas base: `ALERTA` amb `plaactivat: SI` |
| `wj9c-j6vf-prealerta-2024-12-02.json` | Wayback Machine, projecció `SELECT` desaliassada | 2024-12-02 09:18:52 UTC | **`plaactivat: "NO"` amb `PREALERTA`**, i `descripcio` amb un `\n` literal |
| `wj9c-j6vf-buit-2026-06-16.json` | Wayback Machine, endpoint sense filtres | 2026-06-16 18:15:46 UTC | **L'estat buit és `[]`** |
| `wj9c-j6vf-dos-plans-2026-01-19.json` | Wayback Machine, **unió de dues consultes filtrades** del mateix segon | 2026-01-19 11:07:48 UTC | Hi pot haver més d'una fila (INUNCAT + NEUCAT). ⚠️ **Reconstrucció**: les files són literals, l'ordre no està observat |
| `wj9c-j6vf-metadata-2026-08-06.json` | `/api/views/wj9c-j6vf.json` | 2026-08-06 | Descripció oficial de les tres fases, l'estat buit, llicència, atribució, `rowsUpdatedAt` |
| `http-headers-2026-08-06.txt` | Capçaleres + proves de GET condicional | 2026-08-06 11:49 UTC | `If-Modified-Since` dona 304; l'`ETag` està trencat i dona 200; tots els camps són `text`/`url` |
| `comunicat-prealerta-inuncat-2026-08-02.txt` | `pdftotext -layout` de `I-125912_INICI--NOACTIVAT_INUNCAT_202608021847.pdf`, pàgina 1 | doc. 2026-08-02 18:47 local | "La prealerta no comporta l'activació del Pla"; les comarques són prosa; no hi ha comunicat de tancament; les hores són locals i només els mapes van en UTC |
| `cecat-comunicats-blobs-2026-08-06.json` | Llistat del contenidor Azure públic, 1.224 blobs | 2026-08-06 | Cadència real, tokens `ACTIVAT`/`NOACTIVAT`/`DESACTIVACIO`, les 18 icones, els 36 noms de fitxer no canònics |
| `analisi-cadencia-comunicats-2026-08-06.txt` | Sortida de l'anàlisi del llistat anterior | 2026-08-06 | Les xifres de §7.3 i §8: 1,84 comunicats/dia, p05 de 14 min, i els 1.146 punts que demostren el fus Europe/Madrid |
| `registre-plans-generalitat-2026-08-06.json` | `xqqe-tgav` amb `ambit='Generalitat'`, 17 files | 2026-08-06 | El vocabulari autoritatiu de plans de nivell Generalitat |
| `wfei-fjk5-activacions-2017-2022.json` | `wfei-fjk5` sencer, 102 files | 2026-08-06 | Acrònims amb la seva tipologia i el volum d'activacions 2017-2022 |

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
