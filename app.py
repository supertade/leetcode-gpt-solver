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
from utils.clean import clean_html, extract_code_block
# Import der neuen Heatmap-Visualisierung
from heatmap_viz import add_heatmap_tab
# Import der neuen LeetCode-Submission-Komponenten
from utils.submission_ui import show_submission_section, reset_submission_state

st.set_page_config(page_title="LeetCode LLM Evaluator", layout="wide")
st.title("LeetCode LLM Evaluator")

# Tracking von verarbeiteten Problemen (wie in main.py)
processed_problems = set()

# Sitzungsstatus initialisieren
if 'results' not in st.session_state:
    st.session_state.results = {"easy": [], "medium": [], "hard": []}
if 'current_problem' not in st.session_state:
    st.session_state.current_problem = None
if 'active_problems' not in st.session_state:
    st.session_state.active_problems = {}  # Dictionary von Problem-Slugs zu Problem-Details
if 'current_solution' not in st.session_state:
    st.session_state.current_solution = None
if 'solutions' not in st.session_state:
    st.session_state.solutions = {}  # Dictionary von Problem-Slugs zu Lösungen
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

# Hilfsfunktion zum Anzeigen detaillierter Ergebnisinformationen
def show_result_details(result, submission_num=None, is_nested=False):
    """Hilfsfunktion zum Anzeigen detaillierter Ergebnisinformationen."""
    # Zeitstempel
    submission_header = f"Submission {submission_num}" if submission_num else "Submission"
    st.markdown(f"**{submission_header}:** {result.get('timestamp', 'Unbekannt')}")
    
    # Modell-Informationen
    st.markdown(f"**Modell:** {result.get('model', 'Unbekannt')} (Temperatur: {result.get('temperature', 'Unbekannt')})")
    
    # Status und Ergebnis
    status = "Erfolgreich" if result.get('success', False) else "Fehlgeschlagen"
    status_color = "green" if result.get('success', False) else "red"
    
    st.markdown(f"**Status:** <span style='color: {status_color};'>{status}</span>", unsafe_allow_html=True)
    
    if 'leetcode_status' in result:
        st.markdown(f"**LeetCode-Status:** {result.get('leetcode_status', 'Unbekannt')}")
    
    # Leistungsmetriken, falls vorhanden
    metrics_col1, metrics_col2 = st.columns(2)
    
    with metrics_col1:
        if 'runtime_ms' in result and result['runtime_ms'] is not None:
            st.markdown(f"**Laufzeit:** {result.get('runtime_ms', 'N/A')} ms")
    
    with metrics_col2:
        if 'memory_mb' in result and result['memory_mb'] is not None:
            st.markdown(f"**Speicherverbrauch:** {result.get('memory_mb', 'N/A')} MB")
    
    # Fehlertyp und Details (falls fehlgeschlagen)
    if not result.get('success', False) and result.get('error_type'):
        error_type = result.get('error_type', 'unknown_error')
        st.markdown(f"**Fehlertyp:** {error_type.replace('_leetcode', '')}")
        
        # Bei Compiler-Fehlern, zeige die Fehlermeldung an
        if 'compile_error_leetcode' in error_type:
            st.markdown("##### Compiler-Fehler Details")
            if 'full_compile_error' in result and result['full_compile_error']:
                st.code(result['full_compile_error'], language="bash")
            elif 'compile_error' in result and result['compile_error']:
                st.code(result['compile_error'], language="bash")
            else:
                st.info("Keine detaillierten Compiler-Fehler verfügbar.")
        
        # Bei Runtime-Fehlern, zeige die Fehlermeldung an
        if 'runtime_error_leetcode' in error_type:
            st.markdown("##### Laufzeitfehler Details")
            if 'runtime_error' in result and result['runtime_error']:
                st.code(result['runtime_error'], language="bash")
            else:
                st.info("Keine detaillierten Laufzeitfehler verfügbar.")
        
        # Bei Wrong Answer, zeige erwartete und tatsächliche Ausgabe an
        if 'wrong_answer_leetcode' in error_type:
            st.markdown("##### Wrong Answer Details")
            if 'wrong_answer_details' in result and result['wrong_answer_details']:
                details = result['wrong_answer_details']
                if 'last_testcase' in details and details['last_testcase']:
                    st.markdown("**Letzter fehlgeschlagener Testfall:**")
                    st.code(details['last_testcase'])
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Erwartete Ausgabe:**")
                    st.code(details.get('expected', 'Nicht verfügbar'))
                
                with col2:
                    st.markdown("**Tatsächliche Ausgabe:**")
                    st.code(details.get('actual', 'Nicht verfügbar'))
            else:
                st.info("Keine detaillierten Wrong Answer-Informationen verfügbar.")
    
    # Code-Lösung anzeigen
    st.markdown("##### Code-Lösung")
    if 'solution' in result and result['solution']:
        st.code(result['solution'], language="cpp")
    else:
        st.info("Keine Code-Lösung verfügbar.")
    
    # Rohdaten für Debugging
    if not is_nested:
        # Nur im nicht-verschachtelten Kontext Expander verwenden
        with st.expander("Rohdaten", expanded=False):
            if 'raw_result' in result:
                st.json(result['raw_result'])
            else:
                st.json({k: v for k, v in result.items() if k != 'solution' and not isinstance(v, (dict, list)) or k == 'error_type'})

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

