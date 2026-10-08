# Agent MCP Server tools for the banking workshop

The Cosmos DB-backed banking tools are **declared in YAML** in [tools/](tools/) and served by the
[Agent MCP Server](https://github.com/TheovanKraay/agent-mcp-server), a Rust MCP server built on the
Azure Cosmos DB Rust SDK. The tools are no longer hand-written Python handlers.

```
LangGraph app (python/langgraph)
  ├── banking_tools → generic banking MCP server   (mcpserver/python/src/mcp_generic_server.py)
  │                    transfer_to_*_agent, calculate_monthly_payment, get_branch_location
  └── agent_tools   → Agent MCP Server (Rust)      (this folder: tools/*.yaml)
                       bank_balance, get_transaction_history, get_offer_information,
                       create_account, service_request, bank_transfer
```

This mode is **opt-in**. Without `AGENT_MCP_URL` the app uses the original single banking MCP server.

## How the YAML in this folder becomes MCP tools

This folder contains **configuration only**. There is no server code here. The Agent MCP Server is a
separate, generic binary (or container image) built from its own repository. When it starts, it is
pointed at this folder:

```
agent-mcp-server serve --config 02_completed/mcpserver/agent-mcp-server/tools
```

```
tools/                          Agent MCP Server at startup
  _server.yaml                  1. reads every *.yaml in tools/ and merges them
  bank_balance.yaml             2. fills ${COSMOS_ENDPOINT} etc. from environment variables
  bank_transfer.yaml    ──────► 3. validates everything; any error = the server does not start
  create_account.yaml           4. turns each tool into an MCP tool (name, description, input schema)
  ...                           5. connects to Cosmos DB and opens AccountsData / OffersData
                                6. serves http://localhost:8080/mcp
                                              │
LangGraph app  ◄───── tools/list, tools/call ─┘   (the app never reads these files)
```

* **`_server.yaml`** holds what every tool shares: the Cosmos DB account and database, the Azure
  OpenAI embedding deployment, and defaults (read-only unless a tool opts in to writes, timeouts,
  and the token claims used for tenant and user).
* **Each other file is one tool**: description, the Cosmos DB operation, the inputs the agent may
  pass, and the fields to return. The server interprets these at runtime; no code is generated.
* **Changes need a restart.** Tools are loaded once at startup, so after editing a file, stop and
  start the server (about a second).
* **The app only sees MCP.** `banking_agents.py` discovers the tools over MCP and gives them to
  agents by name, so tool names must match the lists in `setup_agents()`.

Full details: the server's [How it works](https://github.com/TheovanKraay/agent-mcp-server#how-it-works)
and [YAML reference](https://github.com/TheovanKraay/agent-mcp-server/blob/main/docs/yaml-reference.md).

## What changed compared with `mcp_http_server.py`

| Tool | YAML operation | Notes |
|---|---|---|
| `bank_balance` | `sequence`: point read + ownership `assert` | Point read on `[tenantId, accountId]` instead of a cross-partition f-string query |
| `get_transaction_history` | partition-scoped parameterised `query` | Needs `tenantId` (from the agent context) |
| `get_offer_information` | `vector-search` with `where` filter | Server embeds the prompt with Azure OpenAI; `type = 'Term'` and `accountType` filters as before |
| `create_account` | `create` | Account numbers are `A<uuid>` instead of a sequential number from a cross-partition scan |
| `service_request` | `create` | Same document shape |
| `bank_transfer` | `sequence`: two reads, two asserts, two transactional batches | Each leg (balance change + transaction record) is atomic; the debit is ETag-pinned to the funds check (a concurrent change makes the server re-read and re-check); destination is verified before any write. Records do not carry `accountBalance`. |

All caller values are bound as Cosmos DB parameters (the original server built SQL with f-strings).
Writes are explicitly enabled per tool, and inputs are validated against closed schemas.

## Run end to end (local)

Prerequisites: Rust (`rustup`), Python 3.12+, Azure CLI logged in (`az login`) with data-plane
access to the workshop's Cosmos DB and Azure OpenAI resources (`azd provision` grants this to the
deploying user).

```powershell
# 0. Build the server once
git clone https://github.com/TheovanKraay/agent-mcp-server Q:\repos\agent-mcp-server
cd Q:\repos\agent-mcp-server; cargo build --release

# 1. Python environments (once)
python -m venv $env:USERPROFILE\.venvs\banking-app
& $env:USERPROFILE\.venvs\banking-app\Scripts\python.exe -m pip install -r <repo>\02_completed\python\langgraph\src\app\requirements.txt
python -m venv $env:USERPROFILE\.venvs\banking-smoke
& $env:USERPROFILE\.venvs\banking-smoke\Scripts\python.exe -m pip install -r <repo>\02_completed\mcpserver\agent-mcp-server\requirements.txt
```

Terminal 1, Agent MCP Server (:8080):

```powershell
$env:DEV_BYPASS_AUTH="true"   # local development only, see "Security" below
$env:COSMOS_ENDPOINT="https://<account>.documents.azure.com:443/"
$env:COSMOS_DATABASE="MultiAgentBanking"
$env:OPENAI_ENDPOINT="https://<aoai>.openai.azure.com/"
$env:OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-3-small"
Q:\repos\agent-mcp-server\target\release\agent-mcp-server.exe serve --config <repo>\02_completed\mcpserver\agent-mcp-server\tools
```

Expect `container ready ... AccountsData`, `container ready ... OffersData`, then
`listening on http://127.0.0.1:8080/mcp (6 tools)`.

Terminal 2, generic banking server (:8090):

```powershell
cd <repo>\02_completed\mcpserver\python\src
$env:PORT="8090"; & $env:USERPROFILE\.venvs\banking-app\Scripts\python.exe mcp_generic_server.py
```

Terminal 3, LangGraph API (:63280):

```powershell
cd <repo>\02_completed\python\langgraph
$env:PYTHONUTF8="1"
$env:MCP_SERVER_BASE_URL="http://localhost:8090"
$env:AGENT_MCP_URL="http://localhost:8080/mcp"
& $env:USERPROFILE\.venvs\banking-app\Scripts\python.exe -m uvicorn src.app.banking_agents_api:app --host 0.0.0.0 --port 63280
```

On the first request the log shows `Loaded 6 tools from the Agent MCP Server`.

Terminal 4, frontend: `cd <repo>\02_completed\frontend; npm install; npm start`, then open
http://localhost:4200 and ask *"What is the balance of my account Acc001?"* (tenant `Contoso`, user
`Mark`).

