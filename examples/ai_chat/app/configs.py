import os

from patera import BaseConfig
from patera.aiinterface import AiServiceConfig, AugmentationConfig, HistorySummaryConfig
from patera.database.sql import SqlDatabaseConfig


class Config(BaseConfig):
    BASE_PATH: str = os.path.dirname(__file__)
    APP_NAME: str = "AI chat example"
    VERSION: str = "1.0.0"

    # SQLite works out of the box (documents are compared in Python). For
    # PostgreSQL with pgvector (one search query in the database) set
    # PATERA_CHAT_DB__DATABASE_URI=postgresql+asyncpg://user:password@host/db
    CHAT_DB: SqlDatabaseConfig = SqlDatabaseConfig(
        DATABASE_URI="sqlite+aiosqlite:///./ai_chat.db"
    )

    # Configuration of the Assistant service (named after the class).
    # The key comes from the environment: PATERA_ASSISTANT__API_KEY=sk-...
    ASSISTANT: AiServiceConfig = AiServiceConfig(
        BASE_URL="https://api.openai.com/v1",
        MODEL="gpt-4o-mini",
        TEMPERATURE=0.2,
        HISTORY_LIMIT=10,  # earlier messages sent with each question
        # Older messages are merged into a summary in the background, 10 at a time.
        HISTORY_SUMMARY=HistorySummaryConfig(EVERY=10, MAX_WORDS=200),
        AUGMENTATION=AugmentationConfig(
            MODEL_NAME_OR_PATH="all-MiniLM-L6-v2",  # 384-dimensional embeddings
            MINIMAL_SIMILARITY=0.4,
            MATCH_LIMIT=4,
            REWRITE_QUERY=True,  # "and how do I install it?" -> a standalone question
        ),
    )
