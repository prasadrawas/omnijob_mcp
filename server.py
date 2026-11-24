"""
OmniJob MCP Server implementation using official FastMCP / MCPServer SDK.
Unified Job Application & Profile Management Server for 7 Platforms:
Naukri, Hirist, Wellfound, Instahyre, Cutshort, Greenhouse, and Foundit.

Implements the Connector Design Pattern exposing 7 High-Level Standardized Meta-Tools:
1. `search_jobs`: Multi-board concurrent search (single platform or connector='all')
2. `get_job_details`: Detailed JD, requirements, and questionnaire inspection
3. `manage_job_pipeline`: Applications, eligibility checks, save/unsave, and tracking
4. `manage_profile`: Candidate profile inspection, section updates, activity pulses, cross-platform syncing
5. `manage_account`: Recruiter inbox, algorithmic recommendations, analytics, company blocking
6. `manage_taxonomy`: Centralized autocomplete for skills, companies, locations, institutes
7. `manage_session`: Unified authentication dashboard, token renewal, cache clearing
"""
import os
import time
import asyncio
from typing import Dict, Any, List, Optional, Union, Literal
from concurrent.futures import ThreadPoolExecutor

from starlette.requests import Request
from starlette.responses import Response, JSONResponse, HTMLResponse

try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except Exception:
    from mcp.server.fastmcp import FastMCP  # type: ignore

from omnijob_mcp.core.registry import ConnectorRegistry
from omnijob_mcp.core.cache import TTLCache

# Global registry and executor for parallel fan-out queries
registry = ConnectorRegistry.get_instance()
executor = ThreadPoolExecutor(max_workers=8)
server_cache = TTLCache(default_ttl=180, max_size=1000)

mcp = FastMCP(
    "omnijob-mcp",
    instructions=(
        "OmniJob MCP Server (Unified 7-Platform Architecture): Production MCP server for job search, "
        "application pipelines, candidate profile synchronization, and recruiter communication across 7 platforms:\n"
        "- Naukri.com (`naukri`)\n"
        "- Hirist.tech (`hirist`)\n"
        "- Wellfound / AngelList (`wellfound`)\n"
        "- Instahyre (`instahyre`)\n"
        "- Cutshort.io (`cutshort`)\n"
        "- Greenhouse ATS (`greenhouse`)\n"
        "- Foundit / Monster APAC (`foundit`)\n\n"
        "CORE TOOLS (Total 7 Meta-Tools):\n"
        "1. `search_jobs`: Search jobs on any individual platform or fan-out across all platforms with connector='all'.\n"
        "2. `get_job_details`: Deep inspect JD, requirements, and questionnaire schema.\n"
        "3. `manage_job_pipeline`: Apply, check apply eligibility, bookmark/save jobs, and view application tracking.\n"
        "4. `manage_profile`: Inspect profile, update sections (headline, summary, skills, experience), pulse activity, or sync across platforms.\n"
        "5. `manage_account`: Access recruiter inbox, AI recommendations, pipeline metrics, and employer blocking.\n"
        "6. `manage_taxonomy`: Look up verified skills, companies, locations, and educational institutes.\n"
        "7. `manage_session`: Real-time authentication dashboard and health diagnostics for all connectors."
    )
)


# ---------------------------------------------------------------------------
# CUSTOM HTTP ROUTES (Health, Landing Page)
# ---------------------------------------------------------------------------

@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    """Public health check endpoint returning aggregated connector authentication status."""
    status_report = registry.get_status_all()
    overall = "healthy" if status_report.get("authenticated_count", 0) > 0 else "degraded"
    return JSONResponse({
        "status": overall,
        "service": "omnijob-mcp",
        "version": "1.0.0",
        "authenticated_platforms": status_report.get("authenticated_count", 0),
        "total_platforms": status_report.get("total_connectors", 7),
        "connectors": status_report.get("connectors", {}),
    })


