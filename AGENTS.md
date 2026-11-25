# Progetto: F1 Race Predictor

Obiettivo: pipeline ML locale in Python puro (no `.ipynb`) per prevedere l'ordine d'arrivo delle gare di Formula 1 usando FastF1, SQLite (`data/f1.db`), pandas, scikit-learn e XGBoost.

# Regole di efficienza token

1. Output conciso: rispondi con il solo codice modificato o i passaggi essenziali, senza spiegazioni introduttive o riassunti finali non richiesti.
2. Ispezione dati: quando esplori DataFrame o CSV via terminale, stampa sempre e solo `.shape`, `.dtypes` e `.head(3)`. Mai stampare intere tabelle.
3. Modifiche mirate: per file sopra le 80 righe, mostra o applica solo il diff della funzione modificata, non riscrivere l'intero file.
4. Fine sessione: su richiesta "salva stato", aggiorna `PROJECT_STATE.md` in massimo 40 righe elenco puntato.
