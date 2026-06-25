"""
Patera default logger
"""

from typing import Any, TypeVar, TYPE_CHECKING
from .logging.logger_config_base import LoggerBase, logger

if TYPE_CHECKING:
    from .patera import Patera

AppT = TypeVar("AppT", bound="Patera[Any]", default="Patera[Any]")


@logger("Patera Logger")
class DefaultLogger(LoggerBase[AppT]):
    """Default logger implementation"""
