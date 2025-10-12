import concurrent.futures
import logging
import socket
import time
from typing import Any, Callable, Dict, List, Optional, Set

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from peewee import IntegrityError

from . import db, message
from .constants import (
    DEFAULT_WORKERS,
    GMAIL_API_VERSION,
    MAX_RESULTS_PER_PAGE,
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    PROGRESS_LOG_INTERVAL,
    COLLECTION_LOG_INTERVAL,
)


class SyncError(Exception):
    """Custom exception for synchronization errors."""

    pass


def _fetch_message(
    service: Any,
    message_id: str,
    labels: Dict[str, str],
    check_interrupt: Optional[Callable[[], bool]] = None,
) -> message.Message:
    """
    Fetches a single message from Gmail API with retry logic and robust error handling.

    Args:
        service: The Gmail API service object.
        message_id: The ID of the message to fetch.
        labels: Dictionary mapping label IDs to label names.
        check_interrupt: Optional callback that returns True if process should be interrupted.

    Returns:
        Message: The parsed message object.

    Raises:
        InterruptedError: If the process was interrupted.
        SyncError: If the message cannot be fetched after all retries.
    """
    for attempt in range(MAX_RETRY_ATTEMPTS):
        if check_interrupt and check_interrupt():
            raise InterruptedError("Process was interrupted")

        try:
            raw_msg = (
                service.users().messages().get(userId="me", id=message_id).execute()
            )
            return message.Message.from_raw(raw_msg, labels)

        except HttpError as e:
            if e.resp.status >= 500 and attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to server error {e.resp.status}. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to HttpError {e.resp.status}: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except (TimeoutError, socket.timeout) as e:
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                logging.warning(
                    f"Attempt {attempt + 1}/{MAX_RETRY_ATTEMPTS} failed for message {message_id} "
                    f"due to timeout. Retrying in {RETRY_DELAY_SECONDS}s..."
                )
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = (
                    f"Failed to fetch message {message_id} after {attempt + 1} attempts "
                    f"due to timeout: {str(e)}"
                )
                logging.error(error_msg)
                raise SyncError(error_msg)

        except Exception as e:
            logging.error(
                f"Unexpected error processing message {message_id} on attempt {attempt + 1}: {str(e)}"
            )
            if attempt < MAX_RETRY_ATTEMPTS - 1:
                if check_interrupt and check_interrupt():
                    raise InterruptedError("Process was interrupted")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                error_msg = f"Failed to fetch message {message_id} after {MAX_RETRY_ATTEMPTS} attempts"
                logging.error(error_msg)
                raise SyncError(error_msg)

    # This should never be reached due to the exception handling above
    raise SyncError(f"Unexpected error: failed to fetch message {message_id}")


def get_labels(service: Any) -> Dict[str, str]:
    """
    Retrieves all labels from the Gmail API.

    Args:
        service: The Gmail API service object.

    Returns:
        Dict[str, str]: Mapping of label IDs to label names.

    Raises:
        SyncError: If labels cannot be retrieved.
    """
    try:
        labels = {}
        response = service.users().labels().list(userId="me").execute()
        for label in response.get("labels", []):
            labels[label["id"]] = label["name"]
        return labels
    except Exception as e:
        raise SyncError(f"Failed to retrieve labels: {e}")


def _create_service(credentials: Any) -> Any:
    """
    Creates a new Gmail API service object.

    Args:
        credentials: The credentials object for API authentication.

    Returns:
        The Gmail API service object.

    Raises:
        SyncError: If service creation fails.
    """
    try:
        return build("gmail", GMAIL_API_VERSION, credentials=credentials)
    except Exception as e:
        raise SyncError(f"Failed to create Gmail service: {e}")


