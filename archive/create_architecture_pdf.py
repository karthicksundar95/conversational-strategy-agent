#!/usr/bin/env python3
"""
Generate Cortex-R Agent Architecture Diagram as PDF

This script creates a comprehensive flowchart diagram showing:
- Entry point and initialization
- Historical check with 3 paths (DIRECT_ANSWER, CONTEXT_AWARE, FRESH_APPROACH)
- Core loop (Perception → Decision → Action)
- MCP infrastructure
- Memory system
- Model management
- Final output flow

Requirements:
- Install graphviz: brew install graphviz (macOS) or apt-get install graphviz (Linux)
- Install Python package: pip install graphviz
- OR use online converter: https://dreampuf.github.io/GraphvizOnline/
"""

import os
import subprocess
import sys

def check_graphviz():
    """Check if graphviz is installed"""
    try:
        result = subprocess.run(['dot', '-V'], capture_output=True, text=True)
        return True
    except FileNotFoundError:
        return False

def create_dot_file():
    """Create the DOT file content"""
    dot_content = '''digraph CortexR_Architecture {
    rankdir=TB;
    size="16,12";
    dpi=300;
    node [shape=box, style="rounded,filled", fontsize=10];
    
    // Entry Point Layer
    subgraph cluster_entry {
        label="Entry Point Layer";
        style=filled;
        color=lightblue;
        fontsize=14;
        fontweight=bold;
        
        agent [label="agent.py\\nMain Entry", fillcolor="#e1f5ff"];
        multimcp [label="MultiMCP\\nServer Manager", fillcolor="#e0f2f1"];
        context [label="AgentContext\\nSession State", fillcolor="#e1f5ff"];
        guardrail [label="Guardrail\\nQuery Check", fillcolor="#ffe1e1"];
        hist_check [label="Historical Check\\nPre-Layer", fillcolor="#fff4e1"];
        
        agent -> multimcp;
        agent -> context;
        agent -> guardrail;
        guardrail -> hist_check;
    }
    
    // Historical Check - 3 Paths
    subgraph cluster_history {
        label="Historical Check (3 Paths)";
        style=filled;
        color=lightyellow;
        fontsize=12;
        fontweight=bold;
        
        path1 [label="PATH 1:\\nDIRECT_ANSWER\\n(Complete answer\\nfound in history)", fillcolor="#90EE90", shape=diamond];
        path2 [label="PATH 2:\\nCONTEXT_AWARE\\n(Partial context\\n+ tools)", fillcolor="#FFE4B5", shape=diamond];
        path3 [label="PATH 3:\\nFRESH_APPROACH\\n(No relevant\\ncontext)", fillcolor="#E6E6FA", shape=diamond];
        
        hist_check -> path1 [label="Answer\\nComplete"];
        hist_check -> path2 [label="Partial\\nContext"];
        hist_check -> path3 [label="No\\nContext"];
    }
    
    // Core Loop
    subgraph cluster_loop {
        label="Core Loop (AgentLoop)";
        style=filled;
        color=lightgreen;
        fontsize=14;
        fontweight=bold;
        
        loop [label="AgentLoop\\nOrchestrator", fillcolor="#fff4e1"];
        perception [label="Perception Module\\n• LLM Analysis\\n• Intent/Entities\\n• Server Selection", fillcolor="#e8f5e9"];
        decision [label="Decision Module\\n• Strategy Selection\\n• Tool Filtering\\n• Plan Generation\\n(solve() function)", fillcolor="#f3e5f5"];
        action [label="Action Module\\n• Sandbox Execution\\n• Tool Calls\\n• Result Formatting", fillcolor="#fce4ec"];
        result_check [label="Result Check\\nFINAL_ANSWER?\\nFURTHER_PROCESSING?", fillcolor="#ffe1e1", shape=diamond];
        
        loop -> perception;
        perception -> decision;
        decision -> action;
        action -> result_check;
        result_check -> perception [label="FURTHER_PROCESSING", style=dashed, color=orange];
        
        path2 -> loop [label="With Context"];
        path3 -> loop [label="No Context"];
    }
    
    // MCP Infrastructure
    subgraph cluster_mcp {
        label="MCP Infrastructure";
        style=filled;
        color=lightcyan;
        fontsize=12;
        fontweight=bold;
        
        mcp1 [label="MCP Server 1\\n(Math Tools)\\n• add, multiply, divide\\n• strings_to_chars_to_int\\n• fibonacci_numbers", fillcolor="#E0F2F1"];
        mcp2 [label="MCP Server 2\\n(Documents)\\n• search_stored_documents\\n• convert_webpage_url_into_markdown\\n• extract_pdf", fillcolor="#E0F2F1"];
        mcp3 [label="MCP Server 3\\n(Web Search)\\n• search\\n• fetch_content", fillcolor="#E0F2F1"];
        mcp_mem [label="MCP Server Memory\\n• search_historical_conversations\\n• answer_from_history\\n• get_current_conversations", fillcolor="#E0F2F1"];
        
        action -> multimcp [label="Tool Calls"];
        multimcp -> mcp1;
        multimcp -> mcp2;
        multimcp -> mcp3;
        multimcp -> mcp_mem;
        hist_check -> mcp_mem [label="Search History"];
    }
    
    // Memory System
    subgraph cluster_memory {
        label="Memory System";
        style=filled;
        color=lightyellow;
        fontsize=12;
        fontweight=bold;
        
        mem_mgr [label="MemoryManager\\n• Session Memory\\n• Tool Outputs\\n• Metadata", fillcolor="#fff9c4"];
        indexer [label="ConversationIndexer\\n• FAISS Vector DB\\n• Semantic Search\\n• Auto-indexing", fillcolor="#fff9c4"];
        
        context -> mem_mgr;
        action -> mem_mgr [label="Store Results"];
        mem_mgr -> indexer;
        indexer -> mcp_mem [label="Vector Search"];
    }
    
    // Model Management
    subgraph cluster_model {
        label="Model Management";
        style=filled;
        color=lavender;
        fontsize=12;
        fontweight=bold;
        
        model_mgr [label="ModelManager\\n• OpenAI\\n• Gemini\\n• Ollama", fillcolor="#E6E6FA"];
        
        perception -> model_mgr [label="LLM Call"];
        decision -> model_mgr [label="LLM Call"];
        hist_check -> model_mgr [label="LLM Call"];
    }
    
    // Final Output
    final [label="Final Answer\\n(Guardrail Check)\\n→ User", fillcolor="#90EE90", shape=ellipse];
    path1 -> final [label="Direct Return", style=bold, color=green];
    result_check -> final [label="FINAL_ANSWER", style=bold, color=green];
    final -> indexer [label="Auto-index"];
}
'''
    return dot_content

