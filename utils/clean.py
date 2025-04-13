from bs4 import BeautifulSoup
import re

def clean_html(raw_html: str) -> str:
    if raw_html is None:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    return soup.get_text()

def extract_code_block(text: str) -> str:
    # Extrahiere nur den Code aus Markdown-Code-Blöcken
    match = re.search(r"```(?:\w+)?\s*(.*?)```", text, re.DOTALL)
    code = match.group(1).strip() if match else text.strip()
    
    # Entferne nur etwaige Sprachmarkierungen am Anfang
    code = re.sub(r"^(?:c\+\+|\+\+|cpp)\s*", "", code)
    
    # Keine weiteren automatischen Korrekturen, um die Fairness der Evaluation zu gewährleisten
    
    return code

# Die folgenden Funktionen sind für die manuelle Korrektur verfügbar,
# werden aber nicht automatisch in extract_code_block aufgerufen,
# um eine faire Evaluation der Sprachmodelle zu gewährleisten.

def fix_class_declaration(code: str) -> str:
    # Fix pattern like //cpp:classSolution
    declaration_match = re.search(r'\/\/\s*cpp\s*:\s*class\s*(\w+)\s*{', code)
    if declaration_match:
        class_name = declaration_match.group(1)
        code = re.sub(r'\/\/\s*cpp\s*:\s*class\s*\w+\s*{', f'class {class_name} {{', code)
    
    # Ensure class has proper declaration
    if not re.search(r'class\s+Solution', code) and "}" in code:
        if re.search(r'\w+\s*\*?\s*\w+\s*\(', code):  # Check if there's a function declaration
            code = "class Solution {\npublic:\n" + code + "\n};"
    
    # Fix extraneous closing braces
    braces_count = code.count('{') - code.count('}')
    if braces_count > 0:
        code += "}" * braces_count
    elif braces_count < 0:
        # Remove extra closing braces
        code = re.sub(r'};*\s*$', ';', code)
    
    return code

def fix_cpp_issues(code: str) -> str:
    # Remove semicolons after code blocks - they cause syntax errors
    code = re.sub(r'}\s*;(\s*else)', r'} \1', code)
    
    # Fix vector<bool> |= operator issue
    if "vector<vector<bool>>" in code and "|=" in code:
        code = code.replace("dp[i][j] |= dp[i - 1][j]", "dp[i][j] = dp[i][j] || dp[i - 1][j]")
    
    # Replace any other problematic vector<bool> usage
    if "vector<bool>" in code and "|=" in code:
        code = re.sub(r'(\w+\[\w+\])\s*\|=\s*(\w+(?:\[\w+\])+)', r'\1 = \1 || \2', code)
    
    # Füge Semikolons bei fehlenden return-Statements hinzu
    code = re.sub(r'return\s+\{([^}]+)\}(?!\s*;)', r'return {\1};', code)
    
    # Füge fehlendes Semikolon nach struct/class-Definitionen hinzu
    code = re.sub(r'(\}\s*)\n(\s*\};)', r'\1;\n\2', code)
    
    # Fix missing semicolons after return statements
    code = re.sub(r'(return\s+[^;{]+)(?!\s*;|\s*{)', r'\1;', code)
    
    # Fix double semicolons
    if ";;" in code:
        code = code.replace(";;", ";")

    # Fix missing include for min/max functions
    if re.search(r'\bmin\b|\bmax\b', code) and not re.search(r'#include\s+<algorithm>', code):
        code = "#include <algorithm>\n" + code
    
    # Make sure common headers are included
    if "string" in code and not re.search(r'#include\s+<string>', code):
        code = "#include <string>\n" + code
    
    if "vector" in code and not re.search(r'#include\s+<vector>', code):
        code = "#include <vector>\n" + code
        
    if "unordered_map" in code and not re.search(r'#include\s+<unordered_map>', code):
        code = "#include <unordered_map>\n" + code
        
    if "unordered_set" in code and not re.search(r'#include\s+<unordered_set>', code):
        code = "#include <unordered_set>\n" + code
    
    # Add using namespace std if we're using std types without qualification
    if re.search(r'\b(string|vector|map|unordered_map|cout|cin)\b', code) and not "using namespace std" in code:
        code = "using namespace std;\n\n" + code
    
    # Fix common syntax errors
    code = code.replace("};", "}")
    code = re.sub(r'}\s*;', "}", code)
    code = code.replace("};", "}")
    
    # Add back a single semicolon at the end of the class declaration
    code = re.sub(r'}$', "};", code)
    
    return code

def parse_testcases(example_string: str, problem_slug=None):
    """
    Diese Funktion ist nicht mehr aktiv, da lokale Tests entfernt wurden.
    Die Funktion bleibt als Platzhalter, gibt aber immer eine leere Liste zurück.
    
    Verwende stattdessen die LeetCode-Submission für Tests.
    """
    # Warnung im Terminal ausgeben (sofern verfügbar)
    try:
        from app import log_to_terminal
        log_to_terminal("Warnung: parse_testcases() wurde aufgerufen, obwohl lokale Tests deaktiviert sind.", "warning")
    except:
        pass
    
    return []
