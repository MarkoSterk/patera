from __future__ import annotations

import mimetypes
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional, TypedDict, cast
from urllib.parse import quote
from pydantic import BaseModel, ValidationError, field_validator

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
    before_request,
)

from patera.auth import login_required

from .exceptions import (
    AdminUnsupportedLanguage,
    AdminLoginRequiredException,
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


class FilePathInput(BaseModel):
    path: str = ""

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, value: Any) -> str:
        if value is None:
            return ""

        normalized = str(value).strip().replace("\\", "/").strip("/")

        return normalized


class FilesUploadInput(FilePathInput):
    files: list[UploadedFile]
    relative_paths: list[str] = []
    directories: list[str] = []

    @field_validator("files", mode="before")
    @classmethod
    def normalize_files(cls, value: Any) -> list[UploadedFile]:
        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return list(value)

        return [value]

    @field_validator("relative_paths", mode="before")
    @classmethod
    def normalize_relative_paths(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        if isinstance(value, tuple):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        return [str(value).strip().replace("\\", "/").strip("/")]

    @field_validator("directories", mode="before")
    @classmethod
    def normalize_directories(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        if isinstance(value, tuple):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        return [str(value).strip().replace("\\", "/").strip("/")]


class FilesDeleteInput(FilePathInput):
    files: list[str]

    @field_validator("files", mode="before")
    @classmethod
    def normalize_files(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item) for item in value]

        if isinstance(value, tuple):
            return [str(item) for item in value]

        return [str(value)]


class FileRenameInput(BaseModel):
    path: str
    new_name: str

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip().replace("\\", "/").strip("/")

    @field_validator("new_name", mode="before")
    @classmethod
    def normalize_new_name(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()


class FilesMoveInput(BaseModel):
    path: str = ""
    files: list[str]
    destination_path: str

    @field_validator("path", mode="before")
    @classmethod
    def normalize_path(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip().replace("\\", "/").strip("/")

    @field_validator("files", mode="before")
    @classmethod
    def normalize_files(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        if isinstance(value, tuple):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        return [str(value).strip().replace("\\", "/").strip("/")]

    @field_validator("destination_path", mode="before")
    @classmethod
    def normalize_destination_path(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip().replace("\\", "/").strip("/")


class FileCreateFolderInput(FilePathInput):
    folder_name: str

    @field_validator("folder_name", mode="before")
    @classmethod
    def normalize_folder_name(cls, value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()


class FilesDownloadInput(FilePathInput):
    files: list[str]

    @field_validator("files", mode="before")
    @classmethod
    def normalize_files(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        if isinstance(value, tuple):
            return [str(item).strip().replace("\\", "/").strip("/") for item in value]

        return [str(value).strip().replace("\\", "/").strip("/")]


class _AdminFileController(Controller[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @before_request
    async def check_language(self, req: Request):
        lang = cast(str, req.route_parameters.get("lang"))

        if lang not in self.admin_interface.supported_languages:
            raise AdminUnsupportedLanguage(lang)

    @get("/explorer")
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def explorer(self, req: Request) -> Response:
        return await req.res.html(
            "_admin/files/file_explorer.html",
            {
                **self.admin_interface.context_variables,
                "file_explorer_root": self.app_static_path,
                "file_explorer_root_indicator": str(self.app_static_path).split(
                    self.app.configs.APP_PACKAGE, 1
                )[1],
            },
        )

    @get("/")
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def list_root(self, req: Request) -> Response:
        try:
            query = FilePathInput.model_validate(req.query_parameters)
            return self.list_directory_response(req, query.path)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid query parameters.")

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to list files and folders.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @get("/<path:directory>")
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def list_directory(self, req: Request, directory: str) -> Response:
        try:
            query = FilePathInput(path=directory)
            return self.list_directory_response(req, query.path)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid directory path.")

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to list files and folders.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @post("/")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def upload(self, req: Request) -> Response:
        try:
            form_data = await req.form_and_files()
            input_data = FilesUploadInput.model_validate(form_data)

            return await self.upload_files_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid upload data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to upload files.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @post("/folder")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def create_folder(self, req: Request) -> Response:
        try:
            json_data = await req.get_data("json") or {}
            input_data = FileCreateFolderInput.model_validate(json_data)

            return self.create_folder_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid folder data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to create folder.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @delete("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def delete(self, req: Request) -> Response:
        try:
            json_data = await req.get_data("json") or {}
            input_data = FilesDeleteInput.model_validate(json_data)

            return self.delete_items_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid delete data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to delete files or folders.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @patch("/")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def rename(self, req: Request) -> Response:
        try:
            json_data = await req.get_data("json") or {}
            input_data = FileRenameInput.model_validate(json_data)

            return self.rename_item_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid rename data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to rename file or folder.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @patch("/move")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def move(self, req: Request) -> Response:
        try:
            json_data = await req.get_data("json") or {}
            input_data = FilesMoveInput.model_validate(json_data)

            return self.move_items_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid move data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to move files or folders.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    @post("/download")
    @consumes(MediaType.APPLICATION_JSON)
    @login_required(raise_authentication_exception=AdminLoginRequiredException)
    async def download(self, req: Request) -> Response:
        try:
            json_data = await req.get_data("json") or {}
            input_data = FilesDownloadInput.model_validate(json_data)

            return self.download_items_response(req, input_data)

        except ValidationError as e:
            return self.validation_error_response(req, e, "Invalid download data.")

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

        except Exception as e:
            self.app.logger.exception(e)
            return self.error_response(
                req,
                "Failed to download files or folders.",
                HttpStatus.INTERNAL_SERVER_ERROR,
            )

    def list_directory_response(self, req: Request, directory: str) -> Response:
        try:
            target_dir = self.resolve_inside_static_root(directory)

            if not target_dir.exists():
                return self.error_response(
                    req,
                    "Directory does not exist.",
                    HttpStatus.NOT_FOUND,
                )

            if not target_dir.is_dir():
                return self.error_response(
                    req,
                    "Path is not a directory.",
                    HttpStatus.BAD_REQUEST,
                )

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

        except ValueError as e:
            return self.error_response(req, str(e), HttpStatus.BAD_REQUEST)

    async def upload_files_response(
        self,
        req: Request,
        input_data: FilesUploadInput,
    ) -> Response:
        target_dir = self.resolve_inside_static_root(input_data.path)

        if not target_dir.exists():
            return self.error_response(
                req,
                "Upload directory does not exist.",
                HttpStatus.NOT_FOUND,
            )

        if not target_dir.is_dir():
            return self.error_response(
                req,
                "Upload path is not a directory.",
                HttpStatus.BAD_REQUEST,
            )

        if not input_data.files and not input_data.directories:
            return self.error_response(
                req,
                "No files or folders were uploaded.",
                HttpStatus.BAD_REQUEST,
            )

        created_directories: list[dict[str, str]] = []

        for directory in input_data.directories:
            safe_directory = self.validate_relative_upload_path(directory)
            directory_path = (target_dir / safe_directory).resolve()

            if not self.is_path_inside_root(directory_path, self.app_static_path):
                raise ValueError("Upload directory is outside the static root folder.")

            directory_path.mkdir(parents=True, exist_ok=True)

            created_directories.append(
                {
                    "path": self.relative_to_static_root(directory_path),
                }
            )

        saved_files: list[dict[str, Any]] = []

        for index, uploaded_file in enumerate(input_data.files):
            if index < len(input_data.relative_paths):
                relative_file_path = input_data.relative_paths[index]
            else:
                relative_file_path = uploaded_file.filename

            safe_relative_file_path = self.validate_relative_upload_path(
                relative_file_path
            )
            destination = (target_dir / safe_relative_file_path).resolve()

            if not self.is_path_inside_root(destination, self.app_static_path):
                raise ValueError(
                    "Upload destination is outside the static root folder."
                )

            if destination.exists() and destination.is_dir():
                return self.error_response(
                    req,
                    f'Cannot overwrite folder "{destination.name}" with a file.',
                    HttpStatus.BAD_REQUEST,
                )

            destination.parent.mkdir(parents=True, exist_ok=True)

            uploaded_file.save(str(destination))

            saved_files.append(
                {
                    "name": destination.name,
                    "path": self.relative_to_static_root(destination),
                    "size": destination.stat().st_size
                    if destination.exists()
                    else None,
                }
            )

        return req.res.json(
            {
                "status": "success",
                "message": "Files and folders uploaded successfully.",
                "data": {
                    "path": self.relative_to_static_root(target_dir),
                    "files": saved_files,
                    "directories": created_directories,
                    "items": self.get_all_files(target_dir),
                },
            }
        ).status(HttpStatus.CREATED)

    def validate_relative_upload_path(self, path: str) -> str:
        safe_path = self.normalize_relative_path(path)

        if not safe_path:
            raise ValueError("Upload path is required.")

        parts = [part for part in safe_path.split("/") if part]

        if not parts:
            raise ValueError("Upload path is required.")

        for part in parts:
            self.validate_file_or_folder_name(part)

        return "/".join(parts)

    def create_folder_response(
        self,
        req: Request,
        input_data: FileCreateFolderInput,
    ) -> Response:
        parent_dir = self.resolve_inside_static_root(input_data.path)

        if not parent_dir.exists():
            return self.error_response(
                req,
                "Parent directory does not exist.",
                HttpStatus.NOT_FOUND,
            )

        if not parent_dir.is_dir():
            return self.error_response(
                req,
                "Parent path is not a directory.",
                HttpStatus.BAD_REQUEST,
            )

        safe_folder_name = self.validate_file_or_folder_name(input_data.folder_name)
        folder_path = (parent_dir / safe_folder_name).resolve()

        if not self.is_path_inside_root(folder_path, self.app_static_path):
            raise ValueError("Folder destination is outside the static root folder.")

        if folder_path.exists():
            return self.error_response(
                req,
                f'File or folder "{safe_folder_name}" already exists.',
                HttpStatus.BAD_REQUEST,
            )

        folder_path.mkdir(parents=False, exist_ok=False)

        return req.res.json(
            {
                "status": "success",
                "message": "Folder created successfully.",
                "data": {
                    "name": safe_folder_name,
                    "path": self.relative_to_static_root(folder_path),
                    "parent_path": self.relative_to_static_root(parent_dir),
                    "items": self.get_all_files(parent_dir),
                },
            }
        ).status(HttpStatus.CREATED)

    def rename_item_response(
        self,
        req: Request,
        input_data: FileRenameInput,
    ) -> Response:
        if not input_data.path:
            return self.error_response(
                req,
                "Missing path.",
                HttpStatus.BAD_REQUEST,
            )

        safe_new_name = self.validate_file_or_folder_name(input_data.new_name)
        old_path = self.resolve_inside_static_root(input_data.path)

        if old_path == self.app_static_path.resolve():
            return self.error_response(
                req,
                "Renaming the static root folder is not allowed.",
                HttpStatus.BAD_REQUEST,
            )

        if not old_path.exists():
            return self.error_response(
                req,
                "File or folder does not exist.",
                HttpStatus.NOT_FOUND,
            )

        parent_dir = old_path.parent
        new_path = (parent_dir / safe_new_name).resolve()

        if not self.is_path_inside_root(new_path, self.app_static_path):
            raise ValueError("Rename destination is outside the static root folder.")

        if new_path == old_path:
            return req.res.json(
                {
                    "status": "success",
                    "message": "Name unchanged.",
                    "data": {
                        "path": self.relative_to_static_root(old_path),
                        "name": old_path.name,
                    },
                }
            ).status(HttpStatus.OK)

        if new_path.exists():
            return self.error_response(
                req,
                f'File or folder "{safe_new_name}" already exists.',
                HttpStatus.BAD_REQUEST,
            )

        old_relative_path = self.relative_to_static_root(old_path)
        old_path.rename(new_path)

        return req.res.json(
            {
                "status": "success",
                "message": "File or folder renamed successfully.",
                "data": {
                    "old_path": old_relative_path,
                    "new_path": self.relative_to_static_root(new_path),
                    "name": safe_new_name,
                    "parent_path": self.relative_to_static_root(parent_dir),
                    "items": self.get_all_files(parent_dir),
                },
            }
        ).status(HttpStatus.ACCEPTED)

    def delete_items_response(
        self,
        req: Request,
        input_data: FilesDeleteInput,
    ) -> Response:
        if not input_data.files:
            return self.error_response(
                req,
                "No files or folders were selected for deletion.",
                HttpStatus.BAD_REQUEST,
            )

        deleted_items: list[dict[str, str]] = []
        missing_items: list[str] = []

        for relative_path in input_data.files:
            normalized_path = self.normalize_relative_path(relative_path)
            target_path = self.resolve_inside_static_root(normalized_path)

            if target_path == self.app_static_path.resolve():
                return self.error_response(
                    req,
                    "Deleting the static root folder is not allowed.",
                    HttpStatus.BAD_REQUEST,
                )

            if not target_path.exists():
                missing_items.append(normalized_path)
                continue

            if target_path.is_dir():
                shutil.rmtree(target_path)
                item_type = "folder"
            else:
                target_path.unlink()
                item_type = "file"

            deleted_items.append(
                {
                    "type": item_type,
                    "path": normalized_path,
                }
            )

        current_dir = self.resolve_inside_static_root(input_data.path)
        refreshed_items: list[FileOrFolder] = []

        if current_dir.exists() and current_dir.is_dir():
            refreshed_items = self.get_all_files(current_dir)

        return req.res.json(
            {
                "status": "success",
                "message": "Files and folders deleted successfully.",
                "data": {
                    "deleted": deleted_items,
                    "missing": missing_items,
                    "items": refreshed_items,
                },
            }
        ).status(HttpStatus.OK)

    def get_all_files(self, cwd: str | Path) -> list[FileOrFolder]:
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
            stat = child_path.stat()

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
                    "last_modified": stat.st_mtime,
                    "size": None if is_folder else stat.st_size,
                }
            )

        files_and_folders.sort(
            key=lambda item: (
                not item["is_folder"],
                item["name"].lower(),
            )
        )

        return files_and_folders

    def move_items_response(
        self,
        req: Request,
        input_data: FilesMoveInput,
    ) -> Response:
        if not input_data.files:
            return self.error_response(
                req,
                "No files or folders were selected for moving.",
                HttpStatus.BAD_REQUEST,
            )

        destination_dir = self.resolve_inside_static_root(input_data.destination_path)

        if not destination_dir.exists():
            return self.error_response(
                req,
                "Destination directory does not exist.",
                HttpStatus.NOT_FOUND,
            )

        if not destination_dir.is_dir():
            return self.error_response(
                req,
                "Destination path is not a directory.",
                HttpStatus.BAD_REQUEST,
            )

        moved_items: list[dict[str, str]] = []
        skipped_items: list[dict[str, str]] = []

        for relative_path in input_data.files:
            source_relative_path = self.normalize_relative_path(relative_path)
            source_path = self.resolve_inside_static_root(source_relative_path)

            if source_path == self.app_static_path.resolve():
                return self.error_response(
                    req,
                    "Moving the static root folder is not allowed.",
                    HttpStatus.BAD_REQUEST,
                )

            if not source_path.exists():
                skipped_items.append(
                    {
                        "path": source_relative_path,
                        "reason": "Source does not exist.",
                    }
                )
                continue

            if source_path.parent.resolve() == destination_dir.resolve():
                skipped_items.append(
                    {
                        "path": source_relative_path,
                        "reason": "Source is already in the destination directory.",
                    }
                )
                continue

            destination_path = (destination_dir / source_path.name).resolve()

            if not self.is_path_inside_root(destination_path, self.app_static_path):
                raise ValueError("Move destination is outside the static root folder.")

            if source_path.is_dir():
                if destination_dir == source_path or destination_dir.is_relative_to(
                    source_path
                ):
                    return self.error_response(
                        req,
                        "Cannot move a folder into itself or one of its subfolders.",
                        HttpStatus.BAD_REQUEST,
                    )

            if destination_path.exists():
                return self.error_response(
                    req,
                    f'File or folder "{source_path.name}" already exists in the destination.',
                    HttpStatus.BAD_REQUEST,
                )

            shutil.move(str(source_path), str(destination_path))

            moved_items.append(
                {
                    "old_path": source_relative_path,
                    "new_path": self.relative_to_static_root(destination_path),
                    "name": source_path.name,
                    "type": "folder" if destination_path.is_dir() else "file",
                }
            )

        current_dir = self.resolve_inside_static_root(input_data.path)
        refreshed_items: list[FileOrFolder] = []

        if current_dir.exists() and current_dir.is_dir():
            refreshed_items = self.get_all_files(current_dir)

        return req.res.json(
            {
                "status": "success",
                "message": "Files and folders moved successfully.",
                "data": {
                    "moved": moved_items,
                    "skipped": skipped_items,
                    "items": refreshed_items,
                },
            }
        ).status(HttpStatus.OK)

    def resolve_inside_static_root(self, directory: str | Path) -> Path:
        static_root = self.app_static_path.resolve()
        directory_str = self.normalize_relative_path(directory)

        if directory_str in {"", ".", "/"}:
            target_path = static_root
        else:
            target_path = static_root / directory_str

        target_path = target_path.resolve()

        if not self.is_path_inside_root(target_path, static_root):
            raise ValueError("Requested path is outside the static root folder.")

        return target_path

    def normalize_relative_path(self, path: str | Path) -> str:
        return str(path or "").strip().replace("\\", "/").strip("/")

    def relative_to_static_root(self, path: str | Path) -> str:
        static_root = self.app_static_path.resolve()
        target_path = Path(path).resolve()

        if not self.is_path_inside_root(target_path, static_root):
            raise ValueError("Path is outside the static root folder.")

        if target_path == static_root:
            return ""

        return target_path.relative_to(static_root).as_posix()

    def build_breadcrumbs(self, relative_path: str) -> list[dict[str, str]]:
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

    def validate_file_or_folder_name(self, name: str) -> str:
        safe_name = str(name or "").strip()

        if not safe_name:
            raise ValueError("File or folder name is required.")

        if safe_name in {".", ".."}:
            raise ValueError("Invalid file or folder name.")

        if "/" in safe_name or "\\" in safe_name:
            raise ValueError("File or folder name cannot contain path separators.")

        if "\x00" in safe_name:
            raise ValueError("File or folder name cannot contain null bytes.")

        if Path(safe_name).name != safe_name:
            raise ValueError("Invalid file or folder name.")

        return safe_name

    def is_path_inside_root(self, path: str | Path, root: str | Path) -> bool:
        root_path = Path(root).resolve()
        target_path = Path(path).resolve()

        return target_path == root_path or target_path.is_relative_to(root_path)

    def validation_error_response(
        self,
        req: Request,
        error: ValidationError,
        message: str,
    ) -> Response:
        return req.res.json(
            {
                "message": message,
                "status": "error",
                "details": error.errors(),
            }
        ).status(HttpStatus.UNPROCESSABLE_ENTITY)

    def error_response(
        self,
        req: Request,
        message: str,
        status: HttpStatus,
    ) -> Response:
        return req.res.json(
            {
                "message": message,
                "status": "error",
            }
        ).status(status)

    def download_items_response(
        self,
        req: Request,
        input_data: FilesDownloadInput,
    ) -> Response:
        if not input_data.files:
            return self.error_response(
                req,
                "No files or folders were selected for download.",
                HttpStatus.BAD_REQUEST,
            )

        selected_paths = [
            self.normalize_relative_path(path)
            for path in input_data.files
            if self.normalize_relative_path(path)
        ]

        if not selected_paths:
            return self.error_response(
                req,
                "No valid files or folders were selected for download.",
                HttpStatus.BAD_REQUEST,
            )

        resolved_paths: list[Path] = []

        for relative_path in selected_paths:
            target_path = self.resolve_inside_static_root(relative_path)

            if not target_path.exists():
                return self.error_response(
                    req,
                    f'File or folder "{relative_path}" does not exist.',
                    HttpStatus.NOT_FOUND,
                )

            if target_path == self.app_static_path.resolve():
                return self.error_response(
                    req,
                    "Downloading the static root folder is not allowed.",
                    HttpStatus.BAD_REQUEST,
                )

            resolved_paths.append(target_path)

        if len(resolved_paths) == 1 and resolved_paths[0].is_file():
            return self.file_download_response(req, resolved_paths[0])

        zip_path = self.create_download_zip(resolved_paths)

        return self.file_download_response(
            req,
            zip_path,
            download_name=zip_path.name,
            content_type="application/zip",
        )

    def file_download_response(
        self,
        req: Request,
        file_path: Path,
        download_name: str | None = None,
        content_type: str | None = None,
    ) -> Response:
        file_path = file_path.resolve()

        if not file_path.exists() or not file_path.is_file():
            raise ValueError("Download file does not exist.")

        if download_name is None:
            download_name = file_path.name

        if content_type is None:
            content_type = (
                mimetypes.guess_type(download_name)[0]
                or MediaType.APPLICATION_OCTET_STREAM.value
            )

        quoted_name = quote(download_name)

        return (
            req.res.status(HttpStatus.OK)
            .set_header("Content-Type", content_type)
            .set_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quoted_name}",
            )
            .set_header("Cache-Control", "no-store")
            .set_zero_copy(
                {
                    "file_path": str(file_path),
                    "start": 0,
                    "length": file_path.stat().st_size,
                }
            )
        )

    def create_download_zip(self, paths: list[Path]) -> Path:
        self.cleanup_old_download_archives()

        temp_dir = self.download_temp_dir
        temp_dir.mkdir(parents=True, exist_ok=True)

        zip_path = temp_dir / f"file-explorer-download-{uuid.uuid4().hex}.zip"

        with zipfile.ZipFile(
            zip_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as zip_file:
            used_archive_names: set[str] = set()

            for path in paths:
                self.add_path_to_zip(
                    zip_file=zip_file,
                    source_path=path,
                    used_archive_names=used_archive_names,
                )

        return zip_path

    def add_path_to_zip(
        self,
        zip_file: zipfile.ZipFile,
        source_path: Path,
        used_archive_names: set[str],
    ) -> None:
        static_root = self.app_static_path.resolve()
        source_path = source_path.resolve()

        if not self.is_path_inside_root(source_path, static_root):
            raise ValueError("Cannot add a path outside the static root folder to ZIP.")

        if source_path.is_file():
            archive_name = self.relative_to_static_root(source_path)
            archive_name = self.unique_zip_archive_name(
                archive_name, used_archive_names
            )
            zip_file.write(source_path, archive_name)
            return

        if not source_path.is_dir():
            return

        folder_archive_name = (
            self.relative_to_static_root(source_path).rstrip("/") + "/"
        )

        if folder_archive_name not in used_archive_names:
            zip_info = zipfile.ZipInfo(folder_archive_name)
            zip_file.writestr(zip_info, b"")
            used_archive_names.add(folder_archive_name)

        for child_path in source_path.rglob("*"):
            child_path = child_path.resolve()

            if not self.is_path_inside_root(child_path, static_root):
                continue

            archive_name = self.relative_to_static_root(child_path)

            if child_path.is_dir():
                archive_name = archive_name.rstrip("/") + "/"

                if archive_name in used_archive_names:
                    continue

                zip_info = zipfile.ZipInfo(archive_name)
                zip_file.writestr(zip_info, b"")
                used_archive_names.add(archive_name)
                continue

            archive_name = self.unique_zip_archive_name(
                archive_name, used_archive_names
            )
            zip_file.write(child_path, archive_name)

    def unique_zip_archive_name(
        self,
        archive_name: str,
        used_archive_names: set[str],
    ) -> str:
        if archive_name not in used_archive_names:
            used_archive_names.add(archive_name)
            return archive_name

        archive_path = Path(archive_name)
        parent = archive_path.parent.as_posix()

        if parent == ".":
            parent = ""

        stem = archive_path.stem
        suffix = archive_path.suffix

        counter = 2

        while True:
            candidate_name = f"{stem} ({counter}){suffix}"
            candidate = f"{parent}/{candidate_name}" if parent else candidate_name

            if candidate not in used_archive_names:
                used_archive_names.add(candidate)
                return candidate

            counter += 1

    def cleanup_old_download_archives(self, max_age_seconds: int = 1800) -> None:
        temp_dir = self.download_temp_dir

        if not temp_dir.exists():
            return

        now = time.time()

        for file_path in temp_dir.glob("file-explorer-download-*.zip"):
            try:
                if now - file_path.stat().st_mtime > max_age_seconds:
                    file_path.unlink(missing_ok=True)
            except Exception:
                continue

    @property
    def download_temp_dir(self) -> Path:
        return Path(tempfile.gettempdir()) / "patera-admin-file-downloads"

    @property
    def app_static_path(self) -> Path:
        return Path(self.app.static_files_path)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
