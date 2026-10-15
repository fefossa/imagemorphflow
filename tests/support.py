"""Test fixture cleanup for Windows file-lock semantics."""

import logging
import tempfile
from contextlib import contextmanager


@contextmanager
def temporary_directory():
    with tempfile.TemporaryDirectory() as directory:
        try:
            yield directory
        finally:
            logging.shutdown()
            for handler in list(logging.getLogger().handlers):
                logging.getLogger().removeHandler(handler)
