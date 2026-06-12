from typing import cast, Optional, TYPE_CHECKING
from patera.controller import Controller, get, post, before_request, produces, consumes
from patera import Patera, Request, Response, HttpStatus, MediaType, UploadedFile
from patera.auth import role_required
from pydantic import BaseModel, EmailStr, ValidationError

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
    sender_email: EmailStr
    subject: str
    attachment: Optional[list[UploadedFile]] = None
    message: str


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
            "_admin/email_client.html", {**self.admin_interface.context_variables}
        )

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
            print(client)
            return req.res.json(
                {"message": "Email send successfully", "status": "success"}
            ).status(HttpStatus.OK)
        except ValidationError as e:
            return req.res.json(
                {
                    "message": "Failed to send email. Please check input data",
                    "status": "error",
                    "data": e.errors(),
                }
            ).status(HttpStatus.UNPROCESSABLE_ENTITY)
        except Exception as e:
            self.app.logger.exception(e)
            return req.res.json(
                {
                    "message": "Unexcpected error. Failed to send email.",
                    "status": "error",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    def get_email_client(self, email: str) -> "EmailClient":
        for client in self.admin_interface._email_services.values():
            if client.configs.SENDER_NAME_OR_ADDRESS == email:
                return client
        raise AdminUnknownEmailClientException(email)

    @property
    def admin_interface(self) -> AdminInterface:
        return self._admin_interface

    @admin_interface.setter
    def admin_interface(self, interface: AdminInterface) -> None:
        self._admin_interface = interface
