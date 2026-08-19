from pathlib import Path

from dotenv import load_dotenv


def load_local_environment() -> None:
    """Load the ignored backend .env once for local production-style execution."""
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
