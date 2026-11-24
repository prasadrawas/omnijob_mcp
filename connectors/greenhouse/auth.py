"""
Authentication, Configuration, and Storage for Greenhouse MCP.
Handles Job Board API keys, board registries, candidate profile discovery, and pipeline tracking.
"""
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

# Base Greenhouse Endpoints
GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1"
GREENHOUSE_HOSTED_BASE = "https://boards.greenhouse.io"
GREENHOUSE_MODERN_HOSTED_BASE = "https://job-boards.greenhouse.io"

# Default Curated Boards for tech discovery
DEFAULT_TARGET_BOARDS = [
    "cloudflare",
    "canonical",
    "stripe",
    "figma",
    "elastic",
    "datadog",
    "databricks",
    "airbnb",
    "pinterest",
    "gitlab",
]

# In-memory stores for runtime
BOARD_REGISTRY: List[str] = list(DEFAULT_TARGET_BOARDS)
PIPELINE_HISTORY: List[Dict[str, Any]] = []

# Optional API Key
_current_api_key: Optional[str] = os.environ.get("GREENHOUSE_API_KEY")


def is_authenticated() -> bool:
    """Greenhouse public job boards are queryable without credentials; API key enables direct apply."""
    return True


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Greenhouse configuration status."""
    key = get_api_key()
    return {
        "authenticated": True,
        "has_keys": bool(key),
        "api_key_configured": bool(key),
        "tracked_boards_count": len(get_tracked_boards()),
        "tracked_boards": get_tracked_boards(),
    }


def get_api_key() -> Optional[str]:
    """Retrieve currently configured Greenhouse Job Board API Key."""
    global _current_api_key
    if not _current_api_key:
        _current_api_key = os.environ.get("GREENHOUSE_API_KEY")
    return _current_api_key


def set_api_key(api_key: Optional[str]) -> None:
    """Set or clear the Greenhouse Job Board API Key in runtime."""
    global _current_api_key
    _current_api_key = api_key if api_key and api_key.strip() else None


def get_tracked_boards() -> List[str]:
    """Return list of currently tracked board tokens."""
    return list(BOARD_REGISTRY)


def add_tracked_board(board_token: str) -> bool:
    """Add a board token to the active registry."""
    token = board_token.strip().lower()
    if token and token not in BOARD_REGISTRY:
        BOARD_REGISTRY.append(token)
        return True
    return False


def remove_tracked_board(board_token: str) -> bool:
    """Remove a board token from the active registry."""
    token = board_token.strip().lower()
    if token in BOARD_REGISTRY:
        BOARD_REGISTRY.remove(token)
        return True
    return False


def record_pipeline_event(event: Dict[str, Any]) -> None:
    """Record an application or validation event in local pipeline history."""
    PIPELINE_HISTORY.append(event)


def get_pipeline_history() -> List[Dict[str, Any]]:
    """Retrieve application history."""
    return list(PIPELINE_HISTORY)


def discover_candidate_profile() -> Dict[str, Any]:
    """
    Discover candidate profile from environment variables or master_resume.json in workspace.
    """
    default_name = os.getenv("CANDIDATE_NAME", "Candidate User")
    default_email = os.getenv("CANDIDATE_EMAIL", "candidate@example.com")
    default_phone = os.getenv("CANDIDATE_PHONE", "+91 9876543210")
    default_location = os.getenv("CANDIDATE_LOCATION", "Pune, India")
    default_linkedin = os.getenv("CANDIDATE_LINKEDIN", "https://linkedin.com")
    default_github = os.getenv("CANDIDATE_GITHUB", "https://github.com")
    default_resume = os.getenv("CANDIDATE_RESUME_PATH", "")

    # Attempt to load from data/master_resume.json or data/dummy_master_resume.json
    workspace_root = Path(__file__).resolve().parent.parent.parent
    data_paths = [
        workspace_root / "data" / "master_resume.json",
        workspace_root / "data" / "dummy_master_resume.json",
    ]

    for p in data_paths:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    basics = data.get("basics", {})
                    if basics:
                        # Find LinkedIn and GitHub
                        linkedin_url = default_linkedin
                        github_url = default_github
                        for prof in basics.get("profiles", []):
                            net = (prof.get("network") or "").lower()
                            if "linkedin" in net:
                                linkedin_url = prof.get("url", default_linkedin)
                            elif "github" in net:
                                github_url = prof.get("url", default_github)

                        full_name = basics.get("name") or default_name
                        name_parts = full_name.split(" ", 1)
                        first_name = name_parts[0]
                        last_name = name_parts[1] if len(name_parts) > 1 else ""

                        city = basics.get("location", {}).get("city", "")
                        loc_str = f"{city}, India" if city else default_location

                        return {
                            "first_name": first_name,
                            "last_name": last_name,
                            "full_name": full_name,
                            "email": basics.get("email", default_email),
                            "phone": basics.get("phone", default_phone),
                            "location": loc_str,
                            "linkedin_url": linkedin_url,
                            "github_url": github_url,
                            "summary": basics.get("summary", ""),
                            "work_authorization": "Authorized to work in India; Requires sponsorship for US/EU roles",
                            "requires_sponsorship": False,
                            "gender": basics.get("personal", {}).get("gender", "Male"),
                            "preferred_locations": ["Pune", "Bengaluru", "Remote"],
                            "resume_path": default_resume,
                        }
            except Exception:
                pass

    # Generic default profile
    name_parts = default_name.split(" ", 1)
    return {
        "first_name": name_parts[0],
        "last_name": name_parts[1] if len(name_parts) > 1 else "",
        "full_name": default_name,
        "email": default_email,
        "phone": default_phone,
        "location": default_location,
        "linkedin_url": default_linkedin,
        "github_url": default_github,
        "summary": "Full Stack & Distributed Systems Engineer specializing in Python, FastAPI, React, and cloud systems.",
        "work_authorization": "Authorized to work in India; Open to global remote roles",
        "requires_sponsorship": False,
        "gender": "Male",
        "preferred_locations": ["Pune", "Bengaluru", "Remote"],
        "resume_path": default_resume,
    }
