# ledger.py
# This is where transfers actually happen. The two things this is built
# to get right:
#
#   1. CORRECTNESS - a transfer either fully happens (both the debit and
#      the credit) or doesn't happen at all. Money can never be deducted
#      from one account without showing up in the other.
#
#   2. CONCURRENCY SAFETY WITHOUT DEADLOCKS - if two transfers touch the
#      same account at the same time (e.g. two people both transferring
#      money out of the same wallet at once), the balance must stay
#      correct. But if we're not careful about HOW we lock two accounts
#      at once, we can deadlock: Thread A locks account 1 then waits for
#      account 2, while Thread B locks account 2 then waits for account 1 -
#      neither can ever finish. This file avoids that on purpose.

import threading
import uuid

from .models import Account, LedgerEntry, InsufficientFundsError


class Ledger:
    def __init__(self):
        self._accounts: dict[str, Account] = {}          # account_id -> Account
        self._entries: list[LedgerEntry] = []              # full history, in the order it happened
        self._account_locks: dict[str, threading.Lock] = {}  # one lock per account
        self._locks_guard = threading.Lock()                # protects _account_locks itself
        self._ledger_guard = threading.Lock()                # protects _accounts / _entries bookkeeping

    def create_account(self, owner: str, initial_balance: float = 0.0) -> Account:
        account = Account(account_id=str(uuid.uuid4()), owner=owner, balance=initial_balance)
        with self._ledger_guard:
            self._accounts[account.account_id] = account
            self._account_locks[account.account_id] = threading.Lock()
        return account

    def get_balance(self, account_id: str) -> float:
        return self._accounts[account_id].balance

    def get_history(self, account_id: str) -> list[LedgerEntry]:
        return [e for e in self._entries if e.account_id == account_id]

    def _lock_for(self, account_id: str) -> threading.Lock:
        return self._account_locks[account_id]

    def transfer(self, from_account_id: str, to_account_id: str, amount: float) -> str:
        """
        Moves `amount` from one account to another. Returns the
        transaction_id that links the two ledger entries this creates.
        """
        if from_account_id == to_account_id:
            raise ValueError("Cannot transfer an account to itself")
        if amount <= 0:
            raise ValueError("Transfer amount must be positive")

        # THE DEADLOCK-AVOIDANCE TRICK:
        # Always acquire the two account locks in the same, fixed order
        # (sorted by account_id), no matter which account is "from" and
        # which is "to". This way, if Thread A is transferring 1 -> 2 and
        # Thread B is transferring 2 -> 1 at the same time, BOTH threads
        # try to lock account 1 first. One of them simply has to wait its
        # turn - there's no scenario where each thread holds one lock and
        # waits forever for the other.
        first_id, second_id = sorted([from_account_id, to_account_id])
        first_lock = self._lock_for(first_id)
        second_lock = self._lock_for(second_id)

        with first_lock, second_lock:
            from_account = self._accounts[from_account_id]
            to_account = self._accounts[to_account_id]

            if from_account.balance < amount:
                raise InsufficientFundsError(
                    f"Account {from_account_id} has {from_account.balance}, "
                    f"tried to send {amount}"
                )

            transaction_id = str(uuid.uuid4())   # links the two entries below as "one transfer"

            # move the money
            from_account.balance -= amount
            to_account.balance += amount

            # record BOTH sides of the transfer - this is the double-entry
            # part. Notice the two amounts below always sum to zero.
            debit_entry = LedgerEntry(
                transaction_id=transaction_id,
                account_id=from_account_id,
                amount=-amount,
                balance_after=from_account.balance,
            )
            credit_entry = LedgerEntry(
                transaction_id=transaction_id,
                account_id=to_account_id,
                amount=amount,
                balance_after=to_account.balance,
            )

            with self._ledger_guard:
                self._entries.append(debit_entry)
                self._entries.append(credit_entry)

            return transaction_id
