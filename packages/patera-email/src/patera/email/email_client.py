"""
Email client extension
"""

import aiosmtplib as smtplib
from email.message import EmailMessage
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    TypeVar,
    cast,
)
from pydantic import BaseModel, Field

from patera.base_extension import BaseExtension
from patera.utilities import run_sync_or_async

if TYPE_CHECKING:
    from patera import Patera


class EmailConfig(BaseModel):
    """
    Email client configuration model
    """

    SENDER_NAME_OR_ADDRESS: str = Field(
        description="The name or address of the email sender"
    )
    SMTP_SERVER: str = Field(description="SMTP server address")
    SMTP_PORT: int = Field(description="SMTP server port")
    USERNAME: Optional[str] = Field(None, description="SMTP username")
    PASSWORD: Optional[str] = Field(None, description="SMTP password")
    USE_TLS: bool = Field(False, description="Use TLS for SMTP connection")


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class EmailClient(BaseExtension[AppT, EmailConfig], Generic[AppT]):
    """
    Email client extension class
    """

    def init(self) -> None:
        """Initilizes the extension with the Patera app"""
        self.configs
        self.render_engine = self._app.jinja_environment

    def get_client(self) -> smtplib.SMTP:
        """Returns the email client instance"""
        return smtplib.SMTP(
            hostname=cast(str, self.configs.SMTP_SERVER),
            port=cast(int, self.configs.SMTP_PORT),
            start_tls=False,
        )

    async def send_email_with_template(
        self,
        to_address: str | list[str],
        subject: str,
        template_path: str,
        attachments: Optional[dict[str, bytes]] = None,
        context: Optional[dict] = None,
    ) -> None:
        """Sends an email using a template and context data"""

        if context is None:
            context = {}

        for method in self.app.global_context_methods:
            additional_context = await run_sync_or_async(method)
            if not isinstance(additional_context, dict):
                raise ValueError(
                    "Return of global context method must be off type dictionary"
                )
            context = {**context, **additional_context}
        context["url_for"] = self.app.url_for

        template = self.render_engine.get_template(template_path)
        rendered = await template.render_async(**context)
        await self.send_email(to_address, subject, rendered, attachments)

    async def send_email(
        self,
        to_address: str | list[str],
        subject: str,
        body: str,
        attachments: Optional[dict[str, bytes]] = None,
    ) -> None:
        """
        Sends an email with attachments using the SMTP client

        :param to_address: Recipient email address or comma separated list of addresses
        :param subject: Email subject
        :param body: Email body
        :param attachments: Dictionary of attachment filenames and their byte content
        """
        if isinstance(to_address, str):
            to_address = [to_address]

        msg: EmailMessage = EmailMessage()
        msg["From"] = cast(str, self.configs.SENDER_NAME_OR_ADDRESS)
        msg["To"] = ", ".join(to_address)
        msg["Subject"] = subject
        msg.set_content(body)

        if attachments:
            for filename, filecontent in attachments.items():
                msg.add_attachment(
                    filecontent,
                    maintype="application",
                    subtype="octet-stream",
                    filename=filename,
                )

        async with self.get_client() as client:
            if cast(bool, self.configs.USE_TLS):
                await client.starttls()
            if self.configs.USERNAME is not None and self.configs.PASSWORD is not None:
                await client.login(
                    cast(str, self.configs.USERNAME),
                    cast(str, self.configs.PASSWORD),
                )
            await client.send_message(msg)
