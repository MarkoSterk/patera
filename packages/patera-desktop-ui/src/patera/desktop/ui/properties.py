"""Python descriptors corresponding to JoltUI reactive accessors."""

from copy import deepcopy


class Reactive:
    def __init__(self, factory, binding=None):
        self.factory, self.binding = factory, binding

    def __set_name__(self, owner, name):
        self.name = name
        self.binding = self.binding or name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        if self.name not in instance.__dict__:
            instance.__dict__[self.name] = self.factory()
        return instance.__dict__[self.name]

    def __set__(self, instance, value):
        previous = self.__get__(instance)
        if previous is value or (
            type(value) in (str, int, float, bool, type(None))
            and type(previous) is type(value)
            and previous == value
        ):
            return
        instance.__dict__[self.name] = value
        instance.invalidate(self.binding)


def react(value, binding=None):
    return Reactive(lambda: deepcopy(value), binding)


def react_factory(factory, binding=None):
    return Reactive(factory, binding)


class QueryParam:
    def __init__(self, name, default=None, binding=None):
        self.name, self.default, self.binding = name, default, binding

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return instance.app.query_parameters.get(self.name, self.default)

    def __set__(self, instance, value):
        instance.app.update_query_parameters({self.name: value})
        if self.binding:
            instance.invalidate(self.binding)


query_param = QueryParam


class Select:
    def __init__(self, selector, *, required=False, many=False):
        self.selector, self.required, self.many = selector, required, many

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        result = (
            instance.select_all(self.selector)
            if self.many
            else instance.select(self.selector)
        )
        if self.required and (not result if self.many else result is None):
            raise LookupError(f"Required selector not found: {self.selector}")
        return result

    def __set__(self, instance, value):
        raise AttributeError("Selected elements are read-only")


def select(selector, *, required=False):
    return Select(selector, required=required)


def select_all(selector, *, required=False):
    return Select(selector, required=required, many=True)
