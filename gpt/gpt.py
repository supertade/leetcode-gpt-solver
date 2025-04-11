import requests
import re
import os
import json

def get_solution(prompt, temperature=0.7, max_tokens=1024, model="codellama"):
    """
    Ruft entweder die Ollama API, die DeepSeek API oder die Claude API auf, um eine Lösung für das gegebene LeetCode-Problem zu erhalten.
    
    Args:
        prompt (str): Der Eingabetext, der das Problem beschreibt.
        temperature (float): Die Kreativität des Modells (0.0 bis 1.0)
        max_tokens (int): Maximale Anzahl von Tokens für die Antwort
        model (str): Das zu verwendende Modell (z.B. codellama, llama3, mistral, deepseek, claude)
    
    Returns:
        str: Die generierte Lösung
    """
    # Füge eine Beispiellösung als Prompt-Engineering hinzu
    example_solution = """
Example of a well-formatted C++ solution:

```cpp
#include <vector>
#include <string>
#include <unordered_map>
using namespace std;

class Solution {
public:
    int twoSum(vector<int>& nums, int target) {
        unordered_map<int, int> map;
        for (int i = 0; i < nums.size(); i++) {
            if (map.find(target - nums[i]) != map.end()) {
                return {map[target - nums[i]], i};
            }
            map[nums[i]] = i;
        }
        return {};
    }
};
```
"""
    
    system_context = """You are an expert C++ developer solving LeetCode problems. 
Always provide complete, compilable solutions with proper C++ syntax. 
Important rules to follow:
1. Never use semicolons in type definitions (e.g., vector<int;> is WRONG, use vector<int>)
2. Always add #include directives for all libraries you use (vector, string, unordered_map, etc.)
3. Always use proper C++ syntax for all standard library classes
4. Never create custom hash functions without implementing them fully
5. Be careful with semicolons at the end of function return statements
6. NEVER insert semicolons within keywords or values like "true", "false", "nullptr", etc.
7. Boolean values in C++ are 'true' and 'false', not 'True' or 'False'
8. Return statements must look like "return value;" NOT "return value;;"
9. Always end class and function definitions with closing braces (})
10. ALWAYS add semicolons after return statements (e.g., return {1, 2}; - NOT return {1, 2})
11. ALWAYS add semicolons after closing braces of function or class definitions if appropriate
12. NEVER use strange operators like ;+ ;1;
13. Make sure return expressions don't have misplaced semicolons (like "return a + b;+1;" should be "return a + b + 1;")
14. NEVER place semicolons inside variable names (like "d;p;" - this should be just "dp")
15. NEVER place semicolons inside array subscripts (like "arr[i;]" - this should be just "arr[i]")
"""
    
    enhanced_prompt = system_context + "\n\n" + example_solution + "\n\n" + prompt + "\n\nMake sure your C++ code compiles without any syntax errors."
    
    try:
        # Prüfe welches Modell verwendet werden soll
        if "claude" in model:
            return get_solution_from_claude(enhanced_prompt, temperature, max_tokens, model)
        elif "deepseek" in model:
            return get_solution_from_deepseek(enhanced_prompt, temperature, max_tokens)
        else:
            return get_solution_from_ollama(enhanced_prompt, temperature, model)
    except Exception as e:
        raise Exception(f"Error calling API: {str(e)}")

def get_solution_from_ollama(prompt, temperature, model):
    """Verwendet die Ollama API, um eine Lösung zu generieren"""
    try:
        # Verwende die Ollama API
        res = requests.post("http://localhost:11434/api/generate", json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        })
        
        # Überprüfe, ob die Anfrage erfolgreich war
        if res.status_code == 200:
            response = res.json()["response"]
            
            # Post-Prozessierung für häufige Fehler
            # Entfernt für faire Evaluation des LLM-Outputs, wie in den Anforderungen spezifiziert
            # Wir wollen alle Fehler behalten, damit die Evaluation fair ist
            
            return response
        else:
            raise Exception(f"Ollama API request failed with status code {res.status_code}: {res.text}")
    except Exception as e:
        raise Exception(f"Error calling Ollama API: {str(e)}")

def get_solution_from_deepseek(prompt, temperature, max_tokens=1024):
    """Verwendet die DeepSeek API, um eine Lösung zu generieren"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise Exception("DEEPSEEK_API_KEY environment variable is not set")
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    # DeepSeek API-Endpunkt
    url = "https://api.deepseek.com/v1/chat/completions"
    
    # Nachrichtenformat für die DeepSeek API
    data = {
        "model": "deepseek-coder",  # oder ein anderes verfügbares Modell
        "messages": [
            {"role": "system", "content": "You are an expert C++ developer solving LeetCode problems."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"DeepSeek API request failed with status code {response.status_code}: {response.text}")
    except Exception as e:
        raise Exception(f"Error calling DeepSeek API: {str(e)}")

def get_solution_from_claude(prompt, temperature, max_tokens=1024, model_name="claude-3-opus-20240229"):
    """Verwendet die Claude API von Anthropic, um eine Lösung zu generieren"""
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        raise Exception("CLAUDE_API_KEY environment variable is not set")
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    
    # Aktuelle Claude-Modellnamen (Stand April 2024)
    CLAUDE_MODEL_MAPPING = {
        "claude": "claude-3-opus-20240229",  # Default
        "claude:opus": "claude-3-opus-20240229", 
        "claude:sonnet": "claude-3-7-sonnet-20250219",
        "claude:haiku": "claude-3-haiku-20240307",
        "claude-3-opus": "claude-3-opus-20240229",
        "claude-3-sonnet": "claude-3-7-sonnet-20250219",
        "claude-3-haiku": "claude-3-haiku-20240307"
    }
    
    # Überprüfe, ob ein spezifisches Claude-Modell angefordert wurde
    if model_name in CLAUDE_MODEL_MAPPING:
        claude_model = CLAUDE_MODEL_MAPPING[model_name]
    else:
        # Falls ein unbekannter Modellname, verwende den Standard
        claude_model = "claude-3-opus-20240229"
    
    log_message = f"Verwende Claude-Modell: {claude_model}"
    print(log_message)
    
    # Claude API-Endpunkt
    url = "https://api.anthropic.com/v1/messages"
    
    # Nachrichtenformat für die Claude API
    data = {
        "model": claude_model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            return result['content'][0]['text']
        else:
            error_detail = "Unknown error"
            try:
                error_json = response.json()
                error_detail = json.dumps(error_json)
            except:
                error_detail = response.text
            
            raise Exception(f"Claude API request failed with status code {response.status_code}: {error_detail}")
    except Exception as e:
        raise Exception(f"Error calling Claude API: {str(e)}")
