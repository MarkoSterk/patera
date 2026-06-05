class UnsupportedLanguage(RuntimeError):
    def __init__(self, lang: str):
        self.lang = lang
        super().__init__(f"Unsupported language: {lang}")


class MissingPermission(RuntimeError):
    def __init__(self, permission: str):
        self.permission = permission
        super().__init__(f"Missing user permission for: {permission}")
