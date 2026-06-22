from pathlib import Path
from typing import Optional, TypedDict, cast
from pydantic import BaseModel

from .admin_interface import AdminInterface

from patera import (
    Patera,
    MediaType,
    HttpStatus,
    Request,
    Response,
    UploadedFile,
)
from patera.controller import (
    Controller,
    get,
    post,
    delete,
    patch,
    consumes,
    produces,
)


class FileOrFolder(TypedDict):
    type: str
    is_folder: bool
    path: str
    name: str
    ext: Optional[str]
    extension: Optional[str]
    last_modified: Optional[float]
    size: Optional[int]


class FilesDeleteInput(BaseModel):
    """List of file paths to delete"""

    files: list[str]


class FilesUploadInput(BaseModel):
    """List of uploaded files"""

    files: list[UploadedFile]


class FileRenameInput(BaseModel):
    file_name: str
    file_path: str


class _AdminFileController(Controller[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @get("/explorer")
    async def explorer(self, req: Request) -> Response:
        return await req.res.html(
            "_admin/files/file_explorer.html",
            {**self.admin_interface.context_variables},
        )

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    async def list_root(self, req: Request) -> Response:
        """
        Lists the static root folder.
        """
        return self.list_directory_response(req, "")

    @get("/<path:directory>")
    @produces(MediaType.APPLICATION_JSON)
    async def list_directory(self, req: Request, directory: str) -> Response:
        """
        Lists a directory inside the static root folder.

        Example:
            GET /admin/files/images
            GET /admin/files/css/vendor
        """
        return self.list_directory_response(req, directory)

    @post("/")
    @consumes(MediaType.APPLICATION_OCTET_STREAM)
    @produces(MediaType.APPLICATION_JSON)
    async def upload(self, req: Request) -> Response:
        return req.res.json({}).status(HttpStatus.CREATED)

    @delete("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def delete(self, req: Request) -> Response:
        return req.res.no_content()

    @patch("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    async def rename(self, req: Request) -> Response:
        return req.res.json({}).status(HttpStatus.ACCEPTED)

    def list_directory_response(self, req: Request, directory: str) -> Response:
        try:
            target_dir = self.resolve_inside_static_root(directory)

            if not target_dir.exists():
                return req.res.json(
                    {
                        "status": "error",
                        "message": "Directory does not exist.",
                    }
                ).status(HttpStatus.NOT_FOUND)

            if not target_dir.is_dir():
                return req.res.json(
                    {
                        "status": "error",
                        "message": "Path is not a directory.",
                    }
                ).status(HttpStatus.BAD_REQUEST)

            items = self.get_all_files(target_dir)
            relative_path = self.relative_to_static_root(target_dir)

            return req.res.json(
                {
                    "status": "success",
                    "message": "Files and folders fetched successfully.",
                    "data": {
                        "root": str(self.app_static_path),
                        "current_path": str(target_dir),
                        "current_relative_path": relative_path,
                        "path": relative_path,
                        "items": items,
                        "breadcrumbs": self.build_breadcrumbs(relative_path),
                    },
                }
            ).status(HttpStatus.OK)

        except ValueError as exc:
            return req.res.json(
                {
                    "status": "error",
                    "message": str(exc),
                }
            ).status(HttpStatus.BAD_REQUEST)

        except Exception as exc:
            self.app.logger.exception(exc)
            return req.res.json(
                {
                    "status": "error",
                    "message": "Failed to list files and folders.",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    def get_all_files(self, cwd: str | Path) -> list[FileOrFolder]:
        """
        Lists direct children of cwd.

        Returned paths are relative to app_static_path and use forward slashes,
        so they are safe to send to the frontend.
        """
        cwd_path = Path(cwd).resolve()
        static_root = self.app_static_path.resolve()

        if not self.is_path_inside_root(cwd_path, static_root):
            raise ValueError(
                f"Directory {cwd_path} is not inside application static folder."
            )

        files_and_folders: list[FileOrFolder] = []

        for child_path in cwd_path.iterdir():
            is_folder = child_path.is_dir()
            relative_path = self.relative_to_static_root(child_path)

            files_and_folders.append(
                {
                    "type": "folder" if is_folder else "file",
                    "is_folder": is_folder,
                    "name": child_path.name,
                    "path": relative_path,
                    "ext": None if is_folder else child_path.suffix,
                    "extension": None
                    if is_folder
                    else child_path.suffix.lstrip(".").lower(),
                    "last_modified": None if is_folder else child_path.stat().st_mtime,
                    "size": None if is_folder else child_path.stat().st_size,
                }
            )

        files_and_folders.sort(
            key=lambda item: (
                not item["is_folder"],
                item["name"].lower(),
            )
        )

        return files_and_folders

    def resolve_inside_static_root(self, directory: str | Path) -> Path:
        """
        Resolves a user-provided relative path inside app_static_path.

        Rejects path traversal such as:
            ../secret.txt
            ../../etc/passwd
        """
        static_root = self.app_static_path.resolve()

        directory_str = str(directory or "").strip()

        if directory_str in {"", ".", "/"}:
            target_path = static_root
        else:
            target_path = static_root / directory_str

        target_path = target_path.resolve()

        if not self.is_path_inside_root(target_path, static_root):
            raise ValueError("Requested path is outside the static root folder.")

        return target_path

    def relative_to_static_root(self, path: str | Path) -> str:
        """
        Returns a normalized POSIX-style path relative to app_static_path.

        Example:
            /app/static/images/logo.png -> images/logo.png
        """
        static_root = self.app_static_path.resolve()
        target_path = Path(path).resolve()

        if not self.is_path_inside_root(target_path, static_root):
            raise ValueError("Path is outside the static root folder.")

        if target_path == static_root:
            return ""

        return target_path.relative_to(static_root).as_posix()

    def build_breadcrumbs(self, relative_path: str) -> list[dict[str, str]]:
        """
        Builds breadcrumbs for the frontend.

        Example:
            images/icons

        Returns:
            [
                {"label": "Root", "path": ""},
                {"label": "images", "path": "images"},
                {"label": "icons", "path": "images/icons"},
            ]
        """
        breadcrumbs: list[dict[str, str]] = [
            {
                "label": "Root",
                "path": "",
            }
        ]

        parts = [part for part in relative_path.split("/") if part]

        current = ""

        for part in parts:
            current = f"{current}/{part}".strip("/")

            breadcrumbs.append(
                {
                    "label": part,
                    "path": current,
                }
            )

        return breadcrumbs

    def is_path_inside_root(self, path: str | Path, root: str | Path) -> bool:
        root_path = Path(root).resolve()
        target_path = Path(path).resolve()

        return target_path == root_path or target_path.is_relative_to(root_path)

    @property
    def app_static_path(self) -> Path:
        return Path(self.app.static_files_path)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
