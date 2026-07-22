import os
import sys
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import subprocess
import logging

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def send_to_recipients(html_content, subject):
    if not os.path.exists("recipients.txt"):
        logging.error("recipients.txt not found.")
        return False
        
    with open("recipients.txt", "r") as f:
        recipients = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        
    if not recipients:
        logging.warning("No recipients found in recipients.txt.")
        return False

    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")
    
    if not user or not password:
        logging.error("Gmail credentials missing. Cannot send emails.")
        return False
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    # Do not set To to all recipients to avoid exposing addresses. Use Bcc.
    msg["To"] = user
    
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        logging.info("Connecting to Gmail SMTP...")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=15)
        server.starttls()
        server.login(user, password)
        
        logging.info(f"Sending email to {len(recipients)} recipients via BCC...")
        # Send from user to all recipients
        server.sendmail(user, [user] + recipients, msg.as_string())
        server.quit()
        logging.info("Emails sent successfully.")
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False

def commit_and_push_state():
    try:
        logging.info("Committing and pushing state...")
        subprocess.run(["git", "pull", "--rebase"], check=True)
        subprocess.run(["git", "add", "data/", "drafts/"], check=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if status.stdout.strip():
            subprocess.run(["git", "commit", "-m", "chore: update state and drafts after sending"], check=True)
            subprocess.run(["git", "push"], check=True)
            logging.info("State committed and pushed successfully.")
        else:
            logging.info("No state changes to commit.")
    except subprocess.CalledProcessError as e:
        logging.error(f"Git operation failed: {e}")

def update_seen_items(date_str):
    draft_json_path = f"drafts/{date_str}.json"
    seen_items_path = "data/seen_items.json"
    
    if not os.path.exists(draft_json_path):
        logging.error(f"Draft JSON not found: {draft_json_path}. Cannot update seen items.")
        return
        
    with open(draft_json_path, "r", encoding="utf-8") as f:
        draft_items = json.load(f)
        
    seen_urls = set()
    if os.path.exists(seen_items_path):
        with open(seen_items_path, "r", encoding="utf-8") as f:
            seen_urls = set(json.load(f))
            
    for item in draft_items:
        url = item.get("url")
        if url:
            seen_urls.add(url)
            
    with open(seen_items_path, "w", encoding="utf-8") as f:
        json.dump(list(seen_urls), f, indent=2)
    logging.info(f"Updated {seen_items_path} with {len(draft_items)} sent items.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python approve_and_send.py drafts/<date>.html")
        sys.exit(1)
        
    draft_path = sys.argv[1]
    if not os.path.exists(draft_path):
        logging.error(f"Draft file not found: {draft_path}")
        sys.exit(1)
        
    with open(draft_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # Extract date from filename
    filename = os.path.basename(draft_path)
    date_str = filename.replace(".html", "")
    
    subject = f"AI Builders Newsletter - {date_str}"
    
    if os.getenv("DRY_RUN", "false").lower() != "true":
        success = send_to_recipients(html_content, subject)
        if success:
            update_seen_items(date_str)
            commit_and_push_state()
    else:
        logging.info("DRY_RUN is enabled. Not sending emails or pushing state.")

if __name__ == "__main__":
    main()
