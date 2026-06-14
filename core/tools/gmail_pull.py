import os
import base64
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

def get_gmail_service(credentials_path="credentials.json", token_path="token.json"):
    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def get_emails(service, max_results=10, query=""):
    results = service.users().messages().list(
        userId="me", maxResults=max_results, q=query
    ).execute()

    messages = results.get("messages", [])
    emails = []

    for msg in messages:
        full_msg = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = full_msg["payload"].get("headers", [])
        header_map = {h["name"]: h["value"] for h in headers}
        body = extract_body(full_msg["payload"])

        emails.append({
            "id": msg["id"],
            "subject": header_map.get("Subject", "(no subject)"),
            "from": header_map.get("From", ""),
            "date": header_map.get("Date", ""),
            "snippet": full_msg.get("snippet", ""),
            "body": body,
        })

    return emails

def extract_body(payload):
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            body += extract_body(part)
    else:
        mime_type = payload.get("mimeType", "")
        data = payload.get("body", {}).get("data", "")
        if mime_type == "text/plain" and data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body

def clean_text(text):
    return text.encode('ascii', 'ignore').decode('ascii')

def display_emails(emails):
    for i, email in enumerate(emails, 1):
        print(f"\n{'='*60}")
        print(f"[{i}] {clean_text(email['subject'])}")
        print(f"    From : {clean_text(email['from'])}")
        print(f"    Date : {clean_text(email['date'])}")
        print(f"    Preview: {clean_text(email['snippet'][:100])}...")

def get_unread_emails(service, max_results=10):
    return get_emails(service, max_results=max_results, query="is:unread")

def get_emails_by_date(service, start_date, end_date, max_results=10):
    query = f"after:{start_date} before:{end_date}"
    return get_emails(service, max_results=max_results, query=query)

def get_latest_emails(service, n=10):
    return get_emails(service, max_results=n)

def get_emails_by_sender(service, sender_email, max_results=10):
    query = f"from:{sender_email}"
    return get_emails(service, max_results=max_results, query=query)

if __name__ == "__main__":
    service = get_gmail_service()
    
    print("1. Fetching unread emails (up to 5)...")
    display_emails(get_unread_emails(service, max_results=5))

    print("\n2. Fetching emails between 2024/01/01 and 2024/01/31...")
    display_emails(get_emails_by_date(service, "2024/01/01", "2024/01/31", max_results=3))

    print("\n3. Fetching latest 3 emails...")
    display_emails(get_latest_emails(service, n=3))

    print("\n4. Fetching emails from Google...")
    display_emails(get_emails_by_sender(service, "no-reply@accounts.google.com", max_results=3))