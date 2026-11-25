from pathlib import Path

# Cartella principale del progetto (risale di un livello rispetto a src/)
BASE_DIR = Path(__file__).resolve().parent.parent

# Percorsi dati e cache
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "f1.db"

# Cartella e file del modello addestrato
MODELS_DIR = BASE_DIR / "models"
MODEL_PATH = MODELS_DIR / "xgb_f1_model.json"

# Parametri Formula 1 (iniziamo con 2 stagioni per scaricare velocemente)
SEASONS = [2024, 2025]

# Parametri Machine Learning
RANDOM_STATE = 42
TEST_SIZE = 0.2

# Crea automaticamente le cartelle se non esistono ancora
for directory in (DATA_DIR, CACHE_DIR, MODELS_DIR):
    directory.mkdir(parents=True, exist_ok=True)