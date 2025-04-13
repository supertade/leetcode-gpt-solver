import requests
import time
import os
import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables with authentication credentials
load_dotenv()

# Konfiguriere Logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_filename = os.path.join(log_dir, f"leetcode_submit_{datetime.now().strftime('%Y%m%d')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_filename)
    ]
)

# LeetCode authentication cookies
LEETCODE_SESSION = os.environ.get("LEETCODE_SESSION", "")
LEETCODE_CSRF = os.environ.get("LEETCODE_CSRF", "")

# Rate limiting settings
MIN_REQUEST_INTERVAL = 2.0
last_request_time = 0


def _rate_limit():
    """Simple rate limiting for API requests"""
    global last_request_time
    current_time = time.time()
    elapsed = current_time - last_request_time
    
    if elapsed < MIN_REQUEST_INTERVAL:
        sleep_time = MIN_REQUEST_INTERVAL - elapsed
        time.sleep(sleep_time)
    
    last_request_time = time.time()


def submit_solution(problem_slug: str, code: str, language: str = "cpp") -> Dict[str, Any]:
    """
    Submit a solution to LeetCode and return the submission ID.
    
    Args:
        problem_slug: The LeetCode problem slug (e.g., "two-sum")
        code: The solution code to submit
        language: The programming language (default: "cpp")
        
    Returns:
        Dict with submission ID and status
    """
    logging.info(f"Submitting solution for problem: {problem_slug}, language: {language}")
    
    # Check if authentication credentials are available
    if not LEETCODE_SESSION or not LEETCODE_CSRF:
        logging.error("Authentication credentials not found")
        return {
            "success": False,
            "error": "Authentication credentials not found. Please set LEETCODE_SESSION and LEETCODE_CSRF in .env file."
        }
    
    # Rate limiting
    _rate_limit()
    
    # First, we need to get the question ID for the problem
    question_id = get_question_id_by_slug(problem_slug)
    if not question_id:
        logging.error(f"Could not get question ID for slug: {problem_slug}")
        return {
            "success": False,
            "error": f"Could not get question ID for slug: {problem_slug}"
        }
    
    logging.info(f"Got question ID: {question_id} for {problem_slug}")
    
    # Set up headers with authentication cookies
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Referer": f"https://leetcode.com/problems/{problem_slug}/",
        "Cookie": f"csrftoken={LEETCODE_CSRF}; LEETCODE_SESSION={LEETCODE_SESSION}",
        "X-CSRFToken": LEETCODE_CSRF,
        "Origin": "https://leetcode.com"
    }
    
    # Submission data
    data = {
        "lang": language,
        "question_id": question_id,
        "typed_code": code
    }
    
    # Submit the solution
    url = f"https://leetcode.com/problems/{problem_slug}/submit/"
    
    try:
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            try:
                result = response.json()
                if "submission_id" in result:
                    return {
                        "success": True,
                        "submission_id": result["submission_id"]
                    }
                else:
                    return {
                        "success": False,
                        "error": "No submission ID in response",
                        "response": result
                    }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": f"Invalid JSON response from LeetCode",
                    "response": response.text[:500]  # First 500 chars for debugging
                }
        else:
            # Try to parse response content for better error message
            try:
                error_content = response.json()
                error_message = error_content.get('error', 'Unknown error')
            except:
                error_message = response.text[:500] if response.text else "No error message"
                
            return {
                "success": False,
                "error": f"Submission failed with status code {response.status_code}",
                "message": error_message,
                "headers": dict(response.headers)
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception during submission: {str(e)}"
        }


