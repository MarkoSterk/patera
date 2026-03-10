"""
Import all extensions and initilize
After that import them into the create_app method and initilize with application
"""

from pyjolt.database.sql import SqlDatabase
from pyjolt.database.migrate import Migrate

db: SqlDatabase = SqlDatabase()
migrate: Migrate = Migrate(db)

__all__ = ["db", "migrate"]
