import subprocess
import tempfile
import os
import re
import json

ERROR_TYPES = {
    # Grundlegende Syntax-Fehler
    "missing_semicolon": ["expected ';'", "missing ';'"],
    "unexpected_semicolon": ["unexpected ';'", "extraneous ';'"],
    "semicolon_in_keyword": ["undeclared identifier 'fals'", "undeclared identifier 'tru'", "use of undeclared identifier 'nul'"],
    "semicolon_in_variable": ["undeclared identifier '", "use of undeclared identifier '"],
    "semicolon_in_expression": ["expected expression", "expression result unused"],
    "semicolon_in_return": ["return value", "return type", "return statement"],
    
    # Referenz-Fehler
    "undefined_reference": ["undefined reference", "undefined symbol"],
    "undeclared_identifier": ["undeclared identifier", "use of undeclared identifier"],
    
    # Typ-Fehler
    "template_error": ["error: template", "no matching function", "invalid template argument", "no matching function template"],
    "expected_expression": ["expected expression", "expected '>'", "expected ')'" , "expected ']'", "expected '{'"],
    "syntax_error": ["syntax error", "parse error", "expected", "unterminated"],
    "conversion_error": ["cannot convert", "no conversion", "invalid conversion", "invalid cast", "no known conversion"],
    "type_error": [
        "invalid type",
        "cannot initialize",
        "incompatible types",
        "no suitable constructor",
        "no viable conversion",
        "no matching function",
        "cannot bind",
        "invalid operands",
        "wrong type argument",
        "no matching member function",
        "no matching constructor"
    ],
    
    # Bibliotheks-Fehler
    "std_error": [
        "use of undeclared identifier 'std'",
        "namespace 'std' not found",
        "did you mean 'std::"
    ],
    "container_error": [
        "vector",
        "unordered_map",
        "map",
        "set",
        "queue",
        "stack",
        "deque",
        "list"
    ].extend([f"use of undeclared identifier '{container}'" for container in [
        "vector", "unordered_map", "map", "set", "queue", "stack", "deque", "list"
    ]]),
    "header_missing": [
        "'vector' file not found",
        "'unordered_map' file not found",
        "'string' file not found",
        "'algorithm' file not found",
        "'queue' file not found",
        "'stack' file not found",
        "'set' file not found",
        "'map' file not found"
    ],
    "namespace_error": [
        "namespace 'std' has no member",
        "is not a member of namespace 'std'",
        "no member named",
        "no type named"
    ],
    
    # Laufzeit-Fehler
    "array_index_error": ["array index out of range", "subscript is outside array bounds", "vector subscript out of range"],
    "null_pointer_error": ["null pointer dereference", "reference to null pointer", "null reference", "segmentation fault"],
    "uninitialized_variable": ["uninitialized", "may be used uninitialized", "variable used without being initialized"],
    "memory_error": ["bad_alloc", "stack overflow", "heap corruption", "memory corruption"],
    
    # Funktionsaufruf-Fehler
    "argument_error": [
        "too many arguments",
        "too few arguments",
        "no matching function call",
        "invalid arguments",
        "cannot convert argument",
        "no known conversion for argument",
        "wrong number of template arguments"
    ],
    "return_type_error": [
        "cannot convert return value",
        "return type mismatch",
        "invalid return type",
        "no viable conversion from returned value"
    ],
    
    # Sonstiges
    "unknown_error": []
}

def inject_standard_leetcode_types(code: str) -> str:
    """Fügt Standard-LeetCode-Datentypen wie ListNode automatisch hinzu, falls sie im Code verwendet werden"""
    additions = []

    # Nur hinzufügen, wenn der Typ noch nicht definiert ist
    if "ListNode" in code and not "struct ListNode" in code and not "class ListNode" in code:
        additions.append("""
struct ListNode {
    int val;
    ListNode *next;
    ListNode() : val(0), next(nullptr) {}
    ListNode(int x) : val(x), next(nullptr) {}
    ListNode(int x, ListNode *next) : val(x), next(next) {}
};
""")

    if "TreeNode" in code and not "struct TreeNode" in code and not "class TreeNode" in code:
        additions.append("""
struct TreeNode {
    int val;
    TreeNode *left;
    TreeNode *right;
    TreeNode() : val(0), left(nullptr), right(nullptr) {}
    TreeNode(int x) : val(x), left(nullptr), right(nullptr) {}
    TreeNode(int x, TreeNode *left, TreeNode *right) : val(x), left(left), right(right) {}
};
""")

    if "Node" in code and "val" in code and "next" in code and not "struct Node" in code and not "class Node" in code:
        # vorsichtshalber nicht TreeNode oder ListNode
        additions.append("""
class Node {
public:
    int val;
    Node* next;
    Node* random;
    Node() : val(0), next(nullptr), random(nullptr) {}
    Node(int _val) : val(_val), next(nullptr), random(nullptr) {}
    Node(int _val, Node* _next, Node* _random) : val(_val), next(_next), random(_random) {}
};
""")
        
    # ✅ Logging
    if additions:
        print("ℹ️ Injected standard LeetCode types:", ", ".join([block.strip().split()[1] for block in additions]))

    return "\n".join(additions) + "\n" + code if additions else code