def get_question_id_by_slug(slug: str) -> Optional[str]:
    """
    Get the numeric question ID from the slug.
    
    Args:
        slug: The problem slug
        
    Returns:
        The question ID as a string, or None if not found
    """
    logging.info(f"Getting question ID for slug: {slug}")
    
    # Rate limiting
    _rate_limit()
    
    # GraphQL query to get question ID
    query = """
    query questionData($titleSlug: String!) {
      question(titleSlug: $titleSlug) {
        questionId
        title
      }
    }
    """
    
    # Set up headers with authentication cookies
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Referer": f"https://leetcode.com/problems/{slug}/",
        "Cookie": f"csrftoken={LEETCODE_CSRF}; LEETCODE_SESSION={LEETCODE_SESSION}",
    }
    
    data = {
        "query": query,
        "variables": {"titleSlug": slug}
    }
    
    try:
        response = requests.post("https://leetcode.com/graphql", json=data, headers=headers)
        logging.info(f"Got response with status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logging.info(f"GraphQL response: {json.dumps(result)[:500]}")
            
            if result and "data" in result and "question" in result["data"] and "questionId" in result["data"]["question"]:
                question_id = result["data"]["question"]["questionId"]
                logging.info(f"Successfully extracted question ID: {question_id}")
                return question_id
            else:
                logging.error(f"Failed to extract question ID, structure not as expected: {json.dumps(result)[:500]}")
        else:
            logging.error(f"Failed to get question ID, status code: {response.status_code}")
        
        return None
    except Exception as e:
        logging.exception(f"Exception during question ID retrieval: {str(e)}")
        return None


def check_submission_result(submission_id: str) -> Dict[str, Any]:
    """
    Check the result of a LeetCode submission.
    
    Args:
        submission_id: The submission ID returned by submit_solution
        
    Returns:
        Dict with submission results
    """
    logging.info(f"Checking submission result for ID: {submission_id}")
    
    # Check if authentication credentials are available
    if not LEETCODE_SESSION or not LEETCODE_CSRF:
        return {
            "success": False,
            "error": "Authentication credentials not found. Please set LEETCODE_SESSION and LEETCODE_CSRF in .env file."
        }
    
    # Rate limiting
    _rate_limit()
    
    # Set up headers with authentication cookies
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36",
        "Referer": "https://leetcode.com/submissions/",
        "Cookie": f"csrftoken={LEETCODE_CSRF}; LEETCODE_SESSION={LEETCODE_SESSION}",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json"
    }
    
    # Check the submission result
    url = f"https://leetcode.com/submissions/detail/{submission_id}/check/"
    
    try:
        response = requests.get(url, headers=headers)
        logging.info(f"Got response with status code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logging.info(f"Parsed JSON response: {json.dumps(result)[:500]}")
                
                if not result:
                    logging.error("Empty response from LeetCode API")
                    return {
                        "success": False,
                        "error": "Empty response from LeetCode API",
                        "response": result
                    }
                
                # Check if the result is ready
                state = result.get("state", "")
                logging.info(f"Submission state: {state}")
                
                if state == "SUCCESS":
                    # Safely access nested values with default values to prevent NoneType errors
                    runtime_percentile = result.get("runtime_percentile", None)
                    memory_percentile = result.get("memory_percentile", None)
                    
                    # Get runtime and memory values safely
                    runtime_ms = None
                    memory_val = None
                    
                    if isinstance(runtime_percentile, dict):
                        runtime_ms = runtime_percentile.get("value", None)
                    elif isinstance(runtime_percentile, (int, float)):
                        runtime_ms = runtime_percentile
                        
                    if isinstance(memory_percentile, dict):
                        memory_val = memory_percentile.get("value", None)
                    elif isinstance(memory_percentile, (int, float)):
                        memory_val = memory_percentile
                    
                    return {
                        "success": True,
                        "result": result.get("status_msg", ""),
                        "runtime_ms": runtime_ms,
                        "memory_percentile": memory_val,
                        "total_testcases": result.get("total_testcases", 0),
                        "passed_testcases": result.get("total_correct", 0),
                        "status_code": result.get("status_code", 0),
                        "language": result.get("lang", "cpp"),
                        "details": result
                    }
                elif state == "PENDING" or state == "STARTED":
                    return {
                        "success": True,
                        "pending": True,
                        "details": result
                    }
                else:
                    # Wenn ein status_code vorhanden ist, ist die Submission abgeschlossen
                    if "status_code" in result:
                        return {
                            "success": True,
                            "status_code": result.get("status_code"),
                            "language": result.get("lang", "cpp"),
                            "details": result
                        }
                    
                    # Andernfalls unbekannter Status
                    return {
                        "success": True,
                        "unknown_state": True,
                        "details": result
                    }
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "error": f"Invalid JSON response from LeetCode",
                    "response": response.text[:500]  # First 500 chars for debugging
                }
        else:
            # Try to parse response content for better error message
            try:
                error_content = response.json()
                error_message = error_content.get('error', 'Unknown error') if error_content else 'Unknown error'
            except:
                error_message = response.text[:500] if response.text else "No error message"
                
            return {
                "success": False,
                "error": f"Check submission failed with status code {response.status_code}",
                "message": error_message,
                "headers": dict(response.headers)
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"Exception during check: {str(e)}",
            "traceback": import_traceback() 
        }


