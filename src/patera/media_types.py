"""
Common and supported media types for incoming requests and responses
"""

from enum import StrEnum


class MediaType(StrEnum):
    APPLICATION_X_WWW_FORM_URLENCODED = "application/x-www-form-urlencoded"
    MULTIPART_FORM_DATA = "multipart/form-data"
    APPLICATION_JSON = "application/json"
    APPLICATION_PROBLEM_JSON = "application/problem+json"
    APPLICATION_XML = "application/xml"
    TEXT_XML = "text/xml"
    TEXT_PLAIN = "text/plain"
    TEXT_HTML = "text/html"
    APPLICATION_OCTET_STREAM = "application/octet-stream"
    IMAGE_PNG = "image/png"
    IMAGE_JPEG = "image/jpeg"
    IMAGE_GIF = "image/gif"
    APPLICATION_PDF = "application/pdf"
    APPLICATION_X_NDJSON = "application/x-ndjson"
    APPLICATION_CSV = "application/csv"
    TEXT_CSV = "text/csv"
    APPLICATION_YAML = "application/yaml"
    TEXT_YAML = "text/yaml"
    APPLICATION_GRAPHQL = "application/graphql"
    NO_CONTENT = "empty"
