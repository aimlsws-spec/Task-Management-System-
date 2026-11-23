import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.modules.ai.models import CompanyKnowledge

log = logging.getLogger(__name__)

# Standard technical, business, HR, and enterprise domain vocabulary known out-of-the-box
GENERIC_TECH_VOCABULARY = {
    "hrms", "tms", "crm", "erp", "pos", "cms", "ui", "ux", "api", "rest", "graphql",
    "auth", "authentication", "authorization", "login", "logout", "signin", "signup",
    "oauth", "oauth2", "jwt", "token", "refresh_token", "password", "reset_password",
    "database", "sql", "mysql", "postgres", "mongodb", "redis", "schema", "table",
    "frontend", "backend", "fullstack", "server", "client", "website", "web", "app",
    "mobile", "ios", "android", "flutter", "react", "vue", "angular", "node", "python",
    "payment", "gateway", "stripe", "razorpay", "paypal", "checkout", "cart", "invoice",
    "billing", "subscription", "pricing", "order", "shipping", "ecommerce",
    "bug", "fix", "issue", "error", "crash", "hotfix", "patch", "regression",
    "feature", "enhancement", "improvement", "refactor", "migration", "redesign",
    "dashboard", "panel", "admin", "portal", "profile", "account", "settings",
    "notification", "email", "sms", "push", "smtp", "otp", "verify", "verification",
    "role", "permission", "rbac", "access", "policy", "security", "encryption",
    "report", "analytics", "metrics", "export", "import", "download", "upload",
    "excel", "csv", "pdf", "audit", "log", "tracking", "history", "search", "filter",
    "sort", "pagination", "table", "list", "grid", "card", "modal", "dialog", "drawer",
    "navbar", "header", "footer", "sidebar", "menu", "tab", "button", "input", "form",
    "responsive", "dark_mode", "light_mode", "theme", "layout", "performance", "cache",
    "optimization", "latency", "load_testing", "docker", "kubernetes", "ci_cd", "deploy",
    "deployment", "pipeline", "git", "github", "gitlab", "branch", "testing", "test",
    "qa", "unit_test", "integration_test", "e2e", "manual_testing", "smoke_test",
    # HR & Business enterprise terms
    "attendance", "leave", "holiday", "shift", "roster", "timesheet", "payroll",
    "salary", "payslip", "bonus", "tax", "deduction", "reimbursement", "compliance",
    "onboarding", "offboarding", "recruitment", "applicant", "interview", "candidate",
    "resume", "hiring", "appraisal", "performance", "kpi", "okr", "goal", "review",
    "promotion", "transfer", "department", "designation", "hierarchy", "employee",
    "staff", "manager", "executive", "lead", "head", "subhead", "contractor", "vendor",
    "client", "customer", "lead", "deal", "pipeline", "inventory", "stock", "sales",
    "purchase", "receipt", "ledger", "voucher", "expense", "finance", "catalog",
    "product", "category", "brand", "discount", "coupon", "ticket", "helpdesk",
    "support", "feedback", "chat", "message", "comment", "file", "document",
    "calendar", "schedule", "kanban", "board", "module", "deadline", "priority",
}

COMMON_STOP_WORDS = {
    "the", "a", "an", "for", "in", "on", "at", "to", "of", "and", "or", "with", "by",
    "from", "up", "down", "new", "add", "create", "make", "update", "edit", "change",
    "changes", "fix", "fixes", "remove", "delete", "implement", "implementation",
    "support", "setup", "integrate", "integration", "enhancement", "redesign", "review",
    "verify", "verification", "check", "page", "screen", "view", "component", "button",
    "flow", "task", "project", "work", "system", "management", "service", "module",
    "all", "user", "users", "employee", "employees", "team", "first", "last",
    "details", "note", "notes", "information", "info", "data", "item", "items",
}


def _is_recognized_word(word: str) -> bool:
    clean = word.strip().lower()
    if clean in GENERIC_TECH_VOCABULARY or clean in COMMON_STOP_WORDS:
        return True
    # Strip basic English suffixes (plurals, verb tenses)
    for suffix in ("s", "es", "ed", "ing", "tion", "ment"):
        if clean.endswith(suffix):
            base = clean[:-len(suffix)]
            if base in GENERIC_TECH_VOCABULARY or base in COMMON_STOP_WORDS:
                return True
    return False


