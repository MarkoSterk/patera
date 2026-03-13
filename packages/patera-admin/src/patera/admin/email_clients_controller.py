"""
Admin dashboard email clients controller.
Handles email client extension for sending emails.
"""

# pylint: disable=W0719,W0212
from __future__ import annotations
from typing import Optional, cast
from pydantic import BaseModel, ValidationError, EmailStr

from .common_controller import CommonAdminController
from patera.email import EmailClient
from patera.auth import login_required
from patera.controller import get, post
from patera import HttpStatus, Request, Response
from patera.utilities import base64_to_bytes, to_kebab_case


class EmailQueryParam(BaseModel):
    """Email validation"""

    client: str
    query: Optional[str] = None


class SendEmailModel(BaseModel):
    """Model for validating emails to be sent"""

    to_address: list[EmailStr]
    subject: str
    attachments: Optional[dict[str, str]] = None
    body: str


class AdminEmailClientsController(CommonAdminController):
    """Admin dashboard controller."""

    @get("/email-clients")
    @login_required
    async def email_clients(self, req: Request) -> Response:
        """Email clients page"""

        return await req.res.html(
            "/__admin_templates/email_clients.html",
            {
                "email_clients": self.dashboard.email_clients,
                **self.get_common_variables(),
            },
        )

    @get("/send-email")
    @login_required
    async def send_email(self, req: Request) -> Response:
        """
        Endpoint for sending emails
        """
        client_query = EmailQueryParam.model_validate(req.query_params)
        client = self.get_email_client(client_query.client)
        return await req.res.html(
            "/__admin_templates/send_email.html",
            {
                "client_name": to_kebab_case(client.configs_name),
                "client": client,
                **self.get_common_variables(),
            },
        )

    @get("/email-query")
    @login_required
    async def email_query(self, req: Request) -> Response:
        """Endpoint for email querying"""
        client_query = EmailQueryParam.model_validate(req.query_params)
        client = self.get_email_client(client_query.client)
        results: list[tuple[str, str]] = await self.dashboard.email_recipient_query(
            req, cast(str, client_query.query), client
        )
        return req.res.json(
            {"message": "Email query results", "status": "success", "data": results}
        ).status(HttpStatus.OK)

    @post("/email-submit")
    @login_required
    async def email_submit(self, req: Request) -> Response:
        """Sends the email"""
        try:
            client_query = EmailQueryParam.model_validate(req.query_params)
            client = self.get_email_client(client_query.client)
            json_data: dict = cast(dict, await req.json())
            message = SendEmailModel.model_validate(json_data)
            attachments: Optional[dict[str, bytes]] = None
            if message.attachments is not None:
                attachments = {}
                for key, value in message.attachments.items():
                    attachments[key] = base64_to_bytes(value)

            await client.send_email(
                to_address=message.to_address,
                subject=message.subject,
                body=message.body,
                attachments=attachments,
            )
            self.app.logger.info(
                f"Email sent with client {client.configs_name} to addresses: {message.to_address} with subject {message.subject}"
            )
            return req.res.json(
                {
                    "message": "Email sent successfully",
                    "status": "success",
                }
            ).status(HttpStatus.OK)
        except ValidationError as exc:
            details = {}
            if hasattr(exc, "errors"):
                for error in exc.errors():
                    details[error["loc"][0]] = error["msg"]
            return req.response.json(
                {"message": "Missing data.", "details": details}
            ).status(HttpStatus.UNPROCESSABLE_ENTITY)
        except Exception as exc:
            self.app.logger.debug(exc)
            return req.res.json(
                {
                    "message": "Something went wrong",
                    "status": "error",
                }
            ).status(HttpStatus.INTERNAL_SERVER_ERROR)

    def get_email_client(self, client_name: str) -> EmailClient:
        client = None
        if self.dashboard.email_clients is None:
            raise Exception("No registered email clients.")
        for name, email_client in self.dashboard.email_clients.items():
            if name == client_name:
                client = email_client
                break
        if client is None:
            raise Exception("Unknown email client.")
        return cast(EmailClient, client)
