class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message


INSUFFICIENT = (
    "I couldn't find enough information in the available company documents to answer that reliably."
)
