"""
Example usage of the guardrail module
This demonstrates how to integrate guardrails without modifying existing scripts.
"""

from modules.guardrail import check_query, check_result, GuardrailResult


def example_usage():
    """Example of how to use guardrails"""
    
    # Example 1: Check a query with banned words
    query1 = "How to hack into a system?"
    result1 = check_query(query1)
    print(f"Query: {query1}")
    print(f"Passed: {result1.passed}")
    print(f"Sanitized: {result1.sanitized_content}")
    print(f"Warnings: {result1.warnings}")
    print()
    
    # Example 2: Check a query with SQL injection
    query2 = "SELECT * FROM users WHERE id = 1 OR 1=1"
    result2 = check_query(query2)
    print(f"Query: {query2}")
    print(f"Blocked: {result2.blocked}")
    print(f"Reason: {result2.reason}")
    print(f"Sanitized: {result2.sanitized_content}")
    print()
    
    # Example 3: Check a result with PII
    result_text = "User John Doe (SSN: 123-45-6789) can be reached at john@example.com"
    result3 = check_result(result_text)
    print(f"Original Result: {result_text}")
    print(f"Sanitized: {result3.sanitized_content}")
    print(f"Warnings: {result3.warnings}")
    print()
    
    # Example 4: Check a result with script injection
    result_text2 = "<script>alert('XSS')</script>Hello World"
    result4 = check_result(result_text2)
    print(f"Original Result: {result_text2}")
    print(f"Blocked: {result4.blocked}")
    print(f"Sanitized: {result4.sanitized_content}")
    print()


if __name__ == "__main__":
    example_usage()