def check_split_tokens(code: str):
    """Erkennt typische semikolon-zerstörte Tokens wie fals;e, retur;n usw."""
    split_tokens = {
        "fals;e": "false",
        "tru;e": "true",
        "retur;n": "return",
        "nul;l": "null",
        "revers;ed": "reversed",
        "retu;rn": "return",
        "vec;tor": "vector",
        "int;": "int",
        "retu;rn true;": "return true;",
    }
    for broken, expected in split_tokens.items():
        if broken in code:
            return {
                "error_type": "token_split_error",
                "error": f"Detected split token: '{broken}' (expected: '{expected}')",
                "friendly_error": f"Das Modell hat das Token '{expected}' fehlerhaft als '{broken}' erzeugt."
            }
    return None

def test_solution(code: str, input_args, problem_slug=None):
    tmp_path = None
    try:
        # Formatiere Eingaben ohne spezielle Behandlung
        formatted_inputs = []
        for arg in input_args:
            if isinstance(arg, list):
                formatted_inputs.append("{" + ", ".join(str(x) for x in arg) + "}")
            elif isinstance(arg, str):
                formatted_inputs.append(f'"{arg}"')  # Strings in Anführungszeichen
            else:
                formatted_inputs.append(str(arg))

        # Füge nur die Standard LeetCode Typen hinzu
        code = inject_standard_leetcode_types(code)

        # Erstelle den Test-Code
        main_code = f"""
#include <iostream>
#include <vector>
#include <string>
#include <unordered_map>
using namespace std;

// Basis-Ausgabefunktion für Vektoren
template<typename T>
ostream& operator<<(ostream& os, const vector<T>& v) {{
    os << "[";
    for (size_t i = 0; i < v.size(); ++i) {{
        if (i > 0) os << ", ";
        os << v[i];
    }}
    os << "]";
    return os;
}}

{code}

int main() {{
    Solution s;
    auto result = s.{extract_function_name(code)}({", ".join(formatted_inputs)});
    cout << "Result: " << result << endl;
    return 0;
}}
"""
        # Vorabprüfung auf zerstörte Tokens
        split_token_check = check_split_tokens(code)
        if split_token_check:
            return {
                "success": False,
                **split_token_check
            }

        with tempfile.NamedTemporaryFile("w+", suffix=".cpp", delete=False) as tmp_file:
            tmp_file.write(main_code)
            tmp_path = tmp_file.name

        compile_result = subprocess.run(
            ["g++", "-std=c++17", "-Wall", "-Werror", tmp_path, "-o", tmp_path.replace(".cpp", ".out")],
            capture_output=True, text=True, timeout=10
        )

        if compile_result.returncode != 0:
            error_msg = compile_result.stderr
            error_type = "unknown_error"
            error_details = {}
            
            # Spezifische Fehlertypen-Erkennung für häufige LLM-Fehler
            
            # 1. Erkenne Semikolon in Schlüsselwörtern (tru;e, fals;e, nul;l)
            if re.search(r"use of undeclared identifier \'fals\'", error_msg) and "e;" in error_msg:
                error_type = "semicolon_in_keyword"
                error_details["keyword"] = "false"
            elif re.search(r"use of undeclared identifier \'tru\'", error_msg) and "e;" in error_msg:
                error_type = "semicolon_in_keyword"
                error_details["keyword"] = "true"
            elif re.search(r"use of undeclared identifier \'nul\'", error_msg) and "l;" in error_msg:
                error_type = "semicolon_in_keyword"
                error_details["keyword"] = "null"
            # 2. Erkenne Semikolon in return-Anweisungen
            elif "return" in error_msg and ";" in error_msg and ("expected expression" in error_msg or "expected ';'" in error_msg):
                error_type = "semicolon_in_return"
            # 3. Erkenne "zu viele Argumente" Fehler
            elif "too many arguments to function call" in error_msg:
                error_type = "argument_count_error"
                # Extrahiere die erwartete vs. tatsächliche Anzahl der Argumente
                arg_match = re.search(r"expected (\w+) argument[s]? '([^']*)', have (\d+) argument", error_msg)
                if arg_match:
                    expected_args = arg_match.group(1)
                    param_types = arg_match.group(2)
                    actual_args = arg_match.group(3)
                    error_details["expected_args"] = expected_args
                    error_details["param_types"] = param_types
                    error_details["actual_args"] = actual_args
            # 4. Allgemeine Fehlertypen aus ERROR_TYPES
            else:
                # Standard-Fehlertyperkennung anhand der Muster
                for err_name, patterns in ERROR_TYPES.items():
                    if err_name == "unknown_error":
                        continue
                    for pattern in patterns:
                        if pattern.lower() in error_msg.lower():
                            error_type = err_name
                            break
                    if error_type != "unknown_error":
                        break
            
            # Extrahiere relevante Fehlerinformationen
            line_match = re.search(r"(\d+):(\d+):\s*error:", error_msg)
            if line_match:
                line_num = line_match.group(1)
                col_num = line_match.group(2)
                error_details["line"] = line_num
                error_details["column"] = col_num
            
            # Extrahiere den spezifischen Fehlertext
            error_lines = error_msg.splitlines()
            for i, line in enumerate(error_lines):
                if "error:" in line:
                    error_details["message"] = line.strip()
                    if i+1 < len(error_lines) and not "error:" in error_lines[i+1]:
                        error_details["context"] = error_lines[i+1].strip()
                    break
            
            # Erstelle eine menschenfreundliche Fehlerbeschreibung basierend auf dem Fehlertyp
            user_friendly_error = generate_friendly_error_message(error_type, error_details, error_msg)
            
            return {
                "success": False,
                "error": f"Compilation failed ({error_type}): {error_msg}",
                "error_type": error_type,
                "error_details": error_details,
                "friendly_error": user_friendly_error
            }

        run_result = subprocess.run([tmp_path.replace(".cpp", ".out")], capture_output=True, text=True, timeout=10)
        if run_result.returncode != 0:
            # Detailed runtime error analysis
            runtime_error = run_result.stderr
            error_type = "runtime_error"
            
            # Classify runtime errors more specifically
            if "segmentation fault" in runtime_error.lower():
                error_type = "segmentation_fault"
            elif "floating point exception" in runtime_error.lower():
                error_type = "floating_point_error"
            elif "bad_alloc" in runtime_error.lower():
                error_type = "memory_allocation_error"
            elif "stack overflow" in runtime_error.lower():
                error_type = "stack_overflow"
            
            return {
                "success": False, 
                "error": f"Runtime error: {runtime_error}", 
                "error_type": error_type,
                "exit_code": run_result.returncode
            }

        return {"success": True, "output": run_result.stdout.strip()}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Runtime error: Execution timed out", "error_type": "timeout"}

    except Exception as e:
        return {"success": False, "error": f"Exception: {str(e)}", "error_type": "unknown_error"}

    finally:
        if tmp_path:
            base = tmp_path.replace(".cpp", "")
            for ext in [".cpp", ".out"]:
                try:
                    os.remove(base + ext)
                except:
                    pass

