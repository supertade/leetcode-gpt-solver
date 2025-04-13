"""
Modul zur Verwaltung und zum Export von Statistiken.
"""

import json
import csv
from datetime import datetime
from typing import Dict, Any
from .config import CSV_SUMMARY_HEADERS, CSV_ERROR_TYPES_HEADERS

class Statistics:
    def __init__(self):
        self.stats = {
            'total': 0,
            'success': 0,
            'compile_errors': 0,
            'runtime_errors': 0,
            'error_types': {},
            'problems': []
        }
    
    def update_from_test_results(self, test_results: Dict[str, Any], problem_info: Dict[str, Any], execution_time: float):
        """
        Aktualisiert die Statistiken basierend auf den Testergebnissen.
        """
        self.stats['total'] += 1
        
        problem_stats = {
            'slug': problem_info['titleSlug'],
            'title': problem_info['title'],
            'success': test_results['success'],
            'error_type': test_results.get('error_type'),
            'execution_time': execution_time
        }
        
        if test_results['success']:
            self.stats['success'] += 1
        elif test_results.get('error_type') == 'compilation_error':
            self.stats['compile_errors'] += 1
        else:
            self.stats['runtime_errors'] += 1
        
        # Error type tracking
        error_type = test_results.get('error_type')
        if error_type:
            if error_type not in self.stats['error_types']:
                self.stats['error_types'][error_type] = 0
            self.stats['error_types'][error_type] += 1
        
        self.stats['problems'].append(problem_stats)
    
    def update_stats(self, problem_info: Dict[str, Any], execution_time: float, result_info: Dict[str, Any]):
        """
        Aktualisiert die Statistiken ohne Testergebnisse, nur mit grundlegenden Informationen.
        
        Args:
            problem_info: Informationen zum Problem
            execution_time: Ausführungszeit
            result_info: Ergebnisinformationen (enthält 'code' und andere relevante Daten)
        """
        self.stats['total'] += 1
        
        problem_stats = {
            'slug': problem_info['titleSlug'],
            'title': problem_info['title'],
            'success': result_info.get('success'),  # None, da kein lokaler Test
            'error_type': None,
            'execution_time': execution_time,
            'code': result_info.get('code', '')
        }
        
        self.stats['problems'].append(problem_stats)
    
    def print_summary(self, difficulty: str):
        """
        Gibt eine Zusammenfassung der Statistiken aus.
        """
        print(f"\n=== STATISTICS FOR {difficulty.upper()} ===")
        print(f"Total problems: {self.stats['total']}")
        
        # Nur anzeigen, wenn lokale Tests durchgeführt wurden
        if self.stats['success'] > 0 or self.stats['compile_errors'] > 0 or self.stats['runtime_errors'] > 0:
            print(f"Successful: {self.stats['success']} ({self.stats['success']/self.stats['total']*100:.1f}%)")
            print(f"Compile errors: {self.stats['compile_errors']} ({self.stats['compile_errors']/self.stats['total']*100:.1f}%)")
            print(f"Runtime errors: {self.stats['runtime_errors']} ({self.stats['runtime_errors']/self.stats['total']*100:.1f}%)")
            
            if self.stats['error_types']:
                print("\nError types:")
                for error_type, count in self.stats['error_types'].items():
                    print(f"  - {error_type}: {count} ({count/self.stats['total']*100:.1f}%)")
        else:
            print("Kein lokaler Test durchgeführt (verwendet LeetCode-Ergebnisse).")

def save_results(all_stats: Dict[str, Any], filename: str = None):
    """
    Speichert die Ergebnisse in JSON- und CSV-Dateien.
    """
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"llm_leetcode_results_{timestamp}"
    
    # JSON-Export
    with open(f"{filename}.json", "w") as f:
        json.dump(all_stats, f, indent=2)
    
    # Übersichts-CSV
    with open(f"{filename}_summary.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_SUMMARY_HEADERS)
        
        for level, data in all_stats.items():
            if data["total"] > 0:
                success_rate = data["success"] / data["total"] * 100
            else:
                success_rate = 0
            
            writer.writerow([
                level, 
                data["total"], 
                data["success"], 
                f"{success_rate:.1f}%", 
                data["compile_errors"], 
                data["runtime_errors"]
            ])
    
    # Fehlertypen-CSV
    with open(f"{filename}_error_types.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_ERROR_TYPES_HEADERS)
        
        for level, data in all_stats.items():
            if data["error_types"]:
                for error_type, count in data["error_types"].items():
                    percentage = count / data["total"] * 100 if data["total"] > 0 else 0
                    writer.writerow([
                        level,
                        error_type,
                        count,
                        f"{percentage:.1f}%"
                    ]) 