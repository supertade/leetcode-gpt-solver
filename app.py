import streamlit as st
import pandas as pd
import json
import os
import time
import random
from datetime import datetime
import re

# Import der vorhandenen Funktionen aus main.py
from main import process_difficulty, save_results
from api.leetcode import fetch_problems, fetch_full_problem
from gpt.gpt import get_solution
from sandbox.executor import test_solution
from utils.clean import clean_html, extract_code_block, parse_testcases
# Import der neuen Heatmap-Visualisierung
from heatmap_viz import add_heatmap_tab

st.set_page_config(page_title="LeetCode LLM Evaluator", layout="wide")
st.title("LeetCode LLM Evaluator")

# Tracking von verarbeiteten Problemen (wie in main.py)
processed_problems = set()

# Sitzungsstatus initialisieren
if 'results' not in st.session_state:
    st.session_state.results = {"easy": [], "medium": [], "hard": []}
if 'current_problem' not in st.session_state:
    st.session_state.current_problem = None
if 'current_solution' not in st.session_state:
    st.session_state.current_solution = None
if 'current_results' not in st.session_state:
    st.session_state.current_results = None
if 'terminal_output' not in st.session_state:
    st.session_state.terminal_output = []
if 'search_results' not in st.session_state:
    st.session_state.search_results = None
if 'last_search_query' not in st.session_state:
    st.session_state.last_search_query = ""
if 'last_search_difficulty' not in st.session_state:
    st.session_state.last_search_difficulty = "Alle"
if 'prompt_template' not in st.session_state:
    st.session_state.prompt_template = """### LeetCode Problem: {title}

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
- Compile without errors using `g++ -std=c++17`
- Use correct return statements (e.g., `return true;`, not `return true;;` or `return;`)
- CRITICAL: Never insert semicolons inside variable names, constants or keywords
  * WRONG: 'fals;e', 'tru;e', 'nul;l', 'i;f', 'e;lse', 'wh;ile'
  * CORRECT: 'false', 'true', 'null', 'if', 'else', 'while'
- Double-check all boolean literals: they are 'true'/'false' (not 'True'/'False')
- End all declarations and statements with proper semicolons
- Avoid using undefined or undeclared variables
- Avoid trailing or extraneous braces
- Return real, working C++ code — not pseudocode, placeholders, or incomplete functions

✅ Output only the C++ code. No explanation, no markdown, no comments. Just clean, valid, and complete code.
"""
if 'default_prompt_template' not in st.session_state:
    st.session_state.default_prompt_template = st.session_state.prompt_template

