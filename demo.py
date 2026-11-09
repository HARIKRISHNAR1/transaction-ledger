# demo.py
# Run with: python demo.py
#
# Walks through what the ledger does, printing results as it goes.

import threading
import time

from ledger import Ledger, InsufficientFundsError


def demo_basic_transfer():
    print("\n--- Demo 1: a simple transfer ---")
    ledger = Ledger()
    alice = ledger.create_account("Alice", initial_balance=1000)
    bob = ledger.create_account("Bob", initial_balance=0)

    ledger.transfer(alice.account_id, bob.account_id, 250)

    print(f"Alice balance: {ledger.get_balance(alice.account_id)} (should be 750)")
    print(f"Bob balance:   {ledger.get_balance(bob.account_id)} (should be 250)")


def demo_insufficient_funds():
    print("\n--- Demo 2: trying to overdraw an account ---")
    ledger = Ledger()
    alice = ledger.create_account("Alice", initial_balance=100)
    bob = ledger.create_account("Bob", initial_balance=0)

    try:
        ledger.transfer(alice.account_id, bob.account_id, 500)
        print("ERROR: this should have raised InsufficientFundsError")
    except InsufficientFundsError as e:
        print(f"Correctly blocked: {e}")


def demo_concurrent_transfers_no_lost_money():
    print("\n--- Demo 3: 50 concurrent transfers, checking total money is conserved ---")
    ledger = Ledger()
    alice = ledger.create_account("Alice", initial_balance=5000)
    bob = ledger.create_account("Bob", initial_balance=5000)
    total_before = ledger.get_balance(alice.account_id) + ledger.get_balance(bob.account_id)

    def worker(from_acc, to_acc):
        try:
            ledger.transfer(from_acc, to_acc, 10)
        except InsufficientFundsError:
            pass   # fine - just means that account ran low, not a bug

    # Half the threads send Alice -> Bob, half send Bob -> Alice, all at once.
    threads = []
    for _ in range(25):
        threads.append(threading.Thread(target=worker, args=(alice.account_id, bob.account_id)))
        threads.append(threading.Thread(target=worker, args=(bob.account_id, alice.account_id)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total_after = ledger.get_balance(alice.account_id) + ledger.get_balance(bob.account_id)
    print(f"Total money before: {total_before}")
    print(f"Total money after:  {total_after} (should match exactly - no money created or lost)")


def demo_no_deadlock_with_reversed_transfers():
    print("\n--- Demo 4: proving reversed transfers don't deadlock ---")
    # This is the classic deadlock scenario: Thread A does 1 -> 2 while
    # Thread B does 2 -> 1, over and over, at the same time. If the lock
    # ordering in ledger.py weren't fixed, this could freeze forever.
    ledger = Ledger()
    acc1 = ledger.create_account("Account1", initial_balance=10000)
    acc2 = ledger.create_account("Account2", initial_balance=10000)

    def hammer(from_acc, to_acc):
        for _ in range(200):
            try:
                ledger.transfer(from_acc, to_acc, 1)
            except InsufficientFundsError:
                pass

    start = time.time()
    t1 = threading.Thread(target=hammer, args=(acc1.account_id, acc2.account_id))
    t2 = threading.Thread(target=hammer, args=(acc2.account_id, acc1.account_id))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    elapsed = time.time() - start

    if t1.is_alive() or t2.is_alive():
        print("DEADLOCK DETECTED - threads did not finish in time")
    else:
        print(f"Finished cleanly in {elapsed:.3f}s - no deadlock")


if __name__ == "__main__":
    demo_basic_transfer()
    demo_insufficient_funds()
    demo_concurrent_transfers_no_lost_money()
    demo_no_deadlock_with_reversed_transfers()