# Speichere die Modellauswahl im Session State
st.session_state.model = model
st.session_state.model_version = model_version
st.session_state.temperature = temperature

# Tabs für verschiedene Funktionen
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Problem auswählen", "Prompt anpassen", "Ergebnisse", "Problem-Logs", "Statistiken"])

# Tab 1: Problem auswählen
with tab1:
    st.header("Problem auswählen")
    
    # Terminal-Ausgabe (collapsed by default)
    # Entferne die gesamte Terminal-Ausgabekomponente
    
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
                                    
                                    # Füge das Problem auch zu den aktiven Problemen hinzu
                                    problem_slug = selected_problem['titleSlug']
                                    st.session_state.active_problems[problem_slug] = {
                                        "title": selected_problem['title'],
                                        "slug": problem_slug,
                                        "difficulty": current_difficulty,
                                        "question": question,
                                        "examples": examples
                                    }
                                    
                                    # Lösung und Ergebnisse zurücksetzen
                                    st.session_state.current_solution = None
                                    
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
                                
                                # Füge das Problem auch zu den aktiven Problemen hinzu
                                problem_slug = selected_problem['titleSlug']
                                st.session_state.active_problems[problem_slug] = {
                                    "title": selected_problem['title'],
                                    "slug": problem_slug,
                                    "difficulty": current_difficulty,
                                    "question": question,
                                    "examples": examples
                                }
                                
                                # Lösung und Ergebnisse zurücksetzen
                                st.session_state.current_solution = None
                                
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
                                    
                                    # Füge das Problem auch zu den aktiven Problemen hinzu
                                    problem_slug = selected_problem['titleSlug']
                                    st.session_state.active_problems[problem_slug] = {
                                        "title": selected_problem['title'],
                                        "slug": problem_slug,
                                        "difficulty": difficulty,
                                        "question": question,
                                        "examples": examples
                                    }
                                    
                                    # Lösung und Ergebnisse zurücksetzen
                                    st.session_state.current_solution = None
                                    
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
                                
                                # Lösungen im Batch-Prozess werden nicht automatisch zur Statistik hinzugefügt
                                # Die Ergebnisse werden erst erfasst, wenn eine LeetCode-Submission erfolgt
                                log_to_terminal(f"[BATCH] Lösung für '{problem['title']}' generiert.", "success")

                                # Problem und Lösung speichern
                                problem_slug = problem['titleSlug']
                                st.session_state.active_problems[problem_slug] = {
                                    "title": problem['title'],
                                    "slug": problem_slug,
                                    "difficulty": difficulty,
                                    "question": question,
                                    "examples": examples
                                }

                                # Lösung speichern
                                st.session_state.solutions[problem_slug] = {
                                    "code": code,
                                    "full_response": llm_response
                                }

                                # Automatisch bei LeetCode einreichen
                                try:
                                    log_to_terminal(f"[BATCH] Reiche Lösung für '{problem['title']}' bei LeetCode ein...")
                                    batch_status_container.info(f"Reiche Lösung für '{problem['title']}' bei LeetCode ein...")
                                    
                                    from utils.submission_ui import submit_to_leetcode  # Importiere die Funktion für LeetCode-Submits
                                    
                                    # Submission starten
                                    submit_result = submit_to_leetcode(problem_slug, code, "cpp")
                                    
                                    if submit_result.get("success", False):
                                        leetcode_status = submit_result.get("result", "Unknown")
                                        is_accepted = (submit_result.get("status_code", 0) == 10)
                                        
                                        if is_accepted:
                                            log_to_terminal(f"[BATCH] Lösung für '{problem['title']}' wurde von LeetCode akzeptiert!", "success")
                                            batch_status_container.success(f"Lösung für '{problem['title']}' wurde von LeetCode akzeptiert!")
                                        else:
                                            log_to_terminal(f"[BATCH] LeetCode-Submit für '{problem['title']}' ergab: {leetcode_status}", "warning")
                                            batch_status_container.warning(f"LeetCode-Submit für '{problem['title']}' ergab: {leetcode_status}")
                                    else:
                                        error_msg = submit_result.get("error", "Unbekannter Fehler")
                                        log_to_terminal(f"[BATCH] Fehler beim Submit für '{problem['title']}': {error_msg}", "error")
                                        batch_status_container.error(f"Fehler beim Submit für '{problem['title']}': {error_msg}")
                                except Exception as e:
                                    log_to_terminal(f"[BATCH] Fehler beim LeetCode-Submit für '{problem['title']}': {str(e)}", "error")
                                    batch_status_container.warning(f"Fehler beim LeetCode-Submit: {str(e)}")

                                success_count += 1
                            
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
                        
                        # Auch in das solutions Dictionary speichern
                        slug = st.session_state.current_problem['slug']
                        st.session_state.solutions[slug] = {
                            "code": code,
                            "full_response": llm_response
                        }
                        
                        log_to_terminal(f"Lösung von {full_model_name} erhalten.", "success")
                        status_container.success("Lösung generiert!")
                        
                        # Löschen des Status-Containers nach erfolgreicher Ausführung
                        status_container.empty()
                        
                        # Seite neu laden, um die Ergebnisse anzuzeigen
                        st.rerun()
                    
                    except Exception as e:
                        log_to_terminal(f"Fehler bei der LLM-Anfrage: {str(e)}", "error")
                        status_container.error(f"Fehler bei der LLM-Anfrage: {str(e)}")

        # Lösung anzeigen, wenn vorhanden
        if st.session_state.current_solution:
            st.markdown("---")
            solution_container = st.container()
            with solution_container:
                # Lösung in zwei Tabs anzeigen: "Lösung" und "LeetCode Submission"
                solution_tab, submission_tab = st.tabs(["Generierte Lösung", "LeetCode Submission"])
                
                with solution_tab:
                    # Get language from session state or default to cpp
                    display_language = st.session_state.get('submission_language', 'cpp')
                    st.code(st.session_state.current_solution["code"], language=display_language)
                
                with submission_tab:
                    # Use submission language from session state
                    show_submission_section(st.session_state.current_problem['slug'], st.session_state.current_solution["code"])
                    
                    # Zurücksetzen des Submission-Status
                    reset_button = st.button("LeetCode-Submission zurücksetzen", key="reset_submission", use_container_width=True)
                    if reset_button:
                        # Zurücksetzen des Submission-Status
                        reset_submission_state()
                        st.rerun()

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
    
    # Info-Box für verfügbare Platzhalter oberhalb des Eingabefelds
    st.info("""
    Verfügbare Platzhalter:
    - {title} - Titel des Problems
    - {question} - Beschreibung des Problems
    - {examples} - Beispieltestfälle
    """)
    
    # Prompt-Eingabefeld über die volle Breite
    prompt_text = st.text_area("Prompt-Inhalt", st.session_state.prompt_template, height=300)
    
    # Speichern-Button
    save_container = st.container()
    with save_container:
        if st.button("Template speichern", key="save_template", use_container_width=True):
            # Automatisch bereinigen, bevor es gespeichert wird
            cleaned_prompt = clean_template(prompt_text)
            if cleaned_prompt != prompt_text:
                st.warning("Ungültige Platzhalter wurden automatisch entfernt.")
                
            st.session_state.prompt_template = cleaned_prompt
            st.success("Prompt-Template aktualisiert!")
    
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
                
                # Erweiterte Fehlerinformationen für LeetCode-Submissions
                error_info = result.get("error_type", "None") if not result["success"] else "None"
                if not result["success"] and result.get("leetcode_status"):
                    error_info = f"{result.get('leetcode_status')} (LeetCode)"
                    
                # Füge zum Ergebnis hinzu
                all_results.append({
                    "Difficulty": difficulty,
                    "Title": result["title"],
                    "Slug": result["slug"],
                    "Success": "✅" if result["success"] else "❌",
                    "Error Type": error_info,
                    "Model": result.get("model", "Unknown"),
                    "Temp": result.get("temperature", "0.7"),
                    "Timestamp": result["timestamp"]
                })
        
        df = pd.DataFrame(all_results)
        
        # Anzeige der gefilterten Ergebnisse
        if len(df) > 0:
            st.dataframe(df, use_container_width=True, height=400)
            st.info(f"{len(df)} Ergebnisse gefunden.")
            
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
            st.warning("Keine Ergebnisse für die gewählten Filter gefunden.")
    else:
        st.info("Noch keine Ergebnisse verfügbar. Generiere eine Lösung im Tab 'Problem auswählen'.")
        
        # Beispielanzeige als Platzhalter
        st.markdown("### Beispiel-Ansicht")
        placeholder_data = pd.DataFrame([
            {"Difficulty": "easy", "Title": "Two Sum", "Success": "✅", "Error Type": "None", "Timestamp": "2023-05-01 12:34:56"},
            {"Difficulty": "medium", "Title": "Add Two Numbers", "Success": "❌", "Error Type": "wrong_answer_leetcode", "Timestamp": "2023-05-01 12:45:12"}
        ])
        st.dataframe(placeholder_data, use_container_width=True)
        st.caption("So werden deine Ergebnisse angezeigt, sobald du einige Probleme gelöst hast.")

