# modules/loop.py

import asyncio
import json
from modules.perception import run_perception
from modules.decision import generate_plan
from modules.action import run_python_sandbox
from modules.model_manager import ModelManager
from core.session import MultiMCP
from core.strategy import select_decision_prompt_path
from core.context import AgentContext
from modules.tools import summarize_tools, extract_python_code_block
from modules.guardrail import check_result
import re

try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")

class AgentLoop:
    def __init__(self, context: AgentContext):
        self.context = context
        self.mcp = self.context.dispatcher
        self.model = ModelManager()

    async def run(self):
        max_steps = self.context.agent_profile.strategy.max_steps
        further_processing_count = 0  # Track FURTHER_PROCESSING_REQUIRED loops

        for step in range(max_steps):
            print(f"🔁 Step {step+1}/{max_steps} starting...")
            self.context.step = step
            lifelines_left = self.context.agent_profile.strategy.max_lifelines_per_step

            while lifelines_left >= 0:
                # === Perception ===
                user_input_override = getattr(self.context, "user_input_override", None)
                historical_context = getattr(self.context, "historical_context", None)
                perception = await run_perception(
                    context=self.context, 
                    user_input=user_input_override or self.context.user_input,
                    historical_context=historical_context
                )

                print(f"[perception] {perception}")

                selected_servers = perception.selected_servers
                selected_tools = self.mcp.get_tools_from_servers(selected_servers)
                if not selected_tools:
                    log("loop", "⚠️ No tools selected — checking historical conversations and using LLM fallback.")
                    
                    # Search historical conversations for context
                    historical_context = ""
                    try:
                        # Search for relevant historical conversations
                        search_input = {"input": {"query": self.context.user_input}}
                        historical_result = await self.mcp.call_tool(
                            'search_historical_conversations', 
                            search_input
                        )
                        
                        # Parse the result
                        if historical_result and hasattr(historical_result, 'content'):
                            try:
                                historical_data = json.loads(historical_result.content[0].text).get("result", [])
                                
                                if historical_data and len(historical_data) > 0:
                                    # Format historical context for the prompt
                                    context_items = []
                                    for conv in historical_data[:3]:  # Top 3 most relevant
                                        context_items.append(
                                            f"Previous conversation:\n"
                                            f"  User: {conv.get('user_query', '')}\n"
                                            f"  Assistant: {conv.get('final_answer', '')}"
                                        )
                                    historical_context = "\n\n".join(context_items)
                                    log("loop", f"📚 Found {len(historical_data)} relevant historical conversations")
                            except Exception as e:
                                log("loop", f"⚠️ Could not parse historical conversations: {e}")
                    except Exception as e:
                        log("loop", f"⚠️ Could not search historical conversations: {e}")
                    
                    # Build enhanced prompt with historical context
                    current_user_input = self.context.user_input_override if self.context.user_input_override else self.context.user_input
                    
                    if historical_context:
                        fallback_prompt = f"""You are a helpful AI assistant. The user asked: "{current_user_input}"

This query doesn't require any tools - it's a simple question or greeting that you can answer directly.

Here are some relevant previous conversations for context:
{historical_context}

Please provide a helpful, concise response. If it's a greeting, respond warmly. If it's a question, answer it directly based on your knowledge and the context from previous conversations if relevant.

Your response:"""
                    else:
                        fallback_prompt = f"""You are a helpful AI assistant. The user asked: "{current_user_input}"

This query doesn't require any tools - it's a simple question or greeting that you can answer directly.

Please provide a helpful, concise response. If it's a greeting, respond warmly. If it's a question, answer it directly based on your knowledge.

Your response:"""
                    
                    try:
                        direct_answer = await self.model.generate_text(fallback_prompt)
                        direct_answer = direct_answer.strip()
                        
                        # Ensure it starts with FINAL_ANSWER if it doesn't already
                        if not direct_answer.startswith("FINAL_ANSWER:"):
                            direct_answer = "FINAL_ANSWER: " + direct_answer
                        
                        # Store original direct answer (no sanitization in memory)
                        self.context.final_answer = direct_answer
                        
                        # Store in memory for future searches
                        self.context.memory.add_tool_output(
                            tool_name="direct_llm_response",
                            tool_args={"user_input": current_user_input},
                            tool_result={"result": self.context.final_answer},
                            success=True,
                            tags=["greeting", "simple_query"] if perception.intent == "greeting" else ["simple_query"],
                        )
                        
                        log("loop", f"✅ Generated direct answer with historical context (no tools needed)")
                        # Return early instead of breaking to prevent going through all steps
                        return {"status": "done", "result": self.context.final_answer}
                    except Exception as e:
                        log("loop", f"❌ Error generating direct answer: {e}")
                        self.context.final_answer = "FINAL_ANSWER: I apologize, but I encountered an error while processing your request."
                        return {"status": "error", "result": self.context.final_answer}

                # === Planning ===
                # Use overridden input if available (from FURTHER_PROCESSING_REQUIRED)
                current_user_input = self.context.user_input_override if self.context.user_input_override else self.context.user_input
                
                # ❗STRICT: If content is already provided via "Your last tool produced this result:", use LLM directly
                if "Your last tool produced this result:" in current_user_input:
                    # Extract the content from the message
                    try:
                        content_start = current_user_input.find("Your last tool produced this result:") + len("Your last tool produced this result:")
                        content = current_user_input[content_start:].strip()
                        # Remove the instruction lines at the end
                        if "❗CRITICAL:" in content:
                            content = content[:content.find("❗CRITICAL:")].strip()
                        
                        log("loop", "🔍 Content already provided - using LLM directly to analyze (bypassing tool selection)")
                        
                        # Truncate content if too long
                        content_to_analyze = content[:50000] if len(content) > 50000 else content
                        if len(content) > 50000:
                            content_to_analyze += f"\n\n[Content truncated - showing first 50000 characters of {len(content)} total]"
                        
                        # Extract original task
                        original_task = self.context.user_input
                        if "Original user task:" in current_user_input:
                            task_start = current_user_input.find("Original user task:") + len("Original user task:")
                            task_end = current_user_input.find("\n\n", task_start)
                            if task_end > 0:
                                original_task = current_user_input[task_start:task_end].strip()
                        
                        # Use LLM directly to analyze
                        analysis_prompt = f"""You are a helpful AI assistant. Analyze the following content and provide a clear, comprehensive answer to the user's question.

Original user task: {original_task}

Content to analyze:
{content_to_analyze}

Your task: Analyze this content and provide a clear, well-structured answer. If the user asked to summarize or explain, provide a comprehensive summary. If they asked a specific question, answer it based on the content.

Respond with FINAL_ANSWER: [your analysis and answer]"""
                        
                        llm_answer = await self.model.generate_text(analysis_prompt)
                        llm_answer = llm_answer.strip()
                        if not llm_answer.startswith("FINAL_ANSWER:"):
                            llm_answer = "FINAL_ANSWER: " + llm_answer
                        
                        self.context.final_answer = llm_answer
                        self.context.memory.add_tool_output(
                            tool_name="llm_direct_analysis",
                            tool_args={"reason": "Content provided via FURTHER_PROCESSING_REQUIRED"},
                            tool_result={"result": self.context.final_answer},
                            success=True,
                            tags=["direct_analysis", "llm"],
                        )
                        log("loop", "✅ LLM direct analysis completed")
                        return {"status": "done", "result": self.context.final_answer}
                    except Exception as e:
                        log("loop", f"⚠️ Error in direct LLM analysis: {e}, falling back to normal planning")
                        # Fall through to normal planning if direct analysis fails
                
                tool_descriptions = summarize_tools(selected_tools)
                prompt_path = select_decision_prompt_path(
                    planning_mode=self.context.agent_profile.strategy.planning_mode,
                    exploration_mode=self.context.agent_profile.strategy.exploration_mode,
                )
                
                # Enhance user input with historical context if available (same as perception layer)
                historical_context = getattr(self.context, "historical_context", None)
                if historical_context:
                    current_user_input = f"""{current_user_input}

Relevant context from previous conversations:
{historical_context}

Use this context to inform your tool selection and search strategy."""
                
                plan = await generate_plan(
                    user_input=current_user_input,
                    perception=perception,
                    memory_items=self.context.memory.get_session_items(),
                    tool_descriptions=tool_descriptions,
                    prompt_path=prompt_path,
                    step_num=step + 1,
                    max_steps=max_steps,
                )
                print(f"[plan] {plan}")

                # === Execution ===
                if re.search(r"^\s*(async\s+)?def\s+solve\s*\(", plan, re.MULTILINE):
                    print("[loop] Detected solve() plan — running sandboxed...")
                    # Extract clean Python code (handles markdown code blocks or uses plan as-is)
                    code = extract_python_code_block(plan)
                    # Verify we still have a valid solve() function after extraction
                    if not re.search(r"^\s*(async\s+)?def\s+solve\s*\(", code, re.MULTILINE):
                        code = plan  # Fallback to original if extraction removed the function
                    print("\nextracted code to run:", code[:200] + "..." if len(code) > 200 else code)
                    self.context.log_subtask(tool_name="solve_sandbox", status="pending")
                    result = await run_python_sandbox(code, dispatcher=self.mcp)
                    # Truncate result for display if too long
                    MAX_RESULT_DISPLAY = 1000
                    if isinstance(result, str) and len(result) > MAX_RESULT_DISPLAY:
                        display_result = result[:MAX_RESULT_DISPLAY] + f"\n... [truncated {len(result) - MAX_RESULT_DISPLAY} more characters]"
                        print("#####", display_result)
                    else:
                        print("#####", result)
                    success = False
                    if isinstance(result, str):
                        result = result.strip()
                        if result.startswith("FINAL_ANSWER:"):
                            # Store original result in memory (no sanitization)
                            self.context.final_answer = result
                            success = True
                            self.context.update_subtask_status("solve_sandbox", "success")
                            self.context.memory.add_tool_output(
                                tool_name="solve_sandbox",
                                tool_args={"plan": plan},
                                tool_result={"result": result},  # Store original, unsanitized
                                success=True,
                                tags=["sandbox"],
                            )
                            return {"status": "done", "result": self.context.final_answer}
                        elif result.startswith("FURTHER_PROCESSING_REQUIRED:"):
                            content = result.split("FURTHER_PROCESSING_REQUIRED:")[1].strip()
                            further_processing_count += 1
                            
                            # ❗STRICT FALLBACK: If we've seen FURTHER_PROCESSING_REQUIRED before, use LLM directly
                            if further_processing_count > 1:
                                log("loop", f"⚠️ Detected loop with FURTHER_PROCESSING_REQUIRED (count: {further_processing_count}). Using LLM fallback to analyze content.")
                                try:
                                    # Use LLM directly to analyze the provided content
                                    # Truncate content if too long (max 50000 chars)
                                    content_to_analyze = content[:50000] if len(content) > 50000 else content
                                    if len(content) > 50000:
                                        content_to_analyze += f"\n\n[Content truncated - showing first 50000 characters of {len(content)} total]"
                                    
                                    analysis_prompt = f"""You are a helpful AI assistant. Analyze the following content and provide a clear, comprehensive answer to the user's question.

Original user task: {self.context.user_input}

Content to analyze:
{content_to_analyze}

Your task: Analyze this content and provide a clear, well-structured answer. If the user asked to summarize or explain, provide a comprehensive summary. If they asked a specific question, answer it based on the content.

Respond with FINAL_ANSWER: [your analysis and answer]"""
                                    
                                    llm_answer = await self.model.generate_text(analysis_prompt)
                                    llm_answer = llm_answer.strip()
                                    if not llm_answer.startswith("FINAL_ANSWER:"):
                                        llm_answer = "FINAL_ANSWER: " + llm_answer
                                    
                                    self.context.final_answer = llm_answer
                                    self.context.memory.add_tool_output(
                                        tool_name="llm_fallback_analysis",
                                        tool_args={"reason": "FURTHER_PROCESSING_REQUIRED loop detected"},
                                        tool_result={"result": self.context.final_answer},
                                        success=True,
                                        tags=["fallback", "llm_analysis"],
                                    )
                                    log("loop", "✅ LLM fallback analysis completed")
                                    return {"status": "done", "result": self.context.final_answer}
                                except Exception as e:
                                    log("loop", f"❌ LLM fallback failed: {e}")
                                    # Continue with normal flow if fallback fails
                            
                            # No guardrail checks on intermediate results - use original content
                            self.context.user_input_override  = (
                                f"Original user task: {self.context.user_input}\n\n"
                                f"Your last tool produced this result:\n\n"
                                f"{content}\n\n"
                                f"❗CRITICAL: Analyze the content above and return FINAL_ANSWER. DO NOT call any tools - the content is already provided!\n\n"
                                f"Return: FINAL_ANSWER: [your analysis]"
                            )
                            # Truncate content for display (keep full content in user_input_override)
                            MAX_DISPLAY_LENGTH = 500
                            if len(content) > MAX_DISPLAY_LENGTH:
                                truncated_content = content[:MAX_DISPLAY_LENGTH] + f"\n... [truncated {len(content) - MAX_DISPLAY_LENGTH} more characters]"
                                display_override = (
                                    f"Original user task: {self.context.user_input}\n\n"
                                    f"Your last tool produced this result:\n\n"
                                    f"{truncated_content}\n\n"
                                    f"❗CRITICAL: Analyze the content above and return FINAL_ANSWER. DO NOT call any tools!\n\n"
                                    f"Return: FINAL_ANSWER: [your analysis]"
                                )
                            else:
                                display_override = self.context.user_input_override
                            log("loop", f"📨 Forwarding intermediate result to next step:\n{display_override}\n\n")
                            log("loop", f"🔁 Continuing based on FURTHER_PROCESSING_REQUIRED — Step {step+1} continues...")
                            break  # Step will continue
                        elif result.startswith("[sandbox error:"):
                            success = False
                            self.context.final_answer = "FINAL_ANSWER: [Execution failed]"
                        else:
                            success = True
                            self.context.final_answer = f"FINAL_ANSWER: {result}"
                    else:
                        self.context.final_answer = f"FINAL_ANSWER: {result}"

                    if success:
                        self.context.update_subtask_status("solve_sandbox", "success")
                    else:
                        self.context.update_subtask_status("solve_sandbox", "failure")

                    self.context.memory.add_tool_output(
                        tool_name="solve_sandbox",
                        tool_args={"plan": plan},
                        tool_result={"result": result},
                        success=success,
                        tags=["sandbox"],
                    )

                    if success and "FURTHER_PROCESSING_REQUIRED:" not in result:
                        return {"status": "done", "result": self.context.final_answer}
                    else:
                        lifelines_left -= 1
                        log("loop", f"🛠 Retrying... Lifelines left: {lifelines_left}")
                        continue
                else:
                    log("loop", f"⚠️ Invalid plan detected — retrying... Lifelines left: {lifelines_left-1}")
                    lifelines_left -= 1
                    continue

        log("loop", "⚠️ Max steps reached without finding final answer.")
        self.context.final_answer = "FINAL_ANSWER: [Max steps reached]"
        return {"status": "done", "result": self.context.final_answer}
