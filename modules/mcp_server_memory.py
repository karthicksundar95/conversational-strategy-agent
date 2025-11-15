from mcp.server.fastmcp import FastMCP, Context
from typing import List, Optional, Dict, Any
from datetime import datetime
import yaml
from memory import MemoryManager  # Import MemoryManager to use its path structure
import json
import os
import sys
import signal
from pathlib import Path
# Add parent directory to path to import conversation_indexer and models
sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.conversation_indexer import search_conversations  # Import semantic search
from models import SearchInput, AnswerFromHistoryInput, AnswerFromHistoryOutput  # Use models from models.py for consistency

BASE_MEMORY_DIR = "memory"

# Get absolute path to config file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)  # Go up one level from modules to S9
CONFIG_PATH = os.path.join(ROOT_DIR, "config", "profiles.yaml")

# Load config
try:
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
        MEMORY_CONFIG = config.get("memory", {}).get("storage", {})
        BASE_MEMORY_DIR = MEMORY_CONFIG.get("base_dir", "memory")
except Exception as e:
    print(f"Error loading config from {CONFIG_PATH}: {e}")
    sys.exit(1)

mcp = FastMCP("memory-service")

class MemoryStore:
    def __init__(self):
        self.memory_dir = BASE_MEMORY_DIR
        # self.memory_manager = None
        self.current_session = None  # Track current session
        os.makedirs(self.memory_dir, exist_ok=True)

    def load_session(self, session_id: str):
        """Load memory manager for a specific session."""
        # self.memory_manager = MemoryManager(session_id=session_id, memory_dir=self.memory_dir)
        self.current_session = session_id

    def _list_all_memories(self) -> List[Dict]:
        """Load all memory files using MemoryManager's date-based structure"""
        all_memories = []
        base_path = self.memory_dir  # Use the simple memory_dir path
        
        for year_dir in os.listdir(base_path):
            year_path = os.path.join(base_path, year_dir)
            if not os.path.isdir(year_path):
                continue
                
            for month_dir in os.listdir(year_path):
                month_path = os.path.join(year_path, month_dir)
                if not os.path.isdir(month_path):
                    continue
                    
                for day_dir in os.listdir(month_path):
                    day_path = os.path.join(month_path, day_dir)
                    if not os.path.isdir(day_path):
                        continue
                        
                    for file in os.listdir(day_path):
                        if file.endswith('.json'):
                            try:
                                with open(os.path.join(day_path, file), 'r') as f:
                                    session_memories = json.load(f)
                                    all_memories.extend(session_memories)  # Extend instead of append
                            except Exception as e:
                                print(f"Failed to load {file}: {e}")
        
        return all_memories

    def _get_conversation_flow(self, conversation_id: str = None) -> Dict:
        """Get sequence of interactions in a conversation"""
        if conversation_id is None:
            conversation_id = self.current_session
        
        # Use the session path we already know
        session_path = os.path.join(self.memory_dir, conversation_id)
        if not os.path.exists(session_path):
            return {"error": "Conversation not found"}
        
        interactions = []
        for file in sorted(os.listdir(session_path)):
            if file.endswith('.json'):
                with open(os.path.join(session_path, file), 'r') as f:
                    interactions.append(json.load(f))
        
        return {
            "conversation_flow": [
                {
                    "query": interaction.get("query", ""),
                    "intent": interaction.get("intent", ""),
                    "tool_calls": [
                        {
                            "tool": call["tool"],
                            "args": call["args"],
                            "result_summary": call.get("result_summary", "No summary available")
                        }
                        for call in interaction.get("tool_calls", [])
                    ],
                    "final_answer": interaction.get("final_answer", ""),
                    "tags": interaction.get("tags", [])
                }
                for interaction in interactions
            ],
            "timestamp_start": interactions[0].get("timestamp") if interactions else None,
            "timestamp_end": interactions[-1].get("timestamp") if interactions else None
        }

# Initialize global memory store
memory_store = MemoryStore()

def handle_shutdown(signum, frame):
    """Global shutdown handler"""
    sys.exit(0)

@mcp.tool()
async def get_current_conversations(input: Dict) -> Dict[str, Any]:
    """Get current session interactions. Usage: input={"input":{}} result = await mcp.call_tool('get_current_conversations', input)"""
    try:
        # Use absolute paths
        memory_root = os.path.join(ROOT_DIR, "memory")  # ROOT_DIR is already defined at top
        dt = datetime.now()
        
        # List all files in today's directory
        day_path = os.path.join(
            memory_root,
            str(dt.year),
            f"{dt.month:02d}",
            f"{dt.day:02d}"
        )
        
        if not os.path.exists(day_path):
            return {"error": "No sessions found for today"}
            
        # Get most recent session file
        session_files = [f for f in os.listdir(day_path) if f.endswith('.json')]
        if not session_files:
            return {"error": "No session files found"}
            
        latest_file = sorted(session_files)[-1]  # Get most recent
        file_path = os.path.join(day_path, latest_file)
        
        # Read and return contents
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        return {"result": {
                    "session_id": latest_file.replace(".json", ""),
                    "interactions": [
                        item for item in data 
                        if item.get("type") != "run_metadata"
                    ]
                }}
    except Exception as e:
        print(f"[memory] Error: {str(e)}")  # Debug print
        return {"error": str(e)}

