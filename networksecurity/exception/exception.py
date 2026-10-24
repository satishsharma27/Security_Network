import sys

from networksecurity.logging import logger


class NetworkSecurityException(Exception):
    def __init__(self, error_message=None, error_details=None):
        self.error_message = str(error_message) if error_message is not None else "Unknown error"
        self.file_name = None
        self.lineno = None

        if error_details is not None and hasattr(error_details, "exc_info"):
            _, _, exc_tb = error_details.exc_info()
            if exc_tb is not None:
                self.lineno = exc_tb.tb_lineno
                self.file_name = exc_tb.tb_frame.f_code.co_filename

    def __str__(self):
        if self.file_name is None or self.lineno is None:
            return self.error_message
        return "Error occured in python script name [{0}] line number [{1}] error message [{2}]".format(
            self.file_name, self.lineno, str(self.error_message)
        )


if __name__ == "__main__":
    try:
        logger.logging.info("Enter the try block")
        a = 1 / 0
        print("This will not be printed", a)
    except Exception as e:
        raise NetworkSecurityException(e, sys)