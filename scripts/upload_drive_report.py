"""Upload a run workbook to Google Drive with free OAuth credentials.

The workflow skips cleanly when Drive secrets are not configured. Credentials are
read only from environment variables and are never written to the repository.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials


def main() -> int:
    workbook = Path(os.environ.get("AMALA_WORKBOOK", "reports/latest/amala-operations.xlsx"))
    status_path = Path(os.environ.get("AMALA_DRIVE_STATUS", "reports/latest/drive-upload.json"))
    status_path.parent.mkdir(parents=True, exist_ok=True)
    client_id = os.environ.get("GOOGLE_DRIVE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_DRIVE_REFRESH_TOKEN")
    if not (client_id and client_secret and refresh_token):
        status = {"status": "skipped", "reason": "Drive OAuth secrets are not configured"}
        status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(status))
        return 0
    if not workbook.is_file():
        raise FileNotFoundError(workbook)
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )
    credentials.refresh(Request())
    session = AuthorizedSession(credentials)
    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    metadata = {"name": f"amala-operations-{run_id}.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
    folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if folder_id:
        metadata["parents"] = [folder_id]
    boundary = "amala_report_boundary"
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
        + json.dumps(metadata).encode()
        + f"\r\n--{boundary}\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n".encode()
        + workbook.read_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    response = session.post(
        "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink",
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
        timeout=120,
    )
    response.raise_for_status()
    result = response.json()
    status = {"status": "uploaded", **result}
    status_path.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(status))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Drive upload failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
