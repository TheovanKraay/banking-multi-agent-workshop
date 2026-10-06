"""Two-server MCP smoke test for the Banking Multi-Agent Workshop.

Talks directly to both MCP servers (no LLM involved):
  * Agent MCP Server (Rust, declarative YAML tools backed by Cosmos DB)  -> AGENT_MCP_URL
  * Generic banking MCP server (Python, non-Cosmos tools)                 -> BANKING_MCP_URL

Usage:
    python smoke_test.py            # read-only checks
    python smoke_test.py --write    # also create an account, a service request and a transfer

Environment:
    AGENT_MCP_URL    default http://localhost:8080/mcp
    BANKING_MCP_URL  default http://localhost:8090/mcp/  (set to "" to skip)
    AGENT_MCP_TOKEN  optional bearer token for the Agent MCP Server
    TENANT_ID / USER_ID  default Contoso / Mark
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

AGENT_MCP_URL = os.getenv("AGENT_MCP_URL", "http://localhost:8080/mcp")
BANKING_MCP_URL = os.getenv("BANKING_MCP_URL", "http://localhost:8090/mcp/")
TENANT = os.getenv("TENANT_ID", "Contoso")
USER = os.getenv("USER_ID", "Mark")


def payload(result):
    text = result.content[0].text if result.content else ""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return text


async def call(session, name, args, expect_error=False):
    result = await session.call_tool(name, args)
    body = payload(result)
    status = "ERROR" if result.isError else "OK"
    print(f"  {name:<26} {status:<6} {json.dumps(body)[:240]}")
    if bool(result.isError) != expect_error:
        raise SystemExit(f"Unexpected result from {name}")
    return body


async def agent_server(write: bool):
    headers = {}
    if os.getenv("AGENT_MCP_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['AGENT_MCP_TOKEN']}"
    print(f"\n== Agent MCP Server (Cosmos DB tools) at {AGENT_MCP_URL}")
    async with streamablehttp_client(AGENT_MCP_URL, headers=headers) as (read, write_stream, _):
        async with ClientSession(read, write_stream) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            for t in tools:
                hints = t.annotations
                mode = "read-only" if hints and hints.readOnlyHint else "write"
                print(f"  tool {t.name:<26} {mode}")
            ctx = {"tenantId": TENANT, "userId": USER}

            before = await call(session, "bank_balance", {"account_number": "Acc001", **ctx})
            await call(session, "bank_balance", {"account_number": "Acc002", **ctx}, expect_error=True)
            await call(session, "get_transaction_history", {
                "accountId": "Acc001", "startDate": "2020-01-01T00:00:00Z",
                "endDate": "2030-01-01T00:00:00Z", "limit": 3, **ctx})
            offers = await call(session, "get_offer_information", {
                "user_prompt": "high interest savings with no fees", "accountType": "Savings", **ctx})
            if not offers:
                raise SystemExit("get_offer_information returned no offers")
            await call(session, "bank_balance", {"account_number": "Acc001' OR '1'='1", **ctx}, expect_error=True)

            if write:
                await call(session, "create_account", {"account_holder": "Smoke Test", "balance": 10, **ctx})
                await call(session, "service_request", {
                    "requestSummary": "Smoke test: please call me back", "recipientPhone": "555-0100", **ctx})
                await call(session, "bank_transfer", {
                    "fromAccount": "Acc001", "toAccount": "Acc003", "amount": 1, **ctx})
                after = await call(session, "bank_balance", {"account_number": "Acc001", **ctx})
                if round(before["balance"] - after["balance"], 2) != 1:
                    raise SystemExit("bank_transfer did not debit the source account")
                await call(session, "bank_transfer", {
                    "fromAccount": "Acc001", "toAccount": "Acc003", "amount": 999999, **ctx}, expect_error=True)


async def banking_server():
    if not BANKING_MCP_URL:
        return
    print(f"\n== Generic banking MCP server (non-Cosmos tools) at {BANKING_MCP_URL}")
    async with streamablehttp_client(BANKING_MCP_URL) as (read, write_stream, _):
        async with ClientSession(read, write_stream) as session:
            await session.initialize()
            print("  tools:", ", ".join(t.name for t in (await session.list_tools()).tools))
            await call(session, "calculate_monthly_payment", {"loan_amount": 10000, "years": 5})


async def main():
    await agent_server(write="--write" in sys.argv)
    await banking_server()
    print("\nSmoke test passed.")


if __name__ == "__main__":
    asyncio.run(main())
