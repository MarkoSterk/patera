"""
Vector column for PostgreSQL database.
"""

from typing import Callable, List, Self, Type
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType):
    """
    Custom Vector type for pgvector in PostgreSQL.

    Requires pgvector extension for the PostgreSQL database.
    """

    cache_ok = True

    def __init__(self, dimensions: int | None = None):
        self.dimensions: int | None = dimensions

    # pylint: disable-next=C0116
    def get_col_spec(self, **kw) -> str:
        if self.dimensions:
            return f"VECTOR({int(self.dimensions)})"
        return "VECTOR"

    # pylint: disable-next=C0116
    def bind_expression(self, bindvalue):
        return bindvalue

    # pylint: disable-next=C0116
    def coerce_compared_value(self, op, value):
        if isinstance(value, (list, tuple)):
            return self
        return super().coerce_compared_value(op, value)

    # pylint: disable-next=C0116
    def literal_processor(self, dialect) -> Callable:
        def process(value):
            if value is None:
                return "NULL"
            inside = ",".join(str(float(x)) for x in value)
            return f"'[{inside}]'::vector"

        return process

    # pylint: disable-next=C0116
    def compare_values(self, x: List, y: List) -> bool:
        if x is y:
            return True
        if x is None or y is None:
            return x is y
        if len(x) != len(y):
            return False
        eps = 1e-9
        return all(abs(float(a) - float(b)) <= eps for a, b in zip(x, y))

    class comparator_factory(UserDefinedType.Comparator):
        # distance operators exposed as methods for nicer query syntax
        def l2_distance(self, other):
            return self.expr.op("<->")(other)

        def inner_product(self, other):
            return self.expr.op("<#>")(other)

        def cosine_distance(self, other):
            return self.expr.op("<=>")(other)

    # pylint: disable-next=C0116
    def column_expression(self, colexpr) -> ColumnElement:
        return colexpr

    # pylint: disable-next=C0116
    def _with_collation(self, collation) -> Self:
        return self

    @property
    def python_type(self) -> Type[List]:
        return list
