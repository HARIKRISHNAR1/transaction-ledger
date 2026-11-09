# test_ledger.py
# Run with: pytest -v

import threading

import pytest

from ledger import Ledger, InsufficientFundsError


def test_basic_transfer_moves_balance_correctly():
    ledger = Ledger()
    alice = ledger.create_account("Alice", 1000)
    bob = ledger.create_account("Bob", 0)

    ledger.transfer(alice.account_id, bob.account_id, 250)

    assert ledger.get_balance(alice.account_id) == 750
    assert ledger.get_balance(bob.account_id) == 250


def test_insufficient_funds_blocks_transfer():
    ledger = Ledger()
    alice = ledger.create_account("Alice", 100)
    bob = ledger.create_account("Bob", 0)

    with pytest.raises(InsufficientFundsError):
        ledger.transfer(alice.account_id, bob.account_id, 500)

    # balances must be unchanged - the failed transfer shouldn't have
    # partially applied
    assert ledger.get_balance(alice.account_id) == 100
    assert ledger.get_balance(bob.account_id) == 0


def test_double_entry_invariant_sum_is_always_zero():
    # Every transfer should create exactly one debit and one credit entry
    # that cancel out. So for any account: its starting balance, plus the
    # sum of all its ledger entries, must equal its current balance.
    ledger = Ledger()
    alice = ledger.create_account("Alice", 1000)
    bob = ledger.create_account("Bob", 0)
    carol = ledger.create_account("Carol", 0)
    starting_balances = {
        alice.account_id: 1000,
        bob.account_id: 0,
        carol.account_id: 0,
    }

    ledger.transfer(alice.account_id, bob.account_id, 300)
    ledger.transfer(bob.account_id, carol.account_id, 100)
    ledger.transfer(alice.account_id, carol.account_id, 50)

    for account_id in (alice.account_id, bob.account_id, carol.account_id):
        entries = ledger.get_history(account_id)
        expected_balance = starting_balances[account_id] + sum(e.amount for e in entries)
        assert expected_balance == ledger.get_balance(account_id)

    # across the WHOLE ledger, every transfer's two entries must cancel
    # out exactly - this is the real double-entry guarantee
    assert sum(e.amount for e in ledger._entries) == 0


def test_transfer_to_self_is_rejected():
    ledger = Ledger()
    alice = ledger.create_account("Alice", 1000)

    with pytest.raises(ValueError):
        ledger.transfer(alice.account_id, alice.account_id, 10)


def test_negative_or_zero_amount_is_rejected():
    ledger = Ledger()
    alice = ledger.create_account("Alice", 1000)
    bob = ledger.create_account("Bob", 0)

    with pytest.raises(ValueError):
        ledger.transfer(alice.account_id, bob.account_id, 0)

    with pytest.raises(ValueError):
        ledger.transfer(alice.account_id, bob.account_id, -50)


def test_concurrent_transfers_preserve_total_money():
    # The real test of the locking design: total money across both
    # accounts must be exactly the same before and after, no matter how
    # many threads hammer the same two accounts at once.
    ledger = Ledger()
    alice = ledger.create_account("Alice", 5000)
    bob = ledger.create_account("Bob", 5000)
    total_before = ledger.get_balance(alice.account_id) + ledger.get_balance(bob.account_id)

    def worker(from_acc, to_acc):
        try:
            ledger.transfer(from_acc, to_acc, 10)
        except InsufficientFundsError:
            pass

    threads = []
    for _ in range(50):
        threads.append(threading.Thread(target=worker, args=(alice.account_id, bob.account_id)))
        threads.append(threading.Thread(target=worker, args=(bob.account_id, alice.account_id)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_after = ledger.get_balance(alice.account_id) + ledger.get_balance(bob.account_id)
    assert total_after == total_before


def test_reversed_concurrent_transfers_do_not_deadlock():
    # Thread A does acc1 -> acc2 while Thread B does acc2 -> acc1, at the
    # same time, repeatedly. With a fixed lock-acquisition order this
    # finishes quickly; without it, this test would hang.
    ledger = Ledger()
    acc1 = ledger.create_account("Account1", 10000)
    acc2 = ledger.create_account("Account2", 10000)

    def hammer(from_acc, to_acc):
        for _ in range(100):
            try:
                ledger.transfer(from_acc, to_acc, 1)
            except InsufficientFundsError:
                pass

    t1 = threading.Thread(target=hammer, args=(acc1.account_id, acc2.account_id))
    t2 = threading.Thread(target=hammer, args=(acc2.account_id, acc1.account_id))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive() and not t2.is_alive()
