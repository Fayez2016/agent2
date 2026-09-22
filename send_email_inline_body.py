#!/usr/bin/env python3
"""
================================================================================
 ✉️ Email Dispatcher with Embedded Inline Plain Text Script Content
================================================================================
 Dispatches operational scripts and reports directly to recipients via Resend.
 Supports both Resend REST API and Resend SMTP with automatic fallback.
================================================================================
"""

import os
import sys
import json
import argparse
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage

DEFAULT_RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
DEFAULT_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Deep Agent SRE <onboarding@resend.dev>")
DEFAULT_RECIPIENT = os.environ.get("NOTIFICATION_EMAIL", "fayez.soufyani@gmail.com")

def send_via_resend_api(api_key: str, from_addr: str, to_addr: str, cc_addr: str, subject: str, body_text: str) -> bool:
    """Dispatches email via Resend HTTPS API."""
    url = "https://api.resend.com/emails"
    recipients = [r.strip() for r in to_addr.split(",") if r.strip()]
    payload = {
        "from": from_addr,
        "to": recipients,
        "subject": subject,
        "text": body_text
    }
    if cc_addr:
        payload["cc"] = [c.strip() for c in cc_addr.split(",") if c.strip()]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "curl/7.88.1"
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"✓ Successfully sent email via Resend API! ID: {data.get('id')}")
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"⚠️ Resend REST API error ({e.code}): {err_body}")
        return False
    except Exception as e:
        print(f"⚠️ Resend REST API exception: {e}")
        return False

def send_via_resend_smtp(api_key: str, from_addr: str, to_addr: str, cc_addr: str, subject: str, body_text: str) -> bool:
    """Fallback: Dispatches email via Resend SMTP (smtp.resend.com:587)."""
    smtp_host = "smtp.resend.com"
    smtp_port = 587
    smtp_user = "resend"
    smtp_pass = api_key

    # Extract bare email for SMTP envelope if needed
    sender = from_addr
    if "<" in from_addr and ">" in from_addr:
        sender = from_addr.split("<")[1].split(">")[0].strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    if cc_addr:
        msg["Cc"] = cc_addr
    msg.set_content(body_text)

    try:
        print(f"⚡ Connecting to Resend SMTP {smtp_host}:{smtp_port} ...")
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            print(f"✓ Successfully sent email via Resend SMTP to {to_addr}!")
            return True
    except Exception as e:
        print(f"❌ Resend SMTP failed: {e}")
        return False

def sanitize_content(text: str) -> str:
    """
    Sanitizes email content to ensure enterprise privacy:
    - Masks company names (Aramco, etc.) -> enterprise
    - Masks private IPv4 addresses -> generic IP tokens
    - Replaces internal hostnames/servers (ps501484, cs-popcorn) -> generic nodes
    - Replaces employee / internal IDs (souffm0a) -> operator
    - Replaces internal domains -> enterprise.local
    """
    if not text:
        return ""
    import re
    s = re.sub(r'(?i)aramco\.com', 'enterprise.local', text)
    s = re.sub(r'(?i)aramco', 'enterprise', s)
    s = re.sub(r'\bps[0-9]{5,7}\b', 'rhel-node01', s)
    s = re.sub(r'\bcs-popcorn\b', 'node-primary', s)
    s = re.sub(r'\bsouffm0a\b', 'operator', s)
    s = re.sub(r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '10.x.x.x', s)
    s = re.sub(r'\b172\.(1[6-9]|2[0-9]|3[0-1])\.\d{1,3}\.\d{1,3}\b', '172.x.x.x', s)
    s = re.sub(r'\b192\.168\.\d{1,3}\.\d{1,3}\b', '192.168.x.x', s)
    return s

def main():
    parser = argparse.ArgumentParser(description="Send emails with embedded inline script content via Resend.")
    parser.add_argument("--to", default=DEFAULT_RECIPIENT, help="Recipient email address")
    parser.add_argument("--cc", default="", help="CC email address")
    parser.add_argument("--subject", default="Deep Agent - Script Content", help="Email subject")
    parser.add_argument("--script", required=True, help="Path to script to embed in body")
    parser.add_argument("--from-addr", default=DEFAULT_FROM_EMAIL, help="Sender email address")
    parser.add_argument("--resend-key", default=DEFAULT_RESEND_API_KEY, help="Resend API Key")
    parser.add_argument("--outbox", default="/home/fayez/agent2/patch_outbox", help="Directory to save .eml copy")

    args = parser.parse_args()

    if not os.path.isfile(args.script):
        print(f"❌ Error: Script file not found at {args.script}")
        sys.exit(1)

    with open(args.script, "r", encoding="utf-8", errors="replace") as f:
        script_code = f.read()

    script_name = os.path.basename(args.script)

    raw_body = f"""Hello,

Please find the requested operational script below.

================================================================================
SCRIPT: {script_name}
================================================================================

{script_code}

================================================================================
End of script content.
"""

    # Apply automated sanitization to prevent leakage of internal corporate data/IPs
    clean_subject = sanitize_content(args.subject)
    clean_body = sanitize_content(raw_body)

    msg = EmailMessage()
    msg["Subject"] = clean_subject
    msg["From"] = args.from_addr
    msg["To"] = args.to
    if args.cc:
        msg["Cc"] = args.cc
    msg.set_content(clean_body)

    print("================================================================================")
    print(" ✉️ SEND EMAIL WITH EMBEDDED PLAIN TEXT SCRIPT VIA RESEND (SANITIZED)")
    print(f" 📧 Recipient : {args.to}")
    print(f" 📋 CC        : {args.cc}")
    print(f" 📝 Subject   : {clean_subject}")
    print(f" 📄 Script    : {script_name} ({len(script_code)} bytes)")
    print(" 🔒 Privacy   : Company names, internal IPs, and hostnames masked.")
    print("================================================================================")

    # 1. Try Resend API first
    success = send_via_resend_api(
        api_key=args.resend_key,
        from_addr=args.from_addr,
        to_addr=args.to,
        cc_addr=args.cc,
        subject=clean_subject,
        body_text=clean_body
    )

    # 2. Fallback to Resend SMTP if API fails
    if not success:
        print("🔄 Trying fallback to Resend SMTP...")
        success = send_via_resend_smtp(
            api_key=args.resend_key,
            from_addr=args.from_addr,
            to_addr=args.to,
            cc_addr=args.cc,
            subject=clean_subject,
            body_text=clean_body
        )

    # 3. Always save outbox copy
    os.makedirs(args.outbox, exist_ok=True)
    outbox_file = os.path.join(args.outbox, f"sent_{script_name}.eml")
    with open(outbox_file, "wb") as f:
        f.write(msg.as_bytes())

    if success:
        print(f"✓ Email successfully delivered to {args.to}!")
    else:
        print(f"⚠️ Could not deliver email online. Message saved to outbox: {outbox_file}")

if __name__ == "__main__":
    main()
