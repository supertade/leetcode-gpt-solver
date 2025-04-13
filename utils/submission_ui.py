import streamlit as st
import time
from typing import Dict, Any, Optional
import pandas as pd
from api.leetcode_submit import submit_and_wait_for_result


def show_submission_section(problem_slug: str, code: str, language: str = "cpp"):
    """
    Display a section for submitting solutions to LeetCode and showing results.
    
    Args:
        problem_slug: The LeetCode problem slug
        code: The solution code
        language: The programming language (default: "cpp")
    """
    # Create a container for the submission section
    with st.container():
        # Cleaner header layout with smaller font 
        st.markdown("<h3 style='font-size: 1.3rem; margin-bottom: 1rem;'>LeetCode Submission</h3>", unsafe_allow_html=True)
        
        # Determine language based on problem type (in the background)
        is_db_problem = is_database_problem(problem_slug, "Unknown Title")
        
        # Set default language based on problem type
        if is_db_problem:
            if 'submission_language' not in st.session_state:
                st.session_state.submission_language = "mysql"  # Default für SQL-Probleme
        else:
            if 'submission_language' not in st.session_state:
                st.session_state.submission_language = "cpp"  # Default für normale Probleme
        
        # Submission controls row
        col1, col2 = st.columns([3, 1])
        
        with col1:
            submit_button = st.button("Submit to LeetCode", type="primary", key="submit_leetcode", use_container_width=True)
        
        with col2:
            if 'submission_status' not in st.session_state:
                st.session_state.submission_status = None
            
            status = st.session_state.submission_status or "ready"
            status_config = {
                "success": {"color": "#478559", "icon": "✓", "text": "Submitted"},
                "error": {"color": "#d76767", "icon": "✗", "text": "Failed"},
                "pending": {"color": "#e2b33a", "icon": "⋯", "text": "Pending"},
                "ready": {"color": "#6c757d", "icon": "▶", "text": "Ready"}
            }
            
            current_status = status_config[status]
            
            st.markdown(f"""
            <div style="height:38px; border-radius:4px; display:flex; align-items:center; justify-content:center; background-color: {current_status['color']}; color: white;">
                <span>{current_status['icon']} {current_status['text']}</span>
            </div>
            """, unsafe_allow_html=True)
        
        # Initialize submission result in session state if it doesn't exist
        if 'submission_result' not in st.session_state:
            st.session_state.submission_result = None
        
        # Previous results for comparison
        if 'previous_results' not in st.session_state:
            st.session_state.previous_results = []
        
        # Handle submission when button is clicked
        if submit_button:
            with st.spinner("Submitting to LeetCode..."):
                st.session_state.submission_status = "pending"
                
                # Use selected language instead of default
                active_language = st.session_state.submission_language
                
                # Submit the solution and wait for result
                result = submit_and_wait_for_result(problem_slug, code, active_language)
                
                if result["success"] and "status_code" in result:
                    # Save previous result for comparison if we have a current result
                    if st.session_state.submission_result and st.session_state.submission_result.get("success", False):
                        st.session_state.previous_results.append(st.session_state.submission_result)
                        # Keep only the last 3 previous results
                        if len(st.session_state.previous_results) > 3:
                            st.session_state.previous_results.pop(0)
                    
                    st.session_state.submission_status = "success"
                    st.session_state.submission_result = result
                    
                    # Add result to global statistics
                    save_leetcode_result_to_stats(result, problem_slug)
                else:
                    st.session_state.submission_status = "error"
                    st.session_state.submission_result = result
                    
                    # Also save failed submissions to statistics
                    if "error" in result:
                        save_leetcode_result_to_stats(result, problem_slug, success=False)
                
                # Rerun to update UI
                st.rerun()
        
        # Subtle divider
        st.markdown("<hr style='margin: 1rem 0; border-color: #e0e6ed; border-style: solid; opacity: 0.5;'>", unsafe_allow_html=True)
        
        # Show submission result if available
        if st.session_state.submission_result:
            show_submission_result(st.session_state.submission_result, st.session_state.previous_results)


