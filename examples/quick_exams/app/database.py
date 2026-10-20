"""ORM mappings over the existing records table, shared with the exam service."""

from datetime import datetime
import json
import secrets
import sqlite3

from sqlalchemy import String, Text, delete
from sqlalchemy.orm import Mapped, mapped_column, registry
from sqlalchemy.ext.asyncio import async_object_session

from patera.admin.form_values import AdminFormError
from patera.database.sql import DeclarativeBaseModel, SqlDatabase, SqlDatabaseManager
from patera.database.sql.declarative_base import ModelMeta
from app import store


class ExamsDb(SqlDatabase):
    __db_name__ = "exams"

    def init(self):
        super().init()
        self.app.add_on_startup_method(self.create_tables)

    async def create_tables(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Record.metadata.create_all)


class Databases(SqlDatabaseManager):
    databases = [ExamsDb]


class Base(DeclarativeBaseModel):
    __abstract__ = True
    registry = registry()
    metadata = registry.metadata


class Record(Base):
    __tablename__ = "records"
    __db_name__ = "exams"

    kind: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    __mapper_args__ = {"polymorphic_on": kind, "polymorphic_identity": "record"}

    class Meta(ModelMeta):
        exclude_from_create_form = ["kind", "id"]
        exclude_from_table = ["kind"]
        custom_labels = {"body": "Record data (JSON)", "id": "Record ID"}

    def validate_data(self, new_data, creating=False):
        """Validate against a private copy; never write through a second connection."""
        data = json.loads(new_data.get("body", "{}"))
        store.require(isinstance(data, dict), "Record data must be a JSON object")
        key = secrets.token_urlsafe(24) if creating else self.id
        store.require(data.get("id", key) == key, "The record ID cannot change")
        data["id"] = key
        kind = self.__mapper_args__["polymorphic_identity"]
        # Existing files need no migration. Service validators run on a disposable
        # copy, then the admin's ORM transaction persists the validated record.
        with sqlite3.connect(store.database_path()) as source:
            copy = sqlite3.connect(":memory:")
            try:
                source.backup(copy)
                old = {} if creating else store.get(copy, kind, key)
                if kind in ("category", "question", "exam"):
                    owner = data.get("owner", "")
                    store.get(copy, "user", owner)
                    store.require(
                        creating or owner == old["owner"], "Owner cannot change"
                    )
                    if kind == "category":
                        name = str(data.get("name", "")).strip()
                        store.require(
                            name and len(name) <= 100,
                            "Provide a category name (up to 100 characters)",
                        )
                        return {"id": key, "name": name, "owner": owner}
                    if kind == "question":
                        return store.question_save(copy, data, owner)
                    return store.exam_save(copy, data, owner)
                if kind == "user":
                    # Existing hashes are retained, never re-hashed as passwords.
                    password = data.get("password", "")
                    if not creating and password == old.get("password"):
                        data["password"] = ""
                    if creating:
                        data.pop("id")
                    result = store.user_save(copy, data)
                    result["id"] = key
                    return result
                if kind == "session":
                    store.require(not creating, "Sessions are created by signing in")
                    store.require(
                        data.get("user") == old["user"],
                        "A session cannot be reassigned",
                    )
                    created = datetime.fromisoformat(data.get("created", ""))
                    store.require(
                        created.tzinfo is not None, "Session timestamp needs a timezone"
                    )
                    store.require(
                        created.isoformat() <= old["created"],
                        "Session lifetime cannot be extended",
                    )
                    return {
                        "id": key,
                        "user": old["user"],
                        "created": created.isoformat(),
                    }
                if kind == "attempt":
                    store.require(
                        not creating, "Attempts are created by students starting exams"
                    )
                    # Email corrections are allowed; evidence and scores remain intact.
                    store.require(
                        {k: v for k, v in data.items() if k != "email"}
                        == {k: v for k, v in old.items() if k != "email"},
                        "Archived snapshots, answers and grades cannot be changed",
                    )
                    return {**old, "email": store.email_value(data.get("email", ""))}
                raise ValueError("Unknown record type")
            finally:
                copy.close()

    async def admin_create(self, new_data):
        try:
            data = self.validate_data(new_data, creating=True)
            self.id = data["id"]
            self.body = json.dumps(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise form_error(exc) from exc

    async def admin_update(self, new_data):
        try:
            data = self.validate_data(new_data)
            if (
                self.kind == "user"
                and data["password"] != json.loads(self.body)["password"]
            ):
                session = async_object_session(self)
                # Changing a password revokes every session for the user.
                rows = (
                    await session.execute(
                        Session.__table__.select().where(Session.kind == "session")
                    )
                ).mappings()
                for row in rows:
                    if json.loads(row["body"])["user"] == self.id:
                        await session.execute(
                            delete(Session).where(Session.id == row["id"])
                        )
            self.body = json.dumps(data)
        except (ValueError, TypeError, KeyError) as exc:
            raise form_error(exc) from exc

    async def admin_delete(self):
        try:
            with sqlite3.connect(store.database_path()) as db:
                if self.kind == "attempt":
                    raise ValueError("Exam attempts and archives must be retained")
                if self.kind == "question":
                    store.require(
                        not any(
                            self.id in e["questions"]
                            for e in store.all_records(db, "exam")
                        ),
                        "Remove the question from live exams first",
                    )
                if self.kind == "category":
                    store.require(
                        not any(
                            q["category"] == self.id
                            for q in store.all_records(db, "question")
                        ),
                        "Move or delete this category's questions first",
                    )
                if self.kind == "user":
                    store.require(
                        not any(
                            r.get("owner") == self.id
                            for kind in ("category", "question", "exam", "attempt")
                            for r in store.all_records(db, kind)
                        ),
                        "This user owns content or archives; remove their roles to disable access instead",
                    )
                    user = json.loads(self.body)
                    store.require(
                        "ADMIN" not in user["roles"]
                        or sum(
                            "ADMIN" in u["roles"] for u in store.all_records(db, "user")
                        )
                        > 1,
                        "Keep at least one admin",
                    )
                    store.require(
                        not any(
                            s["user"] == self.id
                            for s in store.all_records(db, "session")
                        ),
                        "Revoke this user's sessions first",
                    )
        except ValueError as exc:
            raise form_error(exc) from exc


def form_error(exc):
    return AdminFormError([{"loc": ["body"], "msg": str(exc), "type": "value_error"}])


class User(Record):
    __mapper_args__ = {"polymorphic_identity": "user"}


class Category(Record):
    __mapper_args__ = {"polymorphic_identity": "category"}


class Question(Record):
    __mapper_args__ = {"polymorphic_identity": "question"}


class Exam(Record):
    __mapper_args__ = {"polymorphic_identity": "exam"}


class Attempt(Record):
    __mapper_args__ = {"polymorphic_identity": "attempt"}


class Session(Record):
    __mapper_args__ = {"polymorphic_identity": "session"}
