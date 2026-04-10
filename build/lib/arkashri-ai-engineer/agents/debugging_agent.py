# pyre-ignore-all-errors
"""
Debugging Agent — reads incident tracebacks from logs and uses GPT-4o
to identify the root cause and generate a code patch.
"""
from __future__ import annotations
import os
import subprocess
import structlog  # type: ignore[import]
from langchain_openai import ChatOpenAI  # type: ignore[import]
from langchain.agents import AgentExecutor, create_react_agent  # type: ignore[import]
from langchain.tools import tool  # type: ignore[import]
from langchain.prompts import PromptTemplate  # type: ignore[import]
from dotenv import load_dotenv  # type: ignore[import]

load_dotenv()
logger = structlog.get_logger("ai_engineer.debugging")

# ─── Tools ───────────────────────────────────────────────────────────────────

@tool
def read_error_logs(log_path: str) -> str:
    """Read the last 100 lines of a log file to find recent errors."""
    try:
        result = subprocess.run(
            ["tail", "-n", "100", log_path],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "Log file empty or not found."
    except Exception as e:
        return f"Failed to read log: {e}"

@tool
def scan_source_file(file_path: str) -> str:
    """Read the contents of a source code file for analysis."""
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Failed to read file: {e}"

@tool
def write_patch(file_path: str, new_content: str) -> str:
    """Write a corrected file to disk as a code patch."""
    try:
        with open(file_path, "w") as f:
            f.write(new_content)
        return f"Patch written to {file_path}"
    except Exception as e:
        return f"Failed to write patch: {e}"

@tool
def run_shell_command(command: str) -> str:
    """Execute a safe read-only shell command (e.g. git diff, grep, find)."""
    SAFE_PREFIXES = ("git diff", "git log", "grep", "find", "cat ", "ls ")
    if not any(command.startswith(p) for p in SAFE_PREFIXES):
        return "Command blocked: only read-only commands are allowed."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout or result.stderr or "No output."
    except Exception as e:
        return f"Command failed: {e}"

# ─── Agent ────────────────────────────────────────────────────────────────────

DEBUGGING_TOOLS = [read_error_logs, scan_source_file, write_patch, run_shell_command]

DEBUGGING_PROMPT = PromptTemplate.from_template("""
You are an expert Python/TypeScript software engineer and debugging agent for the Arkashri platform.
Your task is to diagnose production incidents and generate minimal, correct code patches.

Incident Report:
{incident_report}

Instructions:
1. Use the available tools to find relevant log files and source code.
2. Identify the root cause of the bug.
3. Generate a minimal, targeted code patch to fix it.
4. Output a plain-text unified diff of the change.

Available tools: {tools}
Tool names: {tool_names}

Scratchpad:
{agent_scratchpad}
""")

def build_debugging_agent() -> AgentExecutor:
    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"))
    agent = create_react_agent(llm, DEBUGGING_TOOLS, DEBUGGING_PROMPT)
    return AgentExecutor(agent=agent, tools=DEBUGGING_TOOLS, verbose=True, max_iterations=8)

def debug_node(state: dict) -> dict:
    """LangGraph node: run the Debugging Agent against the incident report."""
    incident = state.get("incident_report", "Unknown production error.")
    logger.info("Debugging Agent triggered", incident=incident)
    try:
        executor = build_debugging_agent()
        result = executor.invoke({"incident_report": incident})
        patch = result.get("output", "")
        logger.info("Patch generated", patch_length=len(patch))
        return {"code_patch": patch}
    except Exception as e:
        logger.error("Debugging Agent failed", error=str(e))
        return {"code_patch": f"# ERROR: Debugging agent failed — {e}"}

