import argparse
import logging
import os
import signal
import sys
from typing import Any, Callable, List, Optional

from dotenv import load_dotenv

from . import auth, db, sync, chat
from .constants import DEFAULT_WORKERS, LOG_FORMAT


class ApplicationError(Exception):
    """Custom exception for application-level errors."""

    pass


def prepare_data_dir(data_dir: str) -> None:
    """
    Create the data directory if it doesn't exist.

    Args:
        data_dir (str): The path where to store data.

    Raises:
        ApplicationError: If directory creation fails.
    """
    try:
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
    except Exception as e:
        raise ApplicationError(f"Failed to create data directory {data_dir}: {e}")


def setup_signal_handler(
    shutdown_requested: Optional[List[bool]] = None,
    executor: Any = None,
    futures: Any = None,
) -> Any:
    """
    Set up a signal handler for graceful shutdown.

    Args:
        shutdown_requested: Mutable container for shutdown state.
        executor: The executor instance to manage task cancellation.
        futures: Dictionary mapping futures to their IDs.

    Returns:
        The original signal handler.
    """

    def handle_sigint(sig: Any, frame: Any) -> None:
        if shutdown_requested is not None:
            if not shutdown_requested[0]:
                logging.info(
                    "Shutdown requested. Waiting for current tasks to complete..."
                )
                shutdown_requested[0] = True

                # Cancel non-running futures if provided
                if executor and futures:
                    for future in list(futures.keys()):
                        if not future.running():
                            future.cancel()
            else:
                logging.warning("Forced shutdown. Exiting immediately.")
                sys.exit(1)
        else:
            logging.warning(
                "Forced shutdown. No graceful shutdown available. Exiting immediately."
            )
            sys.exit(1)

    original_sigint_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, handle_sigint)
    return original_sigint_handler


def setup_logging() -> None:
    """Set up application logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.StreamHandler()],
    )


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Gmail to SQLite synchronization tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  sync                     Sync all messages (incremental by default)
  sync-message             Sync a single message by ID
  sync-deleted-messages    Detect and mark deleted messages
  chat                     Interactive chat with Gmail analysis agent or ask single question

Examples:
  %(prog)s sync
  %(prog)s sync --full-sync
  %(prog)s sync-message --message-id abc123
  %(prog)s chat --question "Who sent me the most emails?"
  %(prog)s chat
        """,
    )

    parser.add_argument(
        "command",
        choices=["sync", "sync-message", "sync-deleted-messages", "chat"],
        help="The command to run",
    )
    parser.add_argument(
        "--data-dir",
        help="The path where the data should be stored (can also be set via GMAIL_DATA_DIR environment variable)",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Force a full sync of all messages and detect deleted messages",
    )
    parser.add_argument(
        "--message-id",
        help="The ID of the message to sync (required for sync-message command)",
    )
    parser.add_argument(
        "--question",
        help="Natural language question to ask about your emails (for chat command - if provided, asks question and exits; if not provided, starts interactive chat)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=20,
        help="Maximum number of rows to display in query results (default: 20)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Number of worker threads for parallel fetching (default: {DEFAULT_WORKERS})",
    )

    return parser


def main() -> None:
    """Main application entry point."""
    setup_logging()

    # Load environment variables
    load_dotenv()

    try:
        parser = create_argument_parser()
        args = parser.parse_args()

        # Validate command-specific arguments
        if args.command == "sync-message" and not args.message_id:
            parser.error("--message-id is required for sync-message command")

        # Get data directory from args or environment variable
        data_dir = args.data_dir or os.getenv("GMAIL_DATA_DIR")
        if not data_dir:
            parser.error(
                "--data-dir is required or set GMAIL_DATA_DIR environment variable"
            )

        prepare_data_dir(data_dir)

        # Only get credentials for commands that need them
        if args.command != "chat":
            credentials = auth.get_credentials(data_dir)

        # Set up shutdown handling
        shutdown_state = [False]

        def check_shutdown() -> bool:
            return shutdown_state[0]

        original_sigint_handler = setup_signal_handler(
            shutdown_requested=shutdown_state
        )

        try:
            if args.command == "chat":
                # Chat command - either single question or interactive chat
                if args.question:
                    # Single question mode
                    response = chat.ask_single_question(data_dir, args.question)
                    print(response)
                else:
                    # Interactive chat mode
                    chat.start_chat(data_dir)
            elif args.command == "sync":
                # Build sync statistics
                sync_stats = sync.sync_gmail_messages(
                    credentials,
                    data_dir,
                    args.full_sync,
                    args.workers,
                    check_shutdown,
                )

                # Display results summary
                print(f"Sync completed successfully!")
                print(f"New messages synced: {sync_stats.new_messages}")
                print(f"Updated messages: {sync_stats.updated_messages}")

                if sync_stats.deleted_messages > 0:
                    print(f"Deleted messages detected: {sync_stats.deleted_messages}")

                if sync_stats.errors:
                    print(f"Errors encountered: {len(sync_stats.errors)}")
                    for error in sync_stats.errors[:5]:  # Show first 5 errors
                        print(f"  - {error}")
                    if len(sync_stats.errors) > 5:
                        print(f"  ... and {len(sync_stats.errors) - 5} more")

            elif args.command == "sync-message":
                try:
                    success = sync.sync_single_message(
                        credentials, data_dir, args.message_id
                    )
                    if success:
                        print(f"Message {args.message_id} synced successfully!")
                    else:
                        print(f"Failed to sync message {args.message_id}")
                        sys.exit(1)
                except sync.SyncError as e:
                    logging.error(f"Sync error: {e}")
                    sys.exit(1)

            elif args.command == "sync-deleted-messages":
                try:
                    deleted_count = sync.sync_deleted_messages(
                        credentials, data_dir, check_shutdown
                    )
                    print(f"Marked {deleted_count} messages as deleted")
                except sync.SyncError as e:
                    logging.error(f"Sync error: {e}")
                    sys.exit(1)

        finally:
            # Restore original signal handler
            signal.signal(signal.SIGINT, original_sigint_handler)

    except ApplicationError as e:
        logging.error(f"Application error: {e}")
        sys.exit(1)
    except db.DatabaseError as e:
        logging.error(f"Database error: {e}")
        sys.exit(1)
    except auth.AuthenticationError as e:
        logging.error(f"Authentication error: {e}")
        sys.exit(1)
    except sync.SyncError as e:
        logging.error(f"Sync error: {e}")
        sys.exit(1)
    except chat.ChatError as e:
        logging.error(f"Chat error: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
