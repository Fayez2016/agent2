#!/usr/bin/env python3
"""
================================================================================
 ✉️ General-Purpose Email Dispatcher with File Attachments
================================================================================
 Usage:
   python3 send_email_with_attachments.py \
       --to fayez.soufyani@gmail.com \
       --subject "Subject Title" \
       --body "Message body content or file path" \
       --attach /path/to/file1 /path/to/file2 ...
================================================================================
"""

import os
import sys
import argparse
import mimetypes
import smtplib
from email.message import EmailMessage

def main():
    parser = argparse.ArgumentParser(description="Send emails with arbitrary file attachments.")
    parser.add_argument("--to", required=True, help="Recipient email address (e.g. user@gmail.com)")
    parser.add_argument("--subject", default="Deep Agent System Dispatch", help="Email subject")
    parser.add_argument("--body", default="Please find the attached files.", help="Email body text or path to text file")
    parser.add_argument("--attach", nargs="+", default=[], help="List of file paths to attach")
    parser.add_argument("--from-addr", default="deepagent@local.corp", help="Sender email address")
    parser.add_argument("--outbox", default="/home/fayez/agent2/patch_outbox", help="Directory to save .eml bundle if SMTP relay is offline")

    args = parser.parse_args()

def sanitize_content(text: str) -> str:
    """Sanitizes email content to ensure corporate privacy."""
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

    # Determine body content
    body_content = args.body
    if os.path.isfile(args.body):
        with open(args.body, "r", encoding="utf-8", errors="ignore") as f:
            body_content = f.read()

    clean_subject = sanitize_content(args.subject)
    clean_body = sanitize_content(body_content)

    msg = EmailMessage()
    msg["Subject"] = clean_subject
    msg["From"] = args.from_addr
    msg["To"] = args.to
    msg.set_content(clean_body)

    print("================================================================================")
    print(" ✉️ GENERAL-PURPOSE EMAIL & ATTACHMENT DISPATCHER")
    print(f" 📧 Recipient : {args.to}")
    print(f" 📝 Subject   : {args.subject}")
    print("================================================================================")

    # Process attachments
    attached_count = 0
    for file_path in args.attach:
        if not os.path.exists(file_path):
            print(f"  ⚠️ Warning: File not found, skipping: {file_path}")
            continue

        file_size = os.path.getsize(file_path)
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            maintype, subtype = "application", "octet-stream"
        else:
            maintype, subtype = mime_type.split("/", 1)

        filename = os.path.basename(file_path)
        print(f"  📎 Attaching: {filename} ({file_size / 1024:.1f} KB) [{maintype}/{subtype}]")

        with open(file_path, "rb") as f:
            file_data = f.read()
            msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=filename)
        attached_count += 1

    # Attempt dispatch via Resend SMTP or local relay
    sent = False
    resend_key = os.environ.get("RESEND_API_KEY", "")
    
    # 1. Try Resend SMTP first
    try:
        msg["From"] = "Deep Agent SRE <onboarding@resend.dev>"
        with smtplib.SMTP("smtp.resend.com", 587, timeout=20) as s:
            s.starttls()
            s.login("resend", resend_key)
            s.send_message(msg)
            sent = True
            print(f"\n✓ Successfully sent email with {attached_count} attachment(s) via Resend SMTP to {args.to}")
    except Exception as e:
        print(f"  ℹ️ Resend SMTP attempt note: {e}")

    # 2. Try local SMTP if Resend failed
    if not sent:
        try:
            with smtplib.SMTP("localhost", 25, timeout=5) as s:
                s.send_message(msg)
                sent = True
                print(f"\n✓ Successfully sent email with {attached_count} attachment(s) via local SMTP to {args.to}")
        except Exception:
            pass

    # Save to outbox
    os.makedirs(args.outbox, exist_ok=True)
    outbox_file = os.path.join(args.outbox, f"dispatch_{filename if attached_count > 0 else 'msg'}.eml")
    with open(outbox_file, "wb") as f:
        f.write(msg.as_bytes())

    if not sent:
        print(f"\n  ℹ️ SMTP Relay Offline.")
        print(f"  📦 Full RFC-5322 EML Message with {attached_count} attachment(s) saved to:")
        print(f"     {outbox_file}")

    print("================================================================================")

if __name__ == "__main__":
    main()
