"""
Hauptskript für die LeetCode-Problemverarbeitung.
"""

import argparse
from src.problem_processor import process_difficulty
from src.stats_manager import save_results

def main():
    parser = argparse.ArgumentParser(description='LeetCode Problem Solver')
    
    # Schwierigkeitsgrad-Argumente
    parser.add_argument('--easy', type=int, default=0, help='Anzahl der Easy-Probleme')
    parser.add_argument('--medium', type=int, default=0, help='Anzahl der Medium-Probleme')
    parser.add_argument('--hard', type=int, default=0, help='Anzahl der Hard-Probleme')
    
    # Modell-Konfiguration
    parser.add_argument('--temperature', type=float, default=0.7, help='Temperatur für das Language Model')
    parser.add_argument('--model', type=str, default='codellama', help='Zu verwendendes Language Model')
    parser.add_argument('--show-full-prompt', action='store_true', help='Zeigt den vollständigen Prompt an')
    
    # Export-Konfiguration
    parser.add_argument('--output', type=str, help='Dateiname für die Ergebnisse (ohne Erweiterung)')
    
    args = parser.parse_args()
    
    # Verarbeite alle Schwierigkeitsgrade
    all_stats = {}
    
    if args.easy > 0:
        all_stats['easy'] = process_difficulty('easy', args.easy, args.temperature, args.model, args.show_full_prompt)
    
    if args.medium > 0:
        all_stats['medium'] = process_difficulty('medium', args.medium, args.temperature, args.model, args.show_full_prompt)
    
    if args.hard > 0:
        all_stats['hard'] = process_difficulty('hard', args.hard, args.temperature, args.model, args.show_full_prompt)
    
    # Speichere Ergebnisse
    if all_stats:
        save_results(all_stats, args.output)

if __name__ == '__main__':
    main()
