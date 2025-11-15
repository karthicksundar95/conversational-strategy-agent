"""
Guardrail Module - Heuristics for query and result validation
This module provides safety checks without modifying other scripts.
"""

import re
from typing import Tuple, Optional, List
from dataclasses import dataclass


@dataclass
class GuardrailResult:
    """Result of guardrail checks"""
    passed: bool
    sanitized_content: str
    warnings: List[str]
    blocked: bool
    reason: Optional[str] = None


class Guardrail:
    """Guardrail system with 10 heuristics for query and result validation"""
    
    def __init__(self):
        # Heuristic 1: Banned words list
        self.banned_words = {
            "hack", "exploit", "bypass", "crack", "illegal", 
            "malware", "virus", "phishing", "scam", "fraud"
        }
        
        # Heuristic 2: Profanity patterns (basic)
        self.profanity_patterns = [
            r'\b(f\*\*k|fuck|f\*\*king|fucking)\b',
            r'\b(sh\*t|shit|sh\*\*ing|shitting)\b',
            r'\b(a\*\*hole|asshole|a\*\*)\b',
            r'\b(b\*\*ch|bitch|b\*\*\*\*)\b',
            r'\b(damn|hell|bastard|piss|pissed)\b',
            r'\b(crap|c\*\*p|d\*\*n)\b',
        ]
        
        # Heuristic 3: PII patterns
        self.pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',  # SSN: 123-45-6789
            'credit_card': r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Credit card
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # US phone
        }
        
        # Heuristic 4: SQL injection patterns
        # More specific patterns to avoid false positives with normal apostrophes
        self.sql_injection_patterns = [
            r'(\bOR\b|\bAND\b).*=.*',
            r'(\bUNION\b|\bSELECT\b|\bINSERT\b|\bDELETE\b|\bDROP\b)',
            # Only match quotes in SQL injection contexts, not standalone apostrophes
            r'\'\s*(OR|AND|UNION|SELECT|INSERT|DELETE|DROP|EXEC|EXECUTE)',
            r'(OR|AND|UNION|SELECT|INSERT|DELETE|DROP|EXEC|EXECUTE)\s*\'',
            r'\'\s*=\s*\'',  # Pattern like '=' (SQL injection)
            r'\'\s*OR\s*\'',  # Pattern like ' OR ' (SQL injection)
            r'\'\s*AND\s*\'',  # Pattern like ' AND ' (SQL injection)
            r';\s*(--|\/\*)',  # Semicolon followed by SQL comment
            r'[=]\s*--',  # Equal sign followed by SQL comment
            r'\/\*.*\*\/',  # SQL block comment
            r'(\bEXEC\b|\bEXECUTE\b)',
        ]
        
        # Heuristic 5: Command injection patterns (more specific to avoid false positives)
        self.command_injection_patterns = [
            r'[;&|`]\s*\w+',  # Shell metacharacters followed by word (command-like)
            r'\b(cat|ls|rm|mv|cp|chmod|sudo)\s+',  # Common shell commands
            r'(\|\||&&)',  # Command chaining operators
            r'`[^`]+`',  # Backtick command execution
            r'\$\([^)]+\)',  # Command substitution $(...)
            r';\s*(cat|ls|rm|mv|cp|chmod|sudo|wget|curl)',  # Semicolon followed by command
        ]
        
        # Heuristic 6: URL validation patterns
        self.url_pattern = re.compile(
            r'https?://[^\s<>"{}|\\^`\[\]]+',
            re.IGNORECASE
        )
        
        # Heuristic 7: Sensitive file paths
        self.sensitive_paths = [
            r'/etc/passwd',
            r'/etc/shadow',
            r'C:\\Windows\\System32',
            r'\.\.\/\.\.\/',  # Path traversal
        ]
        
        # Heuristic 8: Max length limits
        self.max_query_length = 10000
        self.max_result_length = 50000
        
        # Heuristic 9: Suspicious encoding patterns
        self.encoding_patterns = [
            r'%[0-9A-Fa-f]{2}',  # URL encoding
            r'\\x[0-9A-Fa-f]{2}',  # Hex encoding
            r'\\u[0-9A-Fa-f]{4}',  # Unicode encoding
        ]
        
        # Heuristic 10: Suspicious script tags/HTML injection
        self.script_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'onerror\s*=',
            r'onclick\s*=',
        ]
    
    def check_query(self, query: str) -> GuardrailResult:
        """
        Apply all guardrail heuristics to a user query.
        
        Args:
            query: The user's input query
            
        Returns:
            GuardrailResult with sanitized content and warnings
        """
        warnings = []
        sanitized = query
        blocked = False
        reason = None
        
        # Heuristic 1: Remove banned words
        sanitized, banned_found = self._remove_banned_words(sanitized)
        if banned_found:
            warnings.append("Banned words detected and removed from query")
        
        # Heuristic 2: Check for profanity
        if self._contains_profanity(sanitized):
            warnings.append("Profanity detected in query")
            # Sanitize profanity
            sanitized = self._sanitize_profanity(sanitized)
        
        # Heuristic 3: Check for PII in query (shouldn't be there, but check)
        pii_found = self._detect_pii(sanitized)
        if pii_found:
            warnings.append(f"Potential PII detected in query: {', '.join(pii_found)}")
            # Sanitize PII
            sanitized = self._sanitize_pii(sanitized)
        
        # Heuristic 4: Check for SQL injection patterns
        if self._contains_sql_injection(sanitized):
            blocked = True
            reason = "SQL injection pattern detected in query"
            sanitized = self._sanitize_sql_injection(sanitized)
        
        # Heuristic 5: Check for command injection patterns
        if self._contains_command_injection(sanitized):
            blocked = True
            reason = "Command injection pattern detected in query"
            sanitized = self._sanitize_command_injection(sanitized)
        
        # Heuristic 6: Validate URLs in query
        urls = self._extract_urls(sanitized)
        for url in urls:
            if not self._is_safe_url(url):
                warnings.append(f"Potentially unsafe URL detected: {url[:50]}...")
        
        # Heuristic 7: Check for sensitive file paths
        if self._contains_sensitive_paths(sanitized):
            blocked = True
            reason = "Sensitive file path detected in query"
            sanitized = self._sanitize_paths(sanitized)
        
        # Heuristic 8: Check query length
        if len(query) > self.max_query_length:
            warnings.append(f"Query exceeds maximum length ({self.max_query_length} chars)")
            sanitized = sanitized[:self.max_query_length] + "... [truncated]"
        
        # Heuristic 9: Check for suspicious encoding
        if self._contains_suspicious_encoding(sanitized):
            warnings.append("Suspicious encoding patterns detected")
            sanitized = self._decode_suspicious_encoding(sanitized)
        
        # Heuristic 10: Check for script injection
        if self._contains_script_injection(sanitized):
            blocked = True
            reason = "Script injection pattern detected in query"
            sanitized = self._sanitize_scripts(sanitized)
        
        return GuardrailResult(
            passed=not blocked,
            sanitized_content=sanitized,
            warnings=warnings,
            blocked=blocked,
            reason=reason
        )
    
    def check_result(self, result: str) -> GuardrailResult:
        """
        Apply all guardrail heuristics to a result/output.
        
        Args:
            result: The result/output to check
            
        Returns:
            GuardrailResult with sanitized content and warnings
        """
        warnings = []
        sanitized = result
        blocked = False
        reason = None
        
        # Heuristic 1: Remove banned words from results
        sanitized, banned_found = self._remove_banned_words(sanitized)
        if banned_found:
            warnings.append("Banned words detected and removed from result")
        
        # Heuristic 2: Check for profanity in results
        if self._contains_profanity(sanitized):
            warnings.append("Profanity detected in result")
            sanitized = self._sanitize_profanity(sanitized)
        
        # Heuristic 3: Check for PII in results (critical!)
        pii_found = self._detect_pii(sanitized)
        if pii_found:
            warnings.append(f"PII detected in result: {', '.join(pii_found)}")
            # Always sanitize PII in results
            sanitized = self._sanitize_pii(sanitized)
        
        # Heuristic 4: Check for SQL injection in results
        # Only warn, don't sanitize - results often contain false positives (e.g., "European Union")
        if self._contains_sql_injection(sanitized):
            warnings.append("SQL injection pattern detected in result (may be false positive)")
            # Don't sanitize results - too many false positives in document content
        
        # Heuristic 5: Check for command injection in results
        # Only warn, don't block - document content often contains false positives (e.g., "& Co.", "| Company")
        if self._contains_command_injection(sanitized):
            warnings.append("Command injection pattern detected in result (may be false positive in document content)")
            # Don't block or sanitize results - too many false positives in legitimate document content
        
        # Heuristic 6: Validate URLs in results
        urls = self._extract_urls(sanitized)
        for url in urls:
            if not self._is_safe_url(url):
                warnings.append(f"Potentially unsafe URL in result: {url[:50]}...")
                sanitized = sanitized.replace(url, "[URL REMOVED]")
        
        # Heuristic 7: Check for sensitive file paths in results
        if self._contains_sensitive_paths(sanitized):
            warnings.append("Sensitive file path detected in result")
            sanitized = self._sanitize_paths(sanitized)
        
        # Heuristic 8: Check result length
        if len(result) > self.max_result_length:
            warnings.append(f"Result exceeds maximum length ({self.max_result_length} chars)")
            sanitized = sanitized[:self.max_result_length] + "... [truncated]"
        
        # Heuristic 9: Check for suspicious encoding in results
        if self._contains_suspicious_encoding(sanitized):
            warnings.append("Suspicious encoding patterns detected in result")
            sanitized = self._decode_suspicious_encoding(sanitized)
        
        # Heuristic 10: Check for script injection in results
        # Only warn, don't block - document content may contain script-like patterns in code examples
        if self._contains_script_injection(sanitized):
            warnings.append("Script injection pattern detected in result (may be false positive in document content)")
            # Don't block or sanitize results - document content may legitimately contain script examples
        
        return GuardrailResult(
            passed=not blocked,
            sanitized_content=sanitized,
            warnings=warnings,
            blocked=blocked,
            reason=reason
        )
    
    # Helper methods for each heuristic
    
    def _remove_banned_words(self, text: str) -> Tuple[str, bool]:
        """Heuristic 1: Remove banned words"""
        found = False
        words = text.split()
        sanitized_words = []
        for word in words:
            word_lower = word.lower().strip('.,!?;:()[]{}"\'')
            if word_lower in self.banned_words:
                found = True
                sanitized_words.append("[REDACTED]")
            else:
                sanitized_words.append(word)
        return ' '.join(sanitized_words), found
    
    def _contains_profanity(self, text: str) -> bool:
        """Heuristic 2: Check for profanity"""
        for pattern in self.profanity_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _sanitize_profanity(self, text: str) -> str:
        """Sanitize profanity"""
        for pattern in self.profanity_patterns:
            text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
        return text
    
    def _detect_pii(self, text: str) -> List[str]:
        """Heuristic 3: Detect PII"""
        found = []
        for pii_type, pattern in self.pii_patterns.items():
            if re.search(pattern, text):
                found.append(pii_type.upper())
        return found
    
    def _sanitize_pii(self, text: str) -> str:
        """Sanitize PII"""
        # Replace SSN
        text = re.sub(self.pii_patterns['ssn'], '[SSN REDACTED]', text)
        # Replace credit cards
        text = re.sub(self.pii_patterns['credit_card'], '[CARD REDACTED]', text)
        # Replace emails (keep domain for context)
        text = re.sub(
            self.pii_patterns['email'],
            lambda m: f'[EMAIL: {m.group().split("@")[1]}]',
            text
        )
        # Replace phone numbers
        text = re.sub(self.pii_patterns['phone'], '[PHONE REDACTED]', text)
        return text
    
    def _contains_sql_injection(self, text: str) -> bool:
        """Heuristic 4: Check for SQL injection"""
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _sanitize_sql_injection(self, text: str) -> str:
        """Sanitize SQL injection patterns"""
        for pattern in self.sql_injection_patterns:
            text = re.sub(pattern, '[SQL PATTERN REMOVED]', text, flags=re.IGNORECASE)
        return text
    
    def _contains_command_injection(self, text: str) -> bool:
        """Heuristic 5: Check for command injection (more lenient for URLs and search results)"""
        # If text contains URLs, be more lenient (URLs often have special chars)
        has_urls = bool(self.url_pattern.search(text))
        
        # Check for command injection patterns
        for pattern in self.command_injection_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                # If URLs are present, only block if it's clearly a command (not just URL chars)
                if has_urls:
                    # These patterns are actual command patterns, block them even with URLs
                    if pattern in [r'\b(cat|ls|rm|mv|cp|chmod|sudo)\s+', r'(\|\||&&)', r'`[^`]+`', r'\$\([^)]+\)', r';\s*(cat|ls|rm|mv|cp|chmod|sudo|wget|curl)']:
                        return True
                    # Pattern like `[;&|`]\s*\w+` might match URL chars, skip if URLs present
                    if pattern == r'[;&|`]\s*\w+':
                        continue
                return True
        return False
    
    def _sanitize_command_injection(self, text: str) -> str:
        """Sanitize command injection patterns"""
        for pattern in self.command_injection_patterns:
            text = re.sub(pattern, '[COMMAND PATTERN REMOVED]', text)
        return text
    
    def _extract_urls(self, text: str) -> List[str]:
        """Heuristic 6: Extract URLs"""
        return self.url_pattern.findall(text)
    
    def _is_safe_url(self, url: str) -> bool:
        """Check if URL is safe"""
        unsafe_domains = ['malware.com', 'phishing.com']  # Add more as needed
        url_lower = url.lower()
        return not any(domain in url_lower for domain in unsafe_domains)
    
    def _contains_sensitive_paths(self, text: str) -> bool:
        """Heuristic 7: Check for sensitive file paths"""
        for pattern in self.sensitive_paths:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _sanitize_paths(self, text: str) -> str:
        """Sanitize sensitive paths"""
        for pattern in self.sensitive_paths:
            text = re.sub(pattern, '[PATH REDACTED]', text, flags=re.IGNORECASE)
        return text
    
    def _contains_suspicious_encoding(self, text: str) -> bool:
        """Heuristic 9: Check for suspicious encoding"""
        for pattern in self.encoding_patterns:
            if len(re.findall(pattern, text)) > 5:  # Threshold
                return True
        return False
    
    def _decode_suspicious_encoding(self, text: str) -> str:
        """Decode suspicious encoding (simplified)"""
        # In production, use proper decoding libraries
        # For now, just flag it
        return text  # Keep as-is, but warn
    
    def _contains_script_injection(self, text: str) -> bool:
        """Heuristic 10: Check for script injection"""
        for pattern in self.script_patterns:
            if re.search(pattern, text, re.IGNORECASE | re.DOTALL):
                return True
        return False
    
    def _sanitize_scripts(self, text: str) -> str:
        """Sanitize script tags"""
        for pattern in self.script_patterns:
            text = re.sub(pattern, '[SCRIPT REMOVED]', text, flags=re.IGNORECASE | re.DOTALL)
        return text


# Global instance for easy import
guardrail = Guardrail()


def check_query(query: str) -> GuardrailResult:
    """Convenience function to check a query"""
    return guardrail.check_query(query)


def check_result(result: str) -> GuardrailResult:
    """Convenience function to check a result"""
    return guardrail.check_result(result)