def import_traceback():
    """Helper to import traceback module only when needed"""
    import traceback
    return traceback.format_exc()


def get_status_description(status_code: int) -> Tuple[str, str]:
    """
    Return a user-friendly description and a color code based on the LeetCode status code.
    
    Args:
        status_code: The LeetCode status code
        
    Returns:
        Tuple of (description, color)
    """
    status_map = {
        10: ("Accepted", "green"),
        11: ("Wrong Answer", "red"),
        12: ("Memory Limit Exceeded", "orange"),
        13: ("Output Limit Exceeded", "orange"),
        14: ("Time Limit Exceeded", "orange"),
        15: ("Runtime Error", "red"),
        16: ("Internal Error", "red"),
        20: ("Compile Error", "red"),
        21: ("Unknown Error", "red"),
        30: ("Timeout", "orange")
    }
    
    return status_map.get(status_code, ("Unknown Status", "gray"))


def submit_and_wait_for_result(problem_slug: str, code: str, language: str = "cpp", timeout: int = 30) -> Dict[str, Any]:
    """
    Submit a solution to LeetCode and wait for the result.
    
    Args:
        problem_slug: The LeetCode problem slug (e.g., "two-sum")
        code: The solution code to submit
        language: The programming language (default: "cpp")
        timeout: Maximum time to wait for submission result in seconds
        
    Returns:
        Dict with submission results
    """
    logging.info(f"Starting submission process for {problem_slug}")
    
    try:
        # Step 1: Submit the solution
        submit_result = submit_solution(problem_slug, code, language)
        
        if not submit_result["success"]:
            logging.error(f"Failed to submit solution: {submit_result.get('error')}")
            return submit_result
            
        submission_id = submit_result.get("submission_id")
        if not submission_id:
            logging.error("No submission ID returned")
            return {"success": False, "error": "No submission ID returned"}
            
        # Step 2: Wait for and check the submission result
        start_time = time.time()
        result = None
        
        while time.time() - start_time < timeout:
            check_result = check_submission_result(submission_id)
            
            # If we got a valid result with success flag
            if check_result["success"]:
                # LeetCode gibt zwei verschiedene Antwortformate:
                # 1. Anfangs: {"state": "PENDING"} 
                # 2. Bei Abschluss: {"status_code": 10, ...} ohne state-Feld
                response_data = check_result.get("details", {})
                
                # Wenn status_code vorhanden ist, ist die Submission abgeschlossen
                if "status_code" in response_data:
                    logging.info(f"Submission abgeschlossen mit Status Code: {response_data['status_code']}")
                    result = process_submission_result(response_data)
                    break
                
                # Andernfalls prüfen wir den state
                state = response_data.get("state", "")
                if state in ["SUCCESS", "FAILURE"]:
                    logging.info(f"Submission abgeschlossen mit State: {state}")
                    result = process_submission_result(response_data)
                    break
                elif state == "PENDING" or state == "STARTED":
                    logging.info(f"Submission läuft noch: {state}")
                else:
                    logging.info(f"Unbekannter Submission-Status: {state}")
            else:
                # Bei einem Fehler in der Antwort auch abbrechen
                logging.error(f"Error checking submission: {check_result.get('error', 'Unknown error')}")
                return {"success": False, "error": check_result.get('error', 'Unknown error during check')}
            
            # Wait before checking again
            time.sleep(2)
            
        if result is None:
            logging.error(f"Timed out waiting for submission result after {timeout} seconds")
            return {"success": False, "error": f"Timeout after {timeout} seconds"}
            
        return result
    
    except Exception as e:
        logging.error(f"Error in submission process: {str(e)}")
        return {"success": False, "error": f"Submission error: {str(e)}"}


