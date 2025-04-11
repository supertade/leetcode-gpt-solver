import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
from io import BytesIO

def prepare_model_error_data(session_state_results):
    """
    Bereitet die Daten aus der Session für die Heatmap vor.
    
    Args:
        session_state_results: Das results-Dictionary aus der Streamlit-Session
        
    Returns:
        DataFrame: Eine Pandas DataFrame mit den Fehlerraten je Modell und Fehlertyp
        oder None, wenn nicht genügend Daten verfügbar sind
    """
    # Alle Modelle und Fehlertypen sammeln
    all_models = set()
    all_error_types = set()
    
    for difficulty, results in session_state_results.items():
        for result in results:
            model = result.get("model", "unknown")
            all_models.add(model)
            
            if not result.get("success", True) and result.get("error_type"):
                all_error_types.add(result.get("error_type"))
    
    if not all_models or not all_error_types:
        return None
    
    # Fehlerstatistik nach Modell erstellen
    model_error_stats = {}
    for model in all_models:
        model_error_stats[model] = {"total": 0}
        for error_type in all_error_types:
            model_error_stats[model][error_type] = 0
    
    # Daten sammeln
    for difficulty, results in session_state_results.items():
        for result in results:
            model = result.get("model", "unknown")
            if model in model_error_stats:
                model_error_stats[model]["total"] += 1
                
                if not result.get("success", True) and result.get("error_type") in all_error_types:
                    model_error_stats[model][result.get("error_type")] += 1
    
    # Daten für die Heatmap aufbereiten
    model_error_data = []
    for model, stats in model_error_stats.items():
        model_row = {"Model": model}
        
        for error_type in all_error_types:
            error_count = stats.get(error_type, 0)
            error_rate = (error_count / stats["total"] * 100) if stats["total"] > 0 else 0
            model_row[error_type] = error_rate
        
        model_error_data.append(model_row)
    
    return pd.DataFrame(model_error_data).set_index("Model")

def generate_heatmap(df, title="Fehlerraten nach Modell und Fehlertyp (%)", cmap="YlOrRd", figsize=(12, 8)):
    """
    Generiert eine Heatmap für die Fehlerraten verschiedener Modelle.
    
    Args:
        df: DataFrame mit den Fehlerraten (Modelle als Index, Fehlertypen als Spalten)
        title: Titel der Heatmap
        cmap: Farbschema für die Heatmap
        figsize: Größe der Abbildung als Tuple (Breite, Höhe)
        
    Returns:
        BytesIO: Ein Bildobjekt im PNG-Format
    """
    # Erstelle die Abbildung
    fig, ax = plt.subplots(figsize=figsize)
    
    # Generiere die Heatmap
    sns.heatmap(df, annot=True, fmt=".1f", cmap=cmap, ax=ax, 
                linewidths=0.5, cbar_kws={'label': 'Fehlerrate in %'})
    
    # Formatiere die Abbildung
    plt.title(title, fontsize=16)
    plt.ylabel("Modell", fontsize=12)
    plt.xlabel("Fehlertyp", fontsize=12)
    
    # Rotiere die X-Achsenbeschriftungen für bessere Lesbarkeit
    plt.xticks(rotation=45, ha='right')
    
    # Sorge für ausreichenden Abstand
    plt.tight_layout()
    
    # Konvertiere die Abbildung in ein Byte-Objekt
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    return buf

def display_model_error_heatmap(session_state_results):
    """
    Bereitet die Daten vor und zeigt die Heatmap an.
    
    Args:
        session_state_results: Das results-Dictionary aus der Streamlit-Session
    
    Returns:
        bool: True wenn die Heatmap angezeigt wurde, False wenn nicht genügend Daten verfügbar waren
    """
    # Daten vorbereiten
    heatmap_data = prepare_model_error_data(session_state_results)
    
    if heatmap_data is None or heatmap_data.empty:
        st.info("Nicht genügend Daten für eine Fehleranalyse-Heatmap. Generiere zuerst mehr Lösungen mit verschiedenen Modellen.")
        return False
    
    # Überprüfen, ob wir mindestens 2 Modelle und 2 Fehlertypen haben
    if len(heatmap_data.index) < 2 or len(heatmap_data.columns) < 2:
        st.info("Nicht genügend unterschiedliche Modelle oder Fehlertypen für eine aussagekräftige Heatmap.")
        return False
    
    # Heatmap generieren
    heatmap_img = generate_heatmap(heatmap_data)
    
    # Heatmap anzeigen
    st.subheader("Heatmap: Fehlerraten nach Modell und Fehlertyp")
    st.image(heatmap_img, use_container_width=True)
    
    # Einige Beobachtungen hinzufügen
    st.markdown("#### Beobachtungen")
    
    # Modell mit der niedrigsten durchschnittlichen Fehlerrate finden
    mean_errors = heatmap_data.mean(axis=1).sort_values()
    best_model = mean_errors.index[0]
    best_rate = mean_errors.iloc[0]
    
    st.success(f"📊 **Bestes Gesamtmodell:** {best_model} mit einer durchschnittlichen Fehlerrate von {best_rate:.1f}%")
    
    # Höchste Fehlerrate finden
    max_error_value = heatmap_data.max().max()
    max_error_model = None
    max_error_type = None
    
    for model in heatmap_data.index:
        for error_type in heatmap_data.columns:
            if heatmap_data.loc[model, error_type] == max_error_value:
                max_error_model = model
                max_error_type = error_type
                break
    
    if max_error_model and max_error_type:
        st.warning(f"⚠️ **Höchste Fehlerrate:** {max_error_value:.1f}% bei Modell {max_error_model} für Fehlertyp '{max_error_type}'")
    
    return True

def add_heatmap_tab(tab):
    """
    Fügt einen neuen Tab für die Heatmap-Visualisierung hinzu.
    
    Args:
        tab: Das Streamlit-Tab-Objekt, in dem die Heatmap angezeigt werden soll
    """
    with tab:
        st.subheader("Heatmap-Fehleranalyse")
        
        st.markdown("""
        Diese Visualisierung zeigt einen direkten Vergleich der Fehlerraten verschiedener Modelle 
        für jeden Fehlertyp in Form einer Heatmap. Je dunkler die Farbe, desto höher die Fehlerrate.
        """)
        
        if not any(len(results) > 0 for results in st.session_state.results.values()):
            st.info("Noch keine Ergebnisse verfügbar für die Heatmap. Löse einige Probleme mit verschiedenen Modellen, um hier eine Heatmap zu sehen.")
            
            # Beispielvisualisierung als Platzhalter
            st.markdown("### Beispiel-Heatmap")
            
            # Beispieldaten für Platzhalter-Heatmap
            example_data = pd.DataFrame([
                {"Model": "codellama", "syntax_error": 12.5, "undefined_reference": 8.3, "compilation_error": 4.2},
                {"Model": "llama3", "syntax_error": 8.2, "undefined_reference": 15.7, "compilation_error": 5.1},
                {"Model": "claude", "syntax_error": 5.3, "undefined_reference": 3.9, "compilation_error": 2.8}
            ]).set_index("Model")
            
            # Generiere Beispiel-Heatmap
            example_heatmap = generate_heatmap(example_data, title="Beispiel: Fehlerraten nach Modell und Fehlertyp (%)")
            st.image(example_heatmap, use_container_width=True)
            
            st.caption("So wird deine Heatmap aussehen, sobald du Probleme mit verschiedenen Modellen gelöst hast.")
        else:
            # Zeige die echte Heatmap an
            display_model_error_heatmap(st.session_state.results) 