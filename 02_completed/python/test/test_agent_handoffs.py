"""
End-to-end integration tests for multi-agent banking handoffs.

Prerequisites:
  1. MCP server running (either option):
     - Remote: set USE_REMOTE_MCP_SERVER=true and MCP_SERVER_BASE_URL to the deployed URL
     - Local:  cd 02_completed/mcpserver && python src/mcp_http_server.py  (default port 8080)

  2. Banking API server running on http://127.0.0.1:63280:
     cd 02_completed/python
     uvicorn src.app.banking_agents_api:app --host 127.0.0.1 --port 63280

  3. Environment variables (both servers need these):
     COSMOSDB_ENDPOINT, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_COMPLETIONSDEPLOYMENTID,
     AZURE_OPENAI_EMBEDDINGDEPLOYMENTID, AZURE_OPENAI_API_VERSION

  4. Test data seeded in Cosmos DB:
     - Tenant: "Contoso", User: "Mark", Account: "Acc001" (balance $50,000)
     - Run the /data endpoint or use the seed scripts in python/data/

Usage:
  cd 02_completed/python
  python -m pytest test/test_agent_handoffs.py -v
  # or run directly:
  python test/test_agent_handoffs.py
"""

import requests
import sys

BASE_URL = "http://127.0.0.1:63280"
TENANT_ID = "Contoso"
USER_ID = "Mark"
TIMEOUT = 60


def create_session():
    r = requests.post(f"{BASE_URL}/tenant/{TENANT_ID}/user/{USER_ID}/sessions")
    assert r.status_code == 200, f"Session creation failed: {r.status_code} {r.text}"
    return r.json()["sessionId"]


def send_message(session_id, message):
    r = requests.post(
        f"{BASE_URL}/tenant/{TENANT_ID}/user/{USER_ID}/sessions/{session_id}/completion",
        json=message,
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"Completion failed: {r.status_code} {r.text[:500]}"
    return r.json()


def get_last_assistant_message(messages):
    """Return the last non-User message."""
    for msg in reversed(messages):
        if msg.get("sender") != "User":
            return msg
    return None


# --- Test Cases ---


def test_coordinator_to_transactions():
    """Coordinator routes balance check to Transactions agent."""
    sid = create_session()
    msgs = send_message(sid, "What is the balance on my account Acc001?")

    last = get_last_assistant_message(msgs)
    assert last is not None
    assert last["sender"] == "Transactions", f"Expected Transactions, got {last['sender']}"
    assert "50,000" in last["text"] or "50000" in last["text"], f"Balance not in response: {last['text']}"
    print(f"  PASS: Transactions agent returned balance: {last['text'][:100]}")


def test_coordinator_to_customer_support():
    """Coordinator routes branch location query to Customer Support agent."""
    sid = create_session()
    msgs = send_message(sid, "Where are your branches in California?")

    last = get_last_assistant_message(msgs)
    assert last is not None
    assert last["sender"] == "CustomerSupport", f"Expected CustomerSupport, got {last['sender']}"
    assert "California" in last["text"] or "Los Angeles" in last["text"], f"No CA info: {last['text']}"
    print(f"  PASS: CustomerSupport agent returned branches: {last['text'][:100]}")


def test_coordinator_to_sales():
    """Coordinator routes loan inquiry to Sales agent."""
    sid = create_session()
    msgs = send_message(sid, "What loan offers do you have available?")

    last = get_last_assistant_message(msgs)
    assert last is not None
    assert last["sender"] == "Sales", f"Expected Sales, got {last['sender']}"
    assert "loan" in last["text"].lower(), f"No loan info: {last['text']}"
    print(f"  PASS: Sales agent responded: {last['text'][:100]}")


def test_multi_turn_conversation():
    """Sales agent handles follow-up questions in the same session."""
    sid = create_session()

    # Turn 1: Initial loan inquiry
    msgs = send_message(sid, "What loan offers do you have?")
    last = get_last_assistant_message(msgs)
    assert last["sender"] == "Sales", f"Turn 1: Expected Sales, got {last['sender']}"

    # Turn 2: Follow-up with specific numbers
    msgs = send_message(sid, "I want a personal loan for 50000 over 5 years. What would my monthly payment be?")
    last = get_last_assistant_message(msgs)
    assert last["sender"] == "Sales", f"Turn 2: Expected Sales, got {last['sender']}"
    assert "$" in last["text"] or "monthly" in last["text"].lower(), f"No payment info: {last['text']}"
    print(f"  PASS: Multi-turn payment calculation: {last['text'][:150]}")


def test_sub_agent_transfer():
    """Sales agent transfers to Transactions agent when asked about balance."""
    sid = create_session()

    # Start with sales
    send_message(sid, "What loan offers do you have?")

    # Ask for balance (should trigger transfer to transactions)
    msgs = send_message(sid, "Actually, can you check the balance on my account Acc001 first?")
    last = get_last_assistant_message(msgs)
    # Sales agent acknowledges transfer in this turn
    assert last["sender"] == "Sales", f"Expected Sales acknowledgment, got {last['sender']}"
    assert "transfer" in last["text"].lower(), f"Expected transfer acknowledgment: {last['text']}"

    # Follow-up turn: Transactions agent now handles the request
    msgs = send_message(sid, "Yes please check my balance on Acc001")
    last = get_last_assistant_message(msgs)
    assert last["sender"] == "Transactions", f"Expected Transactions after transfer, got {last['sender']}"
    assert "50,000" in last["text"] or "50000" in last["text"], f"Balance not in response: {last['text']}"
    print(f"  PASS: Sub-agent transfer Sales→Transactions: {last['text'][:100]}")


# --- Runner ---

ALL_TESTS = [
    test_coordinator_to_transactions,
    test_coordinator_to_customer_support,
    test_coordinator_to_sales,
    test_multi_turn_conversation,
    test_sub_agent_transfer,
]


def main():
    print(f"Running {len(ALL_TESTS)} integration tests against {BASE_URL}\n")
    passed = 0
    failed = 0

    for test_fn in ALL_TESTS:
        name = test_fn.__name__
        print(f"[RUN] {name}")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except requests.exceptions.ConnectionError:
            print(f"  FAIL: Cannot connect to {BASE_URL}. Is the server running?")
            failed += 1
        except requests.exceptions.ReadTimeout:
            print(f"  FAIL: Request timed out after {TIMEOUT}s (possible infinite loop)")
            failed += 1
        except Exception as e:
            print(f"  FAIL: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
