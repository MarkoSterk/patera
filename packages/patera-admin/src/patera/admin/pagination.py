"""
Page links for Admin's paginated tables.
"""

from __future__ import annotations

from typing import Optional


def page_items(
    current_page: int, total_pages: int, window: int = 2, edges: int = 1
) -> list[Optional[int]]:
    """
    The pages to link: the first and last ``edges`` pages and ``window``
    pages on each side of the current one, with None where pages are left
    out (shown as an ellipsis). A gap of a single page shows that page
    instead, since an ellipsis would take the same space.

    Example: page 10 of 59 -> [1, None, 8, 9, 10, 11, 12, None, 59]
    """
    if total_pages <= 0:
        return []
    current_page = min(max(current_page, 1), total_pages)
    shown = sorted(
        {
            page
            for page in (
                *range(1, edges + 1),
                *range(current_page - window, current_page + window + 1),
                *range(total_pages - edges + 1, total_pages + 1),
            )
            if 1 <= page <= total_pages
        }
    )
    items: list[Optional[int]] = []
    for page in shown:
        if items and page - items[-1] == 2:  # type: ignore[operator]
            items.append(page - 1)
        elif items and page - items[-1] > 2:  # type: ignore[operator]
            items.append(None)
        items.append(page)
    return items