# Hilfsfunktion zum Logging von Aktionen im Terminal
def log_to_terminal(message, level="info"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Maximum von 100 Zeilen im Terminal speichern
    if len(st.session_state.terminal_output) >= 100:
        st.session_state.terminal_output.pop(0)
    
    # Füge formatierte Nachricht hinzu
    if level == "info":
        prefix = "📋"
    elif level == "success":
        prefix = "✅"
    elif level == "error":
        prefix = "❌"
    elif level == "warning":
        prefix = "⚠️"
    else:
        prefix = "🔄"
    
    st.session_state.terminal_output.append(f"{prefix} [{timestamp}] {message}")

def clean_template(template_text):
    """Hilfsfunktion zum Bereinigen von ungültigen Platzhaltern im Template"""
    valid_placeholders = ['title', 'question', 'examples']
    cleaned_template = template_text
    
    # Entferne Platzhalter mit ' (einzelnen Anführungszeichen)
    cleaned_template = re.sub(r'\{\s*\'[^\']*\'\s*\}', '', cleaned_template)
    
    # Entferne andere ungültige Platzhalter
    for potential_placeholder in re.findall(r'\{([^}]+)\}', cleaned_template):
        if potential_placeholder.strip() not in valid_placeholders:
            cleaned_template = cleaned_template.replace(f"{{{potential_placeholder}}}", "")
    
    return cleaned_template

# Erweiterte Fehlerprotokollierung hinzufügen
def log_detailed_error(error_info, test_input, code_snippet=None):
    """Detaillierte Fehlerprotokolle mit zusätzlichem Kontext erstellen"""
    error_message = error_info.get('error', 'Unbekannter Fehler')
    error_type = error_info.get('error_type', 'unknown_error')
    
    # Grundlegende Fehlerinformationen
    log_to_terminal(f"Fehlertyp: {error_type}", "error")
    
    # Detaillierte Fehlerinformationen, je nach Fehlertyp
    if 'split token' in error_message.lower():
        # Suche nach dem spezifischen Token, das gesplittet wurde
        import re
        split_token_match = re.search(r"Detected split token: '([^']+)'", error_message)
        expected_token_match = re.search(r"expected: '([^']+)'", error_message)
        
        if split_token_match:
            split_token = split_token_match.group(1)
            expected = expected_token_match.group(1) if expected_token_match else "unbekannt"
            log_to_terminal(f"Aufgespaltenes Token gefunden: '{split_token}' (erwartet: '{expected}')", "error")
            log_to_terminal(f"Häufige Ursache: Versehentliches Einfügen von Semikolons in Schlüsselwörtern oder Konstanten", "warning")
    
    elif 'undefined reference' in error_message.lower():
        # Bei undefined reference Fehlern versuchen, die fehlende Funktion zu identifizieren
        import re
        undef_match = re.search(r"undefined reference to [`']([^'`]+)'", error_message)
        if undef_match:
            missing_func = undef_match.group(1)
            log_to_terminal(f"Nicht definierte Referenz: '{missing_func}'", "error")
            log_to_terminal(f"Der Code verweist auf eine Funktion/Symbol, das nicht implementiert wurde", "warning")
    
    elif 'compilation failed' in error_message.lower():
        # Extrahiere relevante Zeilen aus der Kompilierungsfehlermeldung
        import re
        error_lines = [line for line in error_message.split('\n') if 'error:' in line]
        for i, line in enumerate(error_lines[:3]):  # Zeige die ersten 3 Fehler
            log_to_terminal(f"Kompilierungsfehler {i+1}: {line.strip()}", "error")
        
        if len(error_lines) > 3:
            log_to_terminal(f"... und {len(error_lines) - 3} weitere Kompilierungsfehler", "warning")
    
    # Testfall-Informationen
    log_to_terminal(f"Fehlgeschlagen mit Testfall: {test_input}", "warning")
    
    # Wenn Code-Snippet vorhanden, zeigen wir es an
    if code_snippet:
        log_to_terminal(f"Relevanter Code-Ausschnitt: {code_snippet[:150]}...", "info")
        
    # Mögliche Maßnahmen
    log_to_terminal("Empfehlung: Prompt anpassen, um diesen Fehlertyp explizit zu adressieren", "info")

# Seitenleiste für Modellauswahl und Konfiguration
with st.sidebar:
    st.header("Konfiguration")
    
    # Button zum Zurücksetzen der App
    if st.button("🔄 App zurücksetzen", use_container_width=True):
        # Zurücksetzen des Prompt-Templates auf Standard
        st.session_state.prompt_template = st.session_state.default_prompt_template
        # Fehlermeldungen im Terminal löschen
        st.session_state.terminal_output = []
        # Benachrichtigung
        st.success("App wurde zurückgesetzt!")
        st.rerun()
    
    model = st.selectbox(
        "LLM-Modell",
        ["codellama", "llama3", "mistral", "deepseek", "claude"],
        index=0
    )
    
    model_version = st.text_input("Modellversion (optional)", "")
    if model == "claude" and not model_version:
        st.info("Für Claude empfohlene Versionen: opus, sonnet oder haiku")
    
    temperature = st.slider("Temperature", 0.0, 1.0, 0.7, 0.1)
    
    st.header("API-Schlüssel")
    
    # API-Schlüssel basierend auf Modell anzeigen
    if model == "deepseek":
        api_key = st.text_input("DeepSeek API-Schlüssel", type="password")
        if api_key:
            os.environ["DEEPSEEK_API_KEY"] = api_key
    elif model == "claude":
        api_key = st.text_input("Claude API-Schlüssel", type="password")
        if api_key:
            os.environ["CLAUDE_API_KEY"] = api_key
    
    # Modellname mit Version kombinieren
    if model_version:
        full_model_name = f"{model}:{model_version}"
    else:
        full_model_name = model

# Tabs für verschiedene Funktionen
tab1, tab2, tab3, tab4 = st.tabs(["Problem auswählen", "Prompt anpassen", "Ergebnisse", "Statistiken"])

# Tab 1: Problem auswählen
with tab1:
    st.header("Problem auswählen")
    
    # Terminal-Ausgabe (collapsed by default)
    with st.expander("Terminal-Ausgabe", expanded=False):
        # Erstelle einen Container für die Terminal-Ausgabe
        terminal_container = st.container()
        with terminal_container:
            # Darstellung als Code-Block mit Monospace-Font
            if st.session_state.terminal_output:
                terminal_text = "\n".join(st.session_state.terminal_output)
                st.text_area("System-Log", terminal_text, height=200, key="terminal_display", disabled=True)
            else:
                st.text("Noch keine Ausgabe verfügbar.")
        
        # Button zum Löschen des Terminals
        if st.button("Terminal leeren", key="clear_terminal"):
            st.session_state.terminal_output = []
            st.rerun()
    
    # Haupt-Steuerelemente für Problem-Auswahl
    st.subheader("Zufälliges Problem laden")
    
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        difficulty = st.selectbox("Schwierigkeitsgrad", ["easy", "medium", "hard"], key="random_difficulty")
    with col2:
        num_problems = st.number_input("Anzahl der Probleme", min_value=1, max_value=20, value=1, key="num_problems")
    with col3:
        st.write("")
        st.write("")
        load_button = st.button("Laden", use_container_width=True)
    
    # Informationstext zur Funktionsweise basierend auf Anzahl
    if num_problems > 1:
        st.caption(f"Der Button lädt {num_problems} Probleme und testet diese automatisch.")
    else:
        st.caption("Der Button lädt ein einzelnes Problem zum Testen.")
    
    # Trennlinie zwischen den Hauptbereichen
    st.markdown("---")
    
    # Neue Suchfunktion für Probleme - klarer strukturiert
    st.subheader("Nach Problem suchen")
    
    search_row1 = st.container()
    with search_row1:
        search_col1, search_col2 = st.columns([3, 1])
        with search_col1:
            search_query = st.text_input("Suche nach Problem (Titel oder Schlüsselwort)", 
                                        placeholder="z.B. Two Sum, Binary Tree, etc.",
                                        value=st.session_state.get('last_search_query', ''))
        with search_col2:
            search_difficulty = st.selectbox("Schwierigkeit", 
                                           ["Alle", "easy", "medium", "hard"], 
                                           key="search_difficulty_select",
                                           index=["Alle", "easy", "medium", "hard"].index(st.session_state.get('last_search_difficulty', 'Alle')))
    
    search_row2 = st.container()
    with search_row2:
        search_button = st.button("Suchen", use_container_width=False, key="search_button")
    
    # Trennlinie nach der Suche, wenn keine Ergebnisse angezeigt werden
    if not (search_button and search_query):
        st.markdown("---")
    
    # Suche ausführen
    if search_button and search_query:
        log_to_terminal(f"Suche nach Problemen mit Schlüsselwort: '{search_query}'...")
        with st.spinner("Suche nach passenden Problemen..."):
            # Speichere Suchparameter in der Session mit anderen Keys
            st.session_state.last_search_query = search_query
            st.session_state.last_search_difficulty = search_difficulty
            
            # Suche in ausgewähltem oder allen Schwierigkeitsgraden
            all_matching_problems = []
            
            if search_difficulty == "Alle":
                difficulties = ["easy", "medium", "hard"]
            else:
                difficulties = [search_difficulty]
            
            for diff in difficulties:
                # Verwende die erweiterte fetch_problems-Funktion
                matching_problems = fetch_problems(diff, limit=100, search_term=search_query)
                
                for p in matching_problems:
                    p['difficulty'] = diff
                
                all_matching_problems.extend(matching_problems)
            
            # Speichere Suchergebnisse in der Session
            st.session_state.search_results = all_matching_problems
            
            if all_matching_problems:
                log_to_terminal(f"{len(all_matching_problems)} passende Probleme gefunden.", "success")
                
                # Zeige die Suchergebnisse in einer Tabelle an
                st.subheader("Suchergebnisse")
                
                # Erstelle eine Tabelle mit Problemen
                problem_data = []
                for idx, problem in enumerate(all_matching_problems):
                    problem_data.append({
                        "Index": idx + 1,
                        "Title": problem['title'],
                        "Difficulty": problem['difficulty'].capitalize(),
                        "Slug": problem['titleSlug']
                    })
                
                result_df = pd.DataFrame(problem_data)
                
                # Hinzufügen einer Filterfunktion für die Tabelle
                st.dataframe(result_df, use_container_width=True, height=300)
                
                # Auswahl eines Problems zum Testen in einer eigenen Karte
                st.markdown("---")
                st.subheader("Problem auswählen und laden")
                
                result_col1, result_col2 = st.columns([3, 1])
                with result_col1:
                    selected_idx = st.number_input("Wähle ein Problem (Index)", 
                                           min_value=1, 
                                           max_value=len(all_matching_problems),
                                           value=1)
                    selected_title = all_matching_problems[selected_idx - 1]['title']
                    st.info(f"Ausgewählt: **{selected_title}**")
                
                with result_col2:
                    st.write("")
                    st.write("")
                    if st.button("Problem laden", use_container_width=True, key="load_selected"):
                        try:
                            selected_problem = all_matching_problems[selected_idx - 1]
                            current_difficulty = selected_problem['difficulty']
                            
                            log_to_terminal(f"[DEBUG] Starte Laden des ausgewählten Problems: {selected_problem['title']}")
                            with st.spinner(f"Lade Details für {selected_problem['title']}..."):
                                log_to_terminal(f"[DEBUG] Rufe fetch_full_problem für Slug: {selected_problem['titleSlug']} auf")
                                details = fetch_full_problem(selected_problem['titleSlug'])
                                
                                if not details:
                                    log_to_terminal(f"[DEBUG] Fehler: Keine Details zurückgegeben für {selected_problem['titleSlug']}", "error")
                                    st.error(f"Keine Details gefunden für {selected_problem['title']}")
                                else:
                                    log_to_terminal(f"[DEBUG] Details erhalten, Länge: {len(str(details))}")
                                    question = clean_html(details.get("content", ""))
                                    examples = details.get("exampleTestcases", "")
                                    
                                    log_to_terminal(f"[DEBUG] Question-Länge: {len(question)}, Examples-Länge: {len(examples)}")
                                    
                                    # Problem-Infos speichern
                                    st.session_state.current_problem = {
                                        "title": selected_problem['title'],
                                        "slug": selected_problem['titleSlug'],
                                        "difficulty": current_difficulty,
                                        "question": question,
                                        "examples": examples
                                    }
                                    
                                    # Lösung und Ergebnisse zurücksetzen
                                    st.session_state.current_solution = None
                                    st.session_state.current_results = None
                                    
                                    log_to_terminal(f"[DEBUG] Problem '{selected_problem['title']}' erfolgreich in session_state gespeichert")
                                    log_to_terminal(f"Problem '{selected_problem['title']}' erfolgreich geladen.", "success")
                                    st.success(f"Problem geladen: {selected_problem['title']}")
                                    
                                    # Seite neu laden, aber Suchergebnisse beibehalten
                                    st.rerun()
                        except Exception as e:
                            log_to_terminal(f"[DEBUG] Ausnahme beim Laden des Problems: {str(e)}", "error")
                            st.error(f"Fehler beim Laden des Problems: {str(e)}")
                
                # Trennlinie nach den Suchergebnissen
                st.markdown("---")
            else:
                log_to_terminal(f"Keine passenden Probleme für '{search_query}' gefunden.", "warning")
                st.warning(f"Keine passenden Probleme für '{search_query}' gefunden. Versuche einen anderen Suchbegriff.")
                st.markdown("---")  # Trennlinie auch nach Fehlermeldung
    
    # Zeige gespeicherte Suchergebnisse an, wenn vorhanden
    elif st.session_state.search_results is not None:
        all_matching_problems = st.session_state.search_results
        if all_matching_problems:
            log_to_terminal(f"Zeige {len(all_matching_problems)} gespeicherte Suchergebnisse an.")
            
            # Zeige die Suchergebnisse in einer Tabelle an
            st.subheader("Suchergebnisse")
            
            # Erstelle eine Tabelle mit Problemen
            problem_data = []
            for idx, problem in enumerate(all_matching_problems):
                problem_data.append({
                    "Index": idx + 1,
                    "Title": problem['title'],
                    "Difficulty": problem['difficulty'].capitalize(),
                    "Slug": problem['titleSlug']
                })
            
            result_df = pd.DataFrame(problem_data)
            
            # Hinzufügen einer Filterfunktion für die Tabelle
            st.dataframe(result_df, use_container_width=True, height=300)
            
            # Auswahl eines Problems zum Testen in einer eigenen Karte
            st.markdown("---")
            st.subheader("Problem auswählen und laden")
            
            result_col1, result_col2 = st.columns([3, 1])
            with result_col1:
                selected_idx = st.number_input("Wähle ein Problem (Index)", 
                                       min_value=1, 
                                       max_value=len(all_matching_problems),
                                       value=1)
                selected_title = all_matching_problems[selected_idx - 1]['title']
                st.info(f"Ausgewählt: **{selected_title}**")
            
            with result_col2:
                st.write("")
                st.write("")
                if st.button("Problem laden", use_container_width=True, key="load_selected"):
                    try:
                        selected_problem = all_matching_problems[selected_idx - 1]
                        current_difficulty = selected_problem['difficulty']
                        
                        log_to_terminal(f"[DEBUG] Starte Laden des ausgewählten Problems: {selected_problem['title']}")
                        with st.spinner(f"Lade Details für {selected_problem['title']}..."):
                            log_to_terminal(f"[DEBUG] Rufe fetch_full_problem für Slug: {selected_problem['titleSlug']} auf")
                            details = fetch_full_problem(selected_problem['titleSlug'])
                            
                            if not details:
                                log_to_terminal(f"[DEBUG] Fehler: Keine Details zurückgegeben für {selected_problem['titleSlug']}", "error")
                                st.error(f"Keine Details gefunden für {selected_problem['title']}")
                            else:
                                log_to_terminal(f"[DEBUG] Details erhalten, Länge: {len(str(details))}")
                                question = clean_html(details.get("content", ""))
                                examples = details.get("exampleTestcases", "")
                                
                                log_to_terminal(f"[DEBUG] Question-Länge: {len(question)}, Examples-Länge: {len(examples)}")
                                
                                # Problem-Infos speichern
                                st.session_state.current_problem = {
                                    "title": selected_problem['title'],
                                    "slug": selected_problem['titleSlug'],
                                    "difficulty": current_difficulty,
                                    "question": question,
                                    "examples": examples
                                }
                                
                                # Lösung und Ergebnisse zurücksetzen
                                st.session_state.current_solution = None
                                st.session_state.current_results = None
                                
                                log_to_terminal(f"[DEBUG] Problem '{selected_problem['title']}' erfolgreich in session_state gespeichert")
                                log_to_terminal(f"Problem '{selected_problem['title']}' erfolgreich geladen.", "success")
                                st.success(f"Problem geladen: {selected_problem['title']}")
                                
                                # Seite neu laden, aber Suchergebnisse beibehalten
                                st.rerun()
                    except Exception as e:
                        log_to_terminal(f"[DEBUG] Ausnahme beim Laden des Problems: {str(e)}", "error")
                        st.error(f"Fehler beim Laden des Problems: {str(e)}")
            
            # Trennlinie nach den Suchergebnissen
            st.markdown("---")

    if load_button:
        if num_problems == 1:
            # Einzelnes Problem laden
            log_to_terminal(f"Lade zufälliges Problem vom Schwierigkeitsgrad '{difficulty}'...")
            with st.spinner("Lade Problem..."):
                try:
                    log_to_terminal(f"[DEBUG] Rufe fetch_problems für Schwierigkeit '{difficulty}' auf")
                    problems = fetch_problems(difficulty, limit=50)
                    
                    if not problems:
                        log_to_terminal("[DEBUG] Keine Probleme gefunden", "warning")
                        log_to_terminal("Keine Probleme für diesen Schwierigkeitsgrad gefunden.", "warning")
                        st.error("Keine Probleme für diesen Schwierigkeitsgrad gefunden.")
                    else:
                        log_to_terminal(f"[DEBUG] {len(problems)} Probleme gefunden.")
                        log_to_terminal(f"{len(problems)} Probleme gefunden.")
                        # Filter verarbeitete Probleme
                        available_problems = [p for p in problems if p['titleSlug'] not in processed_problems]
                        
                        if not available_problems:
                            log_to_terminal(f"[DEBUG] Alle Probleme wurden bereits verarbeitet.", "warning")
                            log_to_terminal(f"Keine unbearbeiteten Probleme für Schwierigkeitsgrad '{difficulty}' verfügbar.", "warning")
                            st.error("Keine verfügbaren Probleme für diesen Schwierigkeitsgrad")
                        else:
                            log_to_terminal(f"[DEBUG] {len(available_problems)} unbearbeitete Probleme verfügbar.")
                            log_to_terminal(f"{len(available_problems)} unbearbeitete Probleme verfügbar.")
                            selected_problem = random.choice(available_problems)
                            
                            log_to_terminal(f"[DEBUG] Problem ausgewählt: {selected_problem['title']} (Slug: {selected_problem['titleSlug']})")
                            log_to_terminal(f"Problem ausgewählt: {selected_problem['title']}")
                            
                            with st.spinner(f"Lade Details für {selected_problem['title']}..."):
                                log_to_terminal(f"[DEBUG] Rufe fetch_full_problem für Slug: {selected_problem['titleSlug']} auf")
                                details = fetch_full_problem(selected_problem['titleSlug'])
                                
                                if not details:
                                    log_to_terminal(f"[DEBUG] Fehler: Keine Details zurückgegeben für {selected_problem['titleSlug']}", "error")
                                    st.error(f"Keine Details gefunden für {selected_problem['title']}")
                                else:
                                    log_to_terminal(f"[DEBUG] Details erhalten, Länge: {len(str(details))}")
                                    question = clean_html(details.get("content", ""))
                                    examples = details.get("exampleTestcases", "")
                                    
                                    log_to_terminal(f"[DEBUG] Question-Länge: {len(question)}, Examples-Länge: {len(examples)}")
                                    
                                    # Problem-Infos speichern
                                    st.session_state.current_problem = {
                                        "title": selected_problem['title'],
                                        "slug": selected_problem['titleSlug'],
                                        "difficulty": difficulty,
                                        "question": question,
                                        "examples": examples
                                    }
                                    
                                    # Lösung und Ergebnisse zurücksetzen
                                    st.session_state.current_solution = None
                                    st.session_state.current_results = None
                                    
                                    log_to_terminal(f"[DEBUG] Problem '{selected_problem['title']}' erfolgreich in session_state gespeichert")
                                    log_to_terminal(f"Problem '{selected_problem['title']}' erfolgreich geladen.", "success")
                                    st.success(f"Problem geladen: {selected_problem['title']}")
                                    st.rerun()
                except Exception as e:
                    log_to_terminal(f"[DEBUG] Ausnahme beim Laden des Problems: {str(e)}", "error")
                    log_to_terminal("Fehler beim Laden der Probleme von LeetCode API.", "error")
                    st.error(f"Fehler beim Laden der Probleme: {str(e)}")
        else:
            # Batch-Verarbeitung für mehrere Probleme
            log_to_terminal(f"Starte Batch-Verarbeitung für {num_problems} {difficulty}-Probleme...")
            st.info(f"Starte Batch-Verarbeitung für {num_problems} {difficulty}-Probleme...")
            
            # Container für Batch-Progress
            batch_progress_container = st.empty()
            batch_status_container = st.empty()
            
            try:
                log_to_terminal(f"[DEBUG] Rufe fetch_problems für Schwierigkeit '{difficulty}' auf")
                problems = fetch_problems(difficulty, limit=100)  # Mehr Probleme holen für die Filterung
                
                if not problems:
                    log_to_terminal("[DEBUG] Keine Probleme gefunden", "warning")
                    log_to_terminal("Keine Probleme für diesen Schwierigkeitsgrad gefunden.", "warning")
                    st.error("Keine Probleme für diesen Schwierigkeitsgrad gefunden.")
                else:
                    log_to_terminal(f"[DEBUG] {len(problems)} Probleme gefunden.")
                    # Filter verarbeitete Probleme
                    available_problems = [p for p in problems if p['titleSlug'] not in processed_problems]
                    
                    if len(available_problems) < num_problems:
                        log_to_terminal(f"[DEBUG] Nur {len(available_problems)} unbearbeitete Probleme verfügbar.", "warning")
                        log_to_terminal(f"Nur {len(available_problems)} unbearbeitete Probleme verfügbar, aber {num_problems} angefordert.", "warning")
                        st.warning(f"Nur {len(available_problems)} unbearbeitete Probleme verfügbar, aber {num_problems} angefordert.")
                        num_to_process = len(available_problems)
                    else:
                        num_to_process = num_problems
                    
                    if num_to_process == 0:
                        log_to_terminal(f"[DEBUG] Keine unbearbeiteten Probleme verfügbar.", "warning")
                        st.error("Keine verfügbaren Probleme für diesen Schwierigkeitsgrad")
                    else:
                        # Zufällige Probleme auswählen
                        selected_problems = random.sample(available_problems, num_to_process)
                        
                        # Fortschrittsbalken für die Batch-Verarbeitung
                        batch_progress = batch_progress_container.progress(0)
                        
                        success_count = 0
                        failure_count = 0
                        
                        # Verarbeite jedes Problem
                        for idx, problem in enumerate(selected_problems):
                            log_to_terminal(f"[BATCH] Verarbeite Problem {idx+1}/{num_to_process}: {problem['title']}")
                            batch_status_container.info(f"Verarbeite Problem {idx+1}/{num_to_process}: {problem['title']}")
                            
                            try:
                                # Lade Problem-Details
                                log_to_terminal(f"[DEBUG] Rufe fetch_full_problem für Slug: {problem['titleSlug']} auf")
                                details = fetch_full_problem(problem['titleSlug'])
                                
                                if not details:
                                    log_to_terminal(f"[DEBUG] Fehler: Keine Details zurückgegeben für {problem['titleSlug']}", "error")
                                    failure_count += 1
                                    continue
                                
                                # Problem-Daten vorbereiten
                                question = clean_html(details.get("content", ""))
                                examples = details.get("exampleTestcases", "")
                                
                                # Erstelle Prompt
                                cleaned_template = clean_template(st.session_state.prompt_template)
                                prompt = cleaned_template.format(
                                    title=problem['title'],
                                    question=question,
                                    examples=examples
                                )
                                
                                # Lösung generieren
                                log_to_terminal(f"[BATCH] Generiere Lösung für '{problem['title']}' mit {full_model_name}...")
                                llm_response = get_solution(prompt, temperature=temperature, model=full_model_name)
                                code = extract_code_block(llm_response)
                                
                                # Teste die Lösung
                                log_to_terminal(f"[BATCH] Teste Lösung für {problem['title']}...")
                                test_inputs = parse_testcases(examples, problem['titleSlug'])
                                
                                if test_inputs:
                                    results = []
                                    test_success = True
                                    
                                    for j, input_set in enumerate(test_inputs):
                                        result = test_solution(code, input_set, problem['titleSlug'])
                                        results.append({
                                            "input": input_set,
                                            "result": result
                                        })
                                        
                                        if not result['success']:
                                            test_success = False
                                            error_type = result.get('error_type', "Unbekannter Fehler")
                                            log_to_terminal(f"[BATCH] Test {j+1} für {problem['title']} fehlgeschlagen: {error_type}", "error")
                                    
                                    # Ergebnis speichern
                                    result_entry = {
                                        "slug": problem['titleSlug'],
                                        "title": problem['title'],
                                        "success": test_success,
                                        "error_type": None if test_success else error_type,
                                        "solution": code,
                                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                        "model": full_model_name,
                                        "temperature": temperature
                                    }
                                    
                                    st.session_state.results[difficulty].append(result_entry)
                                    
                                    if test_success:
                                        log_to_terminal(f"[BATCH] Lösung für '{problem['title']}' erfolgreich!", "success")
                                        success_count += 1
                                    else:
                                        log_to_terminal(f"[BATCH] Lösung für '{problem['title']}' fehlgeschlagen.", "error")
                                        failure_count += 1
                                else:
                                    log_to_terminal(f"[BATCH] Keine gültigen Testfälle für {problem['title']} gefunden.", "warning")
                                    failure_count += 1
                            
                            except Exception as e:
                                log_to_terminal(f"[BATCH] Fehler bei der Verarbeitung von {problem['title']}: {str(e)}", "error")
                                failure_count += 1
                            
                            # Fortschritt aktualisieren
                            batch_progress.progress((idx + 1) / num_to_process)
                        
                        # Zusammenfassung anzeigen
                        batch_progress_container.empty()
                        batch_status_container.success(f"Batch-Verarbeitung abgeschlossen: {success_count} erfolgreich, {failure_count} fehlgeschlagen.")
                        log_to_terminal(f"[BATCH] Verarbeitung abgeschlossen: {success_count} erfolgreich, {failure_count} fehlgeschlagen.", 
                                        "success" if success_count > failure_count else "warning")
                        
                        # Lade die Seite neu, um die Ergebnisse anzuzeigen
                        st.rerun()
                        
            except Exception as e:
                log_to_terminal(f"[DEBUG] Ausnahme bei der Batch-Verarbeitung: {str(e)}", "error")
                log_to_terminal("Fehler bei der Batch-Verarbeitung.", "error")
                st.error(f"Fehler bei der Batch-Verarbeitung: {str(e)}")

    # Problem anzeigen, wenn vorhanden
    if st.session_state.current_problem:
        st.markdown("---")
        # Erstelle eine "Karte" für das aktuelle Problem
        problem_container = st.container()
        with problem_container:
            st.subheader(f"Aktuelles Problem: {st.session_state.current_problem['title']}")
            
            # Anzeige von Metadaten - verbesserte Positionierung und Layout
            meta_cols = st.columns([1, 1])
            with meta_cols[0]:
                st.markdown(f"**Schwierigkeit:** <span style='color: {'green' if st.session_state.current_problem['difficulty'] == 'easy' else 'orange' if st.session_state.current_problem['difficulty'] == 'medium' else 'red'}'>{st.session_state.current_problem['difficulty'].capitalize()}</span>", unsafe_allow_html=True)
            with meta_cols[1]:
                st.markdown(f"**Problem-ID:** [{st.session_state.current_problem['slug']}](https://leetcode.com/problems/{st.session_state.current_problem['slug']}/)", unsafe_allow_html=True)
            
            # Trennlinie für bessere Visualisierung
            st.markdown("<hr style='margin-top: 0.5em; margin-bottom: 1em;'>", unsafe_allow_html=True)
            
            # Problem-Beschreibung mit Markdown-Unterstützung
            with st.expander("Problem-Beschreibung", expanded=True):
                st.markdown(st.session_state.current_problem['question'], unsafe_allow_html=True)
            
            # Beispiele in einem eigenen Container
            with st.expander("Beispiele", expanded=True):
                st.code(st.session_state.current_problem['examples'])
            
            # Button für Lösungsgenerierung in eigenem Container
            action_container = st.container()
            with action_container:
                generate_col1, generate_col2 = st.columns([1, 3])
                with generate_col1:
                    generate_button = st.button("Lösung generieren", use_container_width=True, key="generate_solution")
                
                # Status-Container für Fortschrittsanzeige
                status_container = st.empty()
                
                if generate_button:
                    # Prompt aus Template erstellen
                    try:
                        # Prüfe und bereinige das Template von ungültigen Platzhaltern
                        cleaned_template = clean_template(st.session_state.prompt_template)
                        
                        if cleaned_template != st.session_state.prompt_template:
                            log_to_terminal("Ungültige Platzhalter im Template gefunden und entfernt.", "warning")
                            status_container.warning("Ungültige Platzhalter im Template wurden für diese Ausführung entfernt.")
                        
                        # Verwende das bereinigte Template
                        prompt = cleaned_template.format(
                            title=st.session_state.current_problem['title'],
                            question=st.session_state.current_problem['question'],
                            examples=st.session_state.current_problem['examples']
                        )
                    except KeyError as e:
                        # Fehlerbehandlung für ungültige Platzhalter
                        log_to_terminal(f"Fehler im Prompt-Template: Ungültiger Platzhalter {e}", "error")
                        status_container.error(f"Fehler im Prompt-Template: Ungültiger Platzhalter {e}")
                        prompt = st.session_state.default_prompt_template.format(
                            title=st.session_state.current_problem['title'],
                            question=st.session_state.current_problem['question'],
                            examples=st.session_state.current_problem['examples']
                        )
                        log_to_terminal("Verwende Standard-Template als Fallback.", "warning")
                    
                    log_to_terminal(f"Generiere Lösung für '{st.session_state.current_problem['title']}' mit {full_model_name}...")
                    status_progress = status_container.progress(0)
                    
                    # Fortschritt anzeigen
                    for i in range(10):
                        time.sleep(0.1)  # Simuliere Fortschritt
                        status_progress.progress((i+1)/10)
                    
                    status_container.info("Generiere Lösung mit LLM...")
                    
                    try:
                        log_to_terminal(f"Prompt an {full_model_name} gesendet...")
                        llm_response = get_solution(prompt, temperature=temperature, model=full_model_name)
                        code = extract_code_block(llm_response)
                        
                        # Lösung speichern
                        st.session_state.current_solution = {
                            "code": code,
                            "full_response": llm_response
                        }
                        
                        log_to_terminal(f"Lösung von {full_model_name} erhalten.", "success")
                        status_container.success("Lösung generiert!")
                        
                        # Automatisch die Lösung testen
                        examples = st.session_state.current_problem['examples']
                        slug = st.session_state.current_problem['slug']
                        
                        log_to_terminal("Teste generierte Lösung...")
                        status_container.info("Teste Lösung...")
                        
                        test_inputs = parse_testcases(examples, slug)
                        
                        if test_inputs:
                            log_to_terminal(f"{len(test_inputs)} Testfälle gefunden.")
                            results = []
                            for j, input_set in enumerate(test_inputs):
                                log_to_terminal(f"Teste Eingabe {j+1}: {input_set}")
                                result = test_solution(code, input_set, slug)
                                results.append({
                                    "input": input_set,
                                    "result": result
                                })
                                
                                if result['success']:
                                    log_to_terminal(f"Test {j+1} erfolgreich.", "success")
                                else:
                                    error_type = result.get('error_type', "Unbekannter Fehler")
                                    log_to_terminal(f"Test {j+1} fehlgeschlagen: {error_type}", "error")
                                    # Füge hier die detaillierte Fehlerprotokollierung hinzu
                                    log_detailed_error(result, input_set, code[:500] if len(code) > 500 else code)
                            
                            # Ergebnisse speichern
                            st.session_state.current_results = results
                            
                            # Ergebnis zur Gesamtstatistik hinzufügen
                            success = all(r["result"]["success"] for r in results)
                            
                            result_entry = {
                                "slug": slug,
                                "title": st.session_state.current_problem['title'],
                                "success": success,
                                "error_type": None if success else error_type,
                                "solution": code,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "model": full_model_name,
                                "temperature": temperature
                            }
                            
                            log_to_terminal(f"Gesamtergebnis für '{st.session_state.current_problem['title']}': {'Erfolg' if success else 'Fehlgeschlagen'}", "success" if success else "error")
                            st.session_state.results[difficulty].append(result_entry)
                            
                            # Löschen des Status-Containers nach erfolgreicher Ausführung
                            status_container.empty()
                            
                            # Seite neu laden, um die Ergebnisse anzuzeigen
                            st.rerun()
                        else:
                            log_to_terminal("Keine gültigen Testfälle gefunden.", "warning")
                            status_container.error("Keine gültigen Testfälle gefunden")
                    
                    except Exception as e:
                        log_to_terminal(f"Fehler bei der LLM-Anfrage: {str(e)}", "error")
                        status_container.error(f"Fehler bei der LLM-Anfrage: {str(e)}")

        # Lösung anzeigen, wenn vorhanden
        if st.session_state.current_solution:
            st.markdown("---")
            solution_container = st.container()
            with solution_container:
                # Lösung in zwei Tabs anzeigen: "Lösung" und "Testergebnisse"
                solution_tab, results_tab = st.tabs(["Generierte Lösung", "Testergebnisse"])
                
                with solution_tab:
                    st.code(st.session_state.current_solution["code"], language="cpp")
                
                with results_tab:
                    if st.session_state.current_results:
                        # Gesamtergebnis am Anfang
                        success = all(r["result"]["success"] for r in st.session_state.current_results)
                        if success:
                            st.success("✅ Alle Tests erfolgreich!")
                        else:
                            st.error("❌ Einige Tests sind fehlgeschlagen")
                        
                        # Individuelle Testergebnisse
                        for i, result in enumerate(st.session_state.current_results):
                            with st.expander(f"Test {i+1}: {'✅ Erfolgreich' if result['result']['success'] else '❌ Fehlgeschlagen'}", expanded=not result["result"]["success"]):
                                st.write(f"**Eingabe:** `{result['input']}`")
                                
                                if result["result"]["success"]:
                                    st.write(f"**Ausgabe:** `{result['result'].get('output')}`")
                                else:
                                    # Zeige benutzerfreundliche Fehlermeldung an, falls verfügbar
                                    if "friendly_error" in result["result"]:
                                        st.warning(f"**Fehleranalyse:** {result['result']['friendly_error']}")
                                    
                                    # Zeige den detaillierten Fehlertyp an
                                    st.write(f"**Fehlertyp:** {result['result'].get('error_type', 'Unbekannter Fehler')}")
                                    
                                    # Zeige die Fehlermeldung an
                                    st.code(f"Fehlermeldung: {result['result'].get('error', 'Keine Fehlermeldung verfügbar')}")
                    else:
                        st.info("Keine Testergebnisse verfügbar.")

# Tab 2: Prompt anpassen
with tab2:
    st.header("Prompt-Template anpassen")
    
    # Sitzungsstatus für den Prompt-Vorschlag
    if 'improved_prompt' not in st.session_state:
        st.session_state.improved_prompt = None
    if 'show_prompt_suggestion' not in st.session_state:
        st.session_state.show_prompt_suggestion = False
    
    # Aktionsbereich mit übersichtlicher Button-Anordnung
    st.subheader("Aktionen")
    with st.container():
        action_cols = st.columns(3)
        with action_cols[0]:
            suggest_button = st.button("KI-Vorschlag generieren", 
                          use_container_width=True, 
                          key="generate_suggestion")
        with action_cols[1]:
            reset_button = st.button("Auf Standard zurücksetzen", 
                          use_container_width=True, 
                          key="reset_to_default")
        with action_cols[2]:
            default_button = st.button("Als Standard setzen", 
                          use_container_width=True, 
                          key="set_as_default")
    
    # Verarbeitung der Button-Aktionen
    if suggest_button:
        if not any(len(results) > 0 for results in st.session_state.results.values()):
            st.warning("Es sind noch keine Ergebnisse verfügbar. Generiere zuerst einige Lösungen.")
        else:
            with st.spinner("Analysiere Fehler und generiere verbesserten Prompt..."):
                # Sammle alle Fehler aus den bisherigen Ergebnissen
                error_examples = []
                for difficulty, results in st.session_state.results.items():
                    for result in results:
                        if not result.get("success", False) and result.get("error_type"):
                            error_examples.append({
                                "problem": result.get("title", "Unbekanntes Problem"),
                                "error_type": result.get("error_type", "unknown_error"),
                                "solution": result.get("solution", "")
                            })
                
                if not error_examples:
                    st.info("Keine Fehler gefunden, die analysiert werden können.")
                else:
                    # Erstelle einen Prompt für das LLM, um einen verbesserten Prompt vorzuschlagen
                    current_prompt = st.session_state.prompt_template
                    
                    meta_prompt = f"""Du bist ein Experte für LLM-Prompting und C++-Programmierung. Analysiere die folgenden Fehler, die bei der Generierung von C++-Code für LeetCode-Probleme aufgetreten sind.

Aktuelles Prompt-Template:
```
{current_prompt}
```

Fehlerbeispiele:
"""
                    
                    # Füge bis zu 5 Fehlerbeispiele hinzu
                    for i, example in enumerate(error_examples[:5]):
                        meta_prompt += f"""
Beispiel {i+1}:
Problem: {example['problem']}
Fehlertyp: {example['error_type']}
Fehlerhafter Code:
```cpp
{example['solution'][:300]}{'...' if len(example['solution']) > 300 else ''}
```
"""
                    
                    meta_prompt += """
Basierend auf diesen Fehlern, schlage ein verbessertes Prompt-Template vor, das:
1. Die häufigsten Fehlerarten adressiert
2. Klarere Anweisungen für die korrekte C++-Syntax gibt
3. Die Platzhalter {title}, {question}, und {examples} beibehält
4. Spezifische Hinweise zur Vermeidung der beobachteten Fehler enthält

WICHTIG:
- Füge KEINEN tatsächlichen C++-Code direkt in den Prompt ein
- Gib keine #include-Direktiven oder "using namespace"-Deklarationen am Anfang des Prompts an
- Der Prompt selbst sollte keine Codezeilen enthalten, sondern nur ANWEISUNGEN zur Codegenerierung
- Formuliere alle Anweisungen als klare Instruktionen, nicht als Code-Beispiele

Das Prompt-Template sollte mit "### LeetCode Problem: {title}" beginnen und nur natürliche Sprache und Platzhalter enthalten.

Gib nur das verbesserte Prompt-Template zurück, ohne Erklärungen.
"""
                    
                    try:
                        # Verwende das gleiche Modell wie für die Lösungen
                        improved_prompt = get_solution(meta_prompt, temperature=0.5, model=full_model_name)
                        
                        # Entferne Code-Block-Markierungen, falls vorhanden
                        improved_prompt = extract_code_block(improved_prompt) if "```" in improved_prompt else improved_prompt
                        
                        # Bereinige den vorgeschlagenen Prompt von ungültigen Platzhaltern
                        improved_prompt = clean_template(improved_prompt)
                        
                        # Validiere den Prompt-Vorschlag
                        def validate_prompt(prompt):
                            # Liste verdächtiger Code-Elemente
                            suspicious_patterns = [
                                "#include",
                                "using namespace",
                                "int main()",
                                "class Solution {",
                                "void"
                            ]
                            
                            if not prompt.startswith("### LeetCode Problem:"):
                                return False, "Der Prompt sollte mit '### LeetCode Problem:' beginnen"
                            
                            # Prüfe auf verdächtige Code-Elemente am Anfang des Prompts
                            first_lines = prompt.split("\n")[:5]  # Überprüfe die ersten 5 Zeilen
                            for line in first_lines:
                                for pattern in suspicious_patterns:
                                    if pattern in line:
                                        return False, f"Der Prompt enthält Code-Element: '{pattern}'"
                            
                            return True, ""
                        
                        is_valid, error_message = validate_prompt(improved_prompt)
                        
                        if is_valid:
                            # Speichere den Vorschlag in session_state
                            st.session_state.improved_prompt = improved_prompt
                            st.session_state.show_prompt_suggestion = True
                        else:
                            st.error(f"Der generierte Prompt ist ungültig: {error_message}")
                            st.warning("Versuche es erneut oder passe den Prompt manuell an.")
                            # Zeige den ungültigen Prompt zur Inspektion an
                            st.code(improved_prompt, language="text")
                        
                    except Exception as e:
                        st.error(f"Fehler bei der Generierung des Prompt-Vorschlags: {str(e)}")
    
    if reset_button:
        st.session_state.prompt_template = st.session_state.default_prompt_template
        st.success("Prompt-Template wurde auf den Standardwert zurückgesetzt.")
        st.rerun()
    
    if default_button:
        st.session_state.default_prompt_template = st.session_state.prompt_template
        st.success("Aktuelles Template als neuer Standardwert gespeichert.")
    
    # Zeige den verbesserten Prompt, wenn verfügbar
    if st.session_state.show_prompt_suggestion and st.session_state.improved_prompt:
        st.markdown("---")
        with st.container():
            st.subheader("Vorgeschlagenes verbessertes Prompt-Template")
            st.code(st.session_state.improved_prompt)
            
            # Buttons für Akzeptieren/Ablehnen des Vorschlags
            decision_cols = st.columns(2)
            with decision_cols[0]:
                if st.button("Vorschlag übernehmen", key="accept_suggestion", use_container_width=True):
                    st.session_state.prompt_template = st.session_state.improved_prompt
                    st.session_state.improved_prompt = None
                    st.session_state.show_prompt_suggestion = False
                    st.success("Prompt-Template wurde aktualisiert!")
                    st.rerun()
            
            with decision_cols[1]:
                if st.button("Vorschlag ablehnen", key="reject_suggestion", use_container_width=True):
                    st.session_state.improved_prompt = None
                    st.session_state.show_prompt_suggestion = False
                    st.info("Prompt-Vorschlag wurde abgelehnt.")
                    st.rerun()
    
    # Trennlinie vor dem Haupteditor
    st.markdown("---")
    
    # Hauptbereich für die Prompt-Eingabe
    st.subheader("Prompt-Template bearbeiten")
    prompt_text = st.text_area("Prompt-Inhalt", st.session_state.prompt_template, height=300)
    
    save_col, info_col = st.columns([1, 3])
    with save_col:
        if st.button("Template speichern", key="save_template", use_container_width=True):
            # Automatisch bereinigen, bevor es gespeichert wird
            cleaned_prompt = clean_template(prompt_text)
            if cleaned_prompt != prompt_text:
                st.warning("Ungültige Platzhalter wurden automatisch entfernt.")
                
            st.session_state.prompt_template = cleaned_prompt
            st.success("Prompt-Template aktualisiert!")
    
    with info_col:
        st.info("""
        Verfügbare Platzhalter:
        - {title} - Titel des Problems
        - {question} - Beschreibung des Problems
        - {examples} - Beispieltestfälle
        """)
    
    # Vorschau des aktuellen Prompts
    if st.session_state.current_problem:
        st.markdown("---")
        st.subheader("Prompt-Vorschau für aktuelles Problem")
        try:
            # Bereinige das Template
            cleaned_template = clean_template(prompt_text)
            
            if cleaned_template != prompt_text:
                st.warning("Ungültige Platzhalter wurden für die Vorschau entfernt.")
            
            # Verwende das bereinigte Template
            preview = cleaned_template.format(
                title=st.session_state.current_problem['title'],
                question=st.session_state.current_problem['question'],
                examples=st.session_state.current_problem['examples']
            )
            st.code(preview)
        except KeyError as e:
            st.error(f"Fehler im Prompt-Template: Ungültiger Platzhalter {e}")
            # Zeige Original-Template mit markierten Fehlern
            st.code(prompt_text)
            
            # Button zum Bereinigen des Templates
            if st.button("Template bereinigen"):
                # Verwende die clean_template-Funktion
                cleaned_template = clean_template(prompt_text)
                st.session_state.prompt_template = cleaned_template
                st.success("Ungültige Platzhalter wurden entfernt.")
                st.rerun()

# Tab 3: Ergebnisse
with tab3:
    st.header("Bisherige Ergebnisse")
    
    # Ergebnisse als Tabelle anzeigen
    if any(len(results) > 0 for results in st.session_state.results.values()):
        # Statistik-Übersicht
        stats_container = st.container()
        with stats_container:
            st.subheader("Zusammenfassung")
            
            # Zähle erfolgreiche und fehlgeschlagene Tests
            total_count = 0
            success_count = 0
            
            for difficulty, results in st.session_state.results.items():
                total_count += len(results)
                success_count += sum(1 for r in results if r["success"])
            
            # Zeige Zusammenfassung in Kacheln an
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric(label="Gesamt", value=total_count)
            with metric_cols[1]:
                st.metric(label="Erfolgreich", value=success_count)
            with metric_cols[2]:
                st.metric(label="Fehlgeschlagen", value=total_count - success_count)
            with metric_cols[3]:
                success_rate = (success_count / total_count * 100) if total_count > 0 else 0
                st.metric(label="Erfolgsrate", value=f"{success_rate:.1f}%")
        
        st.markdown("---")
        
        # Filter-Optionen
        filter_container = st.container()
        with filter_container:
            st.subheader("Ergebnisse filtern")
            filter_cols = st.columns(3)
            
            with filter_cols[0]:
                filter_difficulty = st.selectbox(
                    "Schwierigkeitsgrad", 
                    ["Alle", "easy", "medium", "hard"],
                    key="results_filter_difficulty"
                )
            
            with filter_cols[1]:
                filter_status = st.selectbox(
                    "Status", 
                    ["Alle", "Erfolgreich", "Fehlgeschlagen"],
                    key="results_filter_status"
                )
            
            with filter_cols[2]:
                filter_search = st.text_input(
                    "Suche (Titel)", 
                    key="results_filter_search"
                )
        
        # Tabellendarstellung mit Filtern
        # Alle Ergebnisse kombinieren
        all_results = []
        for difficulty, results in st.session_state.results.items():
            # Filter nach Schwierigkeitsgrad
            if filter_difficulty != "Alle" and difficulty != filter_difficulty:
                continue
                
            for result in results:
                # Filter nach Status
                if filter_status == "Erfolgreich" and not result["success"]:
                    continue
                if filter_status == "Fehlgeschlagen" and result["success"]:
                    continue
                
                # Filter nach Titel
                if filter_search and filter_search.lower() not in result["title"].lower():
                    continue
                    
                # Füge zum Ergebnis hinzu
                all_results.append({
                    "Difficulty": difficulty,
                    "Title": result["title"],
                    "Slug": result["slug"],
                    "Success": "✅" if result["success"] else "❌",
                    "Error Type": result.get("error_type", "None") if not result["success"] else "None",
                    "Model": result.get("model", "Unknown"),
                    "Temp": result.get("temperature", "0.7"),
                    "Timestamp": result["timestamp"]
                })
        
        df = pd.DataFrame(all_results)
        
        # Anzeige der gefilterten Ergebnisse
        if len(df) > 0:
            st.dataframe(df, use_container_width=True, height=400)
            st.info(f"{len(df)} Ergebnisse gefunden.")
        else:
            st.warning("Keine Ergebnisse für die gewählten Filter gefunden.")
        
        # Export-Funktionen
        st.markdown("---")
        export_container = st.container()
        with export_container:
            st.subheader("Ergebnisse exportieren")
            export_col1, export_col2 = st.columns([1, 3])
            with export_col1:
                if st.button("Ergebnisse exportieren", use_container_width=True):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"leetcode_ui_results_{timestamp}"
                    
                    # JSON-Export
                    with open(f"{filename}.json", "w") as f:
                        json.dump(st.session_state.results, f, indent=2)
                    
                    # CSV-Export
                    df.to_csv(f"{filename}.csv", index=False)
                    
                    st.success(f"Ergebnisse gespeichert als {filename}.json und {filename}.csv")
    else:
        st.info("Noch keine Ergebnisse verfügbar. Generiere eine Lösung im Tab 'Problem auswählen'.")
        
        # Beispielanzeige als Platzhalter
        st.markdown("### Beispiel-Ansicht")
        placeholder_data = pd.DataFrame([
            {"Difficulty": "easy", "Title": "Two Sum", "Success": "✅", "Error Type": "None", "Timestamp": "2023-05-01 12:34:56"},
            {"Difficulty": "medium", "Title": "Add Two Numbers", "Success": "❌", "Error Type": "syntax_error", "Timestamp": "2023-05-01 12:45:12"}
        ])
        st.dataframe(placeholder_data, use_container_width=True)
        st.caption("So werden deine Ergebnisse angezeigt, sobald du einige Probleme gelöst hast.")

# Tab 4: Statistiken
with tab4:
    st.header("Statistiken")
    
    if any(len(results) > 0 for results in st.session_state.results.values()):
        # Tabs für verschiedene Statistikansichten
        stat_tab1, stat_tab2, stat_tab3, stat_tab4 = st.tabs(["Allgemeine Statistik", "Modell-Vergleich", "Fehleranalyse nach Modell", "Heatmap"])
        
        # Tab 1: Allgemeine Statistik (bisherige Funktionalität)
        with stat_tab1:
            # Übersicht-Container
            overview_container = st.container()
            with overview_container:
                st.subheader("Gesamtübersicht")
                
                # Erfolgsrate als großes Balkendiagramm
                total_count = 0
                success_count = 0
                
                for difficulty, results in st.session_state.results.items():
                    total_count += len(results)
                    success_count += sum(1 for r in results if r["success"])
                
                failure_count = total_count - success_count
                
                chart_data = pd.DataFrame({
                    "Status": ["Erfolgreich", "Fehlgeschlagen"],
                    "Anzahl": [success_count, failure_count]
                })
                
                chart_cols = st.columns([2, 1])
                with chart_cols[0]:
                    st.bar_chart(chart_data.set_index("Status"), height=250)
                with chart_cols[1]:
                    success_rate = (success_count / total_count * 100) if total_count > 0 else 0
                    st.metric("Erfolgsrate", f"{success_rate:.1f}%")
                    st.metric("Gelöste Probleme", f"{success_count} von {total_count}")
            
            # Horizontale Linie
            st.markdown("---")
            
            # Aufschlüsselung nach Schwierigkeitsgrad
            st.subheader("Erfolgsrate nach Schwierigkeitsgrad")
            
            stats_data = []
            for difficulty, results in st.session_state.results.items():
                if results:
                    total = len(results)
                    success = sum(1 for r in results if r["success"])
                    stats_data.append({
                        "Difficulty": difficulty,
                        "Total": total,
                        "Success": success,
                        "Success Rate": f"{(success/total*100):.1f}%",
                        "Success Rate (raw)": (success/total*100)
                    })
            
            # Statistik-Tabelle
            stats_df = pd.DataFrame(stats_data)
            st.dataframe(stats_df[["Difficulty", "Total", "Success", "Success Rate"]], use_container_width=True)
            
            # Visualisierung der Erfolgsrate nach Schwierigkeitsgrad
            st.subheader("Visualisierung nach Schwierigkeitsgrad")
            if len(stats_df) > 0:
                st.bar_chart(stats_df.set_index("Difficulty")["Success Rate (raw)"], height=300)
            
            # Horizontale Linie
            st.markdown("---")
            
            # Fehlertypen-Statistik
            st.subheader("Häufigste Fehlertypen")
            
            error_types = {}
            for difficulty, results in st.session_state.results.items():
                for result in results:
                    if not result["success"] and result.get("error_type"):
                        error_type = result.get("error_type")
                        if error_type not in error_types:
                            error_types[error_type] = 0
                        error_types[error_type] += 1
            
            if error_types:
                error_df = pd.DataFrame([
                    {"Error Type": error_type, "Count": count}
                    for error_type, count in error_types.items()
                ])
                error_df = error_df.sort_values("Count", ascending=False)
                
                # Balkendiagramm für Fehlertypen
                st.bar_chart(error_df.set_index("Error Type"), height=300)
                
                # Detaillierte Fehleranalyse
                st.subheader("Detaillierte Fehleranalyse")
                st.dataframe(error_df, use_container_width=True)
                
                # Empfehlungen basierend auf häufigsten Fehlern
                if len(error_df) > 0:
                    st.subheader("Empfehlungen")
                    top_error = error_df.iloc[0]["Error Type"]
                    
                    if "syntax" in top_error.lower():
                        st.info("💡 **Tipp**: Die häufigsten Fehler sind Syntaxfehler. Achte besonders auf korrekte Semikolons und Klammerung in deinem Prompt-Template.")
                    elif "undefined" in top_error.lower():
                        st.info("💡 **Tipp**: Viele Fehler beziehen sich auf undefinierte Referenzen. Verbessere dein Prompt-Template, um sicherzustellen, dass alle Funktionen vollständig implementiert werden.")
                    elif "compile" in top_error.lower():
                        st.info("💡 **Tipp**: Compilerfehler treten häufig auf. Achte darauf, dass dein Prompt die Einbindung aller benötigten Header-Dateien anweist.")
                    else:
                        st.info(f"💡 **Tipp**: Analysiere die häufigsten Fehler vom Typ '{top_error}' und passe dein Prompt-Template entsprechend an.")
            else:
                st.info("Bisher keine Fehler gefunden. Prima!")
        
        # Tab 2: Modell-Vergleich
        with stat_tab2:
            st.subheader("Vergleich verschiedener Modelle")
            
            # Sammel alle Modelle aus den Ergebnissen
            all_models = set()
            for difficulty, results in st.session_state.results.items():
                for result in results:
                    model = result.get("model", "unknown")
                    all_models.add(model)
            
            if not all_models:
                st.info("Keine Modelle gefunden. Generiere zuerst einige Lösungen mit verschiedenen Modellen.")
            else:
                # Modell-Erfolgsraten berechnen
                model_stats = {}
                for model in all_models:
                    model_stats[model] = {
                        "total": 0, 
                        "success": 0, 
                        "easy_total": 0, 
                        "easy_success": 0,
                        "medium_total": 0, 
                        "medium_success": 0,
                        "hard_total": 0, 
                        "hard_success": 0
                    }
                
                # Daten sammeln
                for difficulty, results in st.session_state.results.items():
                    for result in results:
                        model = result.get("model", "unknown")
                        if model in model_stats:
                            model_stats[model]["total"] += 1
                            if result.get("success", False):
                                model_stats[model]["success"] += 1
                            
                            # Nach Schwierigkeitsgrad
                            model_stats[model][f"{difficulty}_total"] += 1
                            if result.get("success", False):
                                model_stats[model][f"{difficulty}_success"] += 1
                
                # Daten für die Visualisierung aufbereiten
                model_compare_data = []
                for model, stats in model_stats.items():
                    success_rate = (stats["success"] / stats["total"] * 100) if stats["total"] > 0 else 0
                    easy_rate = (stats["easy_success"] / stats["easy_total"] * 100) if stats["easy_total"] > 0 else 0
                    medium_rate = (stats["medium_success"] / stats["medium_total"] * 100) if stats["medium_total"] > 0 else 0
                    hard_rate = (stats["hard_success"] / stats["hard_total"] * 100) if stats["hard_total"] > 0 else 0
                    
                    model_compare_data.append({
                        "Model": model,
                        "Total Problems": stats["total"],
                        "Success Rate": f"{success_rate:.1f}%",
                        "Success Rate (raw)": success_rate,
                        "Easy Success Rate": f"{easy_rate:.1f}%",
                        "Easy Success Rate (raw)": easy_rate,
                        "Medium Success Rate": f"{medium_rate:.1f}%", 
                        "Medium Success Rate (raw)": medium_rate,
                        "Hard Success Rate": f"{hard_rate:.1f}%",
                        "Hard Success Rate (raw)": hard_rate
                    })
                
                model_compare_df = pd.DataFrame(model_compare_data)
                
                # Tabelle mit Modellvergleich
                st.dataframe(model_compare_df[[
                    "Model", "Total Problems", "Success Rate", 
                    "Easy Success Rate", "Medium Success Rate", "Hard Success Rate"
                ]], use_container_width=True)
                
                # Visualisierung des Modellvergleichs
                st.subheader("Erfolgsraten nach Modell")
                if len(model_compare_df) > 0:
                    # Gesamterfolgsrate
                    st.bar_chart(model_compare_df.set_index("Model")["Success Rate (raw)"], height=300)
                    
                    # Erfolgsraten nach Schwierigkeitsgrad
                    st.subheader("Erfolgsraten nach Schwierigkeitsgrad")
                    
                    # Für die Visualisierung umformatieren
                    model_difficulty_data = []
                    for _, row in model_compare_df.iterrows():
                        model_difficulty_data.append({
                            "Model": row["Model"],
                            "Difficulty": "Easy",
                            "Success Rate": row["Easy Success Rate (raw)"]
                        })
                        model_difficulty_data.append({
                            "Model": row["Model"],
                            "Difficulty": "Medium",
                            "Success Rate": row["Medium Success Rate (raw)"]
                        })
                        model_difficulty_data.append({
                            "Model": row["Model"],
                            "Difficulty": "Hard",
                            "Success Rate": row["Hard Success Rate (raw)"]
                        })
                    
                    model_difficulty_df = pd.DataFrame(model_difficulty_data)
                    
                    # Gruppiertes Balkendiagramm für Schwierigkeitsgrade je Modell
                    chart_data = model_difficulty_df.pivot(index="Model", columns="Difficulty", values="Success Rate")
                    st.bar_chart(chart_data, height=400)
                    
                    # Top-Modell identifizieren
                    top_model = model_compare_df.loc[model_compare_df["Success Rate (raw)"].idxmax()]
                    st.success(f"**Top-Modell:** {top_model['Model']} mit einer Erfolgsrate von {top_model['Success Rate']}")
        
        # Tab 3: Fehleranalyse nach Modell
        with stat_tab3:
            st.subheader("Fehleranalyse nach Modell")
            
            # Alle Modelle und Fehlertypen sammeln
            all_models = set()
            all_error_types = set()
            
            for difficulty, results in st.session_state.results.items():
                for result in results:
                    model = result.get("model", "unknown")
                    all_models.add(model)
                    
                    if not result.get("success", True) and result.get("error_type"):
                        all_error_types.add(result.get("error_type"))
            
            if not all_models or not all_error_types:
                st.info("Nicht genügend Daten für eine Fehleranalyse nach Modell. Generiere zuerst mehr Lösungen mit verschiedenen Modellen.")
            else:
                # Fehlerstatistik nach Modell erstellen
                model_error_stats = {}
                for model in all_models:
                    model_error_stats[model] = {"total": 0}
                    for error_type in all_error_types:
                        model_error_stats[model][error_type] = 0
                
                # Daten sammeln
                for difficulty, results in st.session_state.results.items():
                    for result in results:
                        model = result.get("model", "unknown")
                        if model in model_error_stats:
                            model_error_stats[model]["total"] += 1
                            
                            if not result.get("success", True) and result.get("error_type") in all_error_types:
                                model_error_stats[model][result.get("error_type")] += 1
                
                # Daten für die Visualisierung aufbereiten
                model_error_data = []
                for model, stats in model_error_stats.items():
                    model_row = {"Model": model, "Total Problems": stats["total"]}
                    
                    for error_type in all_error_types:
                        error_count = stats.get(error_type, 0)
                        error_rate = (error_count / stats["total"] * 100) if stats["total"] > 0 else 0
                        model_row[f"{error_type} Count"] = error_count
                        model_row[f"{error_type} Rate"] = f"{error_rate:.1f}%"
                        model_row[f"{error_type} Rate (raw)"] = error_rate
                    
                    model_error_data.append(model_row)
                
                model_error_df = pd.DataFrame(model_error_data)
                
                # Tabelle mit Fehlerraten nach Modell
                display_columns = ["Model", "Total Problems"]
                for error_type in all_error_types:
                    display_columns.append(f"{error_type} Count")
                    display_columns.append(f"{error_type} Rate")
                
                st.dataframe(model_error_df[display_columns], use_container_width=True)
                
                # Visualisierung der häufigsten Fehlertypen nach Modell
                st.subheader("Häufigste Fehlertypen nach Modell")
                
                # Für jedes Modell die häufigsten Fehler visualisieren
                for model in all_models:
                    st.write(f"**Modell: {model}**")
                    
                    model_data = model_error_df[model_error_df["Model"] == model].iloc[0]
                    error_data = []
                    
                    for error_type in all_error_types:
                        error_data.append({
                            "Error Type": error_type,
                            "Rate": model_data.get(f"{error_type} Rate (raw)", 0)
                        })
                    
                    error_chart_df = pd.DataFrame(error_data)
                    if not error_chart_df.empty:
                        st.bar_chart(error_chart_df.set_index("Error Type"), height=200)
                    
                    # Horizontale Linie
                    st.markdown("---")
                
                # Modellempfehlung basierend auf Fehlerraten
                st.subheader("Modellempfehlung")
                
                # Modelle mit niedrigsten Fehlerraten für bestimmte Fehlertypen identifizieren
                best_models = {}
                for error_type in all_error_types:
                    if any(model_error_df[f"{error_type} Rate (raw)"] > 0):
                        best_model_idx = model_error_df[f"{error_type} Rate (raw)"].idxmin()
                        best_model = model_error_df.iloc[best_model_idx]["Model"]
                        best_rate = model_error_df.iloc[best_model_idx][f"{error_type} Rate"]
                        best_models[error_type] = (best_model, best_rate)
                
                for error_type, (model, rate) in best_models.items():
                    st.info(f"💡 Für Fehlertyp '{error_type}': **{model}** hat die niedrigste Fehlerrate ({rate})")
        
        # Tab 4: Heatmap (neu)
        add_heatmap_tab(stat_tab4)
    else:
        st.info("Noch keine Ergebnisse verfügbar für Statistiken. Löse einige Probleme, um hier Statistiken zu sehen.")
        
        # Beispielvisualisierung als Platzhalter
        st.markdown("### Beispiel-Visualisierung")
        placeholder_stats = pd.DataFrame([
            {"Difficulty": "easy", "Success Rate": 75},
            {"Difficulty": "medium", "Success Rate": 50},
            {"Difficulty": "hard", "Success Rate": 25}
        ])
        st.bar_chart(placeholder_stats.set_index("Difficulty"), height=250)
        st.caption("So werden deine Statistiken angezeigt, sobald du einige Probleme gelöst hast.")

# Footer
st.sidebar.markdown("---")
st.sidebar.info("Entwickelt zur Evaluation von LLMs bei der Lösung von LeetCode-Problemen.") 