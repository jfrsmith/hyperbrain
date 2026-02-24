"""
OAuth authentication module for Google Meet and Drive APIs.

Handles token storage, refresh, and initial OAuth flow for transcript fetching.
"""

import json
import logging
import os
import stat
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


# Configure logging to stderr
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Required OAuth scopes for transcript fetching
SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.readonly",  # Read Meet conference records
    "https://www.googleapis.com/auth/drive.readonly",           # Read transcript docs from Drive
]

# Default paths (relative to repo root)
DEFAULT_TOKEN_PATH = Path(__file__).parent.parent / "data" / ".credentials" / "meet-tokens.json"
DEFAULT_CLIENT_SECRETS = Path(__file__).parent.parent / "gcp-oauth.keys.json"


def get_credentials(
    token_path: Path | None = None,
    client_secrets_path: Path | None = None,
    scopes: list[str] | None = None,
) -> Credentials:
    """
    Load existing OAuth tokens or run browser-based OAuth flow.

    Args:
        token_path: Path to store/load tokens. Defaults to data/.credentials/meet-tokens.json
        client_secrets_path: Path to OAuth client config. Defaults to gcp-oauth.keys.json
        scopes: OAuth scopes to request. Defaults to Meet and Drive readonly.

    Returns:
        Valid Credentials object ready for API calls.

    Raises:
        FileNotFoundError: If client_secrets_path doesn't exist.
        google.auth.exceptions.RefreshError: If refresh fails and re-auth needed.
    """
    token_path = token_path or DEFAULT_TOKEN_PATH
    client_secrets_path = client_secrets_path or DEFAULT_CLIENT_SECRETS
    scopes = scopes or SCOPES

    # Validate client secrets exist
    if not client_secrets_path.exists():
        raise FileNotFoundError(
            f"OAuth client config not found at {client_secrets_path}. "
            "Download from Google Cloud Console > APIs & Services > Credentials."
        )

    creds = None

    # Load existing tokens if available
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Invalid token file, will re-authenticate: {e}")
            creds = None

    # Refresh or run new OAuth flow
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds, token_path)
        except Exception as e:
            logger.warning(f"Token refresh failed, re-authenticating: {e}")
            creds = None

    if not creds or not creds.valid:
        creds = _run_oauth_flow(client_secrets_path, scopes)
        _save_credentials(creds, token_path)

    return creds


def _run_oauth_flow(client_secrets_path: Path, scopes: list[str]) -> Credentials:
    """
    Run browser-based OAuth flow to get new credentials.

    Opens a local server and browser window for user authentication.
    """
    logger.info("Starting OAuth flow - a browser window will open for authentication.")

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets_path), scopes)

    # Run local server flow (opens browser automatically)
    creds = flow.run_local_server(
        port=0,  # Use any available port
        prompt="consent",  # Always show consent screen for transparency
        success_message="Authentication successful! You can close this window.",
    )

    logger.info("Authentication complete.")
    return creds


def _save_credentials(creds: Credentials, token_path: Path) -> None:
    """
    Save credentials to JSON file for future use.

    Creates parent directories if they don't exist.
    Sets restrictive file permissions (600) on Unix systems.
    """
    # Ensure directory exists
    token_path.parent.mkdir(parents=True, exist_ok=True)

    # Write credentials
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }

    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)

    # Set restrictive permissions on Unix systems (owner read/write only)
    if os.name != "nt":  # Not Windows
        os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)  # 600

    logger.info(f"Credentials saved to {token_path}")


if __name__ == "__main__":
    # Quick test: run OAuth flow and verify credentials
    print("Testing Meet authentication...")
    creds = get_credentials()
    print(f"Success! Token valid: {creds.valid}")
    print(f"Scopes: {creds.scopes}")