@mcp.tool()
async def search_historical_conversations(input: SearchInput) -> Dict[str, Any]:
    """Search historical conversations using semantic similarity. Usage: input={"input": {"query": "user's name"}} result = await mcp.call_tool('search_historical_conversations', input)"""
    try:
        # Use semantic search from conversation_indexer
        results = search_conversations(input.query, top_k=5)
        
        if not results:
            return {"result": []}
        
        # Error patterns to filter out
        error_patterns = [
            "[max steps reached]",
            "[result blocked",
            "[execution failed]",
            "[sandbox error:",
            "[error",
            "[failed",
            "[blocked",
        ]
        
        # Format results for LLM consumption, filtering out error messages
        formatted_results = []
        for r in results:
            final_answer = r.get("final_answer", "")
            
            # Check if final_answer is an error message
            is_error = False
            if final_answer:
                final_answer_lower = final_answer.lower()
                for pattern in error_patterns:
                    if pattern in final_answer_lower:
                        is_error = True
                        break
                    
                    # Also check if it's just brackets with error-like content
                    if final_answer.strip().startswith("[") and final_answer.strip().endswith("]"):
                        if any(word in final_answer_lower for word in ["error", "failed", "blocked", "max", "steps"]):
                            is_error = True
            
            # Skip conversations with error messages as final answers
            if is_error:
                continue
            
            formatted_results.append({
                "user_query": r.get("user_query", ""),
                "final_answer": final_answer,
                "timestamp": r.get("timestamp", ""),
                "similarity_distance": r.get("similarity_distance", float('inf'))
            })
        
        return {"result": formatted_results}
    except Exception as e:
        print(f"[memory] Error in search_historical_conversations: {e}")
        return {"result": [], "error": str(e)}

@mcp.tool()
async def answer_from_history(input: AnswerFromHistoryInput) -> AnswerFromHistoryOutput:
    """
    Answer user query directly using historical conversation context. 
    This tool searches historical conversations, formats context, and uses LLM to generate FINAL_ANSWER.
    Usage: input={"input": {"query": "what is my name?", "historical_context": ""}} 
    result = await mcp.call_tool('answer_from_history', input)
    """
    try:
        from modules.model_manager import ModelManager
        
        # Step 1: Search historical conversations if context not provided
        historical_context = input.historical_context
        if not historical_context:
            results = search_conversations(input.query, top_k=5)
            
            if results:
                # Format historical context
                context_items = []
                for r in results:
                    final_answer = r.get("final_answer", "")
                    # Skip error messages
                    if final_answer and any(err in final_answer.lower() for err in ["[max steps reached]", "[result blocked", "[error"]):
                        continue
                    context_items.append(
                        f"Previous Q: {r.get('user_query', '')}\n"
                        f"Previous A: {final_answer}"
                    )
                historical_context = "\n\n".join(context_items[:5])  # Top 5 most relevant
        
        # Step 2: Use LLM to generate FINAL_ANSWER from historical context
        model = ModelManager()
        
        if historical_context:
            prompt = f"""You are a helpful AI assistant. Answer the user's question based on the provided historical conversation context.

User's current question: "{input.query}"

Historical conversation context:
{historical_context}

Your task:
1. Analyze the historical conversations above to extract relevant information.
2. If the user's question asks for a comparison, analysis, or synthesis of information from multiple conversations, create a comprehensive answer by combining information from the historical context.
3. If the question can be answered (even partially) using information from the historical context, provide a clear, detailed answer.
4. Only respond with "I don't have that information" if the historical context contains NO relevant information at all about the topic.

Important: For comparison queries (e.g., "compare X and Y"), if information about both X and Y exists in the historical context, you MUST create a comparison even if a direct comparison wasn't explicitly stated in previous conversations.

Respond with FINAL_ANSWER: [your comprehensive answer based on the historical context]"""
        else:
            prompt = f"""You are a helpful AI assistant. The user asked: "{input.query}"

No relevant historical conversations were found. Please provide a helpful response based on your general knowledge.

Respond with FINAL_ANSWER: [your answer]"""
        
        llm_response = await model.generate_text(prompt)
        llm_response = llm_response.strip()
        
        # Ensure it starts with FINAL_ANSWER
        if not llm_response.startswith("FINAL_ANSWER:"):
            llm_response = "FINAL_ANSWER: " + llm_response
        
        return AnswerFromHistoryOutput(result=llm_response)
        
    except Exception as e:
        print(f"[memory] Error in answer_from_history: {e}")
        return AnswerFromHistoryOutput(result=f"FINAL_ANSWER: I encountered an error while processing your request: {str(e)}")

if __name__ == "__main__":
    print("Memory MCP server starting...")
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "dev":
            mcp.run()
        else:
            mcp.run(transport="stdio")
    finally:
        print("\nShutting down memory service...")
