"""
RAG interface
"""

from typing import List, Any


class BaseAugmentationProvider:
    async def augmentation_loader(self, req) -> List[Any]:
        pass
