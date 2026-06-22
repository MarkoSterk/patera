from __future__ import annotations

import copy
from html import escape
from typing import Any, Mapping, Sequence

from markupsafe import Markup


AttributeValue = str | int | float | bool | None


class BaseHtmlElement:
    tag_name: str = ""

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: Sequence[str] | None = None,
        attributes: Mapping[str, AttributeValue] | None = None,
        data_attributes: Mapping[str, AttributeValue] | None = None,
        aria_attributes: Mapping[str, AttributeValue] | None = None,
        styles: Mapping[str, str] | None = None,
        content: str | Markup | None = None,
    ) -> None:
        self.id = id
        self.classes = list(classes or [])
        self.attributes = dict(attributes or {})
        self.data_attributes = dict(data_attributes or {})
        self.aria_attributes = dict(aria_attributes or {})
        self.styles = dict(styles or {})
        self.content = content

    def clone(self) -> "BaseHtmlElement":
        return copy.deepcopy(self)

    def render(self, field: dict[str, Any] | None = None) -> Markup:
        attrs = self.build_attributes(field)
        attrs_html = self.render_attributes(attrs)
        content = self.render_content()

        if attrs_html:
            return Markup(f"<{self.tag_name} {attrs_html}>{content}</{self.tag_name}>")

        return Markup(f"<{self.tag_name}>{content}</{self.tag_name}>")

    def build_attributes(
        self,
        field: dict[str, Any] | None = None,
    ) -> dict[str, AttributeValue]:
        attrs: dict[str, AttributeValue] = {}

        if self.id:
            attrs["id"] = self.id

        if self.classes:
            attrs["class"] = " ".join(self.classes)

        if self.styles:
            attrs["style"] = self.render_style_attribute(self.styles)

        attrs.update(self.attributes)

        for key, value in self.data_attributes.items():
            attrs[f"data-{self.normalize_attribute_name(key)}"] = value

        for key, value in self.aria_attributes.items():
            attrs[f"aria-{self.normalize_attribute_name(key)}"] = value

        return attrs

    def render_content(self) -> str:
        if self.content is None:
            return ""

        if isinstance(self.content, Markup):
            return str(self.content)

        return escape(str(self.content), quote=False)

    @staticmethod
    def render_attributes(attributes: Mapping[str, AttributeValue]) -> str:
        rendered: list[str] = []

        for name, value in attributes.items():
            if value is None or value is False:
                continue

            normalized_name = BaseHtmlElement.normalize_attribute_name(name)

            if value is True:
                rendered.append(normalized_name)
                continue

            rendered.append(f'{normalized_name}="{escape(str(value), quote=True)}"')

        return " ".join(rendered)

    @staticmethod
    def render_style_attribute(styles: Mapping[str, str]) -> str:
        return "; ".join(
            f"{property_name.replace('_', '-')}: {value}"
            for property_name, value in styles.items()
        )

    @staticmethod
    def normalize_attribute_name(name: str) -> str:
        return str(name).replace("_", "-")


class BaseHtmlInput(BaseHtmlElement):
    def __init__(
        self,
        *,
        name: str,
        id: str | None = None,
        label: str | None = None,
        value: Any | None = None,
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
            id=id,
            classes=classes,
            attributes=attributes,
            data_attributes=data_attributes,
            aria_attributes=aria_attributes,
            styles=styles,
        )
        self.name = name
        self.label = label
        self.value = value
        self.required = required
        self.disabled = disabled
        self.readonly = readonly
        self.placeholder = placeholder

    def build_attributes(
        self,
        field: dict[str, Any] | None = None,
    ) -> dict[str, AttributeValue]:
        attrs = super().build_attributes(field)

        field_name = field.get("name") if field else self.name
        field_label = field.get("label") if field else self.label
        field_required = field.get("required") if field else self.required

        attrs["name"] = self.name or field_name
        attrs["id"] = self.id or f"create-field-{field_name}"

        if field_name:
            attrs["data-field-name"] = field_name

        if self.value is not None:
            attrs["value"] = self.serialize_value(self.value)

        if field_required:
            attrs["required"] = True

        if self.disabled:
            attrs["disabled"] = True

        if self.readonly:
            attrs["readonly"] = True

        if self.placeholder is not None:
            attrs["placeholder"] = self.placeholder

        if field_label:
            attrs["aria-label"] = field_label

        return attrs

    def serialize_value(self, value: Any) -> str:
        return str(value)