def get_message_ids_from_gmail(
    service: Any,
    query: Optional[List[str]] = None,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> List[str]:
    """
    Fetches all message IDs from Gmail matching the query.

    Args:
        service: The Gmail API service object.
        query: Optional list of query strings to filter messages.
        check_shutdown: Callback that returns True if shutdown is requested.

    Returns:
        List[str]: List of message IDs from Gmail.

    Raises:
        SyncError: If message ID collection fails.
    """
    all_message_ids = []
    page_token = None
    collected_count = 0

    logging.info("Collecting all message IDs from Gmail...")

    try:
        while not (check_shutdown and check_shutdown()):
            list_params = {
                "userId": "me",
                "maxResults": MAX_RESULTS_PER_PAGE,
            }

            if page_token:
                list_params["pageToken"] = page_token

            if query:
                list_params["q"] = " ".join(query)

            results = service.users().messages().list(**list_params).execute()
            messages_page = results.get("messages", [])

            for m_info in messages_page:
                all_message_ids.append(m_info["id"])
                collected_count += 1

                if collected_count % COLLECTION_LOG_INTERVAL == 0:
                    logging.info(
                        f"Collected {collected_count} message IDs from Gmail..."
                    )

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except KeyboardInterrupt:
        logging.info("Message ID collection interrupted by user")
    except Exception as e:
        raise SyncError(f"Failed to collect message IDs: {e}")

    if check_shutdown and check_shutdown():
        logging.info(
            "Shutdown requested during message ID collection. Exiting gracefully."
        )
        return []

    logging.info(f"Collected {len(all_message_ids)} message IDs from Gmail")
    return all_message_ids


def _detect_and_mark_deleted_messages(
    gmail_message_ids: List[str], check_shutdown: Optional[Callable[[], bool]] = None
) -> Optional[int]:
    """
    Helper function to detect and mark deleted messages based on comparison
    between Gmail message IDs and database message IDs.

    Args:
        gmail_message_ids (list): List of message IDs from Gmail.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: Number of messages newly marked as deleted, or None if no action taken.
    """
    try:
        db_message_ids = set(db.get_all_message_ids())
        logging.info(
            f"Retrieved {len(db_message_ids)} message IDs from database for deletion detection"
        )

        if not db_message_ids:
            logging.info("No messages in database to check for deletion")
            return None

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during deletion detection. Exiting gracefully."
            )
            return None

        already_deleted_ids = set(db.get_deleted_message_ids())
        if already_deleted_ids:
            logging.info(
                f"Found {len(already_deleted_ids)} already deleted messages to skip"
            )

        gmail_ids_set = set(gmail_message_ids)
        potential_deleted_ids = db_message_ids - gmail_ids_set
        new_deleted_ids = (
            list(potential_deleted_ids - already_deleted_ids)
            if already_deleted_ids
            else list(potential_deleted_ids)
        )

        if new_deleted_ids:
            logging.info(f"Found {len(new_deleted_ids)} new deleted messages to mark")
            db.mark_messages_as_deleted(new_deleted_ids)
            logging.info(
                f"Deletion sync complete. {len(new_deleted_ids)} messages newly marked as deleted."
            )
            return len(new_deleted_ids)
        else:
            logging.info("No new deleted messages found")
            return None
    except Exception as e:
        logging.error(f"Error during deletion detection: {str(e)}")
        return None


def all_messages(
    credentials: Any,
    full_sync: bool = False,
    num_workers: int = 4,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> int:
    """
    Fetches messages from the Gmail API using the provided credentials, in parallel.
    Also detects and marks deleted messages.

    Args:
        credentials (object): The credentials object used to authenticate the API request.
        db_conn (object): The database connection object.
        full_sync (bool): Whether to do a full sync or not.
        num_workers (int): Number of worker threads for parallel fetching.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: The number of messages successfully synced.
    """
    executor = None
    future_to_id = {}

    try:
        query = []
        if not full_sync:
            last = db.last_indexed()
            if last:
                # Only get messages after the last indexed timestamp
                query.append(f"after:{int(last.timestamp())}")

        service = _create_service(credentials)
        labels = get_labels(service)

        all_message_ids = get_message_ids_from_gmail(service, query, check_shutdown)

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return 0

        if full_sync:
            _detect_and_mark_deleted_messages(all_message_ids, check_shutdown)

        logging.info(f"Found {len(all_message_ids)} messages to sync.")

        total_synced_count = 0
        processed_count = 0

        def thread_worker(message_id: str) -> bool:
            if check_shutdown and check_shutdown():
                return False

            service = _create_service(credentials)

            try:
                msg = _fetch_message(
                    service,
                    message_id,
                    labels,
                    check_interrupt=check_shutdown,
                )
                try:
                    db.create_message(msg)
                    logging.info(
                        f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
                    )
                    return True
                except IntegrityError as e:
                    logging.error(
                        f"Could not process message {message_id} due to integrity error: {str(e)}"
                    )
                    return False
            except InterruptedError:
                logging.info(f"Message fetch for {message_id} was interrupted")
                return False
            except Exception as e:
                logging.error(f"Failed to fetch message {message_id}: {str(e)}")
                return False

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=num_workers
        ) as executor_instance:
            executor = executor_instance
            future_to_id = {
                executor.submit(thread_worker, msg_id): msg_id
                for msg_id in all_message_ids
            }

            for future in concurrent.futures.as_completed(future_to_id):
                if check_shutdown and check_shutdown() and not future.running():
                    continue

                message_id = future_to_id[future]
                processed_count += 1
                try:
                    if not future.cancelled():
                        if future.result():
                            total_synced_count += 1
                    if (
                        processed_count % PROGRESS_LOG_INTERVAL == 0
                        or processed_count == len(all_message_ids)
                    ):
                        logging.info(
                            f"Processed {processed_count}/{len(all_message_ids)} messages..."
                        )
                except concurrent.futures.CancelledError:
                    logging.info(
                        f"Task for message {message_id} was cancelled due to shutdown"
                    )
                except Exception as exc:
                    logging.error(
                        f"Message ID {message_id} generated an exception during future processing: {exc}"
                    )
                    logging.error(
                        f"Message ID {message_id} generated an exception during future processing: {exc}"
                    )

        if check_shutdown and check_shutdown():
            logging.info("Sync process was interrupted. Partial results saved.")
        else:
            logging.info(
                f"Total messages successfully synced: {total_synced_count} out of {len(all_message_ids)}"
            )
        return total_synced_count
    finally:
        pass


