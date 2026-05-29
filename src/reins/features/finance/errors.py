from __future__ import annotations


class FinanceError(Exception):
    """Base class for Reins finance errors."""


class MissingAmountError(FinanceError):
    """Raised when transaction amount is missing."""


class UnknownTransactionTypeError(FinanceError):
    """Raised when transaction type is not income or expense."""


class TransactionNotFoundError(FinanceError):
    """Raised when a transaction cannot be found."""


class InvalidDateRangeError(FinanceError):
    """Raised when start date is later than end date."""


class InvalidFinanceDateError(FinanceError):
    """Raised when finance text contains an invalid date."""


class InvalidTransactionInputError(FinanceError):
    """Raised when transaction input is invalid."""
