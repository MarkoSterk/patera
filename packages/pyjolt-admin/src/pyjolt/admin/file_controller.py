"""
File controller for pyjolt admin dashboard
"""

import os
import io
import zipfile
import uuid
from typing import Any, Optional
import mimetypes
from pathlib import Path
import shutil
from ..http_statuses import HttpStatus
from ..controller import get, post, delete
from .common_controller import CommonAdminController
from ..auth import login_required
from ..request import Request
from ..response import Response
from ..utilities import get_file, fs_safe_join


class AdminFileController(CommonAdminController):
    @get("/files")
    @login_required
    async def file_explorer(self, req: Request) -> Response:
        """
        File explorer page
        """
        await self.can_enter(req)
        if not await self.dashboard.has_files_permission(req):
            return await self.missing_files_permission(req)
        return await req.res.html(
            "/__admin_templates/file_explorer.html",
            {
                "folder": self.app.get_conf("STATIC_DIR"),
                "files_and_folders": await self.get_files_and_folder(None),
                **self.get_common_variables(),
            },
        )

    @get("/files/fetch")
    @login_required
    async def get_all(self, req: Request) -> Response:
        """
        Returns all files
        """
        folder_path: Optional[str] = req.query_params.get("path", None)
        return req.res.json(
            {
                "message": "Files fetched successfully",
                "status": "success",
                "data": await self.get_files_and_folder(folder_path),
            }
        ).status(HttpStatus.OK)

    @post("/files/fetch/zip")
    @login_required
    async def download_zip(self, req: Request) -> Response:
        """Downloads multiple files as zip"""
        await self.can_enter(req)
        if not await self.dashboard.has_files_permission(req):
            return await self.missing_files_permission(req)
        req_items: Optional[dict[str, Any]] = await req.get_data()
        if req_items is None:
            return req.res.json(
                {
                    "message": "Please provide a valid list of files for download",
                    "status": "error",
                }
            ).status(HttpStatus.BAD_REQUEST)
        allowed_base = Path(self.app.root_path).resolve()

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, rel_path in req_items.items():
                try:
                    target_path = fs_safe_join(
                        allowed_base, rel_path.lstrip("/\\"), name
                    )
                    if target_path is None:
                        raise FileNotFoundError()
                    target = Path(target_path).resolve()
                    if target.is_dir():
                        top = Path(name).name
                        zf.writestr(f"{top}/", b"")
                        for p in target.rglob("*"):
                            if p.is_dir():
                                continue
                            rel_inside = p.relative_to(target)
                            arcname = (Path(top) / rel_inside).as_posix()
                            zf.write(p, arcname=arcname)
                    elif target.is_file():
                        arcname = Path(name).name
                        zf.write(target, arcname=arcname)
                    else:
                        raise FileNotFoundError()
                except FileNotFoundError:
                    self.app.logger.info(
                        f"Requested item not found: {name=} {rel_path=}"
                    )
                    return req.res.json(
                        {
                            "message": f"Requested item '{name=}' does not exist.",
                            "status": "danger",
                        }
                    ).status(HttpStatus.NOT_FOUND)
        zip_buffer.seek(0)
        return req.res.send_file(
            zip_buffer.read(),
            {
                "Content-Type": "application/zip",
                "Content-Disposition": f"attachment; filename={uuid.uuid4().hex}.zip",
            },
        )

    @get("/files/fetch/one")
    @login_required
    async def get_file(self, req: Request) -> Response:
        """
        Returns selected file
        """
        file_path: Optional[str] = req.query_params.get("path", None)
        if file_path is None:
            return req.res.json(
                {"message": "Please provide a valid file path", "status": "warning"}
            ).status(HttpStatus.BAD_REQUEST)
        full_path = os.path.join(self.app.root_path, file_path.lstrip("/\\"))
        if not os.path.isfile(full_path):
            return req.res.json(
                {"message": "File does not exist", "status": "danger"}
            ).status(HttpStatus.BAD_REQUEST)
        guessed, _ = mimetypes.guess_type(full_path)
        content_type = guessed or "application/octet-stream"
        status, headers, body = await get_file(full_path, content_type=content_type)
        headers["Accept-Ranges"] = "bytes"
        return req.res.send_file(body, headers).status(status)

    @get("/files/rename")
    @login_required
    async def rename(self, req: Request) -> Response:
        """
        Renames file or folder
        """
        await self.can_enter(req)
        if not await self.dashboard.has_files_permission(req):
            return await self.missing_files_permission(req)
        data: dict[str, str] = {}
        for param in ["path", "oldName", "newName"]:
            param_data: Optional[str] = req.query_params.get(param, None)
            if param_data is None:
                return req.res.json(
                    {"message": f"Missing parameter '{param}'", "status": "warning"}
                ).status(HttpStatus.BAD_REQUEST)
            data[param] = param_data

        data["path"] = os.path.join(self.app.root_path, data["path"].lstrip("/\\"))
        old_path = os.path.join(data["path"], data["oldName"])
        new_path = os.path.join(data["path"], data["newName"])
        try:
            os.rename(old_path, new_path)
        except Exception:
            return req.res.json(
                {
                    "message": f"Failed to change file name {data['oldName']}",
                    "status": "danger",
                }
            ).status(HttpStatus.BAD_REQUEST)

        return req.res.json(
            {
                "message": "File or folder renamed successfully",
                "status": "success",
                "data": {
                    "old_path": old_path,
                    "new_path": new_path,
                    "new_name": data["newName"],
                    "old_name": data["oldName"],
                },
            }
        ).status(HttpStatus.OK)

    @post("/files/upload")
    @login_required
    async def upload(self, req: Request) -> Response:
        """
        Uploads single file
        """
        await self.can_enter(req)
        if not await self.dashboard.has_files_permission(req):
            return await self.missing_files_permission(req)
        data: dict[str, Any] = await req.form_and_files()
        full_path = os.path.join(self.app.root_path, data["path"].lstrip("/\\"))
        file_path = Path(full_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(data["file"].read())
        return req.res.json(
            {
                "message": "File uploaded successfully",
                "status": "success",
                "data": {
                    "path": data["path"],
                    "name": data["file"].filename,
                    "is_folder": False,
                },
            }
        ).status(HttpStatus.CREATED)

    @delete("/files")
    @login_required
    async def delete(self, req: Request) -> Response:
        """
        Delete a file or folder
        """
        await self.can_enter(req)
        if not await self.dashboard.has_files_permission(req):
            return await self.missing_files_permission(req)
        path: Optional[str] = req.query_params.get("path", None)
        full_path = os.path.join(
            self.app.root_path, path.lstrip("/\\") if path is not None else ""
        )
        if path is None or (
            not os.path.isfile(full_path) and not os.path.isdir(full_path)
        ):
            return req.res.json(
                {
                    "message": "Please provide a valid file or folder path",
                    "status": "danger",
                }
            ).status(HttpStatus.BAD_REQUEST)

        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)

        return req.res.no_content()

    async def get_files_and_folder(
        self, path: Optional[str]
    ) -> list[dict[str, str | bool | None]]:
        """Returns all files and folders at the provided path"""
        if path is None:
            path = self.app.static_files_path
        else:
            if path.startswith("/static"):
                path = path.replace("/static", "")
            elif path.startswith("static"):
                path = path.replace("static", "")
            path = os.path.join(self.app.static_files_path, *path.split("/"))
        items = os.listdir(path)
        files_and_folders = []
        for name in items:
            full = os.path.join(path, name)
            guessed, _ = mimetypes.guess_type(full)
            files_and_folders.append(
                {
                    "path": path.replace(self.app.root_path, ""),
                    "name": name,
                    "is_folder": True if os.path.isdir(full) else False,
                    "mimetype": guessed,
                }
            )

        return files_and_folders

    async def missing_files_permission(self, req: Request) -> Response:
        """Returns missing files permission"""
        return await req.res.html("/__admin_templates/missing_permission.html")
