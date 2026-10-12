from pathlib import Path

from sqlalchemy import text

from patera.cli import CLIController, cli_controller, command
from patera.injectable import Inject

from app import App
from app.assistant import Assistant
from app.database import Base, Databases


@cli_controller(name="assistant")
class AssistantCLI(CLIController[App]):
    assistant: Inject[Assistant]

    @command("setup", help="Creates the chat and document tables")
    async def setup(self) -> None:
        db = self.app.get_extension(Databases).get_database("chat")
        await db.connect()
        async with db.engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        print("Tables created.")

    @command(
        "add-documents", help="Embeds and stores the .md and .txt files of a folder"
    )
    async def add_documents(self, folder: str) -> None:
        files = sorted(
            p
            for p in Path(folder).rglob("*")
            if p.suffix in {".md", ".txt"} and p.is_file()
        )
        for file in files:
            # One document per paragraph keeps each match short and on topic.
            paragraphs = [
                part.strip()
                for part in file.read_text(encoding="utf-8").split("\n\n")
                if part.strip()
            ]
            await self.assistant.augmentation_provider.add_documents(
                paragraphs, source=file.name
            )
            print(f"{file.name}: {len(paragraphs)} documents")
