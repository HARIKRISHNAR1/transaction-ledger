# Concurrent Transaction Ledger

A backend that moves money between accounts the way a real banking or
payments system does: every transfer is recorded as a matched debit and
credit (double-entry bookkeeping), and the system stays correct even when
many transfers happen on the same accounts at the exact same time.

## Table of Contents

- [Overview](#overview)
- [Why This Project Exists](#why-this-project-exists)
- [Key Concepts](#key-concepts)
- [How It Works](#how-it-works)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Usage](#usage)
- [Running Tests](#running-tests)
- [Example Output](#example-output)
- [Design Decisions](#design-decisions)
- [Limitations and Future Improvements](#limitations-and-future-improvements)
- [License](#license)

## Overview

This project implements an in-memory ledger that supports creating
accounts and transferring money between them. It's built around two
guarantees that any real financial system needs:

1. Money is never created or destroyed by a transfer - every amount that
   leaves one account is accounted for arriving in another.
2. Many transfers can run on the same accounts in parallel without
   corrupting a balance or causing a deadlock.

## Why This Project Exists

A payments or banking backend almost never processes transfers one at a
time. Real systems handle many requests concurrently, which creates two
classic problems:

- **Race conditions on balances.** If two transfers read an account's
  balance at the same time, both can "see" the same starting balance and
  both subtract from it, leaving the account with more money removed than
  it should have had.
- **Deadlocks.** If a transfer needs to lock two accounts at once (the
  sender and the receiver), and two transfers happen to involve the same
  two accounts in opposite directions at the same time, naive locking can
  cause both transfers to wait on each other forever.

This project exists to show a correct, tested solution to both problems.

## Key Concepts

**Double-entry bookkeeping**
Every transfer produces exactly two ledger entries: a negative entry on
the sending account and a positive entry on the receiving account, for
the same amount. Added together, the two entries always sum to zero. This
makes it possible to verify, at any point, that no money was created or
lost - you can sum every entry ever recorded and it will always come out
to zero.

**Per-account locking with a fixed lock order**
Each account has its own lock. A transfer locks both the sending and
receiving account before touching either balance. To avoid deadlocks, the
two locks are always acquired in the same order (sorted by account id),
regardless of which account is sending and which is receiving. This means
two transfers going in opposite directions between the same two accounts
can never end up waiting on each other indefinitely.

**Atomicity**
A transfer either fully succeeds (both balances update and both ledger
entries are recorded) or fully fails (nothing changes). There's no state
where money has left one account but not yet arrived in the other.

## How It Works

1. A client creates two or more accounts via `POST /accounts`.
2. A client requests a transfer via `POST /transfer`, specifying a source
   account, destination account, and amount.
3. The ledger determines the lock order for the two accounts involved
   (sorted by account id) and acquires both locks.
4. It checks the sending account has enough balance; if not, the transfer
   is rejected and nothing changes.
5. It deducts the amount from the sender, adds it to the receiver, and
   records two matching ledger entries (one negative, one positive) tied
   together by a shared transaction id.
6. Both locks are released and the result is returned.

## Tech Stack

- **Python 3.12**
- **Flask** - HTTP API
- **pytest** - automated testing, including concurrency tests using real
  threads

## Project Structure

```
transaction-ledger/
├── ledger/
│   ├── __init__.py       # package exports
│   ├── models.py          # Account, LedgerEntry, and InsufficientFundsError
│   ├── ledger.py           # core transfer logic: locking, balance updates, entry recording
│   └── api.py               # Flask API exposing the ledger over HTTP
├── tests/
│   ├── conftest.py          # lets pytest find the package without installing it
│   └── test_ledger.py        # automated tests, including concurrency tests
├── demo.py                  # runnable script demonstrating the core behavior
├── requirements.txt
├── .gitignore
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.10 or newer
- pip

### Installation

```bash
git clone https://github.com/<your-username>/transaction-ledger.git
cd transaction-ledger
pip install -r requirements.txt
```

## Usage

### Option 1: Run the demo script (no server required)

```bash
python demo.py
```

This runs four demonstrations: a basic transfer, a blocked overdraft
attempt, 50 concurrent transfers checked for total-money conservation,
and a stress test proving opposite-direction concurrent transfers don't
deadlock.

### Option 2: Run it as an HTTP API

```bash
python -m ledger.api
```

The server starts on `http://localhost:5001`.

**Create two accounts:**

```bash
curl -X POST http://localhost:5001/accounts \
  -H "Content-Type: application/json" \
  -d '{"owner": "Alice", "initial_balance": 1000}'

curl -X POST http://localhost:5001/accounts \
  -H "Content-Type: application/json" \
  -d '{"owner": "Bob", "initial_balance": 0}'
```

Each response includes an `account_id` - use those in the next step.

**Transfer money:**

```bash
curl -X POST http://localhost:5001/transfer \
  -H "Content-Type: application/json" \
  -d '{"from_account": "<alice_id>", "to_account": "<bob_id>", "amount": 250}'
```

**Check a balance:**

```bash
curl http://localhost:5001/accounts/<account_id>
```

**See an account's full transaction history:**

```bash
curl http://localhost:5001/accounts/<account_id>/history
```

## Running Tests

```bash
pytest -v
```

The test suite verifies:

- a transfer moves the correct amount between two accounts
- an overdraft attempt is blocked and leaves both balances unchanged
- the double-entry invariant holds (every entry recorded, summed against
  each account's starting balance, matches its current balance - and
  across the whole ledger, every entry ever recorded sums to exactly zero)
- a transfer to the same account, or a negative/zero amount, is rejected
- 100 concurrent transfers between two accounts preserve the total amount
  of money across both accounts exactly
- transfers going in opposite directions between the same two accounts,
  fired at the same time, complete without deadlocking

## Example Output

```
--- Demo 1: a simple transfer ---
Alice balance: 750 (should be 750)
Bob balance:   250 (should be 250)

--- Demo 2: trying to overdraw an account ---
Correctly blocked: Account <id> has 100, tried to send 500

--- Demo 3: 50 concurrent transfers, checking total money is conserved ---
Total money before: 10000
Total money after:  10000 (should match exactly - no money created or lost)

--- Demo 4: proving reversed transfers don't deadlock ---
Finished cleanly in 0.005s - no deadlock
```

## Design Decisions

**Why lock two accounts in a fixed, sorted order instead of just "sender
then receiver"?**
This is the key decision that prevents deadlocks. If transfers always
locked "sender first, then receiver," two transfers going in opposite
directions between the same two accounts (A to B, and B to A, at the same
time) would deadlock: the first thread locks A and waits for B, while the
second locks B and waits for A - neither can proceed. By always locking
whichever account id sorts first, both threads agree on the same locking
order no matter which direction they're transferring, so one simply waits
its turn instead of both waiting forever.

**Why double-entry instead of just updating balances directly?**
Recording both sides of every transfer as separate ledger entries creates
an audit trail and makes it possible to verify correctness
independently of the balances - the balances could in principle be
recomputed entirely from the entry history. This is the same principle
real accounting and banking systems are built on.

**Why in-memory instead of a database?**
Same reasoning as with locking: a database transaction with proper
isolation levels would also prevent these race conditions, but building
this with plain Python locks keeps the core logic visible and makes the
concurrency behavior something you can read, test, and explain directly,
without needing a database running to follow along.

## Limitations and Future Improvements

- All data is in memory and is lost when the process restarts. A
  production version would use a database with transactional guarantees
  (e.g., `SELECT ... FOR UPDATE` in PostgreSQL) instead of in-process
  locks.
- There's no authentication - anyone who can reach the API can transfer
  from any account.
- No support for multi-currency accounts or exchange rates.
- A possible extension: add scheduled/recurring transfers, or a
  `/accounts/<id>/freeze` endpoint to block transfers on a specific
  account.

## License

This project is licensed under the MIT License - see the LICENSE file for
details.
