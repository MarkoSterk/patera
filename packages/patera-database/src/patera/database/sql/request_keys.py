"""Request-context keys shared by the database classes and their middleware."""

from collections.abc import Callable

from patera.ctx import get_request_context, has_request_context

# ctx.extras: True while a @transactional request's commit is still ahead.
# See sql_database.in_transactional_request().
TRANSACTION_OPEN = "patera.database.transaction_open"
AFTER_COMMIT = "patera.database.after_commit"


def after_request_commit(callback: Callable[[], object]) -> None:
    """Run now, or after the active request transaction commits successfully."""
    if has_request_context():
        extras = get_request_context().extras
        if extras.get(TRANSACTION_OPEN):
            extras.setdefault(AFTER_COMMIT, []).append(callback)
            return
    callback()
