from dotenv import load_dotenv
import os
from pathlib import Path

# locate .env file in backend folder
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH)

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "naseer")
MYSQL_DB = os.getenv("MYSQL_DB", "legal_ai")

if not MONGO_URI:
    raise ValueError("❌ MONGO_URI not found in .env file")

if not MONGO_DB:
    raise ValueError("❌ MONGO_DB not found in .env file")
