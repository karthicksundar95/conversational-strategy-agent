# agent.py

import asyncio
import yaml
from core.loop import AgentLoop
from core.session import MultiMCP
from core.context import MemoryItem, AgentContext
import datetime
from pathlib import Path
import json
import re
from modules.guardrail import check_query, check_result
from modules.conversation_indexer import index_conversation

def log(stage: str, msg: str):
    """Simple timestamped console logger."""
    now = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] [{stage}] {msg}")

async def main():
    print("🧠 Cortex-R Agent Ready")
    current_session = None

    with open("config/profiles.yaml", "r") as f:
        profile = yaml.safe_load(f)
        mcp_servers_list = profile.get("mcp_servers", [])
        mcp_servers = {server["id"]: server for server in mcp_servers_list}

    multi_mcp = MultiMCP(server_configs=list(mcp_servers.values()))
    await multi_mcp.initialize()
    print("&&&&", multi_mcp)

    try:
        while True:
            user_input = input("🧑 What do you want to solve today? → ")
            if user_input.lower() == 'exit':
                break
            if user_input.lower() == 'new':
                current_session = None
                continue

            # Guardrail: Check user query
            query_check = check_query(user_input)
            if query_check.blocked:
                log("guardrail", f"🚫 Query blocked: {query_check.reason}")
                print(f"\n⚠️  Your query was blocked for security reasons: {query_check.reason}")
                if query_check.warnings:
                    print(f"   Warnings: {', '.join(query_check.warnings)}")
                continue
            
            # Store original query for indexing (before sanitization)
            original_user_input = user_input
            
            # Use sanitized query if warnings were found
            if query_check.warnings:
                log("guardrail", f"⚠️  Query warnings: {', '.join(query_check.warnings)}")
                user_input = query_check.sanitized_content

            while True:
                # Pre-check layer: Check if answer is in historical conversations
                from modules.historical_check import check_historical_conversations
                historical_check = await check_historical_conversations(user_input, multi_mcp)
                
                if historical_check.get("can_answer", False):
                    # Case 1: Answer found in history - return directly
                    answer = historical_check["answer"]
                    log("agent", "✅ Direct answer from historical conversations - skipping tool loop")
                    
                    # Extract final answer text (no guardrail checks here)
                    final_answer_text = answer.split('FINAL_ANSWER:')[1].strip() if "FINAL_ANSWER:" in answer else answer
                    original_answer = final_answer_text
                    
                    # Index this conversation with original (unsanitized) answer
                    context = AgentContext(
                        user_input=user_input,
                        session_id=current_session,
                        dispatcher=multi_mcp,
                        mcp_server_descriptions=mcp_servers,
                    )
                    if not current_session:
                        current_session = context.session_id
                    
                    try:
                        index_conversation(
                            session_id=context.session_id,
                            user_query=original_user_input,
                            final_answer=original_answer,  # Store original, not sanitized
                            tool_calls=None
                        )
                        log("agent", "✅ Conversation indexed for semantic search")
                    except Exception as e:
                        log("agent", f"⚠️  Failed to index conversation: {e}")
                    
                    # Guardrail check ONLY at final print statement
                    result_check = check_result(final_answer_text)
                    sanitized_answer = result_check.sanitized_content
                    if result_check.warnings:
                        log("guardrail", f"⚠️  Final answer warnings: {', '.join(result_check.warnings)}")
                    print(f"\n💡 Final Answer: {sanitized_answer}")
                    break
                
                # Case 2 or 3: Answer not in history - proceed with full agent loop
                context = AgentContext(
                    user_input=user_input,
                    session_id=current_session,
                    dispatcher=multi_mcp,
                    mcp_server_descriptions=mcp_servers,
                )
                
                # If has relevant context, store it to pass to perception layer
                historical_context = None
                if historical_check.get("has_context", False):
                    historical_context = historical_check.get("context", "")
                    log("agent", "📚 Proceeding to tool loop with historical context (will be sent to perception)")
                else:
                    log("agent", "🆕 Proceeding to tool loop with fresh approach (no relevant history)")
                
                # Store historical context in context for perception to use
                context.historical_context = historical_context
                
                agent = AgentLoop(context)
                if not current_session:
                    current_session = context.session_id

                result = await agent.run()

                if isinstance(result, dict):
                    answer = result["result"]
                    if "FINAL_ANSWER:" in answer:
                        # Extract original answer (no guardrail checks here)
                        final_answer_text = answer.split('FINAL_ANSWER:')[1].strip()
                        original_answer = final_answer_text
                        
                        # Index conversation with original (unsanitized) answer
                        try:
                            memory_items = context.memory.get_session_items()
                            tool_calls = []
                            for item in memory_items:
                                if item.type == "tool_output" and item.tool_name:
                                    tool_calls.append({
                                        "tool_name": item.tool_name,
                                        "tool_args": item.tool_args or {},
                                        "success": item.success or False
                                    })
                            
                            index_conversation(
                                session_id=context.session_id,
                                user_query=original_user_input,  # Use original query, not sanitized
                                final_answer=original_answer,  # Store original, not sanitized
                                tool_calls=tool_calls if tool_calls else None
                            )
                            log("agent", "✅ Conversation indexed for semantic search")
                        except Exception as e:
                            log("agent", f"⚠️  Failed to index conversation: {e}")
                        
                        # Guardrail check ONLY at final print statement
                        result_check = check_result(final_answer_text)
                        sanitized_answer = result_check.sanitized_content
                        if result_check.warnings:
                            log("guardrail", f"⚠️  Final answer warnings: {', '.join(result_check.warnings)}")
                        print(f"\n💡 Final Answer: {sanitized_answer}")
                        break
                    elif "FURTHER_PROCESSING_REQUIRED:" in answer:
                        user_input = answer.split("FURTHER_PROCESSING_REQUIRED:")[1].strip()
                        print(f"\n🔁 Further Processing Required: {user_input}")
                        continue  # 🧠 Re-run agent with updated input
                    else:
                        # Store original answer for memory/indexing (no guardrail checks here)
                        original_answer = answer
                        
                        # Index conversation with original (unsanitized) answer
                        try:
                            memory_items = context.memory.get_session_items()
                            tool_calls = []
                            for item in memory_items:
                                if item.type == "tool_output" and item.tool_name:
                                    tool_calls.append({
                                        "tool_name": item.tool_name,
                                        "tool_args": item.tool_args or {},
                                        "success": item.success or False
                                    })
                            index_conversation(
                                session_id=context.session_id,
                                user_query=original_user_input,
                                final_answer=original_answer,  # Store original, not sanitized
                                tool_calls=tool_calls if tool_calls else None
                            )
                            log("agent", "✅ Conversation indexed for semantic search")
                        except Exception as e:
                            log("agent", f"⚠️  Failed to index conversation: {e}")
                        
                        # Guardrail check ONLY at final print statement
                        result_check = check_result(answer)
                        sanitized_answer = result_check.sanitized_content
                        if result_check.warnings:
                            log("guardrail", f"⚠️  Final answer warnings: {', '.join(result_check.warnings)}")
                        print(f"\n💡 Final Answer (raw): {sanitized_answer}")
                        break
                else:
                    # Store original result for memory/indexing (no guardrail checks here)
                    result_str = str(result)
                    original_result = result_str
                    
                    # Index conversation with original (unsanitized) result
                    try:
                        memory_items = context.memory.get_session_items()
                        tool_calls = []
                        for item in memory_items:
                            if item.type == "tool_output" and item.tool_name:
                                tool_calls.append({
                                    "tool_name": item.tool_name,
                                    "tool_args": item.tool_args or {},
                                    "success": item.success or False
                                })
                        index_conversation(
                            session_id=context.session_id,
                            user_query=original_user_input,
                            final_answer=original_result,  # Store original, not sanitized
                            tool_calls=tool_calls if tool_calls else None
                        )
                        log("agent", "✅ Conversation indexed for semantic search")
                    except Exception as e:
                        log("agent", f"⚠️  Failed to index conversation: {e}")
                    
                    # Guardrail check ONLY at final print statement
                    result_check = check_result(result_str)
                    sanitized_result = result_check.sanitized_content
                    if result_check.warnings:
                        log("guardrail", f"⚠️  Final answer warnings: {', '.join(result_check.warnings)}")
                    print(f"\n💡 Final Answer (unexpected): {sanitized_result}")
                    break
    except KeyboardInterrupt:
        print("\n👋 Received exit signal. Shutting down...")

if __name__ == "__main__":
    asyncio.run(main())



# Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
# How much Anmol singh paid for his DLF apartment via Capbridge? 
# What do you know about Don Tapscott and Anthony Williams?
# What is the relationship between Gensol and Go-Auto?
# which course are we teaching on Canvas LMS? "/Users/karthicksundar/Documents/learnings/EAG V2/Project9/documents/How to use Canvas LMS.pdf"
# Summarize this page: https://theschoolof.ai/
# What is the log value of the amount that Anmol singh paid for his DLF apartment via Capbridge? 