"""
Email client extension
"""

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import PurePosixPath

import aiosmtplib as smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr
from typing import (
    ClassVar,
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    TypeVar,
    cast,
)
from pydantic import BaseModel, Field, model_validator

from patera import Request
from patera.base_extension import BaseExtension

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
    USE_TLS: bool = Field(
        False,
        description=(
            "Upgrade a plain connection with STARTTLS before logging in "
            "(usually port 587)."
        ),
    )
    USE_SSL: bool = Field(
        False,
        description=(
            "Use implicit TLS: the connection is encrypted from the first "
            "byte (usually port 465). Cannot be combined with USE_TLS."
        ),
    )

    @model_validator(mode="after")
    def _one_tls_mode(self) -> "EmailConfig":
        if self.USE_TLS and self.USE_SSL:
            raise ValueError(
                "USE_TLS (STARTTLS) and USE_SSL (implicit TLS) are mutually "
                "exclusive; enable only one."
            )
        return self


HTML_TEMPLATE_SUFFIXES: tuple[str, ...] = (".html", ".htm", ".xhtml")


class _HtmlToText(HTMLParser):
    """Converts an HTML email to a readable plain-text alternative."""

    _BLOCKS: ClassVar[set[str]] = {
        "p",
        "div",
        "br",
        "tr",
        "li",
        "ul",
        "ol",
        "table",
        "section",
        "article",
        "header",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "hr",
    }
    _SKIP: ClassVar[set[str]] = {"script", "style", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._links: list[Optional[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCKS:
            self._parts.append("\n")
        if tag == "li":
            self._parts.append("- ")
        if tag == "a":
            self._links.append(dict(attrs).get("href"))

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP:
            self._skip_depth = max(self._skip_depth - 1, 0)
        elif tag in self._BLOCKS and tag not in ("li", "br"):
            self._parts.append("\n")
        if tag == "a" and self._links:
            href = self._links.pop()
            if href and not href.startswith(("#", "javascript:")):
                self._parts.append(f" ({href})")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._parts.append(re.sub(r"\s+", " ", data))

    def text(self) -> str:
        lines = [line.strip() for line in "".join(self._parts).split("\n")]
        text = "\n".join(lines)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(html: str) -> str:
    """Returns a plain-text rendering of an HTML email body."""
    parser = _HtmlToText()
    parser.feed(html)
    parser.close()
    return unescape(parser.text())


AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


class EmailClient(BaseExtension[AppT, EmailConfig], Generic[AppT]):
    """
    Email client extension class
    """

    def init(self) -> None:
        """Initializes the extension with the Patera app"""
        # Reading the settings validates them, so a missing SMTP value fails
        # when the application starts instead of at the first e-mail.
        _ = self.configs
        self.render_engine = self._app.jinja_environment

    def get_client(self) -> smtplib.SMTP:
        """
        Returns a new SMTP client. With USE_SSL the connection uses implicit
        TLS; STARTTLS (USE_TLS) is issued explicitly in send_email.
        """
        return smtplib.SMTP(
            hostname=cast(str, self.configs.SMTP_SERVER),
            port=cast(int, self.configs.SMTP_PORT),
            use_tls=bool(self.configs.USE_SSL),
            start_tls=False,
        )

    async def send_email_with_template(
        self,
        to_address: str | list[str],
        subject: str,
        template_path: str,
        attachments: Optional[dict[str, bytes]] = None,
        context: Optional[dict] = None,
        text_template_path: Optional[str] = None,
        is_html: Optional[bool] = None,
    ) -> None:
        """
        Renders a template and sends it.

        A template ending in .html, .htm or .xhtml (or any template with
        ``is_html=True``) is sent as HTML with a plain-text alternative. The
        alternative is rendered from ``text_template_path`` when given and
        otherwise derived from the HTML. Other templates are sent as plain
        text.
        """
        context = dict(context or {})
        context["url_for"] = self.app.url_for

        rendered = await self._render(template_path, context)
        if is_html is None:
            is_html = PurePosixPath(template_path).suffix.lower() in (
                HTML_TEMPLATE_SUFFIXES
            )

        if not is_html:
            await self.send_email(to_address, subject, rendered, attachments)
            return

        text = (
            await self._render(text_template_path, context)
            if text_template_path
            else html_to_text(rendered)
        )
        await self.send_email(to_address, subject, text, attachments, html=rendered)

    async def _render(self, template_path: str, context: dict) -> str:
        template = self.render_engine.get_template(template_path)
        return await template.render_async(**context)

    async def send_email(
        self,
        to_address: str | list[str],
        subject: str,
        body: str,
        attachments: Optional[dict[str, bytes]] = None,
        html: Optional[str] = None,
    ) -> None:
        """
        Sends an email with attachments using the SMTP client

        :param to_address: Recipient email address or list of addresses
        :param subject: Email subject
        :param body: Plain-text body
        :param attachments: Dictionary of attachment filenames and their byte content
        :param html: Optional HTML body. When given, the message is
            multipart/alternative with ``body`` as the plain-text part.
        """
        if isinstance(to_address, str):
            to_address = [to_address]

        sender = cast(str, self.configs.SENDER_NAME_OR_ADDRESS)
        msg: EmailMessage = EmailMessage()
        msg["From"] = sender
        msg["To"] = ", ".join(to_address)
        msg["Subject"] = subject
        # RFC 5322 requires Date; spam filters penalize a missing Message-ID.
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain=self._message_id_domain(sender))
        msg.set_content(body)
        if html is not None:
            msg.add_alternative(html, subtype="html")

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

    def _message_id_domain(self, sender: str) -> Optional[str]:
        """Domain for Message-ID: the sender's, else the SMTP server's."""
        _, address = parseaddr(sender)
        if "@" in address:
            return address.rsplit("@", 1)[1]
        server = str(self.configs.SMTP_SERVER or "")
        return server or None

    async def query_email_addresses(self, req: Request, query: str) -> dict[str, str]:
        """Query method for admin interface to query for available recipient email addresses"""
        raise NotImplementedError()