### Verify without the UI

```powershell
# Both MCP servers directly, no LLM. Flags: --write (create, file a request, transfer $1),
# --no-search (skip vector search, e.g. on the emulator), --agent-only (skip the generic server)
cd <repo>\02_completed\mcpserver\agent-mcp-server
& $env:USERPROFILE\.venvs\banking-smoke\Scripts\python.exe smoke_test.py

# Through the agents
$base="http://localhost:63280/tenant/Contoso/user/Mark"
$sid=(Invoke-RestMethod -Method Post "$base/sessions").sessionId
Invoke-RestMethod -Method Post "$base/sessions/$sid/completion" -ContentType application/json `
  -Body (ConvertTo-Json "What is the balance of my account Acc001?")
```

## Adding a tool

Add a YAML file to [tools/](tools/), run
`agent-mcp-server validate --config tools`, restart the server, and add the tool name to the agent's
tool list in `python/langgraph/src/app/banking_agents.py`. See the server's
[YAML reference](https://github.com/TheovanKraay/agent-mcp-server/blob/main/docs/yaml-reference.md).

## Security

Locally the server runs with `DEV_BYPASS_AUTH=true` and the agents pass `tenantId`/`userId` from
the session context. In Azure:

1. Run the server with `AUTH_TENANT_ID` and `AUTH_AUDIENCE` (no bypass) and a managed identity that
   has Cosmos DB data-plane and Azure OpenAI access.
2. Set `AGENT_MCP_SCOPE=api://<server-app-id>/.default` for the LangGraph app. It then sends an
   Entra ID token from its managed identity (or `az login` locally) with every request.
3. Issue `bank_tenant` / `bank_user` claims to callers (for example via on-behalf-of user tokens).
   `tools/_server.yaml` makes the server take tenant and user from those claims and reject
   mismatching values from the model.

To try claim enforcement locally without an IdP:
`$env:DEV_CLAIMS='{"bank_tenant":"Contoso","bank_user":"Mark"}'` (with `DEV_BYPASS_AUTH=true`).