def is_database_problem(problem_slug: str, title: str) -> bool:
    """
    Determines if a problem is likely a database/SQL problem based on slug and title.
    
    Args:
        problem_slug: The LeetCode problem slug
        title: The problem title
        
    Returns:
        Boolean indicating if it's a database problem
    """
    # List of keywords that suggest a database problem
    db_keywords = [
        "sql", "database", "query", "select", "join", "order by", "group by", 
        "employee", "customer", "department", "table", "clause", "having",
        "delete", "update", "insert", "distinct", "aggregate", "null"
    ]
    
    # Common database problem slugs on LeetCode
    known_db_slugs = [
        "employees-earning-more-than-their-managers",
        "duplicate-emails", 
        "customers-who-never-order",
        "combine-two-tables",
        "second-highest-salary",
        "nth-highest-salary",
        "rank-scores",
        "department-highest-salary",
        "department-top-three-salaries",
        "consecutive-numbers",
        "rising-temperature"
    ]
    
    # Check if the slug is a known database problem
    if problem_slug in known_db_slugs:
        return True
    
    # Check if slug or title contains database keywords
    slug_and_title = (problem_slug + " " + title).lower()
    for keyword in db_keywords:
        if keyword in slug_and_title:
            return True
    
    return False


def save_leetcode_result_to_stats(result, problem_slug, success=None):
    """
    Save LeetCode submission result to the global statistics.
    
    Args:
        result: The submission result dictionary
        problem_slug: The LeetCode problem slug
        success: Override success flag (for error cases)
    """
    if 'current_problem' not in st.session_state or not st.session_state.current_problem:
        return
    
    if 'results' not in st.session_state:
        return
    
    # Extract relevant data
    difficulty = st.session_state.current_problem.get('difficulty', 'unknown')
    title = st.session_state.current_problem.get('title', 'Unknown Problem')
    
    # Ensure difficulty is valid (easy, medium, hard)
    if difficulty not in ['easy', 'medium', 'hard']:
        difficulty = 'unknown'
        # Try to infer from the problem title or slug
        if 'easy' in problem_slug.lower() or 'easy' in title.lower():
            difficulty = 'easy'
        elif 'medium' in problem_slug.lower() or 'medium' in title.lower():
            difficulty = 'medium'
        elif 'hard' in problem_slug.lower() or 'hard' in title.lower():
            difficulty = 'hard'
    
    # Determine if the submission was successful
    is_success = success
    if is_success is None:
        is_success = (result.get("status_code", 0) == 10)  # Status code 10 is Accepted in LeetCode
    
    # Get error type if applicable
    error_type = None
    if not is_success:
        status_code = result.get("status_code", 0)
        if status_code == 11:
            error_type = "wrong_answer_leetcode"
        elif status_code == 20:
            error_type = "compile_error_leetcode"
        elif status_code in [12, 13, 14]:
            error_type = "performance_error_leetcode"
        elif status_code == 15:
            error_type = "runtime_error_leetcode"
        else:
            error_type = "unknown_error_leetcode"
    
    # Get error message
    error_message = None
    if error_type == "compile_error_leetcode" and is_database_problem(problem_slug, title):
        error_message = "SQL problem submitted as C++ but missing main() function"
    elif error_type == "wrong_answer_leetcode":
        error_message = f"Expected: {result.get('expected_output', 'N/A')[:100]}..., Got: {result.get('code_output', 'N/A')[:100]}..."
    elif error_type == "runtime_error_leetcode":
        error_message = result.get("runtime_error", "N/A")
    elif error_type == "performance_error_leetcode":
        error_message = result.get("error", "N/A")
    elif error_type == "unknown_error_leetcode":
        error_message = result.get("error", "N/A")
    
    # Create result entry for statistics
    from datetime import datetime
    
    # Get the solution code and model information
    code = None
    model = None
    temperature = None
    
    if st.session_state.current_solution and "code" in st.session_state.current_solution:
        code = st.session_state.current_solution["code"]
    
    # Get model and temperature from sidebar if available
    from streamlit import session_state
    if 'model' in session_state:
        model = session_state.get('model', 'Unknown')
        if 'model_version' in session_state and session_state.model_version:
            model = f"{model}:{session_state.model_version}"
    
    if 'temperature' in session_state:
        temperature = session_state.get('temperature', 0.7)
    
    # Extrahiere detaillierte Fehlerinformationen
    full_compile_error = result.get("full_compile_error", None)
    compile_error = result.get("compile_error", None)
    runtime_error = result.get("runtime_error", None)
    wrong_answer_details = None
    
    # Für Wrong Answer, extrahiere erwartete und tatsächliche Ausgabe
    if error_type == "wrong_answer_leetcode":
        expected_output = result.get("expected_output", None)
        actual_output = result.get("code_output", None)
        if expected_output and actual_output:
            wrong_answer_details = {
                "expected": expected_output,
                "actual": actual_output,
                "last_testcase": result.get("last_testcase", None)
            }
    
    # Identifiziere, ob es sich um ein SQL-Problem handelt
    is_sql_problem = is_database_problem(problem_slug, title)
    
    # Bei Compile-Fehlern für SQL-Probleme, spezifischen Fehlertyp vergeben
    if error_type == "compile_error_leetcode" and is_sql_problem:
        if full_compile_error and "undefined symbol: main" in full_compile_error:
            error_type = "sql_missing_main_error"
            compile_error = "SQL problem submitted as C++ but missing main() function"
    
    # Füge den error_message String hinzu, der in der UI angezeigt wird
    if error_message:
        error_message = f"Error: {error_message}"
    
    result_entry = {
        "slug": problem_slug,
        "title": title,
        "success": is_success,
        "error_type": error_type,
        "error_message": error_message,  # Neu: error_message für UI
        "is_sql_problem": is_sql_problem,  # Neu: ist es ein SQL-Problem?
        "solution": code,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "submission_type": "leetcode_api",  # Mark as LeetCode submission
        "runtime_ms": result.get("runtime_ms"),
        "memory_mb": result.get("memory_percentile"),
        "leetcode_status": result.get("status_description", result.get("result", "Unknown")),
        "model": model,
        "temperature": temperature,
        # Detaillierte Fehlerinformationen
        "full_compile_error": full_compile_error,
        "compile_error": compile_error,
        "runtime_error": runtime_error,
        "wrong_answer_details": wrong_answer_details,
        "raw_result": {k: v for k, v in result.items() if k not in ["details"]}  # Speichere das Rohergebnis ohne zu große Daten
    }
    
    # Add to statistics if difficulty is valid
    if difficulty in st.session_state.results:
        # Check if this is a duplicate submission
        for idx, existing_entry in enumerate(st.session_state.results[difficulty]):
            if (existing_entry.get('slug') == problem_slug and 
                existing_entry.get('model') == model and
                existing_entry.get('solution') == code):
                # Update existing entry instead of adding a new one
                st.session_state.results[difficulty][idx] = result_entry
                return
        
        # If not a duplicate, add as new entry
        st.session_state.results[difficulty].append(result_entry)


