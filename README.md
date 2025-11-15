# 🧠 Cortex-R Agent

A reasoning-driven AI agent system that uses a **Perception → Decision → Action** loop to solve complex tasks. The agent leverages multiple MCP (Model Context Protocol) servers, maintains session-based memory with semantic search, and uses LLM-based planning to generate executable Python code.

## ✨ Key Features

- **🧠 Intelligent Memory System**: Semantic search across historical conversations with automatic indexing
- **🔍 Smart Context Awareness**: Leverages previous conversations to provide context-aware answers
- **🌐 Web Content Processing**: Crawl, extract, and summarize web pages with automatic memory indexing
- **🛠️ Multi-Tool Integration**: Seamlessly integrates math, document processing, web search, and memory tools
- **🔄 Adaptive Planning**: Conservative and exploratory planning modes with automatic retry mechanisms

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables
export OPENAI_API_KEY=your_api_key_here

# Run the agent
python agent.py
```

## 📚 Usage Examples

### Example 1: Direct Answer from Historical Memory

When you ask the same question again, Cortex-R retrieves the answer directly from historical conversations without any tool calls.

**Query:**
```
🧑 What do you want to solve today? → Find the ASCII values of characters in INDIA and then return sum of exponentials of those values.
```

**Terminal Output:**
```
[23:19:01] [historical_check] 🔍 Checking historical conversations for direct answer...
[23:19:01] [historical_check] 📚 Found 5 relevant historical conversations

══════════════════════════════════════════════════════════════════════
║                                                                    ║
║                        PATH: DIRECT_ANSWER                         ║
║                                                                    ║
║ Answer found completely in historical conversations                 ║
║                                                                    ║
══════════════════════════════════════════════════════════════════════

[23:19:02] [historical_check] ✅ Answer found in historical conversations - returning directly
[23:19:02] [agent] ✅ Direct answer from historical conversations - skipping tool loop

💡 Final Answer: {"ascii_values": [73, 78, 68, 73, 65], "exponential_sum": 7.59982224609308e+33}
```

**What Happened:**
- The agent searched historical conversations using semantic search
- Found an exact match from a previous conversation
- Returned the answer immediately without any tool calls
- The conversation was automatically indexed for future searches

---

### Example 2: Partial Context + Tool Call

When historical context provides partial information, Cortex-R uses that context and calls appropriate tools to complete the task.

**Query:**
```
🧑 What do you want to solve today? → can you add 5 to ASCII values of INDIA
```

**Terminal Output:**
```
[23:19:22] [historical_check] 🔍 Checking historical conversations for direct answer...
[23:19:23] [historical_check] 📚 Found 5 relevant historical conversations

══════════════════════════════════════════════════════════════════════
║                                                                    ║
║                        PATH: CONTEXT_AWARE                         ║
║                                                                    ║
║ Relevant context found - will send to perception layer              ║
║                                                                    ║
║────────────────────────────────────────────────────────────────────║
║ CONTEXT TAKEN FORWARD:                                             ║
║────────────────────────────────────────────────────────────────────║
║ Previous conversations provide the ASCII values for the characters  ║
║ in "INDIA" as [73, 78, 68, 73, 65]. However, the specific request  ║
║ to add 5 to these ASCII values has not been directly answered.     ║
║                                                                    ║
══════════════════════════════════════════════════════════════════════

[23:19:24] [historical_check] 📚 Relevant context found in history - will send to perception layer
[23:19:24] [agent] 📚 Proceeding to tool loop with historical context (will be sent to perception)
🔁 Step 1/5 starting...
[23:19:26] [perception] intent='Perform arithmetic operation on ASCII values' 
           entities=['5', 'ASCII', 'INDIA'] 
           tool_hint='You can compute the new ASCII values by adding 5 to each of the previous ASCII values.'
           selected_servers=['math']

