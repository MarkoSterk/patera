from typing import Sequence, Any, Mapping
from markupsafe import Markup

from .base_elements import BaseHtmlInput, AttributeValue


class TagsInput(BaseHtmlInput):
    tag_name = "tags-input"


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

    DEFAULT_FEATURES: list[str] = [
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