def process_submission_result(response_data):
    """
    Process the raw submission result data into a more usable format.
    
    Args:
        response_data: The raw submission result data
        
    Returns:
        Processed submission result
    """
    result = {"success": True}
    
    # Copy basic fields
    for key in ["status_code", "lang", "run_success", "status_runtime", "memory", "question_id"]:
        if key in response_data:
            result[key] = response_data[key]
    
    # Convert LeetCode status code to human-readable description
    status_code = response_data.get("status_code")
    if status_code is not None:
        result["status_code"] = status_code
        
        # Status descriptions
        status_map = {
            10: "Accepted",
            11: "Wrong Answer",
            12: "Memory Limit Exceeded",
            13: "Output Limit Exceeded",
            14: "Time Limit Exceeded",
            15: "Runtime Error",
            16: "Internal Error",
            20: "Compile Error",
            21: "Unknown Error",
            22: "Queue Empty",
            23: "Judging",
            24: "Partial Accepted",
            25: "Submission Skipped",
            30: "System Error"
        }
        
        result["status_description"] = status_map.get(status_code, f"Unknown Status ({status_code})")
    
    # Extract runtime information if available
    if "status_runtime" in response_data:
        runtime_str = response_data["status_runtime"]
        try:
            # Parse runtime (e.g., "10 ms" -> 10)
            runtime_value = runtime_str.split()[0]
            result["runtime_ms"] = int(runtime_value) if runtime_value.isdigit() else float(runtime_value)
        except (ValueError, IndexError):
            result["runtime_ms"] = None
    
    # Extract memory information if available
    if "memory" in response_data:
        try:
            # Convert memory from bytes to MB
            result["memory_percentile"] = round(response_data["memory"] / (1024 * 1024), 2)
        except (ValueError, TypeError):
            result["memory_percentile"] = None
    
    # Extract test case information
    if "total_correct" in response_data:
        result["total_testcases"] = response_data.get("total_testcases", response_data["total_correct"])
        result["passed_testcases"] = response_data["total_correct"]
    
    # Extract error details for different error types
    # Compile errors
    if status_code == 20:  # Compile Error
        if "compile_error" in response_data:
            result["compile_error"] = response_data["compile_error"]
        
        if "full_compile_error" in response_data:
            result["full_compile_error"] = response_data["full_compile_error"]
    
    # Runtime errors
    if status_code == 15:  # Runtime Error
        if "runtime_error" in response_data:
            result["runtime_error"] = response_data["runtime_error"]
        
        if "full_runtime_error" in response_data:
            result["full_runtime_error"] = response_data["full_runtime_error"]
        
        if "last_testcase" in response_data:
            result["last_testcase"] = response_data["last_testcase"]
    
    # Wrong answer details
    if status_code == 11:  # Wrong Answer
        for key in ["expected_output", "code_output", "last_testcase", "std_output", "compare_result"]:
            if key in response_data:
                result[key] = response_data[key]
    
    # Include raw response for debugging (except potentially large fields)
    raw_response = {k: v for k, v in response_data.items() if k not in ["judge_type", "code_answer", "expected_code_answer"]}
    result["raw_response"] = raw_response
    
    return result 