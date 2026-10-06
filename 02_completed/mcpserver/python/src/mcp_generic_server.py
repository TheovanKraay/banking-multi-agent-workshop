"""
Banking MCP Server: GENERIC (non-Cosmos) tools only.

Used in two-server mode next to the Agent MCP Server (Rust, ../../agent-mcp-server). This server
keeps ONLY the tools that do not touch Cosmos DB. The Cosmos-backed tools (bank_balance,
get_transaction_history, get_offer_information, create_account, service_request, bank_transfer)
are declared in YAML under ../../agent-mcp-server/tools and served by the Agent MCP Server.

Tools kept here (from mcp_http_server.py):
  - transfer_to_sales_agent / transfer_to_customer_support_agent / transfer_to_transactions_agent
    (LangGraph agent hand-offs, not data operations)
  - calculate_monthly_payment (pure math)
  - get_branch_location (static reference data)

Run (Streamable HTTP):
    set PORT=8090
    python mcp_generic_server.py
"""
import os
import logging
from typing import Annotated, Any, Dict, List

try:
    # Official Model Context Protocol SDK (matches the original mcp_http_server.py).
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - fallback for the standalone FastMCP distribution
    from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("banking-generic-mcp")

port = int(os.getenv("PORT", "8090"))
mcp = FastMCP("BankingGenericTools", host="0.0.0.0", port=port)

# --- Agent hand-off tools (LangGraph). Imported lazily so the server also runs standalone. ------
try:
    from langgraph.types import Command
    from langchain_core.tools.base import InjectedToolCallId

    def _register_transfer(agent_name: str):
        tool_name = f"transfer_to_{agent_name}"

        @mcp.tool(name=tool_name, description=f"Transfer the conversation to the {agent_name.replace('_', ' ')}.")
        def _transfer(tool_call_id: Annotated[str, InjectedToolCallId], **kwargs):
            state = kwargs.get("state", {})
            tool_message = {
                "role": "tool",
                "content": f"Successfully transferred to {agent_name.replace('_', ' ')}",
                "name": tool_name,
                "tool_call_id": tool_call_id,
            }
            return Command(
                goto=agent_name,
                graph=Command.PARENT,
                update={"messages": state.get("messages", []) + [tool_message]},
            )

    for _agent in ("sales_agent", "customer_support_agent", "transactions_agent"):
        _register_transfer(_agent)
    logger.info("Registered LangGraph agent hand-off tools.")
except Exception as exc:  # noqa: BLE001 - optional dependency for standalone/smoke runs
    logger.warning("LangGraph not available; agent hand-off tools not registered (%s).", exc)


@mcp.tool()
def calculate_monthly_payment(loan_amount: float, years: int) -> float:
    """Calculate the monthly payment for a loan (fixed 5% annual rate)."""
    interest_rate = 0.05
    monthly_rate = interest_rate / 12
    total_payments = years * 12
    if monthly_rate == 0:
        return loan_amount / total_payments
    monthly_payment = (loan_amount * monthly_rate * (1 + monthly_rate) ** total_payments) / \
                      ((1 + monthly_rate) ** total_payments - 1)
    return round(monthly_payment, 2)


