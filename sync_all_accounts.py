#!/usr/bin/env python3
"""
Multi-Account Gmail Sync Script

This script synchronizes Gmail messages for all configured accounts in the
.secrets.toml configuration file. It leverages the existing gmail-to-sqlite
CLI infrastructure to ensure maximum reliability and consistency.

Usage:
    python sync_all_accounts.py                    # Incremental sync all accounts
    python sync_all_accounts.py --full-sync        # Full sync all accounts
    python sync_all_accounts.py --parallel         # Parallel sync (faster)
    python sync_all_accounts.py --accounts personal,work  # Specific accounts
    python sync_all_accounts.py --workers 8        # Custom worker count
"""

import argparse
import concurrent.futures
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from gmail_to_sqlite.config import settings


class MultiAccountSyncError(Exception):
    """Custom exception for multi-account sync errors."""

    pass


class AccountSyncResult:
    """Holds the result of syncing a single account."""

    def __init__(self, account_name: str):
        self.account_name = account_name
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.success: bool = False
        self.messages_synced: int = 0
        self.error_message: Optional[str] = None
        self.command_output: str = ""

    @property
    def duration(self) -> float:
        """Get sync duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    def __str__(self) -> str:
        status = "✓ SUCCESS" if self.success else "✗ FAILED"
        duration_str = f"{self.duration:.1f}s" if self.duration > 0 else "N/A"

        if self.success:
            return f"{status} - {self.account_name} ({self.messages_synced} messages, {duration_str})"
        else:
            return (
                f"{status} - {self.account_name} ({duration_str}): {self.error_message}"
            )


class MultiAccountSyncer:
    """Manages synchronization across multiple Gmail accounts."""

    def __init__(self):
        self.setup_logging()

    def setup_logging(self) -> None:
        """Set up logging configuration."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logger = logging.getLogger(__name__)

    def get_configured_accounts(self) -> List[Dict[str, str]]:
        """
        Get list of configured accounts from settings.

        Returns:
            List of account dictionaries with name and data_dir.

        Raises:
            MultiAccountSyncError: If no accounts are configured.
        """
        try:
            accounts = settings.get("ACCOUNT", [])
            if not accounts:
                raise MultiAccountSyncError(
                    "No [[ACCOUNT]] entries found in .secrets.toml"
                )

            account_list = []
            for account in accounts:
                name = account.get("name")
                data_dir = account.get("data_dir")

                if not name:
                    raise MultiAccountSyncError(
                        f"Account missing 'name' field: {account}"
                    )
                if not data_dir:
                    raise MultiAccountSyncError(
                        f"Account '{name}' missing 'data_dir' field"
                    )

                account_list.append({"name": name, "data_dir": data_dir})

            return account_list

        except Exception as e:
            if isinstance(e, MultiAccountSyncError):
                raise
            raise MultiAccountSyncError(f"Failed to read account configuration: {e}")

    def sync_single_account(
        self, account_name: str, full_sync: bool = False, workers: Optional[int] = None
    ) -> AccountSyncResult:
        """
        Sync a single account using the gmail-to-sqlite CLI.

        Args:
            account_name: Name of the account to sync
            full_sync: Whether to perform a full sync
            workers: Number of worker threads to use

        Returns:
            AccountSyncResult with sync results
        """
        result = AccountSyncResult(account_name)
        result.start_time = datetime.now()

        # Build the command
        cmd = ["uv", "run", "gmail-to-sqlite", "sync", "--account", account_name]

        if full_sync:
            cmd.append("--full-sync")

        if workers:
            cmd.extend(["--workers", str(workers)])

        self.logger.info(
            f"Starting sync for account '{account_name}' (command: {' '.join(cmd)})"
        )

        try:
            # Run the sync command
            process = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600  # 1 hour timeout
            )

            result.end_time = datetime.now()
            result.command_output = process.stdout + process.stderr

            if process.returncode == 0:
                result.success = True
                # Try to extract messages synced count from output
                result.messages_synced = self._extract_messages_count(
                    result.command_output
                )
                self.logger.info(
                    f"✓ Account '{account_name}' synced successfully ({result.messages_synced} messages)"
                )
            else:
                result.success = False
                result.error_message = (
                    f"Command failed with exit code {process.returncode}"
                )
                self.logger.error(
                    f"✗ Account '{account_name}' sync failed: {result.error_message}"
                )
                if result.command_output.strip():
                    self.logger.error(f"Output: {result.command_output.strip()}")

        except subprocess.TimeoutExpired:
            result.end_time = datetime.now()
            result.success = False
            result.error_message = "Sync operation timed out (1 hour limit)"
            self.logger.error(f"✗ Account '{account_name}' sync timed out")

        except Exception as e:
            result.end_time = datetime.now()
            result.success = False
            result.error_message = str(e)
            self.logger.error(
                f"✗ Account '{account_name}' sync failed with exception: {e}"
            )

        return result

    def _extract_messages_count(self, output: str) -> int:
        """
        Extract the number of synced messages from command output.

        Args:
            output: Command output text

        Returns:
            Number of messages synced, or 0 if not found
        """
        try:
            # Look for "Total messages synced: N" pattern
            for line in output.split("\n"):
                if "Total messages synced:" in line:
                    parts = line.split(":")
                    if len(parts) >= 2:
                        return int(parts[1].strip().split()[0])
                elif "messages synced" in line.lower() and any(
                    char.isdigit() for char in line
                ):
                    # Fallback pattern matching
                    import re

                    numbers = re.findall(r"\d+", line)
                    if numbers:
                        return int(numbers[-1])  # Take the last number found
        except Exception:
            pass

        return 0

    def sync_accounts_sequential(
        self,
        accounts: List[Dict[str, str]],
        full_sync: bool = False,
        workers: Optional[int] = None,
    ) -> List[AccountSyncResult]:
        """
        Sync accounts sequentially (one after another).

        Args:
            accounts: List of account configurations
            full_sync: Whether to perform full sync
            workers: Number of worker threads to use

        Returns:
            List of AccountSyncResult objects
        """
        self.logger.info(f"Starting sequential sync of {len(accounts)} accounts")
        results = []

        for i, account in enumerate(accounts, 1):
            self.logger.info(
                f"=== Syncing Account {i}/{len(accounts)}: {account['name']} ==="
            )
            result = self.sync_single_account(account["name"], full_sync, workers)
            results.append(result)

        return results

    def sync_accounts_parallel(
        self,
        accounts: List[Dict[str, str]],
        full_sync: bool = False,
        workers: Optional[int] = None,
    ) -> List[AccountSyncResult]:
        """
        Sync accounts in parallel.

        Args:
            accounts: List of account configurations
            full_sync: Whether to perform full sync
            workers: Number of worker threads to use

        Returns:
            List of AccountSyncResult objects
        """
        self.logger.info(f"Starting parallel sync of {len(accounts)} accounts")
        results = []

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(accounts)
        ) as executor:
            # Submit all sync jobs
            future_to_account = {
                executor.submit(
                    self.sync_single_account, account["name"], full_sync, workers
                ): account["name"]
                for account in accounts
            }

            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_account):
                account_name = future_to_account[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    # Create a failed result if the future itself failed
                    result = AccountSyncResult(account_name)
                    result.start_time = datetime.now()
                    result.end_time = datetime.now()
                    result.success = False
                    result.error_message = f"Parallel execution failed: {e}"
                    results.append(result)
                    self.logger.error(f"✗ Parallel sync failed for {account_name}: {e}")

        # Sort results by account name for consistent output
        results.sort(key=lambda r: r.account_name)
        return results

    def print_summary(self, results: List[AccountSyncResult]) -> None:
        """
        Print a summary of sync results.

        Args:
            results: List of AccountSyncResult objects
        """
        total_accounts = len(results)
        successful_accounts = sum(1 for r in results if r.success)
        failed_accounts = total_accounts - successful_accounts
        total_messages = sum(r.messages_synced for r in results)
        total_time = sum(r.duration for r in results)

        print("\n" + "=" * 60)
        print("MULTI-ACCOUNT SYNC SUMMARY")
        print("=" * 60)

        # Print individual results
        for result in results:
            print(f"  {result}")

        print("-" * 60)
        print(
            f"Accounts: {successful_accounts} successful, {failed_accounts} failed ({total_accounts} total)"
        )
        print(f"Messages: {total_messages} synced")
        print(f"Duration: {total_time:.1f} seconds")
        print("=" * 60)

        # Exit with error code if any accounts failed
        if failed_accounts > 0:
            sys.exit(1)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Multi-Account Gmail to SQLite Sync Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Incremental sync all accounts
  %(prog)s --full-sync                  # Full sync all accounts
  %(prog)s --parallel                   # Parallel sync (faster)
  %(prog)s --accounts personal,work     # Sync specific accounts only
  %(prog)s --workers 8                  # Use 8 worker threads per account
  %(prog)s --full-sync --parallel       # Full parallel sync
        """,
    )

    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Force a full sync of all messages and detect deleted messages",
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Sync accounts in parallel (faster but uses more resources)",
    )

    parser.add_argument(
        "--accounts",
        help="Comma-separated list of account names to sync (if not specified, syncs all accounts)",
    )

    parser.add_argument(
        "--workers",
        type=int,
        help="Number of worker threads per account (uses gmail-to-sqlite default if not specified)",
    )

    return parser


def main() -> None:
    """Main application entry point."""
    try:
        parser = create_argument_parser()
        args = parser.parse_args()

        syncer = MultiAccountSyncer()

        # Get all configured accounts
        all_accounts = syncer.get_configured_accounts()

        # Filter accounts if specific ones were requested
        if args.accounts:
            requested_accounts = [name.strip() for name in args.accounts.split(",")]
            available_account_names = [acc["name"] for acc in all_accounts]

            # Validate requested accounts exist
            invalid_accounts = [
                name
                for name in requested_accounts
                if name not in available_account_names
            ]
            if invalid_accounts:
                syncer.logger.error(
                    f"Invalid account names: {', '.join(invalid_accounts)}"
                )
                syncer.logger.error(
                    f"Available accounts: {', '.join(available_account_names)}"
                )
                sys.exit(1)

            # Filter to requested accounts
            accounts_to_sync = [
                acc for acc in all_accounts if acc["name"] in requested_accounts
            ]
        else:
            accounts_to_sync = all_accounts

        syncer.logger.info(
            f"Found {len(accounts_to_sync)} account(s) to sync: {', '.join(acc['name'] for acc in accounts_to_sync)}"
        )

        # Perform the sync
        start_time = datetime.now()

        if args.parallel:
            results = syncer.sync_accounts_parallel(
                accounts_to_sync, args.full_sync, args.workers
            )
        else:
            results = syncer.sync_accounts_sequential(
                accounts_to_sync, args.full_sync, args.workers
            )

        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()

        syncer.logger.info(
            f"Multi-account sync completed in {total_duration:.1f} seconds"
        )
        syncer.print_summary(results)

    except MultiAccountSyncError as e:
        logging.error(f"Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logging.info("Sync interrupted by user")
        sys.exit(130)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
