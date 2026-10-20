from patera.database.sql import SqlDatabase, SqlDatabaseManager
from patera.migrate import Migrate


class ExamsDb(SqlDatabase, Migrate):
    __db_name__ = "exams"


class Databases(SqlDatabaseManager):
    databases = [ExamsDb]
