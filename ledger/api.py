# api.py
# Small Flask API so the ledger can be used over HTTP, not just as a
# Python library.
#
# Start it with:  python -m ledger.api
#
# Then from another terminal:
#   curl -X POST http://localhost:5001/accounts -H "Content-Type: application/json" -d '{"owner": "Alice", "initial_balance": 1000}'
#   curl -X POST http://localhost:5001/accounts -H "Content-Type: application/json" -d '{"owner": "Bob", "initial_balance": 0}'
#   curl -X POST http://localhost:5001/transfer -H "Content-Type: application/json" -d '{"from_account": "<alice_id>", "to_account": "<bob_id>", "amount": 250}'

from flask import Flask, jsonify, request

from .ledger import Ledger
from .models import InsufficientFundsError

app = Flask(__name__)
ledger = Ledger()   # one ledger shared by the whole running app


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "transaction-ledger",
        "status": "running",
        "endpoints": {
            "POST /accounts": "create an account - body: {owner, initial_balance}",
            "GET /accounts/<id>": "check an account's balance",
            "GET /accounts/<id>/history": "see every entry recorded against an account",
            "POST /transfer": "move money between accounts - body: {from_account, to_account, amount}",
        },
    })


@app.route("/accounts", methods=["POST"])
def create_account():
    body = request.get_json(force=True)
    owner = body.get("owner")
    initial_balance = body.get("initial_balance", 0)
    if not owner:
        return jsonify({"error": "owner is required"}), 400

    account = ledger.create_account(owner, initial_balance)
    return jsonify({
        "account_id": account.account_id,
        "owner": account.owner,
        "balance": account.balance,
    }), 201


@app.route("/accounts/<account_id>", methods=["GET"])
def get_account(account_id):
    try:
        balance = ledger.get_balance(account_id)
    except KeyError:
        return jsonify({"error": "account not found"}), 404
    return jsonify({"account_id": account_id, "balance": balance})


@app.route("/accounts/<account_id>/history", methods=["GET"])
def get_history(account_id):
    entries = ledger.get_history(account_id)
    return jsonify([
        {
            "entry_id": e.entry_id,
            "transaction_id": e.transaction_id,
            "amount": e.amount,
            "balance_after": e.balance_after,
            "timestamp": e.timestamp,
        }
        for e in entries
    ])


@app.route("/transfer", methods=["POST"])
def transfer():
    body = request.get_json(force=True)
    from_account = body.get("from_account")
    to_account = body.get("to_account")
    amount = body.get("amount")

    if not from_account or not to_account or amount is None:
        return jsonify({"error": "from_account, to_account and amount are required"}), 400

    try:
        transaction_id = ledger.transfer(from_account, to_account, amount)
    except InsufficientFundsError as e:
        return jsonify({"error": str(e)}), 402
    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "transaction_id": transaction_id,
        "from_account": from_account,
        "to_account": to_account,
        "amount": amount,
        "from_balance": ledger.get_balance(from_account),
        "to_balance": ledger.get_balance(to_account),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
