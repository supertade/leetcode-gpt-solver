"""
Modul zur Generierung von Prompts für das Language Model.
"""

from typing import Dict, Any
from .config import PROMPT_TEMPLATE
from utils.clean import clean_html

def generate_problem_prompt(problem_details: Dict[str, Any], show_full_prompt: bool = False) -> str:
    """
    Generiert einen Prompt für das Language Model basierend auf den Problem-Details.
    
    Args:
        problem_details: Dictionary mit den Problem-Details (title, content, exampleTestcases)
        show_full_prompt: Ob der vollständige Prompt angezeigt werden soll
    
    Returns:
        str: Der generierte Prompt
    """
    title = problem_details.get('title', '')
    question = clean_html(problem_details.get('content', ''))
    examples = problem_details.get('exampleTestcases', '')
    
    prompt = PROMPT_TEMPLATE.format(
        title=title,
        question=question,
        examples=examples
    )
    
    if show_full_prompt:
        print("\n📤 Vollständiger Prompt an LLM:")
        print(prompt)
    else:
        print("\n📤 Prompt an LLM (gekürzte Anzeige):")
        print(prompt[:400], "... [weitere " + str(len(prompt) - 400) + " Zeichen]")
    
    return prompt 