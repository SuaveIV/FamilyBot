# In src/familybot/web/dependencies.py
"""
FastAPI dependency functions shared across route modules.
"""

from familybot.lib.database import get_db_connection


def get_db():
    """
    Yield a SQLite connection for use in a request, closing it afterwards.
    Passed via FastAPI's Depends() mechanism.
    """
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()
