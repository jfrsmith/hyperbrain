#!/usr/bin/env python3
"""
Google Meet Smart Notes Fetcher

Fetches Gemini Smart Notes from Google Meet meetings to support automated debriefs.
Smart Notes are AI-generated summaries with action items from the "Take notes for me" feature.

Requires:
- GCP project enrolled in Workspace Developer Preview Program
- Gemini Business/Enterprise/Education plan for meeting organizer
- "Take notes for me" enabled during the meeting

Usage:
    python get_smart_notes.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00"
    python get_smart_notes.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00" --format text

Output:
    JSON with {found, notes, error} fields, or plain text if --format text
"""

import argparse
import functools
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TypeVar

import requests
from google.api_core import exceptions as google_exceptions
from google.apps import meet_v2
from google.auth import exceptions as auth_exceptions
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from meet_auth import get_credentials


# Configure logging to stderr
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# Default time window if --before not specified (4 hours)
DEFAULT_TIME_WINDOW_HOURS = 4

# Retry configuration
MAX_RETRIES = 3
RETRY_BASE_DELAY_SECONDS = 1.0

# Error code constants
ERROR_INVALID_TIMESTAMP = "invalid_timestamp"
ERROR_AUTH_CONFIG_MISSING = "auth_config_missing"
ERROR_AUTH_REFRESH_FAILED = "auth_refresh_failed"
ERROR_MEET_ACCESS_DENIED = "meet_access_denied"
ERROR_MEET_API_ERROR = "meet_api_error"
ERROR_NO_CONFERENCE = "no_conference_record"
ERROR_API_NOT_AVAILABLE = "api_not_available"
ERROR_NO_SMART_NOTES = "no_smart_notes"
ERROR_NOTES_IN_PROGRESS = "notes_in_progress"
ERROR_NOTES_NOT_READY = "notes_not_ready"
ERROR_DRIVE_ACCESS_DENIED = "drive_access_denied"
ERROR_NOTES_FETCH_ERROR = "notes_fetch_error"


