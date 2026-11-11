# SPDX-FileCopyrightText: 2018 Boerderij
# SPDX-FileCopyrightText: 2026 HoneyBearTech
# SPDX-License-Identifier: MIT
"""Logging: the console and file handlers, and the filter that keeps secrets out of both."""

from logging import DEBUG, INFO, Filter, Formatter, LogRecord, StreamHandler, getLogger
from logging.handlers import RotatingFileHandler
from typing import TYPE_CHECKING, ClassVar

from varken.helpers import mkdir_p

if TYPE_CHECKING:
    from collections.abc import Collection

# What a secret becomes in the log: nothing of it is kept (before 3.0.0 its last five characters were).
MASK = 8 * '*'


class BlacklistFilter(Filter):
    """Log filter for blacklisted tokens and passwords."""

    filename = 'varken.log'
    max_size = 5000000  # 5 MB
    max_files = 5
    log_folder = 'logs'

    blacklisted_strings: ClassVar[list[str]] = ['apikey', 'username', 'password', 'url', 'maxmind_license_key']

    def __init__(self, filteredstrings: Collection[str]) -> None:
        """Mask each of these strings wherever a record has one."""
        super().__init__()
        self.filtered_strings = filteredstrings

    def filter(self, record: LogRecord) -> bool:
        """Mask the secrets in the record's message and arguments; every record is kept."""
        for item in self.filtered_strings:
            try:
                if item in record.msg:
                    record.msg = record.msg.replace(item, MASK)
                if any(item in str(arg) for arg in record.args):
                    # Anything but a number is redacted through its text, so an exception or a request whose
                    # text contains a secret (an API key in a URL, say) doesn't carry it into the log.
                    record.args = tuple(
                        str(arg).replace(item, MASK) if not isinstance(arg, (int, float)) and item in str(arg) else arg
                        for arg in record.args
                    )
            except TypeError:
                pass
        return True


class VarkenLogger:
    """The root logger as Varken sets it up: the console, and a rotating file in the data folder's logs."""

    def __init__(self, *, debug: bool | None = None, data_folder: str | None = None, log_to_file: bool = True) -> None:
        """Add the handlers: DEBUG and up with `debug`, else INFO and up; no file with log_to_file off."""
        self.data_folder = data_folder
        self.log_level = debug

        # Set log level
        if self.log_level:
            self.log_level = DEBUG

        else:
            self.log_level = INFO

        # Create the Logger
        self.logger = getLogger()
        self.logger.setLevel(DEBUG)

        # Create a Formatter for formatting the log messages
        logger_formatter = Formatter('%(asctime)s : %(levelname)s : %(module)s : %(message)s', '%Y-%m-%d %H:%M:%S')

        if log_to_file:
            # Make the log directory if it does not exist
            mkdir_p(f'{self.data_folder}/{BlacklistFilter.log_folder}')

            # Create the Handler for logging data to a file
            file_logger = RotatingFileHandler(
                f'{self.data_folder}/{BlacklistFilter.log_folder}/{BlacklistFilter.filename}',
                mode='a',
                maxBytes=BlacklistFilter.max_size,
                encoding=None,
                delay=0,
                backupCount=BlacklistFilter.max_files,
            )
            file_logger.setLevel(self.log_level)
            file_logger.setFormatter(logger_formatter)
            self.logger.addHandler(file_logger)

        # Add the console logger
        console_logger = StreamHandler()
        console_logger.setFormatter(logger_formatter)
        console_logger.setLevel(self.log_level)
        self.logger.addHandler(console_logger)