def detect_unknown_entity(title: str, known_entities: list[CompanyKnowledge]) -> str | None:
    """Analyze the title for potentially unrecognized company-specific brand names or products (e.g. 'Elala').
    Returns the unknown entity name if found, else None if the title is generic or understood."""
    known_keys = {ent.entity_key for ent in known_entities}
    known_names = {ent.entity_name.lower() for ent in known_entities}

    # Extract words (keeping alphanumeric tokens)
    tokens = re.findall(r"\b[A-Za-z0-9_-]+\b", title)
    for token in tokens:
        clean = token.strip().lower()
        if len(clean) <= 1 or clean.isdigit():
            continue
        # If it matches known company entity, it's known!
        if clean in known_keys or clean in known_names:
            continue
        # If it's a recognized generic word or stop word, skip
        if _is_recognized_word(clean):
            continue
        # If token is capitalized or an unfamiliar acronym/name, candidate unknown entity!
        if token[0].isupper() or len(token) >= 3:
            return token.capitalize()
    return None


def _build_prompt(
    title: str,
    target_type: str,
    priority: str | None,
    department: str | None,
    known_context: str | None,
) -> tuple[str, str]:
    """Build standardized system and user prompts to guarantee identical output structure across all LLMs."""
    system_prompt = (
        "You are an expert technical project manager and software architect for an enterprise Task Management System.\n"
        "Your task is to generate professional, crisp, and actionable task/project details based on the title and context provided.\n"
        "You MUST respond ONLY with a valid JSON object matching this schema exactly:\n"
        "{\n"
        '  "description": "Markdown formatted string containing: ### Objective\\n...\\n\\n### Key Scope\\n- ...\\n\\n### Acceptance Criteria\\n- [ ] ...",\n'
        '  "special_note": "Concise text containing technical edge cases, QA testing precautions, and security/performance considerations."\n'
        "}\n"
        "Do NOT include any preamble, conversational remarks, or text outside the JSON object."
    )

    context_lines = [
        f"Item Type: {target_type.capitalize()}",
        f"Title: {title}",
    ]
    if department:
        context_lines.append(f"Department: {department}")
    if priority:
        context_lines.append(f"Priority: {priority.capitalize()}")
    if known_context:
        context_lines.append(f"Company & Product Context: {known_context}")

    user_prompt = (
        "Generate the description and special note for the following item:\n"
        + "\n".join(context_lines)
        + "\n\nProvide clear objective, bulleted deliverables, acceptance criteria for QA, and crucial precautions in special note."
    )
    return system_prompt, user_prompt


