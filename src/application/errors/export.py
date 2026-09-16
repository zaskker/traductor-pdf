class ExportError(Exception):
    def __init__(
        self,
        message: str,
        *,
        temporary_path: str | None = None,
        cleanup_failed: bool = False,
    ):
        super().__init__(message)
        self.temporary_path = temporary_path
        self.cleanup_failed = cleanup_failed


class InvalidExportRequestError(ExportError):
    pass


class SourceFingerprintMismatchError(ExportError):
    pass


class ExportValidationError(ExportError):
    pass


class ExportFileError(ExportError):
    pass