def main():
    print("=" * 70)
    print("Cortex-R Agent Architecture Diagram Generator")
    print("=" * 70)
    
    # Create DOT file
    dot_file = "architecture_diagram.dot"
    dot_content = create_dot_file()
    
    with open(dot_file, 'w') as f:
        f.write(dot_content)
    
    print(f"✅ Created DOT file: {dot_file}")
    
    # Check if graphviz is available
    if check_graphviz():
        print("\n📊 Converting DOT to PDF using graphviz...")
        try:
            subprocess.run(['dot', '-Tpdf', dot_file, '-o', 'architecture_diagram.pdf'], 
                         check=True)
            print("✅ PDF created successfully: architecture_diagram.pdf")
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ Error converting to PDF: {e}")
            print("\n📝 Alternative: Use online converter:")
            print("   1. Go to: https://dreampuf.github.io/GraphvizOnline/")
            print(f"   2. Copy contents of {dot_file}")
            print("   3. Paste and click 'Generate'")
            print("   4. Download as PDF")
            return False
    else:
        print("\n⚠️  Graphviz not found. To install:")
        print("   macOS: brew install graphviz")
        print("   Linux: sudo apt-get install graphviz")
        print("   Then: pip install graphviz")
        print("\n📝 Alternative: Use online converter:")
        print("   1. Go to: https://dreampuf.github.io/GraphvizOnline/")
        print(f"   2. Copy contents of {dot_file}")
        print("   3. Paste and click 'Generate'")
        print("   4. Download as PDF")
        return False

if __name__ == '__main__':
    main()

