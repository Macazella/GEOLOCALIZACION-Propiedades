# Privacy Audit — Public Repository

Performed before the first commit/push to
`https://github.com/Macazella/GEOLOCALIZACION-Propiedades`.

Scope: the entire working tree of `GEOLOCALIZACCION-PUBLIC` (this
repository), as it stands right before the initial commit.

## Method

Recursive case-insensitive search across all tracked files (excluding
`.git/`) for each category below, plus a manual review of every file
that a search hit touched.

## Results

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Owner's personal name / email | **PASS** | Only hit: `Macazella` in `LICENSE` copyright line — this is the author's own public GitHub handle, already public on the account that owns this repo. No personal email, no legal name, no other personal identifier found. |
| 2 | Original private spreadsheet filename | **PASS (fixed)** | `src/utils/excel_io.py` originally hardcoded the real operational filename (which included the owner's nickname). Replaced with the generic placeholder `input_spreadsheet.xlsx` before this audit was finalized. Verified with a second grep pass: zero hits. |
| 3 | Real listing URLs from the operational dataset | **PASS** | Only hit: `tests/test_dedup_y_comentarios.py`, using `https://www.remax.com.ar/listings/fake-test-url` — an intentionally fake path (literal `fake-test-url` segment), used only to test that a comment field passes through unmodified. No real listing path present anywhere. |
| 4 | Real `comentario_personal` content | **PASS (fixed during prep)** | One test fixture in the source private repository had accidentally reused a real personal comment string. It was replaced with a synthetic one (`"Comentario de prueba, con signos!! y mayúsculas RARAS."`) before this file was even copied into the public tree. Searched for that string and five other known real comment fragments here: zero hits. |
| 5 | Secrets / API keys / tokens / cookies / `.env` | **PASS** | No `.env` file present (only `.env.example`, which is a template with no real values — the project needs no credentials to run). No `key=`, `secret=`, `password=`, private-key blocks, or AWS-style credentials found anywhere. |
| 6 | Cache / checkpoints / logs / real datasets | **PASS** | `data/`, `cache/`, `checkpoints/`, `logs/`, `output/`, `*.xlsx` are all excluded via `.gitignore`. A `data/cache/` and `logs/pipeline.log` were created locally as a side effect of running `pytest` during preparation (the cache/logging modules create their directories on import) — both were empty and have been deleted; they are gitignored regardless. |
| 7 | Real coordinates from the operational dataset | **PASS** | Searched for the Buenos Aires metro area coordinate range (`-34.x`, `-35.x` latitude). Zero hits — the only coordinates in this repo are the fictional ones in `examples/`, placed in an unrelated, sparsely-populated region specifically so they cannot be mistaken for real data. |
| 8 | Original file/directory names specific to the private project | **PASS** | No references to the private repository's structure beyond what's generic to any Python project. |

## Overall result: **PASS**

No personal data, real listing data, real addresses, real comments,
secrets, or operational artifacts are present in this repository as of
the commit this audit corresponds to.

## What's intentionally still real

- The author's GitHub handle (`Macazella`), in `LICENSE` — this is a
  public authorship attribution, the same handle that owns this GitHub
  repository, not a leak.
- Real, publicly-known Argentine street/neighborhood names used only
  inside unit tests to verify a normalization dictionary (e.g. `Lanús`,
  `Lomas de Zamora`, `O'Higgins`) — these are common geographic/street
  names used the same way a US-focused library's tests would reference
  "Main St" or "Brooklyn": they verify the normalizer works, they do
  not disclose which specific address the author is evaluating.

## Rule applied

This audit was a hard gate: publishing to the public repository was
withheld until this document showed **PASS** on every row.
