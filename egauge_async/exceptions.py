class EgaugeException(Exception):
    """Base exception class for Egauge errors"""
    pass


class EgaugeHTTPErrorCode(EgaugeException):
    """Exception raised when the eGauge API responds with an unexpected response code

    Attributes:
        error_code: The HTTP error code returned (e.g. 404)
    """

    def __init__(self, error_code: int):
        self.message = f"Egauge replied with HTTP code {error_code}"
        super().__init__(self.message)


class EgaugeParsingException(EgaugeException):
    pass
