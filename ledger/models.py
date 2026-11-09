# models.py
# Defines the basic building blocks of the ledger: accounts and the
# individual entries that make up a transfer.

import time       # used to timestamp entries
import uuid        # used to generate unique ids for accounts and entries
from dataclasses import dataclass, field


@dataclass
class Account:
    account_id: str                              # unique id for this account
    owner: str                                     # name of whoever owns the account
    balance: float = 0.0                           # current balance - only ever changed through the Ledger class
    created_at: float = field(default_factory=time.time)


@dataclass
class LedgerEntry:
    # A single line in the ledger. A transfer always produces TWO of these:
    # one negative entry (money leaving an account) and one positive entry
    # (money arriving in another account). This is "double-entry
    # bookkeeping" - the two entries always cancel out to zero, which means
    # money is never created or destroyed by a transfer, only moved.
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str = ""        # links the debit and credit entries of one transfer together
    account_id: str = ""
    amount: float = 0.0              # negative = money left this account, positive = money arrived
    balance_after: float = 0.0       # what the account's balance was right after this entry
    timestamp: float = field(default_factory=time.time)


class InsufficientFundsError(Exception):
    # Raised when a transfer would take an account below zero.
    pass
