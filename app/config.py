import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_HOST = os.getenv(
    "OLLAMA_HOST",
    "http://localhost:11434"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:7b"
)

MAX_AGENT_STEPS = int(
    os.getenv("MAX_AGENT_STEPS", "8")
)

OLLAMA_TIMEOUT_SECONDS = float(
    os.getenv("OLLAMA_TIMEOUT_SECONDS", "120")
)

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "worker.db"
)
