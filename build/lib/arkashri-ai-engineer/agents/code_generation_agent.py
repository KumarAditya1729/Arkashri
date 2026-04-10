# pyre-ignore-all-errors
"""
Code Generation Agent — uses GPT-4o to write new Arkashri features
from a plain-English task prompt. Supports API endpoints, React components,
database migrations, and blockchain logic.
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
logger = structlog.get_logger("ai_engineer.code_gen")

# ─── Tools ────────────────────────────────────────────────────────────────────

@tool
def read_file(file_path: str) -> str:
    """Read an existing source file for context before writing new code."""
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Cannot read file: {e}"

@tool
def write_file(file_path: str, content: str) -> str:
    """Write generated code to a new or existing file."""
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return f"File written: {file_path}"
    except Exception as e:
        return f"Cannot write file: {e}"

@tool
def list_directory(directory_path: str) -> str:
    """List files in a directory to understand the project structure."""
    try:
        result = subprocess.run(
            ["ls", "-la", directory_path],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout or "Empty directory."
    except Exception as e:
        return f"Cannot list directory: {e}"

@tool
def run_read_only_command(command: str) -> str:
    """Run a safe read-only shell command such as grep or git log."""
    SAFE_PREFIXES = ("grep", "git log", "git diff", "find", "cat ", "ls ")
    if not any(command.startswith(p) for p in SAFE_PREFIXES):
        return "Blocked: only read-only commands allowed."
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        return result.stdout or result.stderr or "No output."
    except Exception as e:
        return f"Command failed: {e}"

# ─── Agent ────────────────────────────────────────────────────────────────────

CODE_GEN_TOOLS = [read_file, write_file, list_directory, run_read_only_command]

CODE_GEN_PROMPT = PromptTemplate.from_template("""
You are a senior full-stack engineer working on the Arkashri audit platform.
Your task is to implement a new feature exactly as described.

Task:
{task_prompt}

Project root: /Users/adityashrivastava/Desktop/company_1/

Instructions:
- Explore the existing code with tools to understand conventions before writing.
- Follow the existing patterns: FastAPI routers (Python), Next.js pages (TypeScript), SQLAlchemy models.
- Write complete, production-ready code. Do NOT use placeholder comments.
- When done, confirm the file paths you wrote.

Available tools: {tools}
Tool names: {tool_names}

Scratchpad:
{agent_scratchpad}
""")

def build_code_gen_agent() -> AgentExecutor:
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, api_key=os.getenv("OPENAI_API_KEY"))
    agent = create_react_agent(llm, CODE_GEN_TOOLS, CODE_GEN_PROMPT)
    return AgentExecutor(agent=agent, tools=CODE_GEN_TOOLS, verbose=True, max_iterations=12)

def code_generation_node(state: dict) -> dict:
    """LangGraph node: generate new feature code from a task prompt."""
    task_prompt = state.get("task_prompt", "Describe the feature to build.")
    logger.info("Code Generation Agent triggered", task=task_prompt[:120])
    try:
        executor = build_code_gen_agent()
        result = executor.invoke({"task_prompt": task_prompt})
        patch = result.get("output", "")
        logger.info("Code generation complete", output_length=len(patch))
        return {"code_patch": patch}
    except Exception as e:
        logger.error("Code Generation Agent failed", error=str(e))
        return {"code_patch": f"# ERROR: {e}"}

