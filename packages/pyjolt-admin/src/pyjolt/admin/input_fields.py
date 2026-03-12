"""
WTForm inputs
"""

from __future__ import annotations
from enum import StrEnum
from typing import cast
from abc import ABC, abstractmethod
from markupsafe import Markup
from wtforms.widgets import html_params

from pyjolt.utilities import to_kebab_case


class FormFieldTypes(StrEnum):
    TAGS = "TagsField"
    PASSWORD = "PasswordField"
    EMAIL = "EmailField"
    TEXT = "TextField"
    TEXTAREA = "TextAreaField"
    SELECT = "SelectField"
    RADIO = "RedioField"
    CHECKBOX = "CheckboxField"
    FILE_PICKER = "FilePicker"
    RICHTEXT_EDITOR = "RichTextEditor"


class FormField(ABC):
    type: FormFieldTypes = cast(FormFieldTypes, None)

    def __init__(self, **kwargs):
        """
        Initilizer for HTML input elements. Accepts any number of keyword arguments. Each argument will be treated as
        a html attribute.
        """
        if self.type is None:
            raise NotImplementedError(
                "FormField type must be defined in subclass with a defined type attribute of type FormFieldTypes."
            )
        self.id = kwargs.pop("id", None)
        self.name = kwargs.pop("name", None)
        self._label = kwargs.pop("label", None)
        self.kwargs = kwargs

        if self.id is None or self.name is None:
            raise Exception(
                "FormField element must have a valid id and name parameter."
            )

    def __call__(self, **kwargs):
        """
        Render: <tags-input ...standard attrs... as-string="..."></tags-input>
        """
        kwargs.pop("id", None)
        kwargs.pop("name", None)
        kwargs.pop("label", None)
        self.kwargs.update(kwargs)

        for attr, value in self.kwargs.items():
            attr = to_kebab_case(attr)
            kwargs[attr] = value

        return self.markup(**kwargs)

    def generate_string_attributes(self, **kwargs) -> str:
        """Generates a string with html attributes corresponding to the kwargs object"""
        return html_params(**kwargs)

    @abstractmethod
    def markup(self, **kwargs) -> Markup:
        """Must return the markuo of the element"""
        pass

    def label(self, **kwargs) -> Markup:
        """
        Generates the label markup for the form field.
        """
        if self._label is None:
            return Markup("")

        return Markup(
            f'<label for="{self.id}" class="{kwargs.get("class", "")}" style="{kwargs.get("style", "")}">{self._label}</label>'
        )


class FilePicker(FormField):
    type: FormFieldTypes = FormFieldTypes.FILE_PICKER

    def __init__(self, **kwargs):
        """
        Initlizer for TagsInput element. Accepts standard html attributes
        and the special boolean attribute: "as_string".
        If as_string=True, the return value of the html element will be a comma separated string,
        otherwise it will be a list of strings.
        """
        super().__init__(**kwargs)

    def markup(self, **kwargs) -> Markup:
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<file-picker id="{self.id}" name="{self.name}" {attrs}></file-picker>'
        )


class TagsInput(FormField):
    type: FormFieldTypes = FormFieldTypes.TAGS

    def __init__(self, **kwargs):
        """
        Initlizer for TagsInput element. Accepts standard html attributes
        and the special boolean attribute: "as_string".
        If as_string=True, the return value of the html element will be a comma separated string,
        otherwise it will be a list of strings.
        """
        super().__init__(**kwargs)

    def markup(self, **kwargs) -> Markup:
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<tags-input id="{self.id}" name="{self.name}" {attrs}></tags-input>'
        )


class PasswordInput(FormField):
    """
    Password input field
    """

    type: FormFieldTypes = FormFieldTypes.PASSWORD

    def markup(self, **kwargs) -> Markup:
        """
        Password field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<input type="password" id="{self.id}" name="{self.name}" {attrs} />'
        )


class EmailInput(FormField):
    """
    Email input field
    """

    type: FormFieldTypes = FormFieldTypes.EMAIL

    def markup(self, **kwargs) -> Markup:
        """
        Email field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<input type="email" id="{self.id}" name="{self.name}" {attrs} />'
        )


class TextInput(FormField):
    """
    Text input field
    """

    type: FormFieldTypes = FormFieldTypes.TEXT

    def markup(self, **kwargs) -> Markup:
        """
        Text field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<input type="text" id="{self.id}" name="{self.name}" {attrs} />'
        )


class TextAreaInput(FormField):
    """
    Text input field
    """

    type: FormFieldTypes = FormFieldTypes.TEXTAREA

    def markup(self, **kwargs) -> Markup:
        """
        Textarea field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<textarea type="text" id="{self.id}" name="{self.name}" {attrs}></textarea>'
        )


class SelectInput(FormField):
    """
    Select input field
    """

    type: FormFieldTypes = FormFieldTypes.SELECT

    def __init__(self, **kwargs):
        options = kwargs.pop("options", None)
        super().__init__(**kwargs)
        self.options = options
        if (
            self.options is None
            or not isinstance(self.options, list)
            or not isinstance(self.options[0], tuple)
        ):
            raise Exception("Please provide a list of tuples (value, name) as options")

    def generate_options(self) -> str:
        """Generates options string"""
        options: str = ""
        for val, name in self.options:
            options += f'<option value="{val}">{name}</options>'
        return options

    def markup(self, **kwargs) -> Markup:
        """
        Select field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        options: str = self.generate_options()
        return Markup(
            f'<select type="text" id="{self.id}" name="{self.name}" {attrs}>{options}</select>'
        )


class CheckboxInput(FormField):
    """
    Checkbox input field
    """

    type: FormFieldTypes = FormFieldTypes.CHECKBOX

    def markup(self, **kwargs) -> Markup:
        """
        Checkbox field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<input type="checkbox" id="{self.id}" name="{self.name}" {attrs} />'
        )


class RadioInput(FormField):
    """
    Radio input field
    """

    type: FormFieldTypes = FormFieldTypes.RADIO

    def markup(self, **kwargs) -> Markup:
        """
        Radio field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<input type="radio" id="{self.id}" name="{self.name}" {attrs} />'
        )


class RichTextInput(FormField):
    """
    Rich Text Editor input field
    """

    type: FormFieldTypes = FormFieldTypes.RICHTEXT_EDITOR

    def markup(self, **kwargs) -> Markup:
        """
        Rich Text Editor field input
        """
        attrs = self.generate_string_attributes(**kwargs)
        return Markup(
            f'<richtext-editor id="{self.id}" name="{self.name}" {attrs}></richtext-editor>'
        )
