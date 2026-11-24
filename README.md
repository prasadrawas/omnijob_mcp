# 🌐 OmniJob MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP Spec](https://img.shields.io/badge/MCP-1.0+-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Railway Ready](https://img.shields.io/badge/Deploy-Railway-purple.svg)](https://railway.app/)

**OmniJob MCP** is a unified, production-grade **Model Context Protocol (MCP)** server consolidating **7 major job search platforms and ATS systems** into a single container:

1. **Naukri.com** (`naukri`) - India's leading job portal (1-click apply, profile management, recruiter analytics)
2. **Hirist.tech** (`hirist`) - Tech & startup ecosystem jobs (Gladiator microservices gateway)
3. **Wellfound / AngelList** (`wellfound`) - Global startup engineering & AI roles
4. **Instahyre** (`instahyre`) - AI-driven inbound talent platform
5. **Cutshort.io** (`cutshort`) - Verified direct recruiter networking & opportunities
6. **Greenhouse ATS** (`greenhouse`) - Direct ATS job board search & candidate applications
7. **Foundit / Monster APAC** (`foundit`) - Monster India/Southeast Asia job board

---

## 💡 Why OmniJob MCP?

| Challenge | Standalone MCPs (7 Separate Servers) | OmniJob MCP (Unified Server) |
|---|---|---|
| **Railway Hosting Limits** | Requires 7 independent containers (exceeds free tier limits) | **Runs in a single Docker container / service** |
| **Tool Registry Bloat** | 50+ individual tools registered in Claude / Cursor (causing LLM hallucination) | **Exactly 7 Standardized Meta-Tools** |
| **Cross-Platform Search** | Must prompt LLM to call 7 different tools sequentially | **Single tool call `search_jobs(connector='all')` with concurrent fan-out** |
| **Profile Synchronization** | Manual updates platform by platform | **Unified `manage_profile(action='sync_all')` cross-sync** |
| **Session Maintenance** | 7 different status checks and auth monitors | **Unified `/health` route & `manage_session(action='status')` dashboard** |

---

## 🏛️ Connector Architecture

OmniJob MCP implements the **Connector Design Pattern** (Strategy / Adapter pattern). Each platform is isolated into its own self-contained module implementing the `BaseConnector` interface:

```mermaid
flowchart TD
    LLM["AI Client (Claude / Cursor / Gemini)"] --> FastMCP["FastMCP Server (omnijob_mcp)"]
    
    subgraph MetaTools ["7 Unified Meta-Tools"]
        T1["search_jobs"]
        T2["get_job_details"]
        T3["manage_job_pipeline"]
        T4["manage_profile"]
        T5["manage_account"]
        T6["manage_taxonomy"]
        T7["manage_session"]
    end

    FastMCP --> MetaTools
    MetaTools --> Dispatcher["Connector Registry & Dispatcher"]

    subgraph Connectors ["Platform Connectors (BaseConnector)"]
        C1["NaukriConnector"]
        C2["HiristConnector"]
        C3["WellfoundConnector"]
        C4["InstahyreConnector"]
        C5["CutshortConnector"]
        C6["GreenhouseConnector"]
        C7["FounditConnector"]
    end

    Dispatcher -->|connector='naukri'| C1
    Dispatcher -->|connector='hirist'| C2
    Dispatcher -->|connector='wellfound'| C3
    Dispatcher -->|connector='instahyre'| C4
    Dispatcher -->|connector='cutshort'| C5
    Dispatcher -->|connector='greenhouse'| C6
    Dispatcher -->|connector='foundit'| C7
    Dispatcher -->|connector='all' (concurrent asyncio.gather)| Connectors
```

---

## 🛠️ The 7 Standardized Meta-Tools

