import requests
import time
import os
import json
import logging
from typing import Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# Load environment variables with authentication credentials
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("leetcode_api")

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
    logger.info(f"Submitting solution for problem: {problem_slug}, language: {language}")
    
    # Check if authentication credentials are available
    if not LEETCODE_SESSION or not LEETCODE_CSRF:
        logger.error("Authentication credentials not found")
        return {
            "success": False,
            "error": "Authentication credentials not found. Please set LEETCODE_SESSION and LEETCODE_CSRF in .env file."
        }
    
    # Rate limiting
    _rate_limit()
    
    # First, we need to get the question ID for the problem
    question_id = get_question_id_by_slug(problem_slug)
    if not question_id:
        logger.error(f"Could not get question ID for slug: {problem_slug}")
        return {
            "success": False,
            "error": f"Could not get question ID for slug: {problem_slug}"
        }
    
    logger.info(f"Got question ID: {question_id} for {problem_slug}")
    
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
    logger.info(f"Getting question ID for slug: {slug}")
    
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
        logger.info(f"Got response with status code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"GraphQL response: {json.dumps(result)[:500]}")
            
            if result and "data" in result and "question" in result["data"] and "questionId" in result["data"]["question"]:
                question_id = result["data"]["question"]["questionId"]
                logger.info(f"Successfully extracted question ID: {question_id}")
                return question_id
            else:
                logger.error(f"Failed to extract question ID, structure not as expected: {json.dumps(result)[:500]}")
        else:
            logger.error(f"Failed to get question ID, status code: {response.status_code}")
        
        return None
    except Exception as e:
        logger.exception(f"Exception during question ID retrieval: {str(e)}")
        return None


def check_submission_result(submission_id: str) -> Dict[str, Any]:
    """
    Check the result of a LeetCode submission.
    
    Args:
        submission_id: The submission ID returned by submit_solution
        
    Returns:
        Dict with submission results
    """
    logger.info(f"Checking submission result for ID: {submission_id}")
    
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
        logger.info(f"Got response with status code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                logger.info(f"Parsed JSON response: {json.dumps(result)[:500]}")
                
                if not result:
                    logger.error("Empty response from LeetCode API")
                    return {
                        "success": False,
                        "error": "Empty response from LeetCode API",
                        "response": result
                    }
                
                # Check if the result is ready
                state = result.get("state", "")
                logger.info(f"Submission state: {state}")
                
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
                        "state": state
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected submission state: {state}",
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


def submit_and_wait_for_result(problem_slug: str, code: str, language: str = "cpp", max_attempts: int = 10, wait_time: float = 2.0) -> Dict[str, Any]:
    """
    Submit a solution to LeetCode and wait for the result.
    
    Args:
        problem_slug: The LeetCode problem slug (e.g., "two-sum")
        code: The solution code to submit
        language: The programming language (default: "cpp")
        max_attempts: Maximum number of attempts to check the result
        wait_time: Time to wait between checks in seconds
        
    Returns:
        Dict with submission results
    """
    logger.info(f"Starting submission process for {problem_slug}")
    
    # Submit the solution
    submission_result = submit_solution(problem_slug, code, language)
    
    if not submission_result["success"]:
        return submission_result
    
    submission_id = submission_result["submission_id"]
    
    # Wait for the result
    for attempt in range(max_attempts):
        time.sleep(wait_time)
        result = check_submission_result(submission_id)
        
        if not result["success"]:
            # Error occurred during check
            return result
        
        if result.get("pending", False):
            # Result not ready yet, continue waiting
            continue
        
        # Result is ready
        # Add status description and color
        if "status_code" in result:
            status_code = result["status_code"]
            # Ensure status_code is an integer
            if isinstance(status_code, int):
                description, color = get_status_description(status_code)
                result["status_description"] = description
                result["status_color"] = color
            else:
                # Default values if status_code is not an integer
                result["status_description"] = str(status_code) if status_code else "Unknown Status"
                result["status_color"] = "gray"
            
        return result
    
    # Max attempts reached without a result
    return {
        "success": False,
        "error": f"Max attempts ({max_attempts}) reached without getting a result",
        "submission_id": submission_id
    } 