[plan] async def solve():
    # USE the provided values from context - DO NOT call strings_to_chars_to_int!
    ascii_values = [73, 78, 68, 73, 65]  # From context
    # Now add 5 to each
    result = []
    for val in ascii_values:
        add_result = await mcp.call_tool('add', {"input": {"a": val, "b": 5}})
        result.append(json.loads(add_result.content[0].text)["result"])
    return "FINAL_ANSWER: " + str(result)

[23:19:31] [sandbox] 🔧 Calling tool: add (call #1)
[23:19:31] [sandbox] ✅ Tool add completed
...

💡 Final Answer: [78, 83, 73, 78, 70]
```

**What Happened:**
- Found relevant historical context (ASCII values for INDIA)
- Recognized that the context provides partial information
- Used the provided ASCII values directly (didn't re-fetch them)
- Called the `add` tool 5 times to add 5 to each value
- Combined historical context with tool calls to complete the task

---

### Example 3: Web Page Crawling and Automatic Indexing

Cortex-R can crawl web pages, extract content, summarize it, and automatically index it to memory for future searches.

**Query:**
```
🧑 What do you want to solve today? → can you summarize this https://www.seldon.io/managing-realtime-ai-cost-in-production-a-practical-guide/
```

**Terminal Output:**
```
[23:37:14] [historical_check] 🔍 Checking historical conversations for direct answer...
[23:37:15] [historical_check] 🆕 No relevant context in history - proceeding with traditional route
[23:37:15] [agent] 🆕 Proceeding to tool loop with fresh approach (no relevant history)
🔁 Step 1/5 starting...
[23:37:18] [perception] intent='summarize an article' 
           entities=['Seldon', 'AI', 'cost', 'production', 'guide'] 
           selected_servers=['documents', 'websearch']

[plan] async def solve():
    result = await mcp.call_tool('convert_webpage_url_into_markdown', 
                                  {"input": {"url": "https://www.seldon.io/..."}})
    markdown = json.loads(result.content[0].text)["markdown"]
    return "FURTHER_PROCESSING_REQUIRED: " + markdown

[23:37:20] [sandbox] 🔧 Calling tool: convert_webpage_url_into_markdown (call #1)
CAPTION: 🖼️ Attempting to caption image: https://www.seldon.io/wp-content/uploads/...
CAPTION: ✅ Caption generated: [Image descriptions]
[23:37:22] [sandbox] ✅ Tool convert_webpage_url_into_markdown completed

##### FURTHER_PROCESSING_REQUIRED: In the last three years adoption of AI across industries has increased by 56% [1]. This growth has translated into a surge of AI use-cases reaching production...

[23:37:22] [loop] 🔍 Content already provided - using LLM directly to analyze (bypassing tool selection)
[23:37:22] [loop] ✅ LLM direct analysis completed

💡 Final Answer: [Comprehensive summary of the article about managing real-time AI costs in production, including key strategies, cost breakdowns, and best practices...]

[conversation_indexer] Saved index with 35 conversations
[conversation_indexer] ✅ Indexed conversation: 2025/11/14/session-1...
[23:37:38] [agent] ✅ Conversation indexed for semantic search
```

**What Happened:**
- Detected URL in query and selected appropriate tools
- Called `convert_webpage_url_into_markdown` to extract clean markdown
- Automatically captioned images in the webpage
- Used LLM to analyze and summarize the content
- **Automatically indexed the entire conversation** (query + answer) to memory
- Future queries about this article will retrieve it from memory

---

## 🏗️ Architecture

> **📄 Architecture Diagram**: See `architecture_diagram.pdf` for a comprehensive flowchart visualization of the system architecture.

### Three-Path Historical Context System

Cortex-R uses an intelligent pre-check layer that determines the best path for each query:

```
┌─────────────────────────────────────────┐
│   Historical Conversation Check          │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌───────────────┐      ┌───────────────┐
│ PATH 1:       │      │ PATH 2:       │
│ DIRECT_ANSWER │      │ CONTEXT_AWARE │
│               │      │               │
│ Answer found  │      │ Partial info  │
│ completely in │      │ found - use    │
│ history       │      │ with tools    │
└───────────────┘      └───────────────┘
                              │
                              ▼
                    ┌───────────────┐
                    │ PATH 3:       │
                    │ FRESH_APPROACH │
                    │               │
                    │ No relevant   │
                    │ context       │
                    └───────────────┘
```

### Key Components

1. **Historical Check Layer** (`modules/historical_check.py`)
   - Searches historical conversations using semantic search
   - Uses LLM to determine if answer is available
   - Returns one of three paths: DIRECT_ANSWER, CONTEXT_AWARE, or FRESH_APPROACH

2. **Perception Layer** (`modules/perception.py`)
   - Analyzes user intent and entities
   - Selects relevant MCP servers
   - Can receive historical context to inform tool selection

3. **Decision Layer** (`modules/decision.py`)
   - Generates executable Python `solve()` functions
   - Uses provided context values directly (no re-fetching)
   - Handles tool selection and planning

4. **Action Layer** (`modules/action.py`)
   - Executes generated plans in a sandboxed environment
   - Manages tool calls with rate limiting
   - Returns results or `FURTHER_PROCESSING_REQUIRED`

5. **Memory System** (`modules/conversation_indexer.py`)
   - Automatically indexes all conversations
   - Uses FAISS for semantic search
   - Stores conversation metadata and embeddings

## 🔧 Configuration

Edit `config/profiles.yaml` to customize:

- **LLM Provider**: OpenAI, Gemini, or Ollama
- **Planning Mode**: Conservative (one tool per step) or Exploratory (multiple tools)
- **Memory Settings**: Storage location, summarization, tagging
- **MCP Servers**: Add or modify tool servers

## 📝 Features in Detail

### Smart Context Reuse

- **No Re-fetching**: When historical context provides values, the agent uses them directly
- **Context-Aware Tool Selection**: Perception layer receives historical context to make better tool choices
- **Irrelevant Context Filtering**: Automatically detects and ignores irrelevant historical context

### Web Content Processing

- **Clean Markdown Extraction**: Converts web pages to clean, readable markdown
- **Image Captioning**: Automatically generates captions for images using vision models
- **Automatic Indexing**: All crawled content is indexed for future semantic search

### Loop Prevention

- **Strict Rules**: When content is provided via `FURTHER_PROCESSING_REQUIRED`, the agent analyzes it directly
- **LLM Fallback**: If loops are detected, the system automatically uses LLM to analyze content
- **Content Detection**: Automatically detects when content is already provided and bypasses tool selection

## 🛡️ Guardrails

- **Query Validation**: Checks for SQL injection, command injection, and other security threats
- **Result Sanitization**: Sanitizes PII and sensitive information in final outputs
- **Content Filtering**: Removes banned words and profanity
- **Safe Execution**: Sandboxed Python execution with tool call limits

## 📊 Memory System

All conversations are automatically indexed with:
- **Semantic Search**: FAISS-based vector search for finding relevant conversations
- **Metadata Storage**: Stores user queries, final answers, and tool calls
- **Session Management**: Organizes conversations by date and session ID

## 🎯 Use Cases

- **Research & Summarization**: Crawl and summarize web articles
- **Data Analysis**: Perform calculations with context from previous sessions
- **Information Retrieval**: Find answers from historical conversations
- **Multi-step Problem Solving**: Break down complex tasks into steps

## 📸 Screenshots

> **Note**: Add screenshots here showing:
> - Terminal output for each example
> - The PATH selection boxes
> - Memory indexing confirmation messages
> - Tool call logs

## 🤝 Contributing

This is a learning project. Feel free to explore the codebase and suggest improvements!

## 📄 License

[Add your license here]

---

**Built with ❤️ using MCP (Model Context Protocol), FAISS, and modern LLM APIs**

