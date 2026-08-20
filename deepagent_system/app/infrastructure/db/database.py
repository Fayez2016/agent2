import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Generator
from app.config import settings

logger = logging.getLogger("Database")

class DatabasePool:
    """
    Centralized Database Connection Manager.
    Uses settings for credentials and provides safe context-managed connections.
    """

    @staticmethod
    def get_connection():
        db_url = settings.database_url
        if db_url:
            return psycopg2.connect(db_url)
        return psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_pass
        )

    @classmethod
    @contextmanager
    def get_cursor(cls, commit: bool = False) -> Generator:
        conn = cls.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction error: {e}", exc_info=True)
            raise
        finally:
            cursor.close()
            conn.close()
