import re

plan = """Based on your tool catalog and user query, here is a valid Python function named `solve()` that solves the user's query using exactly one function call:```python
import json
async def solve():
    # FUNCTION_CALL: 1
    \"\"\"Convert characters to ASCII values. Usage: input={"input": {"string": "INDIA"}} result = await mcp.call_tool('strings_to_chars_to_int', input)\"\"\"
    input = {"input": {"string": "INDIA"}}
    result = await mcp.call_tool('strings_to_chars_to_int', input)
    numbers = json.loads(result.content[0].text)["result"]

    # FINAL_ANSWER: Since we have the ASCII values, no further processing is required for summing exponentials.
    return f"FINAL_ANSWER: {numbers}"
```"""


print(re.search(r"^\s*(async\s+)?def\s+solve\s*\(", plan, re.MULTILINE))

