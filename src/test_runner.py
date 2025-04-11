"""
Modul zur Ausführung und Validierung von Lösungen.
"""

from typing import Dict, List, Any
import time
from sandbox.executor import test_solution
from utils.clean import parse_testcases
from .config import SPECIAL_CASES, TEST_DELAY

def run_tests(code: str, examples: str, slug: str) -> Dict[str, Any]:
    """
    Führt Tests für eine generierte Lösung aus.
    
    Args:
        code: Der generierte Code
        examples: Die Beispiel-Testfälle
        slug: Der Slug des Problems
    
    Returns:
        Dict mit den Testergebnissen
    """
    results = {
        'success': True,
        'error_type': None,
        'error_message': None,
        'test_results': []
    }
    
    try:
        test_inputs = parse_testcases(examples, slug)
        
        # Spezialfall-Behandlung
        if slug in SPECIAL_CASES and "input_transform" in SPECIAL_CASES[slug]:
            test_inputs = [SPECIAL_CASES[slug]["input_transform"](args) for args in test_inputs]
        
        if not test_inputs:
            results.update({
                'success': False,
                'error_type': 'no_test_cases',
                'error_message': 'Keine gültigen Testfälle gefunden'
            })
            return results
        
        for input_set in test_inputs:
            test_result = test_solution(code, input_set, slug)
            results['test_results'].append(test_result)
            
            if test_result['success']:
                print(f"\n🧪 Input: {input_set} → LLM: {test_result.get('output')} → ✅")
            else:
                results['success'] = False
                error_message = test_result.get('error', "Unknown error")
                error_type = test_result.get('error_type', "unknown_error")
                
                # Trim long error messages
                if len(error_message) > 300:
                    error_message = error_message[:300] + "..."
                
                results['error_type'] = error_type
                results['error_message'] = error_message
                
                print(f"\n🧪 Input: {input_set} → ❌ Fehler: {error_message}")
            
            time.sleep(TEST_DELAY)  # Verzögerung zwischen Tests
            
    except Exception as e:
        results.update({
            'success': False,
            'error_type': 'testing_error',
            'error_message': str(e)
        })
    
    return results 