def show_submission_result(result: Dict[str, Any], previous_results: list = None):
    """
    Show the LeetCode submission result in a visual format.
    
    Args:
        result: The submission result dictionary
        previous_results: List of previous submission results for comparison
    """
    if not previous_results:
        previous_results = []
    
    # Display error if the submission was not successful
    if not result["success"]:
        st.error(f"Submission Error: {result.get('error', 'Unknown error')}")
        if "response" in result:
            with st.expander("Error Details"):
                st.json(result["response"])
        return
    
    # Get status information
    status = result.get("status_description", result.get("result", "Unknown"))
    
    # Map status to color for the badge
    status_colors = {
        "Accepted": "#4caf50",
        "Wrong Answer": "#f44336",
        "Time Limit Exceeded": "#ff9800",
        "Compile Error": "#f44336",
        "Runtime Error": "#f44336"
    }
    status_color = status_colors.get(status, "#757575")
    
    # Get metrics with safe extraction
    runtime = result.get("runtime_ms")
    memory = result.get("memory_percentile")
    total = result.get("total_testcases")
    passed = result.get("passed_testcases")
    
    # Calculate success rate
    success_rate = 100 * (passed / total) if passed is not None and total is not None and total > 0 else 0
    
    # Find previous result for comparison
    prev_result = None
    if previous_results:
        prev_result = previous_results[-1]
    
    # Simple clean header with status badge
    st.markdown(f"""
    <div style="display: flex; align-items: center; margin-bottom: 1rem;">
        <h3 style="font-size: 1.2rem; margin: 0; font-weight: 500;">Submission Result:</h3>
        <span style="margin-left: 10px; background-color: {status_color}; color: white; 
                    padding: 3px 8px; border-radius: 4px; font-size: 0.85rem; font-weight: 500;">
            {status}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    # Create metric cards using native Streamlit components in rows for cleaner look
    col1, col2, col3 = st.columns(3)
    
    # Determine delta values for comparison with previous results
    runtime_delta = None
    if prev_result and runtime is not None and prev_result.get("runtime_ms") is not None:
        runtime_delta = runtime - prev_result.get("runtime_ms")
        
    memory_delta = None
    if prev_result and memory is not None and prev_result.get("memory_percentile") is not None:
        memory_delta = memory - prev_result.get("memory_percentile")
    
    # Show metrics with deltas where available
    with col1:
        st.metric(
            "Runtime", 
            f"{runtime} ms" if runtime is not None else "N/A",
            delta=f"{runtime_delta:+.2f} ms" if runtime_delta is not None else None,
            delta_color="inverse"
        )
    
    with col2:
        st.metric(
            "Memory", 
            f"{memory} MB" if memory is not None else "N/A",
            delta=f"{memory_delta:+.2f} MB" if memory_delta is not None else None,
            delta_color="inverse"
        )
    
    with col3:
        tests_str = f"{passed}/{total}" if passed is not None and total is not None else "N/A"
        st.metric("Test Cases", tests_str, f"{success_rate:.0f}%" if success_rate > 0 else None)
    
    # Full details in a clean expander
    with st.expander("View Details", expanded=False):
        # Two-column layout
        left_col, right_col = st.columns([1, 1])
        
        with left_col:
            st.markdown("##### Submission Summary")
            st.markdown(f"**Status:** {status}")
            st.markdown(f"**Language:** {result.get('language', 'cpp')}")
            st.markdown(f"**Runtime:** {runtime} ms" if runtime is not None else "**Runtime:** N/A")
            st.markdown(f"**Memory:** {memory} MB" if memory is not None else "**Memory:** N/A")
        
        with right_col:
            st.markdown("##### Test Results")
            st.markdown(f"**Total Cases:** {total}" if total is not None else "**Total Cases:** N/A")
            st.markdown(f"**Passed Cases:** {passed}" if passed is not None else "**Passed Cases:** N/A")
            st.markdown(f"**Success Rate:** {success_rate:.1f}%" if success_rate > 0 else "**Success Rate:** N/A")
        
        # Show previous submissions if available
        if previous_results:
            st.markdown("<hr style='margin: 1rem 0;'>", unsafe_allow_html=True)
            st.markdown("##### Previous Submissions")
            
            for i, prev in enumerate(reversed(previous_results)):
                prev_status = prev.get("status_description", prev.get("result", "Unknown"))
                prev_runtime = prev.get("runtime_ms")
                prev_memory = prev.get("memory_percentile")
                
                # Create a bordered container
                with st.container(border=True):
                    # Show previous submission with compact layout
                    col1, col2, col3 = st.columns([3, 2, 2])
                    with col1:
                        prev_color = status_colors.get(prev_status, "#757575")
                        st.markdown(f"""
                        <span style="color: white; background-color: {prev_color}; 
                                 padding: 2px 6px; border-radius: 3px; font-size: 0.8rem;">
                            {prev_status}
                        </span>
                        """, unsafe_allow_html=True)
                    with col2:
                        st.markdown(f"Runtime: **{prev_runtime} ms**" if prev_runtime is not None else "Runtime: N/A")
                    with col3:
                        st.markdown(f"Memory: **{prev_memory} MB**" if prev_memory is not None else "Memory: N/A")
        
        # Show raw data only if requested - keep UI clean
        st.markdown("<hr style='margin: 1rem 0;'>", unsafe_allow_html=True)
        if st.checkbox("Show Technical Details", key="show_technical_details"):
            # Remove verbose details from display
            display_result = result.copy()
            if "details" in display_result:
                del display_result["details"]
            st.json(display_result)


def reset_submission_state():
    """Reset the submission state in the session."""
    if 'submission_status' in st.session_state:
        st.session_state.submission_status = "ready"
    if 'submission_result' in st.session_state:
        st.session_state.submission_result = None


def submit_to_leetcode(problem_slug: str, code: str, language: str = "cpp") -> Dict[str, Any]:
    """
    Submit solution to LeetCode and return the result.
    Also save the result to statistics.
    
    Args:
        problem_slug: The LeetCode problem slug
        code: The solution code
        language: The programming language (default: "cpp")
        
    Returns:
        Dictionary with submission result
    """
    # Submit the solution and wait for result
    result = submit_and_wait_for_result(problem_slug, code, language)
    
    # Initialize or update problem information
    if 'active_problems' in st.session_state and problem_slug in st.session_state.active_problems:
        # Use the active problem info
        problem_info = st.session_state.active_problems[problem_slug]
        difficulty = problem_info.get('difficulty', 'unknown')
        title = problem_info.get('title', 'Unknown Problem')
    else:
        # Try to get information from current problem
        if 'current_problem' in st.session_state and st.session_state.current_problem:
            difficulty = st.session_state.current_problem.get('difficulty', 'unknown') 
            title = st.session_state.current_problem.get('title', 'Unknown Problem')
        else:
            # No problem information available
            difficulty = 'unknown'
            title = 'Unknown Problem'
    
    # Check if the submission was successful
    is_success = (result.get("status_code", 0) == 10)  # Status code 10 is Accepted in LeetCode
    
    # Get error type if applicable
    error_type = None
    if not is_success:
        status_code = result.get("status_code", 0)
        if status_code == 11:
            error_type = "wrong_answer_leetcode"
        elif status_code == 20:
            error_type = "compile_error_leetcode"
        elif status_code in [12, 13, 14]:
            error_type = "performance_error_leetcode"
        elif status_code == 15:
            error_type = "runtime_error_leetcode"
        else:
            error_type = "unknown_error_leetcode"
    
    # Create result entry for statistics
    from datetime import datetime
    
    # Get model and temperature from sidebar if available
    from streamlit import session_state
    model = session_state.get('model', 'Unknown')
    if 'model_version' in session_state and session_state.model_version:
        model = f"{model}:{session_state.model_version}"
    
    temperature = session_state.get('temperature', 0.7)
    
    # Extrahiere detaillierte Fehlerinformationen
    full_compile_error = result.get("full_compile_error", None)
    compile_error = result.get("compile_error", None)
    runtime_error = result.get("runtime_error", None)
    wrong_answer_details = None
    
    # Für Wrong Answer, extrahiere erwartete und tatsächliche Ausgabe
    if error_type == "wrong_answer_leetcode":
        expected_output = result.get("expected_output", None)
        actual_output = result.get("code_output", None)
        if expected_output and actual_output:
            wrong_answer_details = {
                "expected": expected_output,
                "actual": actual_output,
                "last_testcase": result.get("last_testcase", None)
            }
    
    # Identifiziere, ob es sich um ein SQL-Problem handelt
    is_sql_problem = is_database_problem(problem_slug, title)
    
    # Bei Compile-Fehlern für SQL-Probleme, spezifischen Fehlertyp vergeben
    if error_type == "compile_error_leetcode" and is_sql_problem:
        if full_compile_error and "undefined symbol: main" in full_compile_error:
            error_type = "sql_missing_main_error"
            compile_error = "SQL problem submitted as C++ but missing main() function"
    
    # Füge den error_message String hinzu, der in der UI angezeigt wird
    error_message = None
    if compile_error:
        error_message = compile_error
    elif full_compile_error:
        error_message = full_compile_error
    elif runtime_error:
        error_message = runtime_error
    elif wrong_answer_details:
        error_message = f"Expected: {wrong_answer_details['expected'][:100]}..., Got: {wrong_answer_details['actual'][:100]}..."
    
    result_entry = {
        "slug": problem_slug,
        "title": title,
        "success": is_success,
        "error_type": error_type,
        "error_message": error_message,  # Neu: error_message für UI
        "is_sql_problem": is_sql_problem,  # Neu: ist es ein SQL-Problem?
        "solution": code,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "submission_type": "leetcode_api",  # Mark as LeetCode submission
        "runtime_ms": result.get("runtime_ms"),
        "memory_mb": result.get("memory_percentile"),
        "leetcode_status": result.get("status_description", result.get("result", "Unknown")),
        "model": model,
        "temperature": temperature,
        # Detaillierte Fehlerinformationen
        "full_compile_error": full_compile_error,
        "compile_error": compile_error,
        "runtime_error": runtime_error,
        "wrong_answer_details": wrong_answer_details,
        "raw_result": {k: v for k, v in result.items() if k not in ["details"]}  # Speichere das Rohergebnis ohne zu große Daten
    }
    
    # Add to statistics if results initialized and difficulty is valid
    if 'results' in st.session_state and difficulty in st.session_state.results:
        # Check if this is a duplicate submission
        for idx, existing_entry in enumerate(st.session_state.results[difficulty]):
            if (existing_entry.get('slug') == problem_slug and 
                existing_entry.get('model') == model and
                existing_entry.get('solution') == code):
                # Update existing entry instead of adding a new one
                st.session_state.results[difficulty][idx] = result_entry
                return result
        
        # If not a duplicate, add as new entry
        st.session_state.results[difficulty].append(result_entry)
    
    return result 