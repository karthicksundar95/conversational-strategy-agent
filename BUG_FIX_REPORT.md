# Bug Fix Report - Cortex-R Agent

## Date: November 14, 2025

---

## Summary

This report documents critical bugs discovered and fixed in the Cortex-R agent system, primarily related to code extraction from LLM-generated plans and result processing.

---

## Bug #1: Code Extraction Failure - CRITICAL

### Severity: 🔴 CRITICAL
### Status: ✅ FIXED

### Description
The agent was passing raw LLM output (containing markdown code blocks and explanatory text) directly to the Python sandbox, causing syntax errors during execution.

### Root Cause
1. **In `modules/decision.py`**: The code extraction logic only handled cases where the entire string started with markdown fences (````python`), but LLM responses often include explanatory text before/after the code block.

2. **In `core/loop.py`**: The code was attempting to extract the `solve()` function using `.group(1)` on a regex match, which only captured the `(async\s+)?` group instead of the full code.

### Error Manifestation
```
[action] 🔍 Entered run_python_sandbox()
[sandbox] ⚠️ Execution error: invalid syntax (<solve_plan>, line 1)
extracted code to run: async  # ❌ Only extracted "async" instead of full function
```

### Example of Problematic LLM Output
```
Here is a Python function `solve()` that follows your rules:

```python
import json
async def solve():
    # ... code ...
```

This function first converts...
```

The agent was trying to execute the entire string including the markdown and explanatory text.

### Fix Implementation

#### 1. Added `extract_python_code_block()` function in `modules/tools.py`
```python
def extract_python_code_block(text: str) -> str:
    """
    Extracts Python code from markdown code blocks.
    Handles cases where code is wrapped in ```python ... ``` or ``` ... ```
    """
    # Try to find Python code block
    match = re.search(r"```python\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Try generic code block
    match = re.search(r"```\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # If no code block found, return as-is (might already be clean code)
    return text.strip()
```

#### 2. Updated `modules/decision.py`
- Replaced manual markdown stripping with `extract_python_code_block()`
- Now handles text before/after code blocks properly

#### 3. Updated `core/loop.py`
- Replaced incorrect regex group extraction with `extract_python_code_block()`
- Added fallback verification to ensure `solve()` function still exists after extraction

### Files Modified
- `modules/tools.py` - Added `extract_python_code_block()` function
- `modules/decision.py` - Updated to use code extraction function
- `core/loop.py` - Fixed code extraction before sandbox execution

### Testing
✅ Verified with LLM output containing:
- Markdown code blocks with surrounding text
- Clean Python code without markdown
- Multiple code blocks (extracts first Python block)

---

## Bug #2: LLM Writing Custom Parsing Code Instead of Using Tools - HIGH

### Severity: 🟡 HIGH
### Status: ✅ FIXED

### Description
The LLM was generating custom regex patterns and complex string parsing code to extract URLs from search results, instead of using the search result summaries directly or existing tools.

### Root Cause
1. **In `prompts/decision_prompt_conservative.txt`**: Example 6 contained complex regex-based URL extraction code with multiple fallback patterns, normalization, and validation logic.
2. The prompt encouraged the LLM to write custom parsing code rather than using search result summaries directly.
3. The search results already contain sufficient information in their summaries to answer most queries, but the LLM was being guided to extract URLs and fetch full webpage content unnecessarily.

### Error Manifestation
```
# LLM-generated code included:
- Complex regex patterns: r'URL:\\s+(https?://[^\\s\\n]+)'
- String normalization: search_text.replace('\\\\n', '\\n').replace('\\n', '\n')
- Multiple fallback patterns and validation logic
- URL truncation errors: "Could not resolve host: time" (incomplete URL extraction)
```

### Fix Implementation

#### 1. Updated `prompts/decision_prompt_conservative.txt`
- **Removed complex regex example**: Replaced Example 6 with a simple approach that uses search summaries directly
- **Added Example 6 (PREFERRED)**: Shows using search results without any parsing:
  ```python
  async def solve():
      search_result = await mcp.call_tool('search', input)
      search_text = json.loads(search_result.content[0].text)["result"]
      # Search results already contain summaries with the answer
      return f"FURTHER_PROCESSING_REQUIRED: {search_text}"
  ```
- **Added Example 7 (fallback)**: If full content is needed, uses simple string methods (`find`, `split`) instead of regex
- **Added explicit rule**: "❗DO NOT write custom regex or string parsing code. Use existing tools only."
- **Updated tips section**: Emphasizes preferring search result summaries directly

#### 2. Updated tool signatures in `mcp_server_3.py`
- Changed `search` tool to use `SearchInput`/`SearchOutput` models for proper JSON serialization
- Changed `fetch_content` tool to use `UrlInput`/`PythonCodeOutput` models
- Added `SearchOutput` model to `models.py`

### Files Modified
- `prompts/decision_prompt_conservative.txt` - Removed complex parsing examples, added simple usage examples
- `mcp_server_3.py` - Updated tool signatures to use proper input/output models
- `models.py` - Added `SearchOutput` model

### Testing
✅ Verified LLM now:
- Uses search result summaries directly without custom parsing
- Only fetches full webpage content when summaries are insufficient
- Uses simple string methods (find, split) instead of complex regex when URL extraction is needed

---

## Bug #3: FURTHER_PROCESSING_REQUIRED Loop - Agent Not Analyzing Provided Results - CRITICAL

### Severity: 🔴 CRITICAL
### Status: ✅ FIXED

### Description
When a tool returned `FURTHER_PROCESSING_REQUIRED` with search results, the agent would loop indefinitely, repeatedly calling the same search tool instead of analyzing the provided results and generating a `FINAL_ANSWER`.

### Root Cause
1. **In `core/loop.py`**: When `FURTHER_PROCESSING_REQUIRED` was returned, the loop set `user_input_override` with the search results, but `generate_plan()` was still using the original `user_input` instead of the override.
2. **In `core/context.py`**: `user_input_override` was not initialized in the `AgentContext` class.
3. **In `prompts/decision_prompt_conservative.txt`**: The prompt didn't explicitly instruct the LLM to analyze provided content when it already contains tool outputs.

### Error Manifestation
```
Step 1: Calls search → Returns FURTHER_PROCESSING_REQUIRED with search results
Step 2: Should analyze results → Instead calls search again
Step 3: Repeats same behavior
Result: Max steps reached without final answer
```

### Fix Implementation

#### 1. Fixed `core/loop.py`
- **Updated planning step**: Now checks for and uses `user_input_override` when available:
  ```python
  current_user_input = self.context.user_input_override if self.context.user_input_override else self.context.user_input
  plan = await generate_plan(user_input=current_user_input, ...)
  ```

#### 2. Fixed `core/context.py`
- **Initialized `user_input_override`**: Added `self.user_input_override = None` in `AgentContext.__init__()`

#### 3. Enhanced `prompts/decision_prompt_conservative.txt`
- **Added critical rule**: "❗CRITICAL: If the user input already includes search results, tool outputs, or extracted content (e.g., 'Your last tool produced this result:'), DO NOT call any tools. Instead, analyze the provided content and return FINAL_ANSWER directly."
- **Added Example 7**: Shows how to handle the case when user input already contains search results:
  ```python
  async def solve():
      # User input already contains search results from previous step
      # DO NOT call any tools - just analyze and return FINAL_ANSWER
      return "FINAL_ANSWER: Based on the search results, [your analysis here]"
  ```

### Files Modified
- `core/loop.py` - Fixed to use `user_input_override` when available
- `core/context.py` - Initialized `user_input_override` attribute
- `prompts/decision_prompt_conservative.txt` - Added explicit rule and example for analyzing provided content

### Testing
✅ Verified agent now:
- Uses overridden input containing search results in subsequent steps
- Recognizes when content is already provided and doesn't call tools again
- Analyzes provided search results and generates FINAL_ANSWER
- Stops looping and terminates properly after generating final answer

---

## Bug #4: Incorrect Tool Selection for Web URLs - HIGH

### Severity: 🟡 HIGH
### Status: ✅ FIXED

### Description
When a user query contained a URL (http:// or https://), the agent was incorrectly using `fetch_content` or `search` tools instead of the specialized `convert_webpage_url_into_markdown` tool, which provides cleaner markdown output better suited for analysis.

### Root Cause
1. **In `prompts/decision_prompt_conservative.txt`**: The prompt lacked explicit guidance on tool selection when URLs are present in queries.
2. The agent would default to generic web search or content fetching tools instead of the specialized markdown conversion tool.
3. This resulted in raw HTML being returned instead of clean, analyzable markdown.

### Error Manifestation
```
User Query: "can you summarize this https://www.seldon.io/managing-realtime-ai-cost-in-production-a-practical-guide/"

Agent Behavior (Before Fix):
- Selected: fetch_content or search tools
- Returned: Raw HTML content
- Result: Difficult to analyze, poor summarization quality

Agent Behavior (After Fix):
- Selected: convert_webpage_url_into_markdown
- Returned: Clean markdown with image captions
- Result: Better analysis and summarization
```

### Fix Implementation

#### 1. Updated `prompts/decision_prompt_conservative.txt`
- **Added critical rule in TOOL SELECTION section**:
  ```
  - ❗CRITICAL: If user query contains a URL (http:// or https://) → ALWAYS use `convert_webpage_url_into_markdown` (NOT `fetch_content` or `search`!)
    - This tool converts webpage to clean markdown (better for analysis than raw HTML)
    - For "summarize" queries with URLs, use this tool then return FURTHER_PROCESSING_REQUIRED with markdown
  ```

- **Added dedicated WEB CONTENT (URLs) section**:
  ```
  🌐 WEB CONTENT (URLs):
  - ❗If query contains URL → MUST use `convert_webpage_url_into_markdown` (NOT `fetch_content`!)
  - Parse: `json.loads(result.content[0].text)["markdown"]` (not `["result"]`)
  - For "summarize" queries: return FURTHER_PROCESSING_REQUIRED with markdown
  - ❗If markdown PROVIDED in query (not empty) → analyze → FINAL_ANSWER (DO NOT call tool!)
  - ❗If result EMPTY → tool FAILED → fall back to `search` (DO NOT retry!)
  ```

- **Added concrete example**:
  ```python
  ✅ Example: URL with summarize (use convert_webpage_url_into_markdown)
  async def solve():
      # User: "summarize https://example.com/article"
      result = await mcp.call_tool('convert_webpage_url_into_markdown', 
                                    {"input": {"url": "https://example.com/article"}})
      markdown = json.loads(result.content[0].text)["markdown"]  # Parse "markdown" field!
      return "FURTHER_PROCESSING_REQUIRED: " + markdown  # Return for analysis, not FINAL_ANSWER
  ```

### Files Modified
- `prompts/decision_prompt_conservative.txt` - Added explicit URL detection rules and tool selection guidance

### Testing
✅ Verified agent now:
- Detects URLs in queries (http:// or https://)
- Always uses `convert_webpage_url_into_markdown` for URL queries
- Returns clean markdown instead of raw HTML
- Properly handles markdown parsing (uses `["markdown"]` field, not `["result"]`)
- Falls back to `search` if markdown conversion fails

---

## Bug #5: Missing Vector Database Search Before Web Search - MEDIUM

### Severity: 🟠 MEDIUM
### Status: ✅ FIXED

### Description
The agent was performing web searches immediately without first checking if the information was already available in the stored documents (vector database). This led to unnecessary API calls and slower response times when the information was already indexed locally.

### Root Cause
1. **In `prompts/decision_prompt_conservative.txt`**: The tool selection order didn't prioritize local document search before web search.
2. The agent would default to web search tools without checking stored documents first.
3. This resulted in redundant searches and missed opportunities to use already-indexed content.

### Error Manifestation
```
User Query: "What does DLF company do?"

Agent Behavior (Before Fix):
- Step 1: Calls web search tool immediately
- Result: API call, slower response, even if DLF info was already in stored documents

Agent Behavior (After Fix):
- Step 1: Calls search_stored_documents first
- If found: Returns answer immediately (faster, no API call)
- If not found: Falls back to web search
```

### Fix Implementation

#### 1. Updated `prompts/decision_prompt_conservative.txt`
- **Updated TOOL SELECTION section with prioritized order**:
  ```
  🔍 TOOL SELECTION:
  - ❗CRITICAL: Personal/historical queries → Use `answer_from_history` FIRST
  - Pronouns: `get_current_conversations` (if `answer_from_history` unavailable)
  - Company/relationships: `search_stored_documents`, then `search`
  - ❗CRITICAL: If user query contains a URL → ALWAYS use `convert_webpage_url_into_markdown`
  ```

- **Key change**: Explicitly states `search_stored_documents` should be tried **before** `search` for company/relationship queries.

- **Added example showing the search order**:
  ```python
  # For company/entity queries:
  # 1. First try: search_stored_documents (local vector DB)
  # 2. If not found: Then try: search (web search)
  ```

#### 2. Updated `prompts/perception_prompt.txt`
- **Added priority rule**: "❗PRIORITY: For NEW queries that might be answered from stored documents (e.g., company relationships, historical data, stored information), select "documents" server SECOND (after memory if applicable). Only select "websearch" if the query requires real-time/latest information or if stored documents are unlikely to contain the answer."

### Files Modified
- `prompts/decision_prompt_conservative.txt` - Updated tool selection order to prioritize local document search
- `prompts/perception_prompt.txt` - Added priority guidance for document search before web search

### Testing
✅ Verified agent now:
- Checks `search_stored_documents` first for company/entity queries
- Only falls back to web `search` if local search doesn't find relevant information
- Reduces unnecessary API calls
- Provides faster responses when information is already indexed locally

---

## Conclusion

All critical bugs have been **FIXED**:
1. ✅ Code extraction failure - Fixed
2. ✅ LLM writing custom parsing code - Fixed  
3. ✅ FURTHER_PROCESSING_REQUIRED loop - Fixed
4. ✅ Incorrect tool selection for web URLs - Fixed
5. ✅ Missing vector database search before web search - Fixed

The agent now properly:
- Extracts Python code from LLM responses
- Uses search result summaries directly without custom parsing
- Analyzes provided tool outputs and generates final answers
- Terminates properly after completing tasks
- Selects the correct tool (`convert_webpage_url_into_markdown`) when URLs are present
- Prioritizes local document search before web search for better performance

---

## Author
Bug fixes implemented: November 14, 2025
Report generated: November 14, 2025

