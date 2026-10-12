"""Request-context keys shared by the database classes and their middleware."""

# ctx.extras: True while a @transactional request's commit is still ahead.
# See sql_database.in_transactional_request().
TRANSACTION_OPEN = "patera.database.transaction_open"
