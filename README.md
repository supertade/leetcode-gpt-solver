# LeetCode GPT Solver

Ein Tool zur Evaluierung von LLMs (GPT) bei der Lösung von LeetCode-Problemen.

## Beschreibung

Dieses Projekt testet verschiedene Language Models (Claude, DeepSeek, etc.) auf ihre Fähigkeit, LeetCode-Probleme zu lösen. Es analysiert die Erfolgsrate und kategorisiert verschiedene Fehlertypen, um die Stärken und Schwächen der Modelle zu verstehen.

## Features

- Unterstützung für verschiedene LLMs (Claude, DeepSeek)
- Automatische Testausführung für LeetCode-Probleme
- Detaillierte Fehleranalyse und -kategorisierung
- Statistiken über Erfolgsraten und Fehlertypen
- Temperatur-basierte Evaluierung der Modellleistung

## Installation

```bash
# Repository klonen
git clone https://github.com/supertade/leetcode-gpt-solver.git
cd leetcode-gpt-solver

# Virtuelle Umgebung erstellen und aktivieren
python -m venv venv
source venv/bin/activate  # Für Unix/macOS
# oder
.\venv\Scripts\activate  # Für Windows

# Abhängigkeiten installieren
pip install -r requirements.txt
```

## Verwendung

```bash
# Ein einfaches Problem mit Claude testen
python main.py --easy 1 --model claude --temperature 0.4

# Mehrere Probleme testen
python main.py --easy 5 --model claude --temperature 0.4

# Vollständigen Prompt anzeigen
python main.py --easy 1 --model claude --temperature 0.4 --show-full-prompt
```

## Projektstruktur

```
leetcode-gpt-solver/
├── main.py                 # Hauptskript
├── requirements.txt        # Projektabhängigkeiten
├── src/                    # Quellcode
│   ├── __init__.py
│   ├── config.py          # Konfigurationsdatei
│   ├── prompt_generator.py # Prompt-Generierung
│   ├── test_runner.py     # Testausführung
│   ├── problem_processor.py # Problemverarbeitung
│   └── stats_manager.py   # Statistikverwaltung
└── sandbox/               # Sandbox für Code-Ausführung
    └── executor.py       # Code-Ausführung und Fehlerbehandlung
```

## Fehlertypen

Das System erkennt verschiedene Fehlertypen:

- Syntax-Fehler (missing_semicolon, unexpected_semicolon, etc.)
- Typ-Fehler (type_error, conversion_error, etc.)
- Argument-Fehler (argument_count_error, parameter_type_error)
- Laufzeit-Fehler (array_index_error, null_pointer_error, etc.)

## Ergebnisse

Die Evaluierung zeigt:
- Niedrigere Temperaturen (0.2-0.4) führen zu besseren Erfolgsraten
- Häufigste Fehler sind argument_count_error und type_error
- Die Codequalität nimmt mit steigender Temperatur ab

## Lizenz

MIT License 