### 1. `search_jobs`
Search across any individual platform or fan-out concurrently across all 7 platforms:
```json
{
  "connector": "all",
  "query": "Staff Python Engineer",
  "location": "Pune",
  "experience": 5,
  "limit": 10
}
```
*Supported connectors:* `"all"`, `"naukri"`, `"hirist"`, `"wellfound"`, `"instahyre"`, `"cutshort"`, `"greenhouse"`, `"foundit"`.

### 2. `get_job_details`
Inspect comprehensive job descriptions, qualifications, company info, and dynamic screening questionnaire schema:
```json
{
  "connector": "foundit",
  "job_id": "12345678"
}
```

### 3. `manage_job_pipeline`
Handle applications, eligibility pre-checks, bookmarks, and tracking:
```json
{
  "connector": "naukri",
  "action": "apply",
  "job_id": "010124001234",
  "answers": {"expected_ctc": "2500000", "notice_period": "30 days"},
  "dry_run": false
}
```
*Actions:* `can_apply`, `apply`, `save`, `unsave`, `get_applied`, `get_saved`.

### 4. `manage_profile`
View or update candidate profiles, update IT skills, pulse activity timestamps, or synchronize across platforms:
```json
{
  "connector": "foundit",
  "action": "update_summary",
  "payload": {"summary": "Senior Software Engineer with 5+ years building scalable distributed microservices."}
}
```
*Actions:* `get`, `update_basic`, `update_summary`, `update_headline`, `update_skills`, `update_employment`, `update_education`, `touch_pulse`, `sync_all`.

### 5. `manage_account`
Recruiter interactions, alerts, recommendations, and employer privacy controls:
```json
{
  "connector": "cutshort",
  "action": "recruiter_inbox"
}
```
*Actions:* `recommendations`, `recruiter_inbox`, `alerts`, `analytics`, `salary_components`, `blocked_companies`, `block_company`, `boards`.

### 6. `manage_taxonomy`
Centralized autocomplete for ATS-recognized skills, registered companies, cities, and universities:
```json
{
  "connector": "foundit",
  "type": "skills",
  "query": "FastAPI",
  "limit": 5
}
```
*Types:* `skills`, `companies`, `locations`, `institutes`, `designations`.

### 7. `manage_session`
Unified authentication status dashboard and cache maintenance:
```json
{
  "connector": "all",
  "action": "status"
}
```
*Actions:* `status`, `refresh`, `set_token`, `clear_cache`.

---

## 🚀 Deployment Guide

### Option 1: Railway (Recommended - Single Service)

1. Fork or clone this repository to GitHub: `https://github.com/prasadrawas/omnijob_mcp`.
2. In [Railway.app](https://railway.app), create a **New Project** -> **Deploy from GitHub repo** -> select `omnijob_mcp`.
3. In **Settings** -> **Variables**, add your session tokens from `.env.example`.
4. Railway will automatically build the `Dockerfile` and expose the service.
5. In your MCP Client (Claude Desktop / Cursor), connect to your Railway SSE endpoint:
   ```
   https://your-omnijob-app.up.railway.app/sse
   ```

### Option 2: Docker Container

```bash
# Build Docker image
docker build -t omnijob-mcp .

# Run with .env credentials
docker run -d --name omnijob-mcp -p 8000:8000 --env-file .env omnijob-mcp
```

Test health:
```bash
curl http://localhost:8000/health
```

### Option 3: Local Stdio (Claude Desktop / Cursor)

Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "omnijob": {
      "command": "python",
      "args": ["-m", "omnijob_mcp", "--transport", "stdio"],
      "cwd": "/path/to/omnijob_mcp",
      "env": {
        "NAUK_RT": "...",
        "FOUNDIT_MSSOAT": "...",
        "HIRIST_CK1": "...",
        "INSTAHYRE_SESSIONID": "..."
      }
    }
  }
}
```

---

## 🧪 Testing

Run the automated test suite (unit + live integration):
```bash
python3 -m unittest discover -s omnijob_mcp/tests -v
```

---

## 📄 License

MIT License © 2026 Prasad Rawas.
