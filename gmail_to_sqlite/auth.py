import os
from typing import Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .constants import GMAIL_SCOPES, OAUTH2_CREDENTIALS_FILE, TOKEN_FILE_NAME
from .config import settings


class AuthenticationError(Exception):
    """Custom exception for authentication-related errors."""

    pass


def get_credentials() -> Any:
    """
    Retrieves the authentication credentials by either loading them from the token file 
    or by running the authentication flow. Uses data directory from settings.

    Returns:
        Any: The authentication credentials (compatible with Google API clients).

    Raises:
        AuthenticationError: If credentials cannot be obtained or are invalid.
        FileNotFoundError: If the OAuth2 credentials file is not found.
    """
    # Look for credentials.json in the package root directory
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    credentials_file_path = os.path.join(package_dir, OAUTH2_CREDENTIALS_FILE)

    if not os.path.exists(credentials_file_path):
        raise FileNotFoundError(
            f"{OAUTH2_CREDENTIALS_FILE} not found at {credentials_file_path}\n\n"
            f"Please ensure you have downloaded your OAuth 2.0 credentials from the Google Cloud Console "
            f"and saved them as '{OAUTH2_CREDENTIALS_FILE}' in the project root directory."
        )

    data_dir = settings.get("DATA_DIR")
    if not data_dir:
        raise AuthenticationError("DATA_DIR not configured in settings")
    
    token_file_path = os.path.join(data_dir, TOKEN_FILE_NAME)
    creds: Optional[Any] = None

    # Load existing credentials if available
    if os.path.exists(token_file_path):
        try:
            creds = Credentials.from_authorized_user_file(token_file_path, GMAIL_SCOPES)
        except Exception as e:
            raise AuthenticationError(f"Failed to load existing credentials: {e}")

    # Refresh or obtain new credentials if needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                raise AuthenticationError(f"Failed to refresh credentials: {e}")
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(
                    credentials_file_path, GMAIL_SCOPES
                )
                # The flow returns credentials that may be of different types
                # but all are compatible with the API usage
                flow_creds = flow.run_local_server(port=0)
                creds = flow_creds
            except Exception as e:
                raise AuthenticationError(f"Failed to obtain new credentials: {e}")

        # Save credentials for future use
        if creds:
            try:
                with open(token_file_path, "w") as token:
                    token.write(creds.to_json())
            except Exception as e:
                raise AuthenticationError(f"Failed to save credentials: {e}")

    if not creds:
        raise AuthenticationError("Failed to obtain valid credentials")

    return creds
