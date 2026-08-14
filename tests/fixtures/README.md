# Fixtures

Còpia de treball dels tests. La regla d'[`../../AGENTS.md`](../../AGENTS.md) heretada
dels repositoris germans és estricta: **aquí només hi ha respostes reals capturades,
mai inventades**, llevat dels fitxers `_SYNTHETIC` que duen el sufix **i** una clau
`_comment` a cada fila declarant-ho. La distinció és la que fa creïbles els documents
del projecte.

L'endpoint Socrata sempre respon amb un **array JSON de files**, fins i tot buit
([`../../docs/01-data-sources.md`](../../docs/01-data-sources.md) §4: l'estat buit és
`[]`). Tots els fixtures comparteixen aquesta forma: el test paramètric
`tests/test_fixtures.py::test_fixture_is_a_list` el comprova per als onze alhora.

## Fixtures reals (còpies literals)

Còpies byte a byte de [`../../docs/captures/`](../../docs/captures/). Mai editades:
si cal tocar-les, el fitxer d'origen és la evidència i s'hi ha de tornar.

| Fixture | Captura d'origen | Què sosté |
| --- | --- | --- |
| `alerta_2026_08_06.json` | `docs/captures/wj9c-j6vf-alerta-2026-08-06.json` | Cas base `ALERTA` amb `plaactivat: SI`, **projecció pelada** (8 camps de negoci, sense camps de sistema). Força el camí `started_at_source = "fasedatahora"` |
| `camps_sistema_2026_08_06.json` | `docs/captures/wj9c-j6vf-camps-sistema-2026-08-06.json` | **L'únic fixture amb `:created_at`**: `started_at = 2026-08-05T11:18:09+00:00`, `started_at_source = "created_at"`. És la **mateixa fila** que `alerta_2026_08_06` amb `$select=:*,*`, capturada 42 minuts després |
| `prealerta_2024_12_02.json` | `docs/captures/wj9c-j6vf-prealerta-2024-12-02.json` | `plaactivat: "NO"` amb `PREALERTA` (51,4% del senyal), `descripcio` amb `\n` literal |
| `buit_2026_06_16.json` | `docs/captures/wj9c-j6vf-buit-2026-06-16.json` | L'estat buit és exactament `[]` |
| `dos_plans_2026_01_19.json` | `docs/captures/wj9c-j6vf-dos-plans-2026-01-19.json` | Dues files amb acrònims diferents (`INUNCAT` + `NEUCAT`). ⚠️ Reconstrucció: les files són literals, l'ordre no està observat |
| `pdf_url_accents_2026_07_03.json` | `docs/captures/wj9c-j6vf-infocat-2026-07-03.json` | `comunicatpdf.url` amb `ó`, `à` i `'` **sense codificar** (trap 7). També `planom == plaacronim` i `descripcio` amb el sufix `" - "` |

## Fixtures sintètics

**No són evidència.** Existeixen per exercitar camins de codi que les captures no
cobreixen, principalment la fase `EMERGÈNCIA` que **mai s'ha observat en un payload
real** ([`../../docs/01-data-sources.md`](../../docs/01-data-sources.md) §3.1, trap 14).
Cada fila porta una clau `_comment` que ho diu, perquè ningú els confongui amb una
captura. La forma (claus de negoci) imita la real; les URL de comunicat són inventades
i duen `_SYNTHETIC` al nom perquè no es puguin confondre amb un document publicat.

| Fixture | Què prova |
| --- | --- |
| `emergencia_SYNTHETIC.json` | La fase `EMERGÈNCIA`, no observada mai |
| `emergencia_plaactivat_rar_SYNTHETIC.json` | Tres files d'`EMERGÈNCIA` amb `plaactivat` = `Si`, ` SI ` i **camp absent**. Tres han de donar `activated = True`. Cada fila porta un `plaacronim` distint (`INUNCAT`, `INFOCAT`, `NEUCAT`) perquè les tres claus `(acronym, phase)` siguin distintes; amb l'acrònim repetit col·lapsarien en una entrada |
| `fase_desconeguda_SYNTHETIC.json` | `plafase: "MÀXIMA"`, fora de l'enum: vàlvula `unrecognized` sense llançar |
| `camps_absents_SYNTHETIC.json` | `comunicatpdf`, `plaicona` i `descripcio` absents de la fila (no `null`, sinó absents) |
| `dos_procicat_SYNTHETIC.json` | Dues files amb el **mateix** `plaacronim` (`PROCICAT`) en **fases diferents** (`PREALERTA` + `ALERTA`) i `planom` diferent. Sintètic perquè aquesta forma és una inferència de [`../../docs/01-data-sources.md`](../../docs/01-data-sources.md) §3.2 nota 2, mai observada; cobreix la reconciliació per clau `(acronym, phase)` i l'ambigüitat dels subplans del PROCICAT |

## Ús

```python
from tests.conftest import load_fixture

rows = load_fixture("alerta_2026_08_06")  # .json opcional
empty = load_fixture("buit_2026_06_16")  # == []
```

`load_fixture` accepta el nom amb o sense extensió i torna una llista (o diccionari
si algun dia calgués). El `FakeClock` del mateix `conftest` és el rellotge de tota la
lògica dependent del temps, mai `sleep()` ni `freezegun`.
