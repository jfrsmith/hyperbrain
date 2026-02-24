#!/usr/bin/env python3
"""
Google Meet Transcript Fetcher

Fetches transcripts from Google Meet meetings to support automated debriefs.
Given a meeting code and time window, retrieves the transcript text.

Usage:
    python get_transcript.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00"
    python get_transcript.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00" --format text

Output:
    JSON with {found, transcript, error} fields, or plain text if --format text
"""

import argparse
import functools
import json
import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, TypeVar

from google.api_core import exceptions as google_exceptions
from google.apps import meet_v2
from google.auth import exceptions as auth_exceptions
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
ERROR_TRANSCRIPT_ACCESS_DENIED = "transcript_access_denied"
ERROR_TRANSCRIPT_API_ERROR = "transcript_api_error"
ERROR_NO_TRANSCRIPT = "no_transcript"
ERROR_TRANSCRIPT_NOT_READY = "transcript_not_ready"
ERROR_DRIVE_ACCESS_DENIED = "drive_access_denied"
ERROR_TRANSCRIPT_EMPTY = "transcript_empty"
ERROR_TRANSCRIPT_FETCH_ERROR = "transcript_fetch_error"


# Type variable for generic retry decorator
T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY_SECONDS,
    retryable_exceptions: tuple = (google_exceptions.ServiceUnavailable, google_exceptions.DeadlineExceeded),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff.

    Handles rate limiting (HTTP 429) and transient errors.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds, doubles each retry (default: 1.0)
        retryable_exceptions: Tuple of exception types to retry on

    Returns:
        Decorated function with retry logic.
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
                        # HTTP 429 from Google APIs
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
        description="Fetch Google Meet transcript for a meeting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python get_transcript.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00"
  python get_transcript.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00" --format text
  python get_transcript.py --meeting-code "abc-defg-hij" --after "2024-01-15T14:00:00" --before "2024-01-15T16:00:00"
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
    parser.add_argument(
        "--include-speakers",
        action="store_true",
        help="Include speaker labels in text output (only affects --format text)",
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


def output_success(data: dict, format_type: str, include_speakers: bool) -> None:
    """Output successful response."""
    if format_type == "json":
        print(json.dumps(data, indent=2))
    else:
        # Text format - just output the transcript
        transcript = data.get("transcript", "")
        if not include_speakers:
            transcript = strip_speaker_labels(transcript)
        print(transcript)


def strip_speaker_labels(transcript: str) -> str:
    """
    Strip speaker labels from transcript text.

    Handles various formats:
    - "Speaker N:" format (e.g., "Speaker 1: Hello")
    - Named speakers (e.g., "John Smith: Hello")
    - Handles speaker labels at the start of lines

    Args:
        transcript: Raw transcript text with speaker labels

    Returns:
        Transcript text with speaker labels removed.
    """
    lines = []
    # Pattern matches:
    # - "Speaker N:" where N is a number
    # - "Name:" where Name is 1-3 words (handles "John", "John Smith", "John Q. Smith")
    # The pattern looks for speaker label at start of line followed by colon and space
    speaker_pattern = re.compile(
        r"^(?:Speaker\s+\d+|[A-Z][a-zA-Z]*(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z]*)?):\s*",
        re.MULTILINE,
    )
    for line in transcript.split("\n"):
        # Remove speaker prefix if present
        stripped_line = speaker_pattern.sub("", line)
        lines.append(stripped_line)
    return "\n".join(lines)


@retry_with_backoff()
def find_conference_record(
    client: meet_v2.ConferenceRecordsServiceClient,
    meeting_code: str,
    after: datetime,
    before: datetime,
) -> meet_v2.ConferenceRecord | None:
    """
    Find conference record matching meeting code and time window.

    Args:
        client: Meet API conference records client
        meeting_code: The meeting code (e.g., "abc-defg-hij")
        after: Find conferences starting after this time
        before: Find conferences starting before this time

    Returns:
        ConferenceRecord if found, None otherwise.
        If multiple matches, returns the one closest to 'after' time.
    """
    # Build filter for meeting code
    # The API filter syntax uses the meeting_code from the space
    filter_str = f'space.meeting_code="{meeting_code}"'

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


@retry_with_backoff()
def get_transcript_metadata(
    client: meet_v2.ConferenceRecordsServiceClient,
    conference_record_name: str,
) -> meet_v2.Transcript | None:
    """
    Get transcript metadata for a conference record.

    Args:
        client: Meet API conference records client
        conference_record_name: Full resource name of the conference record

    Returns:
        Transcript object if found, None if no transcript exists.
    """
    try:
        request = meet_v2.ListTranscriptsRequest(parent=conference_record_name)
        transcripts = list(client.list_transcripts(request=request))
    except google_exceptions.NotFound:
        return None
    except google_exceptions.PermissionDenied as e:
        raise PermissionError(f"Permission denied accessing transcripts: {e}")

    if not transcripts:
        return None

    # Return first transcript (typically only one per meeting)
    return transcripts[0]


@retry_with_backoff()
def download_transcript_doc(doc_id: str, credentials: Credentials) -> str:
    """
    Download transcript content from Google Drive.

    Args:
        doc_id: Google Doc ID from transcript metadata
        credentials: OAuth credentials for Drive API

    Returns:
        Transcript text content.

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
                f"Access denied to transcript document. "
                f"Ensure you have read access to the Google Doc."
            )
        elif e.resp.status == 404:
            raise FileNotFoundError(f"Transcript document not found: {doc_id}")
        raise


@retry_with_backoff()
def get_transcript_entries(
    client: meet_v2.ConferenceRecordsServiceClient,
    transcript_name: str,
) -> list[meet_v2.TranscriptEntry]:
    """
    Get raw transcript entries (fallback if doc not ready).

    Args:
        client: Meet API conference records client
        transcript_name: Full resource name of the transcript

    Returns:
        List of TranscriptEntry objects with speaker and text.
    """
    entries = []
    page_token = None

    while True:
        request = meet_v2.ListTranscriptEntriesRequest(
            parent=transcript_name,
            page_token=page_token,
        )
        response = client.list_transcript_entries(request=request)

        entries.extend(response.transcript_entries)

        page_token = response.next_page_token
        if not page_token:
            break

    return entries


def format_entries_as_text(entries: list[meet_v2.TranscriptEntry]) -> str:
    """
    Format transcript entries into readable text.

    Groups consecutive entries by same speaker for readability.

    Args:
        entries: List of TranscriptEntry objects

    Returns:
        Formatted transcript string.
    """
    if not entries:
        return ""

    lines = []
    current_speaker = None
    current_text = []

    for entry in entries:
        speaker = entry.participant or "Unknown"
        text = entry.text or ""

        if speaker != current_speaker:
            # Flush previous speaker's text
            if current_text:
                lines.append(f"{current_speaker}: {' '.join(current_text)}")
            current_speaker = speaker
            current_text = [text]
        else:
            current_text.append(text)

    # Flush final speaker
    if current_text:
        lines.append(f"{current_speaker}: {' '.join(current_text)}")

    return "\n\n".join(lines)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Parse timestamps
    try:
        after = parse_timestamp(args.after)
    except ValueError as e:
        output_error(ERROR_INVALID_TIMESTAMP, f"Invalid --after timestamp: {e}", args.format)
        return  # Defensive: output_error exits, but explicit return for clarity

    if args.before:
        try:
            before = parse_timestamp(args.before)
        except ValueError as e:
            output_error(ERROR_INVALID_TIMESTAMP, f"Invalid --before timestamp: {e}", args.format)
            return  # Defensive: output_error exits, but explicit return for clarity
    else:
        before = after + timedelta(hours=DEFAULT_TIME_WINDOW_HOURS)

    # Authenticate
    try:
        creds = get_credentials()
    except FileNotFoundError as e:
        output_error(ERROR_AUTH_CONFIG_MISSING, str(e), args.format)
        return  # Defensive: output_error exits, but explicit return for clarity
    except auth_exceptions.RefreshError as e:
        output_error(
            ERROR_AUTH_REFRESH_FAILED,
            f"Token refresh failed. Delete meet-tokens.json and re-authenticate: {e}",
            args.format,
        )
        return  # Defensive: output_error exits, but explicit return for clarity

    # Create Meet API client
    client = meet_v2.ConferenceRecordsServiceClient(credentials=creds)

    # Find conference record
    try:
        record = find_conference_record(client, args.meeting_code, after, before)
    except PermissionError as e:
        output_error(ERROR_MEET_ACCESS_DENIED, str(e), args.format)
        return  # Defensive: output_error exits, but explicit return for clarity
    except Exception as e:
        output_error(ERROR_MEET_API_ERROR, f"Meet API error: {e}", args.format)
        return  # Defensive: output_error exits, but explicit return for clarity

    if not record:
        output_error(
            ERROR_NO_CONFERENCE,
            f"No conference found for meeting code '{args.meeting_code}' "
            f"between {after.isoformat()} and {before.isoformat()}",
            args.format,
            meeting_code=args.meeting_code,
        )
        return  # Defensive: output_error exits, but explicit return for clarity

    # Get transcript metadata
    try:
        transcript = get_transcript_metadata(client, record.name)
    except PermissionError as e:
        output_error(ERROR_TRANSCRIPT_ACCESS_DENIED, str(e), args.format)
        return  # Defensive: output_error exits, but explicit return for clarity
    except Exception as e:
        output_error(ERROR_TRANSCRIPT_API_ERROR, f"Transcript API error: {e}", args.format)
        return  # Defensive: output_error exits, but explicit return for clarity

    if not transcript:
        output_error(
            ERROR_NO_TRANSCRIPT,
            "Meeting found but transcription was not enabled",
            args.format,
            conference_id=record.name.split("/")[-1],
            meeting_code=args.meeting_code,
        )
        return  # Defensive: output_error exits, but explicit return for clarity

    # Check transcript state using proper enum comparison
    transcript_ready = transcript.state == meet_v2.Transcript.State.FILE_GENERATED

    # Get state name for error messages
    state_name = transcript.state.name if hasattr(transcript.state, "name") else str(transcript.state)

    if not transcript_ready:
        # Transcript still processing - differentiate message based on state
        if transcript.state == meet_v2.Transcript.State.STARTED:
            message = f"Transcript is still processing (state: {state_name}). Meeting may still be in progress."
        elif transcript.state == meet_v2.Transcript.State.ENDED:
            message = f"Transcript is still processing (state: {state_name}). Try again in a few minutes."
        else:
            message = f"Transcript is still processing (state: {state_name}). Try again in a few minutes."
        output_error(
            ERROR_TRANSCRIPT_NOT_READY,
            message,
            args.format,
            conference_id=record.name.split("/")[-1],
            transcript_state=state_name,
        )
        return  # Defensive: output_error exits, but explicit return for clarity

    # Get transcript content
    transcript_text = None
    doc_url = None

    # Try downloading from Google Doc first (preferred, better formatting)
    if transcript.docs_destination and transcript.docs_destination.document:
        doc_id = transcript.docs_destination.document
        doc_url = transcript.docs_destination.export_uri or f"https://docs.google.com/document/d/{doc_id}/edit"

        try:
            transcript_text = download_transcript_doc(doc_id, creds)
        except PermissionError as e:
            output_error(
                ERROR_DRIVE_ACCESS_DENIED,
                str(e),
                args.format,
                conference_id=record.name.split("/")[-1],
                doc_url=doc_url,
            )
            return  # Defensive: output_error exits, but explicit return for clarity
        except FileNotFoundError:
            # Doc not found, fall back to entries
            pass
        except Exception as e:
            # Log warning but try fallback
            logger.warning(f"Could not download transcript doc: {e}")

    # Fallback: get raw transcript entries
    if not transcript_text:
        try:
            entries = get_transcript_entries(client, transcript.name)
            if entries:
                transcript_text = format_entries_as_text(entries)
            else:
                output_error(
                    ERROR_TRANSCRIPT_EMPTY,
                    "Transcript exists but contains no content",
                    args.format,
                    conference_id=record.name.split("/")[-1],
                )
                return  # Defensive: output_error exits, but explicit return for clarity
        except Exception as e:
            output_error(
                ERROR_TRANSCRIPT_FETCH_ERROR,
                f"Failed to fetch transcript content: {e}",
                args.format,
                conference_id=record.name.split("/")[-1],
            )
            return  # Defensive: output_error exits, but explicit return for clarity

    # Build success response
    result = {
        "found": True,
        "meeting_code": args.meeting_code,
        "conference_id": record.name.split("/")[-1],
        "start_time": record.start_time.isoformat() if record.start_time else None,
        "end_time": record.end_time.isoformat() if record.end_time else None,
        "transcript_state": state_name,
        "transcript": transcript_text,
    }

    if doc_url:
        result["doc_url"] = doc_url

    output_success(result, args.format, args.include_speakers)


if __name__ == "__main__":
    main()
