import argparse
import logging
import os
import pathlib
import signal
import sys
from typing import Any, Callable, List, Optional

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

Configuration:
  Accounts and data directories are configured in .secrets.toml file.

Examples:
  %(prog)s sync
  %(prog)s sync --account work
  %(prog)s sync --full-sync --account personal
  %(prog)s sync-message --message-id abc123 --account work
  %(prog)s chat --question "Who sent me the most emails?"
  %(prog)s chat --model openai
  %(prog)s chat -m anthropic
  %(prog)s chat
        """,
    )

    parser.add_argument(
        "command",
        choices=["sync", "sync-message", "sync-deleted-messages", "chat"],
        help="The command to run",
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

    parser.add_argument(
        "--model",
        "-m",
        choices=["gemini", "openai", "anthropic"],
        default="openai",
        help="AI model to use for chat (default: openai)",
    )

    parser.add_argument(
        "--account",
        "-a",
        help="Account name to use for sync operations (if not specified, uses first account)",
    )

    return parser


def main() -> None:
    """Main application entry point."""
    setup_logging()

    try:
        parser = create_argument_parser()
        args = parser.parse_args()

        # Validate command-specific arguments
        if args.command == "sync-message" and not args.message_id:
            parser.error("--message-id is required for sync-message command")

        # Get account-specific data directory and confirm account selection
        try:
            data_dir = auth._get_account_data_dir(args.account)

            # Show which account will be used if none was explicitly specified
            if args.account is None:
                accounts = auth.get_available_accounts()
                if len(accounts) > 1:
                    account_name = accounts[0]
                    print(f"Using account: {account_name}")
                    print(f"Available accounts: {', '.join(accounts)}")
                    print("Press Enter to continue or Ctrl+C to cancel...")
                    input()

        except auth.AuthenticationError as e:
            parser.error(str(e))

        prepare_data_dir(data_dir)

        # Only get credentials for commands that need them
        if args.command != "chat":
            credentials = auth.get_credentials(args.account)

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
                    response = chat.ask_single_question(
                        args.question, model=args.model, account=args.account
                    )
                    print(response)
                else:
                    # Interactive chat mode
                    chat.start_chat(model=args.model, account=args.account)
            elif args.command == "sync":
                # Initialize database first
                db.init(data_dir)

                # Build sync statistics
                sync_count = sync.all_messages(
                    credentials,
                    args.full_sync,
                    args.workers,
                    check_shutdown,
                )

                # Display results summary
                print(f"Sync completed successfully!")
                print(f"Total messages synced: {sync_count}")

            elif args.command == "sync-message":
                # Initialize database first
                db.init(data_dir)

                try:
                    sync.single_message(credentials, args.message_id, check_shutdown)
                    print(f"Message {args.message_id} synced successfully!")
                except sync.SyncError as e:
                    logging.error(f"Sync error: {e}")
                    sys.exit(1)

            elif args.command == "sync-deleted-messages":
                # Initialize database first
                db.init(data_dir)

                try:
                    deleted_count = sync.sync_deleted_messages(
                        credentials, check_shutdown
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
