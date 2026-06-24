import logging


class ErrorOnlyFilter(logging.Filter):
    """Pass only ERROR and CRITICAL records to the errors aggregation log."""
    def filter(self, record):
        return record.levelno >= logging.ERROR


class WarningOnlyFilter(logging.Filter):
    """Pass only WARNING records (errors go separately to errors.log)."""
    def filter(self, record):
        return record.levelno == logging.WARNING