def _parse_llm_json(raw_text: str | None) -> dict[str, str] | None:
    """Safely extracts JSON from LLM output even if surrounded by markdown code blocks."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    text = raw_text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    else:
        # Check if text contains a raw JSON object
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            text = text[brace_start:brace_end + 1].strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "description" in data:
            return {
                "description": str(data.get("description", "")).strip(),
                "special_note": str(data.get("special_note", "")).strip(),
            }
    except Exception as e:
        log.warning("Failed to parse JSON from LLM: %s | text: %s", e, text[:200])
    return None


def call_gemini_api(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    model: str = "gemini-3.5-flash",
) -> dict[str, str] | None:
    """Call Google Gemini Free API directly."""
    if not api_key:
        return None

    # Try configured model, fallback to gemini-3-flash-preview
    models_to_try = [model]
    if "gemini-3-flash-preview" not in models_to_try:
        models_to_try.append("gemini-3-flash-preview")

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }

    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        try:
            with httpx.Client(timeout=12.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    body = resp.json()
                    candidates = body.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            res = _parse_llm_json(parts[0].get("text", ""))
                            if res:
                                return res
                else:
                    log.warning("Gemini API (%s) error %s: %s", m, resp.status_code, resp.text[:150])
        except Exception as e:
            log.warning("Gemini API (%s) request failed: %s", m, e)
    return None


def call_openrouter_api(
    system_prompt: str,
    user_prompt: str,
    api_key: str,
    models_csv: str,
) -> dict[str, str] | None:
    """Call OpenRouter Free Model Pool with auto-fallback."""
    if not api_key:
        return None
    models = [m.strip() for m in models_csv.split(",") if m.strip()]
    if not models:
        models = [
            "openrouter/free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-3.5-lightning:free",
        ]

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://seawindsolution.com/tms",
        "X-Title": "SeaWind TMS AI Assistant",
    }
    payload = {
        "models": models,
        "route": "fallback",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 2048,
    }
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                body = resp.json()
                choices = body.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content")
                    if content:
                        return _parse_llm_json(content)
            else:
                log.warning("OpenRouter error status %s: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        log.warning("OpenRouter request failed: %s", e)
    return None


def generate_smart_heuristic(
    title: str,
    target_type: str,
    priority: str | None,
    department: str | None,
    known_context: str | None,
) -> dict[str, str]:
    """Smart technical deterministic generator when external LLM APIs are offline/unconfigured.
    Always succeeds instantly with 0 external dependencies."""
    title_clean = title.strip()
    title_lower = title_clean.lower()

    # Determine domain focus
    domain = "General Technical Task"
    if any(k in title_lower for k in ("ui", "ux", "design", "css", "layout", "responsive", "frontend")):
        domain = "Frontend & User Interface"
    elif any(k in title_lower for k in ("api", "backend", "database", "sql", "migration", "service")):
        domain = "Backend Architecture & API"
    elif any(k in title_lower for k in ("auth", "login", "signup", "jwt", "otp", "security")):
        domain = "Authentication & Security"
    elif any(k in title_lower for k in ("bug", "fix", "issue", "crash", "error", "patch")):
        domain = "Bug Resolution & Stability"
    elif any(k in title_lower for k in ("hrms", "payroll", "attendance", "employee")):
        domain = "HR Management System (HRMS)"
    elif any(k in title_lower for k in ("tms", "task", "project", "kanban")):
        domain = "Task Management System (TMS)"
    elif any(k in title_lower for k in ("payment", "checkout", "cart", "gateway")):
        domain = "Payment & Checkout Integration"

    context_str = f" for **{known_context}**" if known_context else ""

    description = (
        f"### Objective\n"
        f"Implement and verify {title_clean}{context_str} within the {domain} scope, ensuring high quality, modular structure, and adherence to company coding standards.\n\n"
        f"### Scope of Work\n"
        f"- Analyze requirements and verify interface contracts for `{title_clean}`.\n"
        f"- Implement core functionality and handle edge cases across desktop and mobile devices.\n"
        f"- Integrate error handling, user feedback states, and validation rules.\n"
        f"- Document changes and coordinate with the team for review.\n\n"
        f"### Acceptance Criteria\n"
        f"- [ ] Implementation satisfies all functional requirements specified in `{title_clean}`.\n"
        f"- [ ] Verified with zero runtime errors, responsive layout, and clean logging.\n"
        f"- [ ] QA testing completed and signed off without regressions in existing flows."
    )

    special_note = (
        f"Ensure complete regression testing before marking as complete. "
        f"Verify cross-device responsiveness, boundary conditions, and backward compatibility. "
        f"If database schema or API endpoints are modified, notify the QA and backend team."
    )

    return {
        "description": description,
        "special_note": special_note,
    }


def generate_recommendation(
    title: str,
    target_type: str = "task",
    priority: str | None = None,
    department: str | None = None,
    known_entities: list[CompanyKnowledge] | None = None,
) -> dict[str, Any]:
    """Top-level recommendation orchestrator with unknown entity challenge and dual cloud-free fallback."""
    known_entities = known_entities or []

    # 1. Check if the title mentions any known company entities
    matched_known = []
    for ent in known_entities:
        if ent.entity_key in title.lower() or ent.entity_name.lower() in title.lower():
            matched_known.append(f"{ent.entity_name}: {ent.description}")

    known_context = "; ".join(matched_known) if matched_known else None

    # 2. Check for unknown brand/project name (like "Elala") if not already matched
    if not known_context:
        unknown = detect_unknown_entity(title, known_entities)
        if unknown:
            return {
                "status": "NEEDS_CONTEXT",
                "missing_entity": unknown,
                "prompt_question": f"We haven't seen '{unknown}' before. What is it? (e.g. mobile app, internal portal, client)",
                "suggestions": None,
            }

    # 3. Context is ready! Build prompts
    sys_prompt, user_prompt = _build_prompt(
        title=title,
        target_type=target_type,
        priority=priority,
        department=department,
        known_context=known_context,
    )

    settings = get_settings()
    out = None

    # Priority 1: Google Gemini Free API (if key configured)
    if settings.gemini_api_key:
        out = call_gemini_api(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            api_key=settings.gemini_api_key,
            model=settings.ai_gemini_model,
        )

    # Priority 2: OpenRouter Free Models Pool (fallback or primary if OpenRouter key is set)
    if not out and settings.openrouter_api_key:
        out = call_openrouter_api(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            api_key=settings.openrouter_api_key,
            models_csv=settings.ai_openrouter_models,
        )

    # Priority 3: Smart Technical Heuristic Fallback (zero downtime)
    if not out:
        out = generate_smart_heuristic(
            title=title,
            target_type=target_type,
            priority=priority,
            department=department,
            known_context=known_context,
        )

    return {
        "status": "READY",
        "missing_entity": None,
        "prompt_question": None,
        "suggestions": out,
    }
