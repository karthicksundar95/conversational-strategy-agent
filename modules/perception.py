# modules/perception.py

from typing import List, Optional
from pydantic import BaseModel
from modules.model_manager import ModelManager
from modules.tools import load_prompt, extract_json_block
from core.context import AgentContext

import json


# Optional logging fallback
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

model = ModelManager()


prompt_path = "prompts/perception_prompt.txt"

class PerceptionResult(BaseModel):
    intent: str
    entities: List[str] = []
    tool_hint: Optional[str] = None
    tags: List[str] = []
    selected_servers: List[str] = []  # 🆕 NEW field

async def extract_perception(user_input: str, mcp_server_descriptions: dict, historical_context: Optional[str] = None) -> PerceptionResult:
    """
    Extracts perception details and selects relevant MCP servers based on the user query.
    
    Args:
        user_input: The user's query
        mcp_server_descriptions: Dictionary of MCP server descriptions
        historical_context: Optional historical conversation context to inform tool selection
    """

    server_list = []
    for server_id, server_info in mcp_server_descriptions.items():
        description = server_info.get("description", "No description available")
        server_list.append(f"- {server_id}: {description}")

    servers_text = "\n".join(server_list)

    prompt_template = load_prompt(prompt_path)
    
    # Enhance user input with historical context if provided
    enhanced_user_input = user_input
    if historical_context:
        enhanced_user_input = f"""{user_input}

Relevant context from previous conversations:
{historical_context}

Use this context to inform your tool selection and search strategy."""

    prompt = prompt_template.format(
        servers_text=servers_text,
        user_input=enhanced_user_input
    )
    

    try:
        raw = await model.generate_text(prompt)
        raw = raw.strip()
        log("perception", f"Raw output: {raw}")

        # Try parsing into PerceptionResult
        json_block = extract_json_block(raw)
        result = json.loads(json_block)

        # If selected_servers missing, fallback
        if "selected_servers" not in result:
            result["selected_servers"] = list(mcp_server_descriptions.keys())
        print("result", result)

        return PerceptionResult(**result)

    except Exception as e:
        log("perception", f"⚠️ Perception failed: {e}")
        # Fallback: select all servers
        return PerceptionResult(
            intent="unknown",
            entities=[],
            tool_hint=None,
            tags=[],
            selected_servers=list(mcp_server_descriptions.keys())
        )


async def run_perception(context: AgentContext, user_input: Optional[str] = None, historical_context: Optional[str] = None):
    
    """
    Clean wrapper to call perception from context.
    
    Args:
        context: AgentContext with user input and server descriptions
        user_input: Optional override for user input
        historical_context: Optional historical conversation context
    """
    return await extract_perception(
        user_input = user_input or context.user_input,
        mcp_server_descriptions=context.mcp_server_descriptions,
        historical_context=historical_context
    )

