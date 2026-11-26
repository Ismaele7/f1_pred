# Stato Progetto: F1 Race Predictor

## Completato

- Struttura cartelle (`src/`, `data/`, `models/`) e file di controllo (`AGENTS.md`, `.gitignore`, `.cursorignore`).
- `src/config.py`: percorsi `pathlib`, `DB_PATH = data/f1.db`, `SEASONS = [2021, 2022, 2023, 2024, 2025, 2026]`.
- `src/fetch_data.py`:
  - Cache FastF1 e flag CLI `--force-refresh`.
  - Normalizzazione temporale (UTC) e filtraggio eventi già conclusi.
  - Parsing sessioni `Q` e `R` con chiave univoca `(year, round_number, driver_code)`.
  - Salvataggio tabelle con conteggi e NA:
    - `sessions`: 220 righe, air/temp missing 220, anno 2021‑2026.
    - `qualifying_results`: 2213 righe, NA in q1/q2/q3 (47/596/1146), anno 2021‑2026.
    - `race_results`: 2214 righe, NA in `avg_clean_lap_sec` (2214), anno 2021‑2026.
  - Transazioni atomiche per weekend e cancellazione sicura con `--force-refresh`.
- Database `data/f1.db` popolato con stagioni 2021‑2026, verificato con conteggi e valori mancanti.

## Prossimo Task

- **Task 3:** esplorazione e diagnostica dei dati (`src/eda_report.py`). Caricare le tabelle, analizzare distribuzioni, valori mancanti e pattern temporali.
