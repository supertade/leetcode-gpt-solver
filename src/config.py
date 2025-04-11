"""
Konfigurationsdatei für die LeetCode-Problemverarbeitung.
"""

# API und Modell-Einstellungen
DEFAULT_MODEL = "codellama"
DEFAULT_TEMPERATURE = 0.4
DEFAULT_PROBLEM_LIMIT = 50

# Zeitverzögerungen
API_RETRY_DELAY = 1  # Sekunden zwischen API-Aufrufen
TEST_DELAY = 1  # Sekunden zwischen Tests

# Prompt-Einstellungen
PROMPT_TEMPLATE = """### LeetCode Problem: {title}

{question}

### Examples:
{examples}

---
Write a complete and compilable solution to this problem in modern C++17, wrapped in a single class `Solution` as required by LeetCode.

Requirements for a valid solution:

1. Use the exact method signature specified by LeetCode (e.g., `bool isValid(string s)` or `vector<int> twoSum(vector<int>& nums, int target)`).
2. Do not include a `main()` function, test code, `cin`/`cout`, or extra I/O logic.
3. Assume the method will be tested externally — write only the logic inside `class Solution`.

The solution must:
- Include all necessary `#include` statements at the top
- Use correct C++ types (e.g., `vector<int>`, not just `vector`, always with `std::` or `using namespace std`)
- Initialize all variables before use
- Use proper C++ containers (vector, unordered_map, etc.) with correct template parameters
- Handle edge cases (empty input, null pointers, etc.)
- Use nullptr for null pointers, not NULL or 0
- Return the exact type specified (e.g., don't return int when vector<int> is required)
- Use references (&) for large objects to avoid copying
- Use const where appropriate
- End all statements with semicolons
- Match all braces and parentheses
- Follow standard C++ naming conventions

Common pitfalls to avoid:
- Don't mix up . and -> operators for pointers
- Don't forget to include required headers
- Don't use C-style arrays, use std::vector instead
- Don't use raw pointers except for tree/linked list nodes
- Don't leave any variables uninitialized
- Don't return from void functions
- Don't mix signed and unsigned integers

✅ Output only the C++ code. No explanation, no markdown, no comments. Just clean, valid, and complete code.
"""

# Spezielle Problem-Behandlung
SPECIAL_CASES = {
    "valid-parentheses": {
        "input_transform": lambda args: [args[0][0]] if isinstance(args, list) and len(args) >= 1 and isinstance(args[0], list) and len(args[0]) == 1 else args
    }
}

# Export-Einstellungen
CSV_SUMMARY_HEADERS = ["Difficulty", "Total", "Success", "Success Rate", "Compile Errors", "Runtime Errors"]
CSV_ERROR_TYPES_HEADERS = ["Difficulty", "Error Type", "Count", "Percentage"] 