# Tab 4: Problem-Logs
with tab4:
    st.header("Problem-Logs")
    
    if any(len(results) > 0 for results in st.session_state.results.values()):
        # Sammle alle Probleme über alle Schwierigkeitsgrade
        all_problems = {}
        
        for difficulty, results in st.session_state.results.items():
            for result in results:
                slug = result.get('slug', 'unknown')
                if slug not in all_problems:
                    all_problems[slug] = {
                        'title': result.get('title', 'Unbekanntes Problem'),
                        'difficulty': difficulty,
                        'results': []
                    }
                all_problems[slug]['results'].append(result)
        
        # Zeige Filteroptionen
        filter_cols = st.columns(3)
        with filter_cols[0]:
            filter_difficulty = st.selectbox(
                "Nach Schwierigkeitsgrad filtern", 
                ["Alle", "easy", "medium", "hard"],
                key="problem_logs_filter_difficulty"
            )
        
        with filter_cols[1]:
            filter_status = st.selectbox(
                "Nach Status filtern", 
                ["Alle", "Erfolgreich", "Fehlgeschlagen"],
                key="problem_logs_filter_status"
            )
        
        with filter_cols[2]:
            filter_search = st.text_input(
                "Suche (Titel oder Slug)", 
                key="problem_logs_filter_search"
            )
        
        st.markdown("---")
        
        # Gruppiere nach Schwierigkeitsgrad für die Anzeige
        problems_by_difficulty = {
            'easy': [],
            'medium': [],
            'hard': [],
            'unknown': []
        }
        
        for slug, problem_data in all_problems.items():
            difficulty = problem_data['difficulty']
            if difficulty in problems_by_difficulty:
                problems_by_difficulty[difficulty].append((slug, problem_data))
        
        # Filtere nach Schwierigkeitsgrad
        difficulties_to_show = ['easy', 'medium', 'hard', 'unknown'] if filter_difficulty == "Alle" else [filter_difficulty]
        
        for difficulty in difficulties_to_show:
            if not problems_by_difficulty[difficulty]:
                continue
                
            st.subheader(f"{difficulty.capitalize()} Probleme")
            
            for slug, problem_data in sorted(problems_by_difficulty[difficulty], key=lambda x: x[1]['title']):
                # Filtere nach Suchbegriff
                title = problem_data['title']
                if filter_search and filter_search.lower() not in title.lower() and filter_search.lower() not in slug.lower():
                    continue
                
                # Filtere nach Status
                results = problem_data['results']
                latest_result = results[-1]  # Neuestes Ergebnis
                
                if filter_status == "Erfolgreich" and not latest_result['success']:
                    continue
                if filter_status == "Fehlgeschlagen" and latest_result['success']:
                    continue
                
                # Bestimme Farbe basierend auf Status
                status_color = "green" if latest_result['success'] else "red"
                status_icon = "✅" if latest_result['success'] else "❌"
                
                # Erstelle Expander für das Problem
                with st.expander(f"{status_icon} **{title}** ({slug})"):
                    # Zeige grundlegende Probleminfos
                    st.markdown(f"**Schwierigkeitsgrad:** {difficulty.capitalize()}")
                    st.markdown(f"**LeetCode-Link:** [Problem öffnen](https://leetcode.com/problems/{slug}/)")
                    
                    # Zeige alle Submissions in Tabs
                    if len(results) > 1:
                        st.markdown(f"**{len(results)} Submissions:**")
                        submission_tabs = st.tabs([f"Submission {i+1}" for i in range(len(results))])
                        
                        for i, (tab, result) in enumerate(zip(submission_tabs, results)):
                            with tab:
                                show_result_details(result, i + 1, is_nested=True)
                    else:
                        show_result_details(results[0], is_nested=True)
    else:
        st.info("Noch keine Ergebnisse verfügbar. Generiere eine Lösung im Tab 'Problem auswählen'.")

# Tab 5: Statistiken
with tab5:
    st.header("Statistiken")
    
    if any(len(results) > 0 for results in st.session_state.results.items()):
        # Tabs für verschiedene Statistikansichten - entferne "Lokal vs. LeetCode"
        stat_tab1, stat_tab2, stat_tab3, stat_tab4 = st.tabs(["Allgemeine Statistik", "Modell-Vergleich", "Fehleranalyse nach Modell", "Heatmap"])
        
        # Tab 1: Allgemeine Statistik
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
            if not stats_df.empty and all(col in stats_df.columns for col in ["Difficulty", "Total", "Success", "Success Rate"]):
                st.dataframe(stats_df[["Difficulty", "Total", "Success", "Success Rate"]], use_container_width=True)
            else:
                # Fallback für den Fall, dass die Daten nicht die erwarteten Spalten haben
                st.dataframe(stats_df, use_container_width=True)
            
            # Visualisierung der Erfolgsrate nach Schwierigkeitsgrad
            st.subheader("Visualisierung nach Schwierigkeitsgrad")
            if len(stats_df) > 0 and "Success Rate (raw)" in stats_df.columns and "Difficulty" in stats_df.columns:
                st.bar_chart(stats_df.set_index("Difficulty")["Success Rate (raw)"], height=300)
            else:
                st.info("Nicht genügend Daten für eine Visualisierung der Erfolgsraten.")
            
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
            
            # Zeige Fehler an
            if error_types:
                st.markdown("##### Fehler bei LeetCode-Submissions")
                error_df = pd.DataFrame([
                    {"Error Type": error_type.replace("_leetcode", ""), "Count": count}
                    for error_type, count in error_types.items()
                ])
                error_df = error_df.sort_values("Count", ascending=False)
                
                # Balkendiagramm für Fehlertypen
                if not error_df.empty and "Error Type" in error_df.columns:
                    st.bar_chart(error_df.set_index("Error Type"), height=250)
                    st.dataframe(error_df, use_container_width=True)
                
                # Empfehlungen basierend auf häufigsten Fehlern
                st.subheader("Empfehlungen")
                
                # Bestimme häufigsten Fehlertyp
                top_error = None
                top_error_count = 0
                
                for error_type, count in error_types.items():
                    if count > top_error_count:
                        top_error = error_type
                        top_error_count = count
                
                if top_error:
                    if "wrong_answer" in top_error.lower():
                        st.info("💡 **Tipp**: Die häufigsten Fehler sind falsche Antworten. Achte darauf, dass deine Lösungen alle Randfälle (edge cases) behandeln.")
                    elif "performance" in top_error.lower():
                        st.info("💡 **Tipp**: Optimiere die Laufzeit und den Speicherverbrauch deiner Lösungen.")
                    elif "compile" in top_error.lower():
                        st.info("💡 **Tipp**: Überprüfe die Syntax und Bibliotheksimports für deine Submissions. Stelle sicher, dass für C++-Submissions ein 'main()' vorhanden ist, besonders für SQL-Probleme.")
                    elif "runtime" in top_error.lower():
                        st.info("💡 **Tipp**: Deine Lösungen haben Laufzeitfehler. Achte auf Speicherzugriffsfehler, Division durch Null oder ähnliche Probleme.")
                    else:
                        st.info(f"💡 **Tipp**: Analysiere die häufigsten Fehler vom Typ '{top_error.replace('_leetcode', '')}' und passe deine Lösungen entsprechend an.")
                else:
                    st.info("Fehlertypen können nicht visualisiert werden.")

                # Detaillierte Fehleranalyse für häufige Fehler
                st.subheader("Detaillierte Fehleranalyse")
                
                # Sammeln der Fehlermeldungen für jeden Fehlertyp
                error_messages = {}
                problem_types_with_errors = {}
                
                for difficulty, results in st.session_state.results.items():
                    for result in results:
                        if not result.get("success", True) and result.get("error_type"):
                            error_type = result.get("error_type")
                            
                            # Sammle Fehlermeldungen
                            if error_type not in error_messages:
                                error_messages[error_type] = []
                            
                            error_msg = result.get("error_message", "")
                            if error_msg and error_msg not in error_messages[error_type]:
                                error_messages[error_type].append(error_msg)
                            
                            # Problematische Problem-Typen identifizieren
                            problem_title = result.get("title", "")
                            problem_slug = result.get("slug", "")
                            
                            # Kategorisiere Problem-Typen (Database, Array, String, etc.)
                            problem_type = "Other"
                            if "sql" in problem_slug.lower() or "database" in problem_slug.lower() or any(db_term in problem_slug.lower() for db_term in ["query", "select", "join", "order", "employee", "customer", "table"]):
                                problem_type = "Database"
                            elif any(arr_term in problem_slug.lower() for arr_term in ["array", "list", "subarray", "matrix"]):
                                problem_type = "Array"
                            elif any(str_term in problem_slug.lower() for str_term in ["string", "word", "substring", "anagram", "palindrome"]):
                                problem_type = "String"
                            elif any(tree_term in problem_slug.lower() for tree_term in ["tree", "binary", "node", "bst"]):
                                problem_type = "Tree"
                            
                            if problem_type not in problem_types_with_errors:
                                problem_types_with_errors[problem_type] = {"count": 0, "problems": []}
                            
                            problem_types_with_errors[problem_type]["count"] += 1
                            if problem_title and problem_title not in [p["title"] for p in problem_types_with_errors[problem_type]["problems"]]:
                                problem_types_with_errors[problem_type]["problems"].append({
                                    "title": problem_title,
                                    "slug": problem_slug,
                                    "error_type": error_type
                                })
                
                # Zeige häufige Fehlermeldungen
                for error_type, messages in error_messages.items():
                    with st.expander(f"Häufige Fehlermeldungen für '{error_type.replace('_leetcode', '')}'"):
                        for msg in messages:
                            if "undefined symbol: main" in msg:
                                st.error(f"{msg}\n\n**Hinweis**: Dies tritt auf, wenn der Code keine 'main()'-Funktion enthält. Besonders für SQL-Probleme bei Verwendung von C++ als Sprache.")
                            else:
                                st.error(msg)
                
                # Problematische Problem-Typen
                if problem_types_with_errors:
                    st.subheader("Probleme nach Kategorie")
                    problem_type_data = []
                    
                    for ptype, data in problem_types_with_errors.items():
                        problem_type_data.append({
                            "Kategorie": ptype, 
                            "Fehleranzahl": data["count"]
                        })
                    
                    problem_type_df = pd.DataFrame(problem_type_data)
                    if not problem_type_df.empty:
                        st.bar_chart(problem_type_df.set_index("Kategorie"), height=250)
                    
                    # Detaillierte Liste der Probleme pro Kategorie
                    for ptype, data in problem_types_with_errors.items():
                        with st.expander(f"Probleme in Kategorie '{ptype}' ({data['count']} Fehler)"):
                            for problem in data["problems"]:
                                st.markdown(f"- **{problem['title']}** ({problem['slug']}) - Fehlertyp: {problem['error_type'].replace('_leetcode', '')}")
                
                # Spezielle Tipps für SQL/Database-Probleme wenn vorhanden
                if "Database" in problem_types_with_errors:
                    st.warning("""
                    **Tipp für Database/SQL-Probleme:**
                    
                    Bei SQL-Problemen und C++ Submissions sollte der Code eine main()-Funktion enthalten:
                    ```cpp
                    #include <iostream>
                    using namespace std;
                    
                    // SQL Query als Kommentar angeben
                    // SELECT column FROM table WHERE condition;
                    
                    int main() {
                        cout << "SQL Query ausgeführt" << endl;
                        return 0;
                    }
                    ```
                    Oder besser: Wähle SQL als Sprache für Database-Probleme statt C++.
                    """)
                    
                    # Zeige eine Liste der SQL-Probleme mit Fehlern an
                    st.subheader("SQL/Database Probleme mit Fehlern")
                    
                    sql_errors = []
                    for difficulty, results in st.session_state.results.items():
                        for result in results:
                            if (not result.get("success", True) and 
                                result.get("is_sql_problem", False)):
                                sql_errors.append(result)
                    
                    if sql_errors:
                        # Erstelle eine Tabelle mit SQL-Problemen und ihren Fehlern
                        sql_error_data = []
                        for error in sql_errors:
                            sql_error_data.append({
                                "Problem": error.get("title", "Unbekannt"),
                                "Slug": error.get("slug", "unknown"),
                                "Fehlertyp": error.get("error_type", "unknown").replace("_leetcode", ""),
                                "Fehlermeldung": error.get("error_message", "Keine Meldung verfügbar")
                            })
                        
                        # Zeige die Tabelle an
                        sql_error_df = pd.DataFrame(sql_error_data)
                        st.dataframe(sql_error_df, use_container_width=True)
                        
                        # Vorschlag für korrekte SQL-Lösung
                        with st.expander("Beispiel für korrekte SQL-Lösung in C++"):
                            st.code("""
#include <iostream>
using namespace std;

// Beispiel: employees-earning-more-than-their-managers
/*
SELECT e1.name as Employee
FROM Employee e1, Employee e2
WHERE e1.managerId = e2.id AND e1.salary > e2.salary;
*/

int main() {
    cout << "SQL-Query wird ausgeführt..." << endl;
    return 0;
}
                            """, language="cpp")
                        
                        # Vorschlag für direkte SQL-Lösung
                        with st.expander("Direkte SQL-Lösung (empfohlen)"):
                            st.markdown("""
Um SQL-Probleme zu lösen, ist es am besten, SQL als Sprache zu wählen statt C++.
Das würde bedeuten, dass du einfach nur die SQL-Abfrage ohne C++-Boilerplate schreiben müsstest.

**Beispiel für ein SQL-Problem:**

```sql
-- Beispiel: employees-earning-more-than-their-managers
SELECT e1.name as Employee
FROM Employee e1, Employee e2
WHERE e1.managerId = e2.id AND e1.salary > e2.salary;
```

Um die Sprache zu ändern, müsstest du im Code des Tools:
1. Die Sprache auf 'mysql' statt 'cpp' setzen
2. Sicherstellen, dass SQL-Syntax korrekt formatiert ist
                            """)

            if not error_types:
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
                if not model_compare_df.empty and all(col in model_compare_df.columns for col in [
                    "Model", "Total Problems", "Success Rate", 
                    "Easy Success Rate", "Medium Success Rate", "Hard Success Rate"
                ]):
                    st.dataframe(model_compare_df[[
                        "Model", "Total Problems", "Success Rate", 
                        "Easy Success Rate", "Medium Success Rate", "Hard Success Rate"
                    ]], use_container_width=True)
                else:
                    st.dataframe(model_compare_df, use_container_width=True)
                
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
                    if not chart_data.empty:
                        st.bar_chart(chart_data, height=400)
                    else:
                        st.info("Nicht genügend Daten für eine Visualisierung nach Schwierigkeitsgrad.")
                    
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
        
        # Tab 4: Heatmap 
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