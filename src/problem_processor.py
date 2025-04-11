"""
Hauptmodul für die Verarbeitung von LeetCode-Problemen.
"""

import time
import random
from typing import Dict, List, Any
from api.leetcode import fetch_problems, fetch_full_problem
from gpt.gpt import get_solution
from utils.clean import extract_code_block
from .config import DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_PROBLEM_LIMIT, API_RETRY_DELAY
from .prompt_generator import generate_problem_prompt
from .test_runner import run_tests
from .stats_manager import Statistics

# Set zur Verfolgung bereits verarbeiteter Probleme
processed_problems = set()

def process_difficulty(
    level: str,
    num_problems: int = 5,
    temperature: float = DEFAULT_TEMPERATURE,
    model: str = DEFAULT_MODEL,
    show_full_prompt: bool = False
) -> Dict[str, Any]:
    """
    Verarbeitet Probleme einer bestimmten Schwierigkeitsstufe.
    
    Args:
        level: Schwierigkeitsgrad (easy, medium, hard)
        num_problems: Anzahl der zu verarbeitenden Probleme
        temperature: Temperatur für das Language Model
        model: Zu verwendendes Language Model
        show_full_prompt: Ob der vollständige Prompt angezeigt werden soll
    
    Returns:
        Dict mit den Statistiken
    """
    print(f"\n==== {level.upper()} ====")
    stats = Statistics()
    
    # Probleme abrufen
    all_problems = fetch_problems(level, limit=DEFAULT_PROBLEM_LIMIT)
    if not all_problems:
        print(f"No problems found for difficulty level: {level}")
        return stats.stats
    
    # Verfügbare Probleme filtern
    available_problems = [p for p in all_problems if p['titleSlug'] not in processed_problems]
    if not available_problems:
        print(f"No more available problems for difficulty level: {level}")
        return stats.stats
    
    # Zufällige Probleme auswählen
    selected_problems = random.sample(available_problems, min(num_problems, len(available_problems)))
    
    for problem in selected_problems:
        try:
            title = problem['title']
            slug = problem['titleSlug']
            processed_problems.add(slug)
            
            print(f"\n🔍 {title} ({slug})")
            start_time = time.time()
            
            # Problem-Details abrufen
            try:
                details = fetch_full_problem(slug)
            except Exception as e:
                print(f"Error fetching problem details: {e}")
                test_results = {'success': False, 'error_type': 'api_error', 'error_message': str(e)}
                stats.update_from_test_results(test_results, problem, 0)
                continue
            
            # Prompt generieren und Lösung erhalten
            try:
                prompt = generate_problem_prompt(details, show_full_prompt)
                llm_response = get_solution(prompt, temperature=temperature, model=model)
                code = extract_code_block(llm_response)
                
                print(f"\n💬 {model.upper()}-Code:")
                print(f"""```
{code}
```""")
            except Exception as e:
                print(f"Error getting LLM solution: {e}")
                test_results = {'success': False, 'error_type': 'llm_error', 'error_message': str(e)}
                stats.update_from_test_results(test_results, problem, 0)
                continue
            
            # Tests ausführen
            test_results = run_tests(code, details.get('exampleTestcases', ''), slug)
            execution_time = time.time() - start_time
            stats.update_from_test_results(test_results, problem, execution_time)
            
            time.sleep(API_RETRY_DELAY)  # Verzögerung zwischen Problemen
            
        except Exception as e:
            print(f"Error processing problem: {e}")
            continue
    
    stats.print_summary(level)
    return stats.stats 