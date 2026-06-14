from typing import cast, Optional, TYPE_CHECKING, Any
from patera.controller import Controller, get, post, before_request, produces, consumes
from patera import Patera, Request, Response, HttpStatus, MediaType, UploadedFile
from patera.utilities import run_in_background
from patera.auth import role_required
from pydantic import BaseModel, ValidationError, field_validator

from .exceptions import (
    AdminUnsupportedLanguage,
    AdminAuthorizationRequiredException,
    AdminLoginRequiredException,
    AdminUnknownEmailClientException,
)
from .admin_interface import AdminInterface, Permissions

if TYPE_CHECKING:
    from patera.email import EmailClient


class SendEmailInput(BaseModel):
    sender_email: str
    recipients: list[str]
    subject: str
    attachment: Optional[list[UploadedFile]] = None
    message: str

    @field_validator("recipients", mode="before")
    @classmethod
    def recipients_to_list(cls, value: Any) -> list[Any]:
        if value is None:
            return []

        if isinstance(value, list):
            return value

        if isinstance(value, str):
            return [
                recipient.strip()
                for recipient in value.replace(";", ",").split(",")
                if recipient.strip()
            ]

        return [value]

    @field_validator("attachment", mode="before")
    @classmethod
    def attachment_to_list(cls, value: Any) -> Optional[list[Any]]:
        if value is None:
            return None

        if isinstance(value, list):
            return value

        return [value]


class _AdminEmailClientController(Controller[Patera]):
    def __init__(self, *args, **kwargs):
        self._admin_interface: AdminInterface = cast(AdminInterface, None)
        super().__init__(*args, **kwargs)

    @before_request
    async def check_language(self, req: Request):
        lang = cast(str, req.route_parameters.get("lang"))
        if lang not in self.admin_interface.supported_languages:
            raise AdminUnsupportedLanguage(lang)

    @get("/")
    @produces(MediaType.TEXT_HTML)
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        Permissions.ADMIN_CAN_VIEW,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def email_client(self, req: Request) -> Response:
        return await req.res.html(
            "_admin/email_clients/email_client.html",
            {**self.admin_interface.context_variables, "clients": self.all_clients},
        )

    @post("/recipients")
    @consumes(MediaType.APPLICATION_JSON)
    @produces(MediaType.APPLICATION_JSON)
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        Permissions.ADMIN_CAN_VIEW,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def email_query_recipients(self, req: Request) -> Response:
        payload = await req.json()
        if payload is None:
            return req.res.json(
                {"message": "Missing client or query.", "status": "error"}
            ).status(HttpStatus.BAD_REQUEST)
        client = payload.get("client", None)
        if client is None:
            return req.res.json(
                {"message": "Missing client for recipient querying", "status": "error"}
            ).status(HttpStatus.BAD_REQUEST)
        query = payload.get("query", "")
        email_client = self.get_email_client(client)
        try:
            results = await email_client.query_email_addresses(req, query) or []
            return req.res.json(
                {"message": "Query successful", "status": "success", "data": results}
            ).status(HttpStatus.OK)
        except NotImplementedError as e:
            self.app.logger.exception(e)
            return req.res.json(
                {
                    "message": "Recipient query for selected email client is not implemented.",
                    "status": "error",
                }
            ).status(HttpStatus.NOT_IMPLEMENTED)

    @post("/")
    @consumes(MediaType.MULTIPART_FORM_DATA)
    @produces(MediaType.APPLICATION_JSON)
    @role_required(
        Permissions.ADMIN_CAN_ENTER,
        Permissions.ADMIN_CAN_CREATE,
        raise_authentication_exception=AdminLoginRequiredException,
        raise_authorization_exception=AdminAuthorizationRequiredException,
    )
    async def send_email(self, req: Request) -> Response:
        try:
            form_and_files: dict = await req.form_and_files()

            data: SendEmailInput = SendEmailInput.model_validate(form_and_files)

            client: "EmailClient" = self.get_email_client(data.sender_email)

            attachments = self.prepare_email_attachments(data.attachment)

            run_in_background(
                client.send_email,
                to_address=data.recipients,
                subject=data.subject,
                body=data.message,
                attachments=attachments,
            )

            return req.res.json(
                {
                    "message": "Email sent successfully",
                    "status": "success",
                }
            ).status(HttpStatus.OK)

        except ValidationError as e:
            return req.res.json(
                {
                    "message": "Failed to send email. Please check input data",
                    "status": "error",
                    "data": e.errors(include_input=False),
                }
            ).status(HttpStatus.UNPROCESSABLE_ENTITY)

        except Exception as e:
            self.app.logger.exception(e)
            return req.res.json(
                {
                    "message": "Unexpected error. Failed to send email.",
                    "status": "error",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    def get_email_client(self, email: str) -> "EmailClient":
        for client in self.admin_interface._email_services.values():
            if client.configs.SENDER_NAME_OR_ADDRESS == email:
                return client
        raise AdminUnknownEmailClientException(email)

    def prepare_email_attachments(
        self,
        attachments: Optional[list[UploadedFile]],
    ) -> Optional[dict[str, bytes]]:
        """
        Converts UploadedFile objects into the attachment format expected by EmailClient.

        EmailClient.send_email expects:
            {
                "filename.ext": b"..."
            }
        """
        if not attachments:
            return None

        prepared: dict[str, bytes] = {}

        for attachment in attachments:
            filename = attachment.filename or "attachment"

            if filename in prepared:
                filename = self.get_unique_attachment_filename(filename, prepared)

            prepared[filename] = attachment.read()

        return prepared

    def get_unique_attachment_filename(
        self,
        filename: str,
        existing_attachments: dict[str, bytes],
    ) -> str:
        """
        Ensures that duplicate attachment filenames do not overwrite each other.
        """
        if filename not in existing_attachments:
            return filename

        if "." in filename:
            stem, extension = filename.rsplit(".", 1)
            extension = f".{extension}"
        else:
            stem = filename
            extension = ""

        counter = 2
        unique_filename = f"{stem}_{counter}{extension}"

        while unique_filename in existing_attachments:
            counter += 1
            unique_filename = f"{stem}_{counter}{extension}"

        return unique_filename

    @property
    def all_clients(self) -> list["EmailClient"]:
        return [client for client in self.admin_interface._email_services.values()]

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
