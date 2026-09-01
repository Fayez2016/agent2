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
