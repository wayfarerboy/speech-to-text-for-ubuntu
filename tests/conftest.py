"""Test fixtures and setup."""
import logging
import sys
from unittest import mock


def _safe_filehandler(*args, **kwargs):
    try:
        return _orig_handler(*args, **kwargs)
    except PermissionError:
        return logging.NullHandler()


_orig_handler = logging.FileHandler
logging.FileHandler = _safe_filehandler