@mcp.tool()
def get_branch_location(state: str) -> Dict[str, List[str]]:
    """Find bank branch locations in a specific US state.

    Args:
        state: The US state name to search for branch locations

    Returns:
        Dictionary with counties and their branch locations
    """
    branches = {
            "Alabama": {"Jefferson County": ["Central Bank - Birmingham", "Trust Bank - Hoover"],
                        "Mobile County": ["Central Bank - Mobile", "Trust Bank - Prichard"]},
            "Alaska": {"Anchorage": ["Central Bank - Anchorage", "Trust Bank - Eagle River"],
                    "Fairbanks North Star Borough": ["Central Bank - Fairbanks", "Trust Bank - North Pole"]},
            "Arizona": {"Maricopa County": ["Central Bank - Phoenix", "Trust Bank - Scottsdale"],
                        "Pima County": ["Central Bank - Tucson", "Trust Bank - Oro Valley"]},
            "Arkansas": {"Pulaski County": ["Central Bank - Little Rock", "Trust Bank - North Little Rock"],
                        "Benton County": ["Central Bank - Bentonville", "Trust Bank - Rogers"]},
            "California": {"Los Angeles County": ["Central Bank - Los Angeles", "Trust Bank - Long Beach"],
                        "San Diego County": ["Central Bank - San Diego", "Trust Bank - Chula Vista"]},
            "Colorado": {"Denver County": ["Central Bank - Denver", "Trust Bank - Aurora"],
                        "El Paso County": ["Central Bank - Colorado Springs", "Trust Bank - Fountain"]},
            "Connecticut": {"Fairfield County": ["Central Bank - Bridgeport", "Trust Bank - Stamford"],
                            "Hartford County": ["Central Bank - Hartford", "Trust Bank - New Britain"]},
            "Delaware": {"New Castle County": ["Central Bank - Wilmington", "Trust Bank - Newark"],
                        "Sussex County": ["Central Bank - Seaford", "Trust Bank - Lewes"]},
            "Florida": {"Miami-Dade County": ["Central Bank - Miami", "Trust Bank - Hialeah"],
                        "Orange County": ["Central Bank - Orlando", "Trust Bank - Winter Park"]},
            "Georgia": {"Fulton County": ["Central Bank - Atlanta", "Trust Bank - Sandy Springs"],
                        "Cobb County": ["Central Bank - Marietta", "Trust Bank - Smyrna"]},
            "Hawaii": {"Honolulu County": ["Central Bank - Honolulu", "Trust Bank - Pearl City"],
                    "Maui County": ["Central Bank - Kahului", "Trust Bank - Lahaina"]},
            "Idaho": {"Ada County": ["Central Bank - Boise", "Trust Bank - Meridian"],
                    "Canyon County": ["Central Bank - Nampa", "Trust Bank - Caldwell"]},
            "Illinois": {"Cook County": ["Central Bank - Chicago", "Trust Bank - Evanston"],
                        "DuPage County": ["Central Bank - Naperville", "Trust Bank - Wheaton"]},
            "Indiana": {"Marion County": ["Central Bank - Indianapolis", "Trust Bank - Lawrence"],
                        "Lake County": ["Central Bank - Gary", "Trust Bank - Hammond"]},
            "Iowa": {"Polk County": ["Central Bank - Des Moines", "Trust Bank - West Des Moines"],
                    "Linn County": ["Central Bank - Cedar Rapids", "Trust Bank - Marion"]},
            "Kansas": {"Sedgwick County": ["Central Bank - Wichita", "Trust Bank - Derby"],
                    "Johnson County": ["Central Bank - Overland Park", "Trust Bank - Olathe"]},
            "Kentucky": {"Jefferson County": ["Central Bank - Louisville", "Trust Bank - Jeffersontown"],
                        "Fayette County": ["Central Bank - Lexington", "Trust Bank - Nicholasville"]},
            "Louisiana": {"Orleans Parish": ["Central Bank - New Orleans", "Trust Bank - Metairie"],
                        "East Baton Rouge Parish": ["Central Bank - Baton Rouge", "Trust Bank - Zachary"]},
            "Maine": {"Cumberland County": ["Central Bank - Portland", "Trust Bank - South Portland"],
                    "Penobscot County": ["Central Bank - Bangor", "Trust Bank - Brewer"]},
            "Maryland": {"Baltimore County": ["Central Bank - Baltimore", "Trust Bank - Towson"],
                        "Montgomery County": ["Central Bank - Rockville", "Trust Bank - Bethesda"]},
            "Massachusetts": {"Suffolk County": ["Central Bank - Boston", "Trust Bank - Revere"],
                            "Worcester County": ["Central Bank - Worcester", "Trust Bank - Leominster"]},
            "Michigan": {"Wayne County": ["Central Bank - Detroit", "Trust Bank - Dearborn"],
                        "Oakland County": ["Central Bank - Troy", "Trust Bank - Farmington Hills"]},
            "Minnesota": {"Hennepin County": ["Central Bank - Minneapolis", "Trust Bank - Bloomington"],
                        "Ramsey County": ["Central Bank - Saint Paul", "Trust Bank - Maplewood"]},
            "Mississippi": {"Hinds County": ["Central Bank - Jackson", "Trust Bank - Clinton"],
                            "Harrison County": ["Central Bank - Gulfport", "Trust Bank - Biloxi"]},
            "Missouri": {"Jackson County": ["Central Bank - Kansas City", "Trust Bank - Independence"],
                        "St. Louis County": ["Central Bank - St. Louis", "Trust Bank - Florissant"]},
            "Montana": {"Yellowstone County": ["Central Bank - Billings", "Trust Bank - Laurel"],
                        "Missoula County": ["Central Bank - Missoula", "Trust Bank - Lolo"]},
            "Nebraska": {"Douglas County": ["Central Bank - Omaha", "Trust Bank - Bellevue"],
                        "Lancaster County": ["Central Bank - Lincoln", "Trust Bank - Waverly"]},
            "Nevada": {"Clark County": ["Central Bank - Las Vegas", "Trust Bank - Henderson"],
                    "Washoe County": ["Central Bank - Reno", "Trust Bank - Sparks"]},
            "New Hampshire": {"Hillsborough County": ["Central Bank - Manchester", "Trust Bank - Nashua"],
                            "Rockingham County": ["Central Bank - Portsmouth", "Trust Bank - Derry"]},
            "New Jersey": {"Essex County": ["Central Bank - Newark", "Trust Bank - East Orange"],
                        "Bergen County": ["Central Bank - Hackensack", "Trust Bank - Teaneck"]},
            "New Mexico": {"Bernalillo County": ["Central Bank - Albuquerque", "Trust Bank - Rio Rancho"],
                        "Santa Fe County": ["Central Bank - Santa Fe", "Trust Bank - Eldorado"]},
            "New York": {"New York County": ["Central Bank - Manhattan", "Trust Bank - Harlem"],
                        "Kings County": ["Central Bank - Brooklyn", "Trust Bank - Williamsburg"]},
            "North Carolina": {"Mecklenburg County": ["Central Bank - Charlotte", "Trust Bank - Matthews"],
                            "Wake County": ["Central Bank - Raleigh", "Trust Bank - Cary"]},
            "North Dakota": {"Cass County": ["Central Bank - Fargo", "Trust Bank - West Fargo"],
                            "Burleigh County": ["Central Bank - Bismarck", "Trust Bank - Lincoln"]},
            "Ohio": {"Cuyahoga County": ["Central Bank - Cleveland", "Trust Bank - Parma"],
                    "Franklin County": ["Central Bank - Columbus", "Trust Bank - Dublin"]},
            "Oklahoma": {"Oklahoma County": ["Central Bank - Oklahoma City", "Trust Bank - Edmond"],
                        "Tulsa County": ["Central Bank - Tulsa", "Trust Bank - Broken Arrow"]},
            "Oregon": {"Multnomah County": ["Central Bank - Portland", "Trust Bank - Gresham"],
                    "Lane County": ["Central Bank - Eugene", "Trust Bank - Springfield"]},
            "Pennsylvania": {"Philadelphia County": ["Central Bank - Philadelphia", "Trust Bank - Germantown"],
                            "Allegheny County": ["Central Bank - Pittsburgh", "Trust Bank - Bethel Park"]},
            "Rhode Island": {"Providence County": ["Central Bank - Providence", "Trust Bank - Cranston"],
                            "Kent County": ["Central Bank - Warwick", "Trust Bank - Coventry"]},
            "South Carolina": {"Charleston County": ["Central Bank - Charleston", "Trust Bank - Mount Pleasant"],
                            "Richland County": ["Central Bank - Columbia", "Trust Bank - Forest Acres"]},
            "South Dakota": {"Minnehaha County": ["Central Bank - Sioux Falls", "Trust Bank - Brandon"],
                            "Pennington County": ["Central Bank - Rapid City", "Trust Bank - Box Elder"]},
            "Tennessee": {"Davidson County": ["Central Bank - Nashville", "Trust Bank - Antioch"],
                        "Shelby County": ["Central Bank - Memphis", "Trust Bank - Bartlett"]},
            "Texas": {"Harris County": ["Central Bank - Houston", "Trust Bank - Pasadena"],
                    "Dallas County": ["Central Bank - Dallas", "Trust Bank - Garland"]},
            "Utah": {"Salt Lake County": ["Central Bank - Salt Lake City", "Trust Bank - West Valley City"],
                    "Utah County": ["Central Bank - Provo", "Trust Bank - Orem"]},
            "Vermont": {"Chittenden County": ["Central Bank - Burlington", "Trust Bank - South Burlington"],
                        "Rutland County": ["Central Bank - Rutland", "Trust Bank - Killington"]},
            "Virginia": {"Fairfax County": ["Central Bank - Fairfax", "Trust Bank - Reston"],
                        "Virginia Beach": ["Central Bank - Virginia Beach", "Trust Bank - Chesapeake"]},
            "Washington": {"King County": ["Central Bank - Seattle", "Trust Bank - Bellevue"],
                        "Pierce County": ["Central Bank - Tacoma", "Trust Bank - Lakewood"]},
            "West Virginia": {"Kanawha County": ["Central Bank - Charleston", "Trust Bank - South Charleston"],
                            "Berkeley County": ["Central Bank - Martinsburg", "Trust Bank - Hedgesville"]},
            "Wisconsin": {"Milwaukee County": ["Central Bank - Milwaukee", "Trust Bank - Wauwatosa"],
                        "Dane County": ["Central Bank - Madison", "Trust Bank - Fitchburg"]},
            "Wyoming": {"Laramie County": ["Central Bank - Cheyenne", "Trust Bank - Ranchettes"],
                        "Natrona County": ["Central Bank - Casper", "Trust Bank - Mills"]}
        }
    return branches.get(state, {"Unknown County": ["No branches available"]})


@mcp.tool()
def server_info() -> Dict[str, Any]:
    """Information about this generic (non-Cosmos) banking MCP server."""
    return {
        "server_name": "Banking Generic (non-Cosmos) MCP Server",
        "version": "1.0.0",
        "transport": "streamable_http",
        "tools": ["transfer_to_*_agent", "calculate_monthly_payment", "get_branch_location", "server_info"],
        "cosmos_backed_tools_served_by": "Agent MCP Server (../../agent-mcp-server/tools/*.yaml)",
    }


if __name__ == "__main__":
    logger.info("Starting Banking Generic (non-Cosmos) MCP server on port %s (streamable-http)", port)
    mcp.run(transport="streamable-http")