# Type variable for generic retry decorator
T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    retryable_exceptions: tuple = (
        google_exceptions.ServiceUnavailable,
        google_exceptions.DeadlineExceeded,
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
    ),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff.

    Handles rate limiting (HTTP 429) and transient errors.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.info(f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {delay}s: {e}")
                        time.sleep(delay)
                except google_exceptions.ResourceExhausted as e:
                    # Rate limiting (HTTP 429)
                    last_exception = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited, retry {attempt + 1}/{max_retries} after {delay}s")
                        time.sleep(delay)
                except HttpError as e:
                    if e.resp.status == 429:
                        last_exception = e
                        if attempt < max_retries:
                            delay = base_delay * (2 ** attempt)
                            logger.warning(f"Rate limited (HTTP 429), retry {attempt + 1}/{max_retries} after {delay}s")
                            time.sleep(delay)
                    else:
                        raise
            raise last_exception
        return wrapper
    return decorator


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fetch Google Meet Smart Notes (Gemini AI notes) for a meeting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python get_smart_notes.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00"
  python get_smart_notes.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00" --format text

Note: Requires GCP project enrollment in Workspace Developer Preview Program.
        """,
    )
    parser.add_argument(
        "--meeting-code",
        required=True,
        help="Google Meet code (e.g., abc-defg-hij from the meeting URL)",
    )
    parser.add_argument(
        "--after",
        required=True,
        help="ISO timestamp - find conference starting after this time (e.g., 2024-01-15T14:00:00)",
    )
    parser.add_argument(
        "--before",
        help="ISO timestamp - find conference starting before this time (default: --after + 4 hours)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format (default: json)",
    )
    return parser.parse_args()


def parse_timestamp(ts_str: str) -> datetime:
    """
    Parse ISO timestamp string to datetime.

    Handles both naive (assumes UTC) and timezone-aware timestamps.
    """
    # Try parsing with timezone
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    # Try common formats
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            dt = datetime.strptime(ts_str, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError(f"Cannot parse timestamp: {ts_str}")


def output_error(error_code: str, message: str, format_type: str = "json", **extra) -> None:
    """Output error response and exit."""
    if format_type == "json":
        result = {
            "found": False,
            "error": error_code,
            "message": message,
            **extra,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def output_success(data: dict, format_type: str) -> None:
    """Output successful response."""
    # Handle unicode on Windows
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    if format_type == "json":
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        # Text format - just output the notes content
        notes = data.get("notes", "")
        print(notes)


@retry_with_backoff()
def find_conference_record(
    client: meet_v2.ConferenceRecordsServiceClient,
    meeting_code: str,
    after: datetime,
    before: datetime,
) -> meet_v2.ConferenceRecord | None:
    """
    Find conference record matching meeting code and time window.

    Note: The filter syntax MUST have spaces around the = operator.
    """
    # Build filter for meeting code - SPACES around = are required!
    filter_str = f'space.meeting_code = "{meeting_code}"'

    try:
        request = meet_v2.ListConferenceRecordsRequest(filter=filter_str)
        records = list(client.list_conference_records(request=request))
    except google_exceptions.NotFound:
        return None
    except google_exceptions.PermissionDenied as e:
        raise PermissionError(f"Permission denied accessing Meet API: {e}")

    if not records:
        return None

    # Filter by time window and find closest match
    matching_records = []
    for record in records:
        if record.start_time:
            record_start = record.start_time
            # Ensure timezone-aware comparison
            if record_start.tzinfo is None:
                record_start = record_start.replace(tzinfo=timezone.utc)

            if after <= record_start <= before:
                matching_records.append(record)

    if not matching_records:
        return None

    # Return the record closest to the 'after' time
    matching_records.sort(key=lambda r: abs((r.start_time - after).total_seconds()))
    return matching_records[0]


def get_smart_notes_metadata(
    conference_record_id: str,
    credentials: Credentials,
) -> dict:
    """
    Get Smart Notes metadata from v2beta API.

    Uses direct REST call since Python library doesn't support smartNotes yet.

    Returns:
        Dict with smartNotes list, or error key if API unavailable.
    """
    # Ensure token is fresh
    if credentials.expired:
        credentials.refresh(Request())

    url = f"https://meet.googleapis.com/v2beta/conferenceRecords/{conference_record_id}/smartNotes"
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.exceptions.Timeout:
        raise TimeoutError("Request to Smart Notes API timed out")
    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Failed to connect to Smart Notes API: {e}")

    if response.status_code == 200:
        return response.json()

    if response.status_code == 404:
        error_data = response.json().get("error", {})
        message = error_data.get("message", "")

        if "Method not found" in message:
            return {"error": "api_not_available"}
        # Conference found but no smart notes resource
        return {"smartNotes": []}

    if response.status_code == 403:
        return {"error": "permission_denied", "message": response.text}

    if response.status_code == 429:
        raise google_exceptions.ResourceExhausted(response.text)

    response.raise_for_status()
    return response.json()


@retry_with_backoff()
def download_notes_document(doc_id: str, credentials: Credentials) -> str:
    """
    Download Smart Notes content from Google Drive.

    Args:
        doc_id: Google Doc ID from Smart Notes metadata
        credentials: OAuth credentials for Drive API

    Returns:
        Notes text content.

    Raises:
        PermissionError: If access to the document is denied.
    """
    try:
        service = build("drive", "v3", credentials=credentials)

        # Export Google Doc as plain text
        request = service.files().export(fileId=doc_id, mimeType="text/plain")
        content = request.execute()

        # Handle bytes vs string response
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    except HttpError as e:
        if e.resp.status == 403:
            raise PermissionError(
                f"Access denied to Smart Notes document. "
                f"Ensure you have read access to the Google Doc."
            )
        elif e.resp.status == 404:
            raise FileNotFoundError(f"Smart Notes document not found: {doc_id}")
        raise


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Parse timestamps
    try:
        after = parse_timestamp(args.after)
    except ValueError as e:
        output_error(ERROR_INVALID_TIMESTAMP, f"Invalid --after timestamp: {e}", args.format)
        return

    if args.before:
        try:
            before = parse_timestamp(args.before)
        except ValueError as e:
            output_error(ERROR_INVALID_TIMESTAMP, f"Invalid --before timestamp: {e}", args.format)
            return
    else:
        before = after + timedelta(hours=DEFAULT_TIME_WINDOW_HOURS)

    # Authenticate
    try:
        creds = get_credentials()
    except FileNotFoundError as e:
        output_error(ERROR_AUTH_CONFIG_MISSING, str(e), args.format)
        return
    except auth_exceptions.RefreshError as e:
        output_error(
            ERROR_AUTH_REFRESH_FAILED,
            f"Token refresh failed. Delete meet-tokens.json and re-authenticate: {e}",
            args.format,
        )
        return

    # Create Meet API client
    client = meet_v2.ConferenceRecordsServiceClient(credentials=creds)

    # Find conference record
    try:
        record = find_conference_record(client, args.meeting_code, after, before)
    except PermissionError as e:
        output_error(ERROR_MEET_ACCESS_DENIED, str(e), args.format)
        return
    except Exception as e:
        output_error(ERROR_MEET_API_ERROR, f"Meet API error: {e}", args.format)
        return

    if not record:
        output_error(
            ERROR_NO_CONFERENCE,
            f"No conference found for meeting code '{args.meeting_code}' "
            f"between {after.isoformat()} and {before.isoformat()}",
            args.format,
            meeting_code=args.meeting_code,
        )
        return

    # Extract conference ID
    conference_id = record.name.split("/")[-1]

    # Get Smart Notes metadata (v2beta API)
    try:
        notes_response = get_smart_notes_metadata(conference_id, creds)
    except (TimeoutError, ConnectionError) as e:
        output_error(ERROR_NOTES_FETCH_ERROR, str(e), args.format, conference_id=conference_id)
        return
    except Exception as e:
        output_error(ERROR_NOTES_FETCH_ERROR, f"Smart Notes API error: {e}", args.format, conference_id=conference_id)
        return

    # Check for API availability error
    if notes_response.get("error") == "api_not_available":
        output_error(
            ERROR_API_NOT_AVAILABLE,
            "Smart Notes API returned 404. Ensure your GCP project is enrolled in Developer Preview Program.",
            args.format,
            conference_id=conference_id,
        )
        return

    if notes_response.get("error") == "permission_denied":
        output_error(
            ERROR_MEET_ACCESS_DENIED,
            f"Permission denied accessing Smart Notes: {notes_response.get('message', '')}",
            args.format,
            conference_id=conference_id,
        )
        return

    # Parse Smart Notes response
    smart_notes = notes_response.get("smartNotes", [])

    if not smart_notes:
        output_error(
            ERROR_NO_SMART_NOTES,
            "Conference found but Smart Notes were not enabled for this meeting",
            args.format,
            conference_id=conference_id,
            meeting_code=args.meeting_code,
        )
        return

    # Take the first (usually only) smart note
    note = smart_notes[0]
    state = note.get("state")
    docs_dest = note.get("docsDestination")

    # Check state
    if state == "STARTED":
        output_error(
            ERROR_NOTES_IN_PROGRESS,
            "Smart Notes are still being generated (state: STARTED). Meeting may still be in progress.",
            args.format,
            conference_id=conference_id,
            notes_state=state,
        )
        return

    if state == "ENDED":
        output_error(
            ERROR_NOTES_NOT_READY,
            "Smart Notes are still processing (state: ENDED). Try again in a few minutes.",
            args.format,
            conference_id=conference_id,
            notes_state=state,
        )
        return

    if state != "FILE_GENERATED":
        output_error(
            ERROR_NOTES_NOT_READY,
            f"Smart Notes not ready (state: {state})",
            args.format,
            conference_id=conference_id,
            notes_state=state,
        )
        return

    # State is FILE_GENERATED - download from Drive
    if not docs_dest or not docs_dest.get("document"):
        output_error(
            ERROR_NOTES_FETCH_ERROR,
            "Smart Notes state is FILE_GENERATED but no document ID found",
            args.format,
            conference_id=conference_id,
            notes_state=state,
        )
        return

    doc_id = docs_dest.get("document")
    doc_url = docs_dest.get("exportUri") or f"https://docs.google.com/document/d/{doc_id}/edit"

    # Download notes content
    try:
        notes_text = download_notes_document(doc_id, creds)
    except PermissionError as e:
        output_error(
            ERROR_DRIVE_ACCESS_DENIED,
            str(e),
            args.format,
            conference_id=conference_id,
            doc_url=doc_url,
        )
        return
    except FileNotFoundError:
        output_error(
            ERROR_NOTES_FETCH_ERROR,
            "Smart Notes document not found in Drive",
            args.format,
            conference_id=conference_id,
            doc_url=doc_url,
        )
        return
    except Exception as e:
        output_error(
            ERROR_NOTES_FETCH_ERROR,
            f"Failed to download Smart Notes: {e}",
            args.format,
            conference_id=conference_id,
            doc_url=doc_url,
        )
        return

    # Build success response
    result = {
        "found": True,
        "meeting_code": args.meeting_code,
        "conference_id": conference_id,
        "start_time": record.start_time.isoformat() if record.start_time else None,
        "end_time": record.end_time.isoformat() if record.end_time else None,
        "notes_state": state,
        "doc_id": doc_id,
        "doc_url": doc_url,
        "notes": notes_text,
    }

    output_success(result, args.format)


if __name__ == "__main__":
    main()