@mcp.custom_route("/", methods=["GET"])
async def landing_page(request: Request) -> Response:
    """Landing dashboard displaying available connectors and capabilities."""
    status_report = registry.get_status_all()
    rows = ""
    for name, c in status_report.get("connectors", {}).items():
        st = c.get("status", "unknown")
        color = "#10b981" if st == "authenticated" else ("#f59e0b" if st == "configured" else "#ef4444")
        rows += f"""
        <tr>
            <td style="padding: 10px 14px; font-weight: 600;">{c.get('display_name', name)}</td>
            <td style="padding: 10px 14px; font-family: monospace;">{name}</td>
            <td style="padding: 10px 14px;"><span style="background: {color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">{st.upper()}</span></td>
            <td style="padding: 10px 14px; font-size: 13px; color: #64748b;">{', '.join(c.get('supported_features', []))}</td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>OmniJob MCP Server</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 40px 20px; }}
            .container {{ max-width: 960px; margin: 0 auto; background: #1e293b; border-radius: 12px; border: 1px solid #334155; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
            h1 {{ margin-top: 0; color: #38bdf8; display: flex; align-items: center; gap: 10px; }}
            p.lead {{ color: #94a3b8; font-size: 16px; margin-bottom: 24px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: #0f172a; border-radius: 8px; overflow: hidden; }}
            th {{ background: #1e293b; padding: 12px 14px; text-align: left; font-size: 13px; color: #94a3b8; border-bottom: 2px solid #334155; }}
            tr:nth-child(even) {{ background: #162032; }}
            .badge {{ background: #38bdf8; color: #0f172a; font-weight: 700; padding: 4px 10px; border-radius: 6px; font-size: 13px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌐 OmniJob MCP Server <span class="badge">Unified 7-in-1</span></h1>
            <p class="lead">Universal Model Context Protocol server consolidating Naukri, Hirist, Wellfound, Instahyre, Cutshort, Greenhouse, and Foundit into 7 Standardized Meta-Tools.</p>
            <div style="display: flex; gap: 20px; margin-bottom: 24px;">
                <div style="background: #0f172a; padding: 14px 20px; border-radius: 8px; border: 1px solid #334155;">
                    <span style="font-size: 12px; color: #94a3b8; text-transform: uppercase;">Active Platforms</span>
                    <h2 style="margin: 4px 0 0; color: #10b981;">{status_report.get('authenticated_count')}/{status_report.get('total_connectors')}</h2>
                </div>
                <div style="background: #0f172a; padding: 14px 20px; border-radius: 8px; border: 1px solid #334155;">
                    <span style="font-size: 12px; color: #94a3b8; text-transform: uppercase;">Meta-Tools</span>
                    <h2 style="margin: 4px 0 0; color: #38bdf8;">7 Tools</h2>
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>Platform</th>
                        <th>Connector Slug</th>
                        <th>Auth Status</th>
                        <th>Supported Features</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# ---------------------------------------------------------------------------
# META-TOOL 1: search_jobs
# ---------------------------------------------------------------------------

@mcp.tool()
async def search_jobs(
    connector: Literal["all", "naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"] = "all",
    query: str = "Software Engineer",
    location: Optional[str] = "Pune",
    experience: Optional[int] = None,
    board_token: Optional[str] = None,
    start: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Search jobs across job platforms and applicant tracking systems.

    Supports querying an individual platform (e.g. connector='foundit') or concurrently fanning
    out across all active platforms with connector='all' to aggregate listings into normalized results.

    Args:
        connector: Target platform slug ('naukri', 'hirist', 'wellfound', 'instahyre', 'cutshort', 'greenhouse', 'foundit', or 'all').
        query: Search keywords, tech stack, or job title (e.g. 'Python Backend Engineer', 'React Lead').
        location: Target city or region (e.g. 'Pune', 'Bangalore', 'Remote').
        experience: Relevant years of experience (e.g. 3, 5).
        board_token: Optional company board token for Greenhouse (e.g. 'cloudflare', 'stripe').
        start: Pagination start offset.
        limit: Max results to return per platform (default 20).
    """
    loop = asyncio.get_running_loop()

    if connector != "all":
        conn = registry.get(connector)
        if not conn:
            return {"success": False, "error": f"Unknown connector: {connector}. Available: {registry.list_connectors()}"}
        return await loop.run_in_executor(
            executor,
            lambda: conn.search_jobs(query=query, location=location, experience=experience, start=start, limit=limit, board_token=board_token)
        )

    # Fan-out search across all active/authenticated connectors
    auth_conns = registry.get_authenticated()
    if not auth_conns:
        # Fallback to all connectors even if not explicitly authenticated (e.g. greenhouse is public)
        auth_conns = registry.get_all()

    async def _query_connector(name: str, c: Any) -> Dict[str, Any]:
        try:
            return await loop.run_in_executor(
                executor,
                lambda: c.search_jobs(query=query, location=location, experience=experience, start=0, limit=min(limit, 10), board_token=board_token)
            )
        except Exception as e:
            return {"platform": name, "error": str(e), "jobs": []}

    tasks = [_query_connector(name, c) for name, c in auth_conns.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    aggregated_jobs: List[Dict[str, Any]] = []
    platform_breakdown: Dict[str, int] = {}

    for res in results:
        if isinstance(res, dict):
            plat = res.get("platform", "unknown")
            items = res.get("jobs", [])
            aggregated_jobs.extend(items)
            platform_breakdown[plat] = len(items)

    return {
        "success": True,
        "mode": "multi_platform_search",
        "query": query,
        "location": location,
        "total_aggregated": len(aggregated_jobs),
        "platform_breakdown": platform_breakdown,
        "jobs": aggregated_jobs[:limit * 2],
    }


# ---------------------------------------------------------------------------
# META-TOOL 2: get_job_details
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_job_details(
    connector: Literal["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"],
    job_id: str,
    board_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Retrieve comprehensive job details, full description, qualifications, and questionnaire questions.

    Args:
        connector: Job platform slug ('naukri', 'hirist', 'wellfound', 'instahyre', 'cutshort', 'greenhouse', 'foundit').
        job_id: Platform-specific job listing ID.
        board_token: Required for Greenhouse jobs if not encoded in job_id (e.g. 'cloudflare').
    """
    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        lambda: conn.get_job_details(job_id=job_id, board_token=board_token)
    )


# ---------------------------------------------------------------------------
# META-TOOL 3: manage_job_pipeline
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_job_pipeline(
    connector: Literal["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"],
    action: Literal["apply", "can_apply", "save", "unsave", "get_applied", "get_saved"] = "can_apply",
    job_id: Optional[str] = None,
    answers: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    start: int = 0,
    limit: int = 20,
    board_token: Optional[str] = None,
    resume_file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage job application workflow across platforms.

    Actions:
    - `can_apply`: Pre-check eligibility, questionnaire requirements, and application status.
    - `apply`: Submit job application (set dry_run=True for validation without committing).
    - `save`: Bookmark a job for future reference.
    - `unsave`: Remove a bookmark.
    - `get_applied`: Retrieve application history and submitted job listings.
    - `get_saved`: Retrieve saved/bookmarked jobs.

    Args:
        connector: Platform slug ('naukri', 'hirist', 'wellfound', 'instahyre', 'cutshort', 'greenhouse', 'foundit').
        action: 'can_apply', 'apply', 'save', 'unsave', 'get_applied', or 'get_saved'.
        job_id: Target job ID (required for apply, can_apply, save, unsave).
        answers: Dictionary or questionnaire response mapping for screening questions.
        dry_run: If True, validates application payload without submitting live application.
        start: Pagination start offset for applied/saved queries.
        limit: Max items to return.
        board_token: Greenhouse company board slug.
        resume_file_path: Optional local path to custom PDF resume.
    """
    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    loop = asyncio.get_running_loop()

    if action == "can_apply":
        if not job_id:
            return {"success": False, "error": "job_id is required for can_apply"}
        return await loop.run_in_executor(
            executor,
            lambda: conn.can_job_apply(job_id=job_id, board_token=board_token, answers=answers)
        )
    elif action == "apply":
        if not job_id:
            return {"success": False, "error": "job_id is required for apply"}
        return await loop.run_in_executor(
            executor,
            lambda: conn.apply_to_job(
                job_id=job_id,
                answers=answers,
                dry_run=dry_run,
                board_token=board_token,
                resume_file_path=resume_file_path
            )
        )
    elif action == "save":
        if not job_id:
            return {"success": False, "error": "job_id is required for save"}
        return await loop.run_in_executor(executor, lambda: conn.save_job(job_id=job_id))
    elif action == "unsave":
        if not job_id:
            return {"success": False, "error": "job_id is required for unsave"}
        return await loop.run_in_executor(executor, lambda: conn.unsave_job(job_id=job_id))
    elif action == "get_applied":
        return await loop.run_in_executor(executor, lambda: conn.get_applied_jobs(start=start, limit=limit))
    elif action == "get_saved":
        return await loop.run_in_executor(executor, lambda: conn.get_saved_jobs(start=start, limit=limit))
    else:
        return {"success": False, "error": f"Unknown action: {action}"}


# ---------------------------------------------------------------------------
# META-TOOL 4: manage_profile
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_profile(
    connector: Literal["all", "naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"] = "naukri",
    action: Literal["get", "update_basic", "update_summary", "update_headline", "update_skills", "update_employment", "update_education", "touch_pulse", "sync_all"] = "get",
    fields: Optional[List[str]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Candidate profile management and cross-platform profile synchronization.

    Actions:
    - `get`: Retrieve current candidate profile from the specified platform.
    - `update_basic`: Update contact, name, or primary location details.
    - `update_summary`: Update candidate summary / executive bio.
    - `update_headline`: Update professional headline / designation.
    - `update_skills`: Add or update technical IT skills.
    - `update_employment`: Add or update current/past employment records.
    - `update_education`: Add or update degree, institute, and graduation records.
    - `touch_pulse`: Update candidate activity timestamp to boost recruiter search ranking.
    - `sync_all`: Cross-sync profile data or trigger activity pulses across all authenticated platforms.

    Args:
        connector: Target platform slug, or 'all' for cross-platform operations.
        action: Profile action to perform.
        fields: Specific profile fields to retrieve (for 'get').
        payload: Update parameters (e.g. {'summary': '...'}, {'skills': ['Python', 'FastAPI']}).
    """
    loop = asyncio.get_running_loop()

    if action == "sync_all" or (connector == "all" and action == "touch_pulse"):
        auth_conns = registry.get_authenticated()
        report: Dict[str, Any] = {}
        for name, c in auth_conns.items():
            try:
                if action == "touch_pulse":
                    res = await loop.run_in_executor(executor, lambda c=c: c.update_profile(action="touch_pulse"))
                    report[name] = {"success": True, "result": res}
                else:
                    res = await loop.run_in_executor(executor, lambda c=c: c.update_profile(action=action, payload=payload))
                    report[name] = {"success": True, "result": res}
            except Exception as e:
                report[name] = {"success": False, "error": str(e)}
        return {"mode": "sync_all", "action": action, "results": report}

    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    if action == "get":
        return await loop.run_in_executor(executor, lambda: conn.get_profile(fields=fields))
    else:
        return await loop.run_in_executor(
            executor,
            lambda: conn.update_profile(action=action, payload=payload)
        )


# ---------------------------------------------------------------------------
# META-TOOL 5: manage_account
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_account(
    connector: Literal["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"],
    action: Literal["recommendations", "recruiter_inbox", "alerts", "analytics", "salary_components", "blocked_companies", "block_company", "boards"] = "recommendations",
    company_name: Optional[str] = None,
    company_id: Optional[str] = None,
    board_token: Optional[str] = None,
    start: int = 0,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Account management, recruiter communication, recommendations, and employer privacy controls.

    Actions:
    - `recommendations`: Retrieve algorithmic job recommendations curated for candidate.
    - `recruiter_inbox`: View direct messages and interview invitations from recruiters.
    - `analytics`: View profile views, recruiter search appearances, and CV downloads.
    - `salary_components`: Inspect market salary benchmarks and pay insights.
    - `blocked_companies`: View list of employers blocked from viewing profile.
    - `block_company`: Prevent specific companies / current employers from accessing profile.
    - `boards`: View or configure tracked Greenhouse ATS job boards.

    Args:
        connector: Target platform slug ('naukri', 'hirist', 'wellfound', 'instahyre', 'cutshort', 'greenhouse', 'foundit').
        action: Account management action.
        company_name: Target company name for blocking/unblocking.
        company_id: Target company ID.
        board_token: Greenhouse company board slug.
        start: Pagination start offset.
        limit: Max records.
    """
    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        lambda: conn.manage_account(
            action=action,
            company_name=company_name,
            company_id=company_id,
            board_token=board_token,
            start=start,
            limit=limit,
        )
    )


# ---------------------------------------------------------------------------
# META-TOOL 6: manage_taxonomy
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_taxonomy(
    connector: Literal["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"] = "foundit",
    type: Literal["skills", "companies", "locations", "institutes", "designations"] = "skills",
    query: str = "Python",
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Centralized taxonomy search and autocomplete for standardized platform entities.

    Autocompletes verified skill keywords, registered company entities, standard city locations,
    and accredited educational institutions to ensure 100% ATS matching.

    Args:
        connector: Platform taxonomy to query ('foundit', 'naukri', 'hirist', 'instahyre').
        type: Taxonomy category ('skills', 'companies', 'locations', 'institutes', 'designations').
        query: Prefix or search query string (e.g. 'Pyth', 'Google', 'Pune').
        limit: Max autocomplete suggestions (default 10).
    """
    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor,
        lambda: conn.lookup_taxonomy(type_name=type, query=query, limit=limit)
    )


# ---------------------------------------------------------------------------
# META-TOOL 7: manage_session
# ---------------------------------------------------------------------------

@mcp.tool()
async def manage_session(
    connector: Literal["all", "naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"] = "all",
    action: Literal["status", "refresh", "set_token", "clear_cache"] = "status",
    tokens: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Unified authentication status dashboard, session renewal, and cache maintenance.

    Provides end-to-end visibility across all 7 platform connectors:
    - `status`: Comprehensive health check showing auth validity, user identity, and token expiry.
    - `refresh`: Attempt token renewal (e.g. Naukri access token from refresh token).
    - `clear_cache`: Purge in-memory TTLCache across servers and clients.

    Args:
        connector: 'all' for global report, or specific platform slug.
        action: 'status', 'refresh', 'set_token', or 'clear_cache'.
        tokens: Optional dictionary of tokens for runtime updates.
    """
    if action == "clear_cache":
        server_cache.clear()
        return {
            "success": True,
            "message": "OmniJob in-memory cache successfully cleared.",
        }

    if connector == "all":
        return registry.get_status_all()

    conn = registry.get(connector)
    if not conn:
        return {"success": False, "error": f"Unknown connector: {connector}"}

    if action == "refresh":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, lambda: conn.refresh_session())

    return conn.get_health().model_dump()


# ---------------------------------------------------------------------------
# SERVER APPLICATION BUILDER & RUNNER (Multi-Transport)
# ---------------------------------------------------------------------------

def get_app() -> Any:
    """Return unified Starlette app supporting both Streamable HTTP (/mcp) and SSE (/sse), with full CORS."""
    from starlette.applications import Starlette
    from starlette.middleware.cors import CORSMiddleware
    from starlette.routing import Route
    from mcp.server.transport_security import TransportSecuritySettings

    sec = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    sse_subapp = mcp.sse_app(transport_security=sec)
    http_subapp = mcp.streamable_http_app(streamable_http_path="/mcp", transport_security=sec)

    from typing import Callable

    http_handler: Optional[Callable[..., Any]] = None
    for r in http_subapp.routes:
        if getattr(r, "path", "") == "/mcp":
            ep = getattr(r, "endpoint", None)
            if callable(ep):
                http_handler = ep
            break

    sse_handler: Optional[Callable[..., Any]] = None
    for r in sse_subapp.routes:
        if getattr(r, "path", "") == "/sse":
            ep = getattr(r, "endpoint", None)
            if callable(ep):
                sse_handler = ep
            break

    if http_handler is None or sse_handler is None:
        raise RuntimeError("Failed to resolve MCP handler endpoints from sub-apps")

    routes = [
        Route("/sse", endpoint=sse_handler, methods=["GET", "HEAD"]),
        Route("/sse", endpoint=http_handler, methods=["POST"]),
        Route("/mcp", endpoint=http_handler, methods=["GET", "POST", "HEAD"]),
        Route("/", endpoint=http_handler, methods=["POST"]),
        *[r for r in sse_subapp.routes if getattr(r, "path", "") not in ("/sse", "/mcp")],
    ]

    unified_app = Starlette(
        routes=routes,
        lifespan=http_subapp.router.lifespan_context,
    )

    return CORSMiddleware(
        unified_app,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )


app = get_app()


def run_server(transport: str = "stdio", port: Optional[int] = None, host: str = "0.0.0.0") -> None:
    """Run the FastMCP server in either stdio, sse, or streamable-http mode."""
    if port is None:
        port = int(os.getenv("PORT", 8000))

    if transport == "sse":
        import uvicorn
        import anyio
        print(f"Starting omnijob-mcp in SSE mode on http://{host}:{port} ...")
        app_instance = get_app()
        config = uvicorn.Config(
            app_instance,
            host=host,
            port=port,
            log_level="info",
            timeout_keep_alive=65,
        )
        server = uvicorn.Server(config)
        anyio.run(server.serve)
    elif transport == "streamable-http":
        print(f"Starting omnijob-mcp in streamable-http mode on http://{host}:{port} ...")
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")