def extract_function_name(code: str) -> str:
    match = re.search(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(.*\)\s*\{", code)
    return match.group(1) if match else "solution"

def generate_friendly_error_message(error_type, error_details, raw_error):
    """Generiert eine benutzerfreundliche Fehlermeldung basierend auf dem Fehlertyp"""
    
    if error_type == "semicolon_in_keyword":
        keyword = error_details.get("keyword", "keyword")
        return f"Semicolon in keyword: '{keyword}' enthält ein Semikolon (;), das entfernt werden muss."
    
    elif error_type == "semicolon_in_return":
        return "Fehler in return-Anweisung: Es gibt ein falsch platziertes Semikolon (;) in einer return-Anweisung."
    
    elif error_type == "argument_count_error":
        expected = error_details.get("expected_args", "eine bestimmte Anzahl")
        actual = error_details.get("actual_args", "eine andere Anzahl")
        return f"Falsche Anzahl von Argumenten: Erwartet wurden {expected} Argumente, aber {actual} wurden übergeben."
    
    elif error_type == "undeclared_identifier":
        message = error_details.get("message", "")
        match = re.search(r"use of undeclared identifier '([^']+)'", message)
        if match:
            identifier = match.group(1)
            return f"Nicht deklarierte Variable: '{identifier}' wurde nicht definiert, bevor sie verwendet wurde."
    
    elif error_type == "missing_semicolon":
        return "Fehlendes Semikolon: Eine Anweisung endet nicht mit einem Semikolon (;)."
    
    elif error_type == "unexpected_semicolon":
        return "Unerwartetes Semikolon: Ein Semikolon (;) wurde an einer falschen Stelle eingefügt."
    
    elif error_type == "syntax_error":
        return "Syntaxfehler: Der Code enthält eine grundlegende Syntaxverletzung."
    
    # Fallback für andere Fehlertypen
    return f"Fehler vom Typ {error_type}: Überprüfe den Compiler-Fehler für Details."