def validate_label_exists(service: Any, label_name: str) -> bool:
    """
    Check if a label exists in the user's Gmail account.

    Args:
        service: The Gmail API service object.
        label_name: The name of the label to check.

    Returns:
        bool: True if the label exists, False otherwise.

    Raises:
        SyncError: If label validation fails due to API error.
    """
    try:
        labels = get_labels(service)
        return label_name in labels.values()
    except Exception as e:
        raise SyncError(f"Failed to validate label '{label_name}': {e}")


def format_gmail_label_query(label: str) -> str:
    """
    Format a label name for use in Gmail API queries.
    Handles labels with spaces and special characters.

    Args:
        label: The label name to format.

    Returns:
        str: The formatted query string.
    """
    # If label contains spaces or special characters, wrap in quotes
    if " " in label or any(
        char in label for char in ["/", "(", ")", "[", "]", "<", ">", "@"]
    ):
        return f'label:"{label}"'
    else:
        return f"label:{label}"


def sync_messages_with_label(
    credentials: Any,
    label: str,
    full_sync: bool = False,
    num_workers: int = 4,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> int:
    """
    Syncs messages that have a specific label from Gmail.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        label: The label name to sync messages for.
        full_sync: If True, syncs all messages with the label and detects removals.
                  If False, only syncs new messages added to the label.
        num_workers: Number of worker threads for parallel fetching.
        check_shutdown: Callback that returns True if shutdown is requested.

    Returns:
        int: Number of messages successfully synced.

    Raises:
        SyncError: If sync fails due to API or validation errors.
    """
    try:
        # Create service and validate label exists
        service = _create_service(credentials)

        if not validate_label_exists(service, label):
            raise SyncError(f"Label '{label}' does not exist in Gmail account")

        logging.info(f"Starting label sync for '{label}' (full_sync={full_sync})")

        # Get existing messages with this label from database
        db_message_ids = set(db.get_message_ids_by_label(label))
        logging.info(
            f"Found {len(db_message_ids)} messages with label '{label}' in database"
        )

        # Get messages with this label from Gmail
        formatted_query = format_gmail_label_query(label)
        query = [formatted_query]

        if not full_sync:
            # For incremental sync, add timestamp filter
            last = db.last_indexed()
            if last:
                query.append(f"after:{int(last.timestamp())}")

        gmail_message_ids = get_message_ids_from_gmail(service, query, check_shutdown)

        if check_shutdown and check_shutdown():
            logging.info("Shutdown requested during Gmail message collection.")
            return 0

        gmail_ids_set = set(gmail_message_ids)
        logging.info(
            f"Found {len(gmail_ids_set)} messages with label '{label}' in Gmail"
        )

        # Determine which messages need to be synced
        if full_sync:
            # Full sync: sync all Gmail messages, detect database messages that lost the label
            messages_to_sync = list(gmail_ids_set)

            # Find messages in DB that no longer have the label in Gmail
            removed_from_label = db_message_ids - gmail_ids_set
            if removed_from_label:
                logging.info(
                    f"Found {len(removed_from_label)} messages that may have lost the '{label}' label"
                )
                # Note: We would need to re-sync these messages to update their labels
                # For now, we'll just log this information
        else:
            # Incremental sync: only sync messages not already in database
            messages_to_sync = list(gmail_ids_set - db_message_ids)

        logging.info(f"Need to sync {len(messages_to_sync)} messages")

        if not messages_to_sync:
            logging.info("No new messages to sync")
            return 0

        # Use the existing sync infrastructure to sync the identified messages
        labels = get_labels(service)
        total_synced_count = 0
        processed_count = 0

        def thread_worker(message_id: str) -> bool:
            if check_shutdown and check_shutdown():
                return False

            thread_service = _create_service(credentials)

            try:
                msg = _fetch_message(
                    thread_service,
                    message_id,
                    labels,
                    check_interrupt=check_shutdown,
                )
                try:
                    db.create_message(msg)
                    logging.info(f"Successfully synced message {msg.id}")
                    return True
                except Exception as e:
                    logging.error(f"Could not save message {message_id}: {str(e)}")
                    return False
            except InterruptedError:
                logging.info(f"Message fetch for {message_id} was interrupted")
                return False
            except Exception as e:
                logging.error(f"Failed to fetch message {message_id}: {str(e)}")
                return False

        # Use thread pool to sync messages in parallel
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            future_to_id = {
                executor.submit(thread_worker, msg_id): msg_id
                for msg_id in messages_to_sync
            }

            for future in concurrent.futures.as_completed(future_to_id):
                if check_shutdown and check_shutdown() and not future.running():
                    continue

                message_id = future_to_id[future]
                processed_count += 1

                try:
                    if not future.cancelled() and future.result():
                        total_synced_count += 1

                    if processed_count % 10 == 0 or processed_count == len(
                        messages_to_sync
                    ):
                        logging.info(
                            f"Processed {processed_count}/{len(messages_to_sync)} messages..."
                        )

                except concurrent.futures.CancelledError:
                    logging.info(f"Task for message {message_id} was cancelled")
                except Exception as exc:
                    logging.error(f"Message {message_id} generated exception: {exc}")

        if check_shutdown and check_shutdown():
            logging.info("Label sync was interrupted. Partial results saved.")
        else:
            logging.info(
                f"Label sync complete. {total_synced_count} messages synced for label '{label}'"
            )

        return total_synced_count

    except Exception as e:
        raise SyncError(f"Failed to sync messages with label '{label}': {e}")


def sync_deleted_messages(
    credentials: Any, check_shutdown: Optional[Callable[[], bool]] = None
) -> None:
    """
    Compares message IDs in Gmail with those in the database and marks missing messages as deleted.
    This function only updates the is_deleted flag and doesn't download full message content.
    It skips messages that are already marked as deleted for efficiency.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        int: Number of messages marked as deleted.
    """
    try:
        service = _create_service(credentials)
        gmail_message_ids = get_message_ids_from_gmail(
            service, check_shutdown=check_shutdown
        )

        if check_shutdown and check_shutdown():
            logging.info(
                "Shutdown requested during message ID collection. Exiting gracefully."
            )
            return None

        _detect_and_mark_deleted_messages(gmail_message_ids, check_shutdown)
    except Exception as e:
        logging.error(f"Error during deletion sync: {str(e)}")
        return None


def single_message(
    credentials: Any,
    message_id: str,
    check_shutdown: Optional[Callable[[], bool]] = None,
) -> None:
    """
    Syncs a single message from Gmail using the provided credentials and message ID.

    Args:
        credentials: The credentials used to authenticate the Gmail API.
        message_id: The ID of the message to fetch.
        check_shutdown (callable): A callback function that returns True if shutdown is requested.

    Returns:
        None
    """
    try:
        service = _create_service(credentials)
        labels = get_labels(service)

        if check_shutdown and check_shutdown():
            logging.info("Shutdown requested. Exiting gracefully.")
            return None

        try:
            msg = _fetch_message(
                service,
                message_id,
                labels,
                check_interrupt=check_shutdown,
            )
            if check_shutdown and check_shutdown():
                logging.info(
                    "Shutdown requested after message fetch. Exiting gracefully."
                )
                return None

            try:
                db.create_message(msg)
                logging.info(
                    f"Successfully synced message {msg.id} (Original ID: {message_id}) from {msg.timestamp}"
                )
            except IntegrityError as e:
                logging.error(
                    f"Could not process message {message_id} due to integrity error: {str(e)}"
                )
        except InterruptedError:
            logging.info(f"Message fetch for {message_id} was interrupted")
        except Exception as e:
            logging.error(f"Failed to fetch message {message_id}: {str(e)}")
    finally:
        pass
