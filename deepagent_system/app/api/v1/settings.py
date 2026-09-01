from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.infrastructure.db.hitl_repository import HitlRepository

router = APIRouter(prefix="/v1/settings", tags=["Settings"])

class ModeUpdateRequest(BaseModel):
    mode: str  # enforced or autonomous

@router.get("/hitl_mode")
async def get_hitl_mode():
    """Returns current system guardrail mode ('enforced' vs 'autonomous')."""
    try:
        mode = HitlRepository.get_guardrail_mode()
        return {"mode": mode}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch hitl_mode: {e}")

@router.post("/hitl_mode")
async def update_hitl_mode(req: ModeUpdateRequest):
    """Updates system guardrail mode."""
    target_mode = req.mode.strip().lower()
    if target_mode not in ["enforced", "autonomous"]:
        raise HTTPException(status_code=400, detail="Mode must be 'enforced' or 'autonomous'")
        
    try:
        success = HitlRepository.set_guardrail_mode(target_mode)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to persist setting in DB")
        return {"status": "success", "mode": target_mode}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update hitl_mode: {e}")

class SettingUpdateRequest(BaseModel):
    value: str

@router.get("/notification_email")
async def get_notification_email():
    """Returns configured SRE report recipient email."""
    try:
        email = HitlRepository.get_setting("notification_email", "fayez.soufyani@gmail.com")
        return {"email": email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notification_email: {e}")

@router.post("/notification_email")
async def update_notification_email(req: SettingUpdateRequest):
    """Updates SRE report recipient email in database."""
    email = req.value.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address format")
    try:
        success = HitlRepository.set_setting("notification_email", email)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to persist email in DB")
        return {"status": "success", "email": email}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update notification_email: {e}")

class DBCleanupRequest(BaseModel):
    purge_threads: bool = True
    purge_hitl: bool = True
    keep_days: int = 0  # 0 means purge all

@router.post("/db/cleanup")
async def cleanup_database_endpoint(req: DBCleanupRequest):
    """Purges old threads, message history, and HITL authorization audits based on retention policy."""
    try:
        from app.infrastructure.db.thread_repository import ThreadRepository
        stats = {
            "deleted_messages": 0,
            "deleted_threads": 0,
            "deleted_hitl_requests": 0,
            "retention_days": req.keep_days
        }

        if req.purge_threads:
            if req.keep_days > 0:
                t_stats = ThreadRepository.purge_older_than(req.keep_days)
            else:
                t_stats = ThreadRepository.purge_all()
            stats["deleted_messages"] = t_stats["deleted_messages"]
            stats["deleted_threads"] = t_stats["deleted_threads"]

        if req.purge_hitl:
            if req.keep_days > 0:
                h_count = HitlRepository.purge_older_than(req.keep_days)
            else:
                h_count = HitlRepository.purge_all()
            stats["deleted_hitl_requests"] = h_count

        return {"status": "success", "stats": stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database cleanup failed: {e}")

class SMTPSettingsRequest(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    sender_email: str = "deepagent-sre@enterprise.local"

@router.get("/smtp")
async def get_smtp_settings():
    """Returns configured SMTP relay configuration from PostgreSQL."""
    try:
        return {
            "smtp_host": HitlRepository.get_setting("smtp_host", "smtp.gmail.com"),
            "smtp_port": int(HitlRepository.get_setting("smtp_port", "587")),
            "smtp_user": HitlRepository.get_setting("smtp_user", ""),
            "sender_email": HitlRepository.get_setting("sender_email", "deepagent-sre@enterprise.local"),
            "is_configured": bool(HitlRepository.get_setting("smtp_user", ""))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch SMTP settings: {e}")

@router.post("/smtp")
async def update_smtp_settings(req: SMTPSettingsRequest):
    """Updates SMTP relay credentials in PostgreSQL."""
    try:
        HitlRepository.set_setting("smtp_host", req.smtp_host.strip())
        HitlRepository.set_setting("smtp_port", str(req.smtp_port))
        HitlRepository.set_setting("smtp_user", req.smtp_user.strip())
        if req.smtp_pass:
            HitlRepository.set_setting("smtp_pass", req.smtp_pass.strip())
        HitlRepository.set_setting("sender_email", req.sender_email.strip())
        return {"status": "success", "message": "SMTP settings saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save SMTP settings: {e}")

@router.post("/smtp/test")
async def test_smtp_connection(req: SMTPSettingsRequest):
    """Tests sending an actual test email via configured SMTP relay."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    recipient = HitlRepository.get_setting("notification_email", "fayez.soufyani@gmail.com")
    host = req.smtp_host.strip() or "smtp.gmail.com"
    port = req.smtp_port or 587
    user = req.smtp_user.strip()
    pwd = req.smtp_pass.strip() or HitlRepository.get_setting("smtp_pass", "")
    sender = req.sender_email.strip() or user or "deepagent-sre@enterprise.local"

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = "🧪 [Test] Deep Agent SMTP Verification"
    msg.attach(MIMEText(f"Hello,\n\nThis is a verification email from your Deep Agent system sent to {recipient}.\n\nTimestamp: {HitlRepository.get_setting('last_test', 'Now')}", "plain"))

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10.0)
        else:
            server = smtplib.SMTP(host, port, timeout=10.0)
            server.starttls()

        if user and pwd:
            server.login(user, pwd)

        server.send_message(msg)
        server.quit()
        return {"status": "success", "message": f"Test email successfully dispatched to {recipient}!"}
    except Exception as e:
        return {"status": "error", "message": f"SMTP delivery failed: {str(e)}"}

# --- AAP (Ansible Automation Platform) Settings Endpoints ---
class AAPSettingsRequest(BaseModel):
    backend_mode: str = "mock"  # "mock" or "prd"
    aap_host: str = "http://aap-server:5000"
    aap_token: Optional[str] = None
    verify_ssl: bool = False

@router.get("/aap")
async def get_aap_settings():
    """Returns current AAP connection credentials and backend mode from PostgreSQL."""
    try:
        mode = HitlRepository.get_setting("ansible_backend_mode", "mock")
        host = HitlRepository.get_setting("aap_host", "http://aap-server:5000")
        token = HitlRepository.get_setting("aap_token", "")
        verify_ssl = HitlRepository.get_setting("aap_verify_ssl", "false").lower() == "true"
        
        # Mask token for security
        masked_token = f"{token[:4]}••••{token[-4:]}" if len(token) > 8 else ("••••••••" if token else "")
        return {
            "backend_mode": mode,
            "aap_host": host,
            "aap_token_masked": masked_token,
            "is_token_set": bool(token),
            "verify_ssl": verify_ssl
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch AAP settings: {e}")

@router.post("/aap")
async def update_aap_settings(req: AAPSettingsRequest):
    """Updates AAP connection credentials in PostgreSQL."""
    try:
        HitlRepository.set_setting("ansible_backend_mode", req.backend_mode.strip().lower())
        HitlRepository.set_setting("aap_host", req.aap_host.strip())
        if req.aap_token is not None and req.aap_token.strip():
            HitlRepository.set_setting("aap_token", req.aap_token.strip())
        HitlRepository.set_setting("aap_verify_ssl", str(req.verify_ssl).lower())
        return {"status": "success", "message": "AAP connection credentials saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save AAP settings: {e}")

@router.post("/aap/test")
async def test_aap_connection(req: AAPSettingsRequest):
    """Tests live connection and token authentication against configured AAP instance."""
    import requests
    host = req.aap_host.strip() or HitlRepository.get_setting("aap_host", "http://aap-server:5000")
    token = req.aap_token.strip() if req.aap_token else HitlRepository.get_setting("aap_token", "mock-token-123")
    
    # Ensure protocol
    if not host.startswith("http://") and not host.startswith("https://"):
        protocol = "http" if "localhost" in host or "5000" in host else "https"
        url = f"{protocol}://{host}/api/v2/job_templates"
    else:
        url = f"{host.rstrip('/')}/api/v2/job_templates"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=8.0, verify=req.verify_ssl)
        if resp.status_code == 200:
            count = len(resp.json().get("results", []))
            return {
                "status": "success",
                "message": f"✓ Successfully connected to AAP! Found {count} registered Job Templates."
            }
        else:
            return {
                "status": "error",
                "message": f"AAP returned HTTP {resp.status_code}: {resp.text[:200]}"
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Connection to AAP host failed: {str(e)}"
        }

# --- Global LLM Provider & OpenAI-Compliant Gateways ---
class LLMProviderSettingsRequest(BaseModel):
    default_provider: str = "openrouter"  # "openrouter", "groq", "ollama", "custom_openai"
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "qwen/qwen-2.5-72b-instruct"
    groq_api_key: Optional[str] = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "qwen/qwen3.6-27b"
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "qwen2.5:3b"
    custom_openai_base_url: str = "https://api.openai.com/v1"
    custom_openai_api_key: Optional[str] = None
    custom_openai_model: str = "gpt-4o"

@router.get("/llm_providers")
async def get_llm_provider_settings():
    """Returns configured OpenAI-compatible LLM gateways from PostgreSQL."""
    try:
        from app.config import settings
        return {
            "default_provider": HitlRepository.get_setting("llm_default_provider", settings.llm_provider),
            "openrouter_base_url": HitlRepository.get_setting("openrouter_base_url", settings.openrouter_base_url),
            "openrouter_model": HitlRepository.get_setting("openrouter_model", settings.openrouter_model),
            "is_openrouter_set": bool(HitlRepository.get_setting("openrouter_api_key", settings.openrouter_api_key)),
            "groq_base_url": HitlRepository.get_setting("groq_base_url", settings.groq_base_url),
            "groq_model": HitlRepository.get_setting("groq_model", settings.groq_model),
            "is_groq_set": bool(HitlRepository.get_setting("groq_api_key", settings.groq_api_key)),
            "ollama_host": HitlRepository.get_setting("ollama_host", settings.ollama_host),
            "ollama_model": HitlRepository.get_setting("ollama_model", settings.ollama_model),
            "custom_openai_base_url": HitlRepository.get_setting("custom_openai_base_url", "https://api.openai.com/v1"),
            "custom_openai_model": HitlRepository.get_setting("custom_openai_model", "gpt-4o"),
            "is_custom_openai_set": bool(HitlRepository.get_setting("custom_openai_api_key", ""))
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch LLM settings: {e}")

@router.post("/llm_providers")
async def update_llm_provider_settings(req: LLMProviderSettingsRequest):
    """Saves global LLM gateway credentials and endpoints in PostgreSQL."""
    try:
        HitlRepository.set_setting("llm_default_provider", req.default_provider.strip().lower())
        HitlRepository.set_setting("openrouter_base_url", req.openrouter_base_url.strip())
        HitlRepository.set_setting("openrouter_model", req.openrouter_model.strip())
        if req.openrouter_api_key is not None and req.openrouter_api_key.strip():
            HitlRepository.set_setting("openrouter_api_key", req.openrouter_api_key.strip())

        HitlRepository.set_setting("groq_base_url", req.groq_base_url.strip())
        HitlRepository.set_setting("groq_model", req.groq_model.strip())
        if req.groq_api_key is not None and req.groq_api_key.strip():
            HitlRepository.set_setting("groq_api_key", req.groq_api_key.strip())

        HitlRepository.set_setting("ollama_host", req.ollama_host.strip())
        HitlRepository.set_setting("ollama_model", req.ollama_model.strip())

        HitlRepository.set_setting("custom_openai_base_url", req.custom_openai_base_url.strip())
        HitlRepository.set_setting("custom_openai_model", req.custom_openai_model.strip())
        if req.custom_openai_api_key is not None and req.custom_openai_api_key.strip():
            HitlRepository.set_setting("custom_openai_api_key", req.custom_openai_api_key.strip())

        return {"status": "success", "message": "LLM Provider configurations saved successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save LLM settings: {e}")
