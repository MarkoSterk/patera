from html import escape
from typing import ClassVar, Any, Mapping, Sequence

from markupsafe import Markup

from .base_elements import BaseHtmlInput, AttributeValue


class TagsInput(BaseHtmlInput):
    tag_name = "tags-input"


class PasswordInput(BaseHtmlInput):
    """Masked input, never prefilled. Hash submitted passwords in an admin hook."""

    tag_name = "input"
    void_element = True

    def __init__(
        self, *, name: str, autocomplete: str = "new-password", **kwargs: Any
    ) -> None:
        kwargs.setdefault("classes", ["form-control"])
        super().__init__(name=name, **kwargs)
        self.autocomplete = autocomplete

    def build_attributes(
        self, field: dict[str, Any] | None = None
    ) -> dict[str, AttributeValue]:
        attrs = super().build_attributes(field)
        attrs.pop("value", None)
        attrs["type"] = "password"
        attrs["autocomplete"] = self.autocomplete
        return attrs


class SelectInput(BaseHtmlInput):
    """Single selection with (value, label) options declared in model metadata.

    Options can be a mapping or a sequence of pairs. Validate allowed values
    in the model's schema or admin hook; the choices only constrain the UI.
    """

    tag_name = "select"
    converts_value = True

    def __init__(
        self,
        *,
        name: str,
        options: Mapping[str | int, str] | Sequence[tuple[str | int, str]],
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault("classes", ["form-select"])
        super().__init__(name=name, **kwargs)
        self.options = list(
            options.items() if isinstance(options, Mapping) else options
        )

    def render(self, field: dict[str, Any] | None = None) -> Markup:
        attrs = self.build_attributes(field)
        value = attrs.pop("value", None)
        options = []
        for option_value, label in self.options:
            option_attrs = self.render_attributes(
                {
                    "value": str(option_value),
                    "selected": value is not None and str(option_value) == str(value),
                }
            )
            options.append(
                f"<option {option_attrs}>{escape(str(label), quote=False)}</option>"
            )
        return Markup(
            f"<select {self.render_attributes(attrs)}>{''.join(options)}</select>"
        )


class SummernoteEditor(BaseHtmlInput):
    """
    Python wrapper for the <summernote-editor> custom element.

    Default features:
        - headings
        - font
        - alignment

    If upload_url is provided, the image feature is added automatically.
    """

    tag_name = "summernote-editor"

    DEFAULT_FEATURES: ClassVar[list[str]] = [
        "headings",
        "font",
        "alignment",
    ]

    def __init__(
        self,
        *,
        name: str,
        id: str | None = None,
        label: str | None = None,
        value: str | Markup | None = None,
        upload_url: str | None = None,
        features: Sequence[str] | None = None,
        height: int | None = None,
        required: bool | None = None,
        disabled: bool = False,
        readonly: bool = False,
        placeholder: str | None = None,
        classes: Sequence[str] | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        data_attributes: Mapping[str, AttributeValue] | None = None,
        aria_attributes: Mapping[str, AttributeValue] | None = None,
        styles: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            label=label,
            value=value,
            required=required,
            disabled=disabled,
            readonly=readonly,
            placeholder=placeholder,
            classes=classes,
            attributes=attributes,
            data_attributes=data_attributes,
            aria_attributes=aria_attributes,
            styles=styles,
        )

        self.upload_url = upload_url
        self.features = list(features) if features is not None else None
        self.height = height

    def build_attributes(
        self,
        field: dict[str, Any] | None = None,
    ) -> dict[str, AttributeValue]:
        attrs = super().build_attributes(field)

        if self.upload_url:
            attrs["upload-url"] = self.upload_url

        features = self.get_features()

        if features:
            attrs["features"] = ",".join(features)

        if self.height is not None:
            attrs["height"] = self.height

        return attrs

    def get_features(self) -> list[str]:
        if self.features is not None:
            features = list(self.features)
        else:
            features = list(self.DEFAULT_FEATURES)

        if self.upload_url and "image" not in features:
            features.append("image")

        return features

    def serialize_value(self, value: Any) -> str:
        if value is None:
            return ""

        if isinstance(value, Markup):
            return str(value)

        return str(value)


class FileInput(BaseHtmlInput):
    """
    A file upload, ``<input type="file">``. The model's admin hooks receive
    the chosen file as a ``patera.UploadedFile`` and decide what to store.
    When no file is chosen the field is left out of the submitted form, so
    an update keeps the record's current value.

    ``accept`` limits the file chooser (MIME types or extensions) and
    ``max_size`` (bytes) is checked in the browser before the form is sent;
    the model must still validate what it receives.
    """

    tag_name = "input"
    void_element = True

    def __init__(
        self,
        *,
        name: str,
        accept: Sequence[str] | str | None = None,
        max_size: int | None = None,
        id: str | None = None,
        label: str | None = None,
        required: bool | None = None,
        disabled: bool = False,
        classes: Sequence[str] | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        data_attributes: Mapping[str, AttributeValue] | None = None,
        aria_attributes: Mapping[str, AttributeValue] | None = None,
        styles: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            label=label,
            required=required,
            disabled=disabled,
            classes=classes if classes is not None else ["form-control"],
            attributes=attributes,
            data_attributes=data_attributes,
            aria_attributes=aria_attributes,
            styles=styles,
        )
        self.accept = (
            accept if isinstance(accept, str) or accept is None else ",".join(accept)
        )
        self.max_size = max_size

    def build_attributes(
        self,
        field: dict[str, Any] | None = None,
    ) -> dict[str, AttributeValue]:
        attrs = super().build_attributes(field)
        attrs["type"] = "file"
        if self.accept:
            attrs["accept"] = self.accept
        if self.max_size is not None:
            attrs["data-max-size"] = self.max_size
        return attrs


class DateInput(BaseHtmlInput):
    """
    A date picker, ``<input type="date">``, or a date and time picker,
    ``<input type="datetime-local">``, with ``include_time=True``.

    The submitted text is converted to the column's type like a generated
    input, so it suits ``Date``, ``DateTime`` and string columns. With
    ``utc=True`` (date and time only) the browser shows a stored ISO 8601
    timestamp in the viewer's local time and submits it back in UTC, for
    example ``2026-10-20T08:00:00.000Z``.
    """

    tag_name = "input"
    void_element = True
    converts_value = True

    def __init__(
        self,
        *,
        name: str,
        include_time: bool = False,
        utc: bool = False,
        min: str | None = None,
        max: str | None = None,
        id: str | None = None,
        label: str | None = None,
        required: bool | None = None,
        disabled: bool = False,
        readonly: bool = False,
        classes: Sequence[str] | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        data_attributes: Mapping[str, AttributeValue] | None = None,
        aria_attributes: Mapping[str, AttributeValue] | None = None,
        styles: Mapping[str, str] | None = None,
    ) -> None:
        if utc and not include_time:
            raise ValueError(
                "utc=True needs include_time=True: a date has no time zone."
            )
        super().__init__(
            name=name,
            id=id,
            label=label,
            required=required,
            disabled=disabled,
            readonly=readonly,
            classes=classes if classes is not None else ["form-control"],
            attributes=attributes,
            data_attributes=data_attributes,
            aria_attributes=aria_attributes,
            styles=styles,
        )
        self.include_time = include_time
        self.utc = utc
        self.min = min
        self.max = max

    def build_attributes(
        self,
        field: dict[str, Any] | None = None,
    ) -> dict[str, AttributeValue]:
        attrs = super().build_attributes(field)
        attrs["type"] = "datetime-local" if self.include_time else "date"
        if self.utc:
            attrs["data-utc"] = "true"
        if self.min is not None:
            attrs["min"] = self.min
        if self.max is not None:
            attrs["max"] = self.max
        return attrs


class LatexInput(BaseHtmlInput):
    """
    A textarea, or a text input with ``multiline=False``, for text with LaTeX
    math, with a preview underneath that updates while the user types.

    Math goes between ``$...$`` (inline) or ``$$...$$`` (on a line of its
    own), and ``\\$`` is a literal dollar sign. The preview is rendered as
    MathML by Temml, which Admin serves from its own static assets and loads
    only on pages with this input. The submitted value is the text as typed,
    converted to the column's type like a generated input.
    """

    tag_name = "latex-input"
    converts_value = True

    CONTROL_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "name",
        "id",
        "value",
        "required",
        "disabled",
        "readonly",
        "placeholder",
        "aria-label",
    )

    def __init__(
        self,
        *,
        name: str,
        multiline: bool = True,
        rows: int = 4,
        maxlength: int | None = None,
        preview_label: str = "Preview",
        id: str | None = None,
        label: str | None = None,
        value: str | None = None,
        required: bool | None = None,
        disabled: bool = False,
        readonly: bool = False,
        placeholder: str | None = None,
        classes: Sequence[str] | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        data_attributes: Mapping[str, AttributeValue] | None = None,
        aria_attributes: Mapping[str, AttributeValue] | None = None,
        styles: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            id=id,
            label=label,
            value=value,
            required=required,
            disabled=disabled,
            readonly=readonly,
            placeholder=placeholder,
            classes=classes,
            attributes=attributes,
            data_attributes=data_attributes,
            aria_attributes=aria_attributes,
            styles=styles,
        )
        self.multiline = multiline
        self.rows = rows
        self.maxlength = maxlength
        self.preview_label = preview_label

    def render(self, field: dict[str, Any] | None = None) -> Markup:
        attrs = self.build_attributes(field)
        control = {
            key: attrs.pop(key) for key in self.CONTROL_ATTRIBUTES if key in attrs
        }
        control["class"] = "form-control"
        if self.maxlength is not None:
            control["maxlength"] = self.maxlength
        value = control.pop("value", None)

        if self.multiline:
            control["rows"] = self.rows
            text = escape(str(value or ""), quote=False)
            control_html = (
                f"<textarea {self.render_attributes(control)}>\n{text}</textarea>"
            )
        else:
            control["type"] = "text"
            control["value"] = value
            control_html = f"<input {self.render_attributes(control)}>"

        preview = self.render_attributes(
            {
                "class": "latex-input-preview form-control bg-body-tertiary mt-1",
                "data-preview": True,
                "aria-live": "polite",
                "aria-label": self.preview_label,
                "hidden": True,
            }
        )
        return Markup(
            f"<{self.tag_name} {self.render_attributes(attrs)}>"
            f"{control_html}<div {preview}></div>"
            f"</{self.tag_name}>"
        )
