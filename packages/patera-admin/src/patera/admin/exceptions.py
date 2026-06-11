class UnsupportedLanguage(RuntimeError):
    def __init__(self, lang: str):
        self.lang = lang
        super().__init__(f"Unsupported language: {lang}")


class MissingPermission(RuntimeError):
    def __init__(self, permission: str):
        self.permission = permission
        super().__init__(f"Missing user permission for: {permission}")


class UnknownModelException(RuntimeError):
    def __init__(self, model_name: str, db_name):
        self.model_name = model_name
        self.db_name = db_name
        super().__init__(f"Model {model_name} in database {db_name} not found.")


class UnknownDatabaseException(RuntimeError):
    def __init__(self, db_name: str):
        self.db_name = db_name
        super().__init__(f"Database with name {db_name} not found.")


class RecordNotFound(RuntimeError):
    def __init__(self, db_name: str, model_name, **pk_values):
        self.db_name = db_name
        self.model_name = model_name
        self.pk_values = pk_values
        super().__init__(
            f"Record with values {pk_values} for found in database {db_name} and table {model_name}"
        )


class AdminLoginRequiredException(RuntimeError):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)


class AdminAuthorizationRequiredException(RuntimeError):
    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(msg)
