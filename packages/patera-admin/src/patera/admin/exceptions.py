class UnsupportedLanguage(RuntimeError):
    def __init__(self, lang: str):
        super().__init__(f"Unsupported language: {lang}")
        self.lang = lang
