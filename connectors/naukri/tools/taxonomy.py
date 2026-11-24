"""
Central taxonomy and standardized entity search tools for naukri_mcp.
"""
import urllib.parse
from typing import Dict, Any, Optional

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import CENTRAL_ENTITY_URL, get_headers, make_api_request


def get_taxonomy_versions(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    List all 32 central entity taxonomies available in Naukri and their current versions.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    url = f"{CENTRAL_ENTITY_URL}/version"
    status, data = make_api_request(url, method="GET", headers=headers)

    if status == 200 and isinstance(data, list):
        return {"status": "success", "total_taxonomies": len(data), "taxonomies": data}
    return {"status": "error", "http_status": status, "message": str(data)}


def search_taxonomy(
    entity_type: str = "certificate",
    query: str = "",
    limit: int = 20,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search standardized Naukri entities by keyword.

    :param entity_type: One of 'certificate' (4,000+ certifications with vendor IDs), 'city' (5,800+ cities), 'language', 'country', 'state'.
    :param query: Search keyword (e.g. 'AWS', 'Pune', 'English'). Leave empty to list from top.
    :param limit: Max number of matches to return (default 20).
    :param nauk_at: Optional access token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    clean_entity = urllib.parse.quote(entity_type.strip().lower())
    url = f"{CENTRAL_ENTITY_URL}/{clean_entity}"
    status, data = make_api_request(url, method="GET", headers=headers)

    if status != 200 or not isinstance(data, list):
        return {"status": "error", "http_status": status, "message": str(data)}

    q_lower = query.strip().lower()
    matches = []
    for item in data:
        label = item.get("label", "") or ""
        vendor_label = item.get("vendor", {}).get("label", "") if isinstance(item.get("vendor"), dict) else ""
        if not q_lower or (q_lower in label.lower()) or (q_lower in vendor_label.lower()):
            matches.append(item)
            if len(matches) >= limit:
                break

    return {
        "status": "success",
        "entity_type": entity_type,
        "query": query,
        "count": len(matches),
        "results": matches
    }
