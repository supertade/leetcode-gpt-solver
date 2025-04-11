import requests
import random
import time
from typing import Dict, List, Any, Optional

# Zuvor wurde ein lokaler Server verwendet, jetzt nutzen wir direkt die LeetCode API
# BASE_URL = "http://localhost:3000"

# Rate-Limiting für die LeetCode API
# Mindestzeit zwischen Anfragen in Sekunden
MIN_REQUEST_INTERVAL = 1.0
last_request_time = 0

def _rate_limit():
    """Implementiert ein einfaches Rate-Limiting für API-Anfragen"""
    global last_request_time
    current_time = time.time()
    elapsed = current_time - last_request_time
    
    # Wenn die letzte Anfrage weniger als MIN_REQUEST_INTERVAL Sekunden her ist, warte
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - elapsed
        time.sleep(sleep_time)
    
    # Aktualisiere die Zeit der letzten Anfrage
    last_request_time = time.time()

def make_leetcode_request(url: str, data: Dict, max_retries: int = 3, retry_delay: float = 2.0) -> Optional[Dict]:
    """
    Führt eine Anfrage an die LeetCode API mit Rate-Limiting und Wiederholungslogik aus
    
    Args:
        url: Die URL für die Anfrage
        data: Die JSON-Daten für die Anfrage
        max_retries: Maximale Anzahl von Wiederholungsversuchen
        retry_delay: Verzögerung zwischen Wiederholungsversuchen in Sekunden
        
    Returns:
        Dict oder None: Die JSON-Antwort oder None bei Fehler
    """
    # User-Agent hinzufügen, um die Anfrage legitimer erscheinen zu lassen
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Referer": "https://leetcode.com/problemset/all/"
    }
    
    for attempt in range(max_retries):
        try:
            # Rate-Limiting anwenden
            _rate_limit()
            
            # API-Anfrage senden
            response = requests.post(url, json=data, headers=headers)
            
            # Erfolgreiche Antwort
            if response.status_code == 200:
                return response.json()
            
            # Bei bestimmten Fehlern (z.B. 429 Too Many Requests) oder Serverproblemen (5xx) erneut versuchen
            if response.status_code in [429, 500, 502, 503, 504]:
                wait_time = retry_delay * (attempt + 1)  # Exponentielle Verzögerung
                print(f"API-Anfrage fehlgeschlagen (Statuscode {response.status_code}). Wiederhole in {wait_time:.1f} Sekunden...")
                time.sleep(wait_time)
                continue
            
            # Bei anderen Fehlern aufgeben
            print(f"API-Anfrage fehlgeschlagen mit Statuscode {response.status_code}: {response.text[:200]}...")
            return None
            
        except Exception as e:
            print(f"Fehler bei der API-Anfrage (Versuch {attempt+1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return None
    
    return None

def fetch_problems(difficulty: str, limit: int = 50, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Ruft Probleme von LeetCode ab und filtert sie nach Schwierigkeitsgrad.
    Optional kann ein Suchbegriff für das Filtern nach Titeln verwendet werden.
    
    Args:
        difficulty (str): Der Schwierigkeitsgrad ('easy', 'medium', 'hard')
        limit (int): Die maximale Anzahl der abzurufenden Probleme
        search_term (str, optional): Suchbegriff, um nach Titeln zu filtern
        
    Returns:
        list: Eine Liste von Problem-Dictionaries mit 'title' und 'titleSlug'
    """
    # GraphQL Query für die LeetCode API
    query = """
    query problemsetQuestionListV2($categorySlug: String, $limit: Int, $skip: Int) {
        problemsetQuestionListV2(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
        ) {
            questions {
                title
                titleSlug
                difficulty
            }
        }
    }
    """
    
    # Variablen für die Query
    variables = {
        "categorySlug": "",
        "skip": 0,
        "limit": limit * 3  # Request more problems since we'll filter locally
    }
    
    data = {"query": query, "variables": variables}
    result = make_leetcode_request("https://leetcode.com/graphql", data)
    
    if result is None:
        print("Keine Antwort von der LeetCode API erhalten")
        return []
    
    if "data" in result and "problemsetQuestionListV2" in result["data"] and "questions" in result["data"]["problemsetQuestionListV2"]:
        all_problems = result["data"]["problemsetQuestionListV2"]["questions"]
        
        # Filter by difficulty locally
        problems = [p for p in all_problems if p.get("difficulty", "").lower() == difficulty.lower()]
        
        # Limit to requested number
        problems = problems[:limit]
        
        # Optional: Filtern nach Suchbegriff, wenn angegeben
        if search_term and search_term.strip():
            search_term = search_term.lower()
            filtered_problems = [
                p for p in problems 
                if search_term in p["title"].lower() or search_term in p["titleSlug"].lower()
            ]
            return filtered_problems
        
        return problems
    else:
        print(f"Unerwartetes Antwortformat von der LeetCode API: {result}")
        return []

def fetch_full_problem(slug: str) -> Dict[str, Any]:
    """
    Ruft die vollständigen Details zu einem LeetCode-Problem anhand seines Slugs ab.
    
    Args:
        slug (str): Der titleSlug des Problems
        
    Returns:
        dict: Ein Dictionary mit den Problem-Details oder leeres Dictionary bei Fehler
    """
    query = """
    query getQuestionDetail($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        content
        exampleTestcases
      }
    }
    """
    
    data = {
        "query": query,
        "variables": {"titleSlug": slug}
    }
    
    result = make_leetcode_request("https://leetcode.com/graphql", data)
    
    if result is None:
        print(f"Keine Antwort von der LeetCode API für Problem {slug}")
        return {"content": "", "exampleTestcases": ""}
    
    if "data" in result and "question" in result["data"]:
        return result["data"]["question"]
    else:
        print(f"Unerwartetes Antwortformat für Problem {slug}: {result}")
        return {"content": "", "exampleTestcases": ""}