"""
Chat augmentation (RAG) provider subpackage.

The provider needs the optional embedding libraries:
pip install "patera-aiinterface[augmentation]"
"""

from .config import AugmentationConfig
from .base_augmentation_provider import BaseAugmentationProvider

__all__ = ["AugmentationConfig", "BaseAugmentationProvider"]
