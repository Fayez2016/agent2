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

    # Determine body content
    body_content = args.body
    if os.path.isfile(args.body):
        with open(args.body, "r", encoding="utf-8", errors="ignore") as f:
            body_content = f.read()

    msg = EmailMessage()
    msg["Subject"] = args.subject
    msg["From"] = args.from_addr
    msg["To"] = args.to
    msg.set_content(body_content)

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

    # Attempt local SMTP dispatch or save to outbox
    sent = False
    try:
        with smtplib.SMTP("localhost", 25, timeout=5) as s:
            s.send_message(msg)
            sent = True
            print(f"\n✓ Successfully sent email with {attached_count} attachment(s) via SMTP to {args.to}")
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
