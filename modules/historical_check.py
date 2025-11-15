"""
Historical conversation pre-check layer.
Before running the full agent loop, check if the answer is already in historical conversations.
"""

import json
from modules.model_manager import ModelManager

try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

model = ModelManager()

async def check_historical_conversations(user_input: str, mcp_dispatcher) -> dict:
    """
    Pre-check layer: Search historical conversations and use LLM to determine
    if the answer can be found directly without tools.
    
    Returns:
        - {"can_answer": True, "answer": "FINAL_ANSWER: ..."} if answer found completely
        - {"can_answer": False, "has_context": True, "context": "..."} if has relevant context but needs tools
        - {"can_answer": False, "has_context": False} if no relevant context, needs fresh approach
    """
    try:
        # Step 1: Search historical conversations
        log("historical_check", "🔍 Checking historical conversations for direct answer...")
        
        search_input = {"input": {"query": user_input}}
        historical_result = await mcp_dispatcher.call_tool(
            'search_historical_conversations',
            search_input
        )
        
        if not historical_result or not hasattr(historical_result, 'content'):
            log("historical_check", "⚠️ No historical conversations found")
            return {"can_answer": False}
        
        # Parse historical data
        try:
            historical_data = json.loads(historical_result.content[0].text).get("result", [])
        except Exception as e:
            log("historical_check", f"⚠️ Could not parse historical conversations: {e}")
            return {"can_answer": False}
        
        if not historical_data or len(historical_data) == 0:
            log("historical_check", "📭 No relevant historical conversations found")
            return {"can_answer": False}
        
        # Step 2: Format historical context
        context_items = []
        for conv in historical_data[:5]:  # Top 5 most relevant
            user_query = conv.get("user_query", "")
            final_answer = conv.get("final_answer", "")
            
            # Skip error messages
            if any(err in final_answer.lower() for err in ["[max steps reached]", "[result blocked", "[error"]):
                continue
                
            context_items.append(
                f"Previous Q: {user_query}\n"
                f"Previous A: {final_answer}"
            )
        
        if not context_items:
            log("historical_check", "📭 No valid historical conversations (all errors)")
            return {"can_answer": False}
        
        historical_context = "\n\n".join(context_items)
        log("historical_check", f"📚 Found {len(context_items)} relevant historical conversations")
        
        # Step 3: Use LLM to determine if answer is directly available
        decision_prompt = f"""You are analyzing whether a user's question can be answered directly from previous conversation history, without needing any tools.

User's current question: "{user_input}"

Previous conversations:
{historical_context}

Your task:
1. Determine if the user's question can be answered COMPLETELY and ACCURATELY from the previous conversations above.
2. The answer must be:
   - Directly available in the previous conversations
   - Complete (not partial)
   - Accurate (not requiring additional information)
   - Relevant to the current question

3. For comparison queries (e.g., "compare X and Y"), if information about both X and Y exists in the historical context, you can synthesize a comparison even if not explicitly stated.

Respond with ONE of these options:

1. If answer is COMPLETE and available:
   FINAL_ANSWER: [your complete answer based on the previous conversations]

2. If previous conversations have RELEVANT CONTEXT but answer is incomplete/needs tools:
   HAS_CONTEXT: [brief summary of relevant context from previous conversations]

3. If previous conversations are NOT RELEVANT or completely unrelated:
   NO_CONTEXT

Examples:
- User asks "what is my name?" and previous says "my name is John" → FINAL_ANSWER: Based on our previous conversation, your name is John.
- User asks "compare Dhoni and Sachin" and previous has info about both → FINAL_ANSWER: [synthesize comparison from available info]
- User asks "how much did Anmol pay?" and previous mentions "Anmol" and "DLF" but no payment amount → HAS_CONTEXT: Previous conversations mention Anmol Singh and DLF apartment, but payment amount not found.
- User asks "what is the weather?" and previous conversations don't mention weather → NO_CONTEXT

Now analyze the question and respond:"""
        
        llm_response = await model.generate_text(decision_prompt)
        llm_response = llm_response.strip()
        
        # Step 4: Check LLM decision
        if llm_response.startswith("FINAL_ANSWER:"):
            answer = llm_response
            _print_path_box("DIRECT_ANSWER", "Answer found completely in historical conversations")
            log("historical_check", "✅ Answer found in historical conversations - returning directly")
            return {"can_answer": True, "answer": answer}
        elif llm_response.startswith("HAS_CONTEXT:"):
            context_summary = llm_response.replace("HAS_CONTEXT:", "").strip()
            
            # ❗STRICT CHECK: If context summary explicitly says context doesn't contain the answer, treat as NO_CONTEXT
            context_lower = context_summary.lower()
            negative_indicators = [
                "do not provide",
                "does not provide",
                "does not contain",
                "not provide",
                "not contain",
                "no information",
                "no relevant",
                "completely unrelated",
                "unrelated",
                "not relevant"
            ]
            
            if any(indicator in context_lower for indicator in negative_indicators):
                _print_path_box("FRESH_APPROACH", "Historical context found but not relevant to query - proceeding with traditional route", context_summary)
                log("historical_check", f"⚠️ Context summary indicates irrelevant context: {context_summary[:100]}... - treating as NO_CONTEXT")
                return {"can_answer": False, "has_context": False}
            
            _print_path_box("CONTEXT_AWARE", "Relevant context found - will send to perception layer", context_summary)
            log("historical_check", "📚 Relevant context found in history - will send to perception layer")
            return {"can_answer": False, "has_context": True, "context": historical_context, "context_summary": context_summary}
        else:
            _print_path_box("FRESH_APPROACH", "No relevant context - proceeding with traditional route")
            log("historical_check", "🆕 No relevant context in history - proceeding with traditional route")
            return {"can_answer": False, "has_context": False}
            
    except Exception as e:
        log("historical_check", f"⚠️ Error in historical check: {e}")
        return {"can_answer": False, "has_context": False}

def _print_path_box(path_type: str, description: str, context: str = None):
    """Print a nice box showing which path was chosen."""
    width = 70
    print("\n" + "═" * width)
    print("║" + " " * (width - 2) + "║")
    
    # Path type
    path_text = f"PATH: {path_type}"
    padding = (width - 2 - len(path_text)) // 2
    print("║" + " " * padding + path_text + " " * (width - 2 - padding - len(path_text)) + "║")
    print("║" + " " * (width - 2) + "║")
    
    # Description
    desc_lines = _wrap_text(description, width - 4)
    for line in desc_lines:
        print("║ " + line.ljust(width - 4) + " ║")
    print("║" + " " * (width - 2) + "║")
    
    # Context if provided
    if context:
        print("║" + "─" * (width - 2) + "║")
        print("║ " + "CONTEXT TAKEN FORWARD:".ljust(width - 4) + " ║")
        print("║" + "─" * (width - 2) + "║")
        context_lines = _wrap_text(context, width - 4)
        for line in context_lines:
            print("║ " + line.ljust(width - 4) + " ║")
    
    print("║" + " " * (width - 2) + "║")
    print("═" * width + "\n")

def _wrap_text(text: str, max_width: int) -> list:
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = ""
    
    for word in words:
        if len(current_line) + len(word) + 1 <= max_width:
            current_line += (word + " ") if current_line else word
        else:
            if current_line:
                lines.append(current_line.rstrip())
            current_line = word + " "
    
    if current_line:
        lines.append(current_line.rstrip())
    
    return lines if lines else [""]

