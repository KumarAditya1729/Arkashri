# pyre-ignore-all-errors
from typing import TypedDict, Annotated, Sequence
import operator
from langgraph.graph import StateGraph, END  # type: ignore[import]
import structlog  # type: ignore[import]

logger = structlog.get_logger("ai_engineer.orchestrator")

class AgentState(TypedDict):
    """
    The state shared between all nodes (agents) in the graph.
    """
    incident_report: str
    code_patch: str
    test_results: str
    security_clearance: bool
    deployment_status: str

# Import Agents here
from .debugging_agent import debug_node
from .testing_agent import test_node
from .security_agent import security_node
from .devops_agent import deploy_node

def route_debugging(state: AgentState):
    """Determine where to go after debugging."""
    if state.get("code_patch"):
        return "test"
    return END

def route_testing(state: AgentState):
    """Determine where to go after testing."""
    results = str(state.get("test_results", ""))
    if "PASS" in results:
        return "security"
    return "debug" # Send back to fix it

def route_security(state: AgentState):
    """Determine where to go after security scan."""
    if state.get("security_clearance"):
        return "deploy"
    return "debug" # Failed security, rewrite

# --- Build the Orchestrator Graph ---
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("debug", debug_node)
workflow.add_node("test", test_node)
workflow.add_node("security", security_node)
workflow.add_node("deploy", deploy_node)

# Add Edges
workflow.set_entry_point("debug")
workflow.add_conditional_edges("debug", route_debugging, {"test": "test", END: END})
workflow.add_conditional_edges("test", route_testing, {"security": "security", "debug": "debug"})
workflow.add_conditional_edges("security", route_security, {"deploy": "deploy", "debug": "debug"})
workflow.add_edge("deploy", END)

# Compile
engine = workflow.compile()
