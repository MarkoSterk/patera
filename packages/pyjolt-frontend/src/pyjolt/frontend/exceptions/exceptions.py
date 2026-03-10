"""Custom exceptions"""


class NoRouteMatch(LookupError):
    pass


class AppDataException(Exception):
    def __init__(self, msg):
        super().__init__(msg)
