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
    Discover candidate profile from master_resume.json in the workspace
    or return complete default profile for Prasad Rawas.
    """
    # Attempt to load from data/master_resume.json or data/dummy_master_resume.json
    workspace_root = Path(__file__).resolve().parent.parent
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
                        linkedin_url = ""
                        github_url = ""
                        for prof in basics.get("profiles", []):
                            net = (prof.get("network") or "").lower()
                            if "linkedin" in net:
                                linkedin_url = prof.get("url", "")
                            elif "github" in net:
                                github_url = prof.get("url", "")

                        name_parts = (basics.get("name") or "Prasad Rawas").split(" ", 1)
                        first_name = name_parts[0]
                        last_name = name_parts[1] if len(name_parts) > 1 else ""

                        return {
                            "first_name": first_name,
                            "last_name": last_name,
                            "full_name": basics.get("name", "Prasad Rawas"),
                            "email": basics.get("email", "contactprasadrawas@gmail.com"),
                            "phone": basics.get("phone", "+91 7276974942"),
                            "location": basics.get("location", {}).get("city", "Pune") + ", India",
                            "linkedin_url": linkedin_url or "https://www.linkedin.com/in/prasadrawas",
                            "github_url": github_url or "https://github.com/prasadrawas",
                            "summary": basics.get("summary", ""),
                            "work_authorization": "Authorized to work in India; Requires sponsorship for US/EU roles",
                            "requires_sponsorship": False,  # For India/Remote or set as needed
                            "gender": basics.get("personal", {}).get("gender", "Male"),
                            "preferred_locations": ["Pune", "Bengaluru", "Remote"],
                            "resume_path": str(workspace_root / "data" / "pooja_rawas_resume.pdf"),
                        }
            except Exception:
                pass

    # Default profile
    return {
        "first_name": "Prasad",
        "last_name": "Rawas",
        "full_name": "Prasad Rawas",
        "email": "contactprasadrawas@gmail.com",
        "phone": "+91 7276974942",
        "location": "Pune, India",
        "linkedin_url": "https://www.linkedin.com/in/prasadrawas",
        "github_url": "https://github.com/prasadrawas",
        "summary": "Full Stack & Distributed Systems Engineer specializing in Python, FastAPI, React, Node.js, and autonomous agent systems.",
        "work_authorization": "Authorized to work in India; Open to global remote roles",
        "requires_sponsorship": False,
        "gender": "Male",
        "preferred_locations": ["Pune", "Bengaluru", "Remote"],
        "resume_path": "",
    }
