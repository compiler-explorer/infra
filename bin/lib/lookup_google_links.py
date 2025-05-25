#!/usr/bin/env python3
"""
Script to expand Google shortened URLs from a CSV file.
Reads a CSV with uri column containing /g/* links and expands them.
Stores results in a SQLite database for idempotent operation.
Supports multi-threaded processing for faster operation.
"""

import csv
import http.client
import queue
import random
import sqlite3
import threading
import time
import urllib.parse
from typing import Any, Dict, Optional, Tuple, Union


def create_database(db_path: str) -> sqlite3.Connection:
    """
    Create or connect to the SQLite database.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        Database connection
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS google_links (
            fragment TEXT PRIMARY KEY,
            expanded_url TEXT
        )
    """)

    conn.commit()
    return conn


def get_cached_url(conn: sqlite3.Connection, fragment: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a fragment is already in the database.

    Args:
        conn: Database connection
        fragment: The link fragment (e.g., 'xyz123')

    Returns:
        Tuple of (found, expanded_url)
        - found: True if fragment exists in DB
        - expanded_url: The URL if valid, None if invalid fragment
    """
    cursor = conn.cursor()
    cursor.execute("SELECT expanded_url FROM google_links WHERE fragment = ?", (fragment,))
    result = cursor.fetchone()

    if result is None:
        return False, None
    else:
        return True, result[0]


def store_url(conn: sqlite3.Connection, fragment: str, expanded_url: Optional[str]) -> None:
    """
    Store a fragment and its expanded URL in the database.

    Args:
        conn: Database connection
        fragment: The link fragment
        expanded_url: The expanded URL (None for invalid fragments)
    """
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO google_links (fragment, expanded_url) VALUES (?, ?)", (fragment, expanded_url)
    )
    conn.commit()


class Stats:
    """Thread-safe statistics tracking."""

    def __init__(self):
        self.lock = threading.Lock()
        self.total = 0
        self.cached = 0
        self.success = 0
        self.failed = 0
        self.errors_429 = 0
        self.errors_other = 0
        self.start_time = time.time()

    def increment(self, field: str, amount: int = 1) -> None:
        with self.lock:
            setattr(self, field, getattr(self, field) + amount)

    def get_progress(self) -> Dict[str, Any]:
        with self.lock:
            elapsed = time.time() - self.start_time
            processed = self.cached + self.success + self.failed
            rate = processed / elapsed if elapsed > 0 else 0

            return {
                "total": self.total,
                "processed": processed,
                "cached": self.cached,
                "success": self.success,
                "failed": self.failed,
                "errors_429": self.errors_429,
                "errors_other": self.errors_other,
                "elapsed": elapsed,
                "rate": rate,
                "percent": (processed / self.total * 100) if self.total > 0 else 0,
            }


def expand_google_link(short_url: str, backoff_time: float = 0) -> Tuple[Optional[str], int]:
    """
    Expand a Google shortened URL by following the redirect.

    Args:
        short_url: The shortened URL (e.g., /g/xyz123)
        backoff_time: Time to wait before making request (for rate limiting)

    Returns:
        Tuple of (expanded_url, status_code)
    """
    if backoff_time > 0:
        time.sleep(backoff_time)

    try:
        # Construct the full Google shortener URL
        if short_url.startswith("/g/"):
            # Extract the ID part after /g/
            link_id = short_url[3:]
            full_url = f"https://goo.gl/{link_id}"
        else:
            print(f"Warning: URL doesn't match expected format: {short_url}")
            return None, 0

        # Parse the URL
        parsed = urllib.parse.urlparse(full_url)

        # Create connection
        conn: Union[http.client.HTTPSConnection, http.client.HTTPConnection]
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(parsed.netloc, timeout=10)
        else:
            conn = http.client.HTTPConnection(parsed.netloc, timeout=10)

        try:
            # Make HEAD request with ?si=1 parameter (as in the TypeScript code)
            path = parsed.path
            if parsed.query:
                path += "?" + parsed.query + "&si=1"
            else:
                path += "?si=1"

            conn.request("HEAD", path)
            response = conn.getresponse()

            # Check for 302 redirect
            if response.status == 302:
                location = response.getheader("Location")
                if location:
                    return location, response.status
                else:
                    print(f"Error: No Location header in redirect for {short_url}")
                    return None, response.status
            else:
                if response.status != 429:  # Don't spam logs with rate limit errors
                    print(f"Error: Got status {response.status} for {short_url}")
                return None, response.status

        finally:
            conn.close()

    except Exception as e:
        print(f"Error expanding {short_url}: {type(e).__name__}: {e}")
        return None, 0


def worker_thread(
    work_queue: queue.Queue, result_queue: queue.Queue, stats: Stats, thread_id: int, max_retries: int = 3
) -> None:
    """
    Worker thread that processes URLs from the work queue.

    Args:
        work_queue: Queue containing (uri, fragment) tuples to process
        result_queue: Queue for results to be written to database
        stats: Shared statistics object
        thread_id: Thread identifier for logging
        max_retries: Maximum retries for rate-limited requests
    """
    backoff_base = 1.0  # Start with 1 second backoff

    while True:
        try:
            # Get work item with timeout to allow clean shutdown
            uri, fragment = work_queue.get(timeout=1)
        except queue.Empty:
            break

        try:
            # Add small random jitter to prevent thundering herd
            time.sleep(random.uniform(0, 0.5))

            # Try to expand the link with exponential backoff
            expanded = None
            status = 0
            backoff = 0

            for attempt in range(max_retries):
                expanded, status = expand_google_link(uri, backoff)

                if status == 429:  # Rate limited
                    stats.increment("errors_429")
                    backoff = min(backoff_base * (2**attempt), 60)  # Max 60s backoff
                    print(f"Thread {thread_id}: Rate limited, backing off {backoff:.1f}s")
                    continue
                elif status == 503:  # Service unavailable
                    backoff = min(backoff_base * (2**attempt), 30)
                    time.sleep(backoff)
                    continue
                else:
                    break

            # Queue the result for database write
            result_queue.put((fragment, expanded, status))

            if expanded:
                if status != 302:
                    stats.increment("errors_other")
                else:
                    stats.increment("success")
                    print(f"Thread {thread_id}: Success: {uri} -> {expanded}")
            else:
                stats.increment("failed")
                if status != 429:  # Don't double-count 429s
                    print(f"Thread {thread_id}: Failed: {uri} (status: {status})")

        except Exception as e:
            print(f"Thread {thread_id}: Error processing {uri}: {type(e).__name__}: {e}")
            stats.increment("failed")
            result_queue.put((fragment, None, 0))
        finally:
            work_queue.task_done()


def writer_thread(result_queue: queue.Queue, db_path: str, stop_event: threading.Event) -> None:
    """
    Single writer thread that handles all database writes.

    Args:
        result_queue: Queue containing (fragment, expanded_url, status) tuples
        db_path: Path to database file
        stop_event: Event to signal thread shutdown
    """
    # Create connection in this thread
    conn = sqlite3.connect(db_path)

    while not stop_event.is_set() or not result_queue.empty():
        try:
            fragment, expanded_url, status = result_queue.get(timeout=0.1)
            store_url(conn, fragment, expanded_url)
            result_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Writer thread error: {type(e).__name__}: {e}")

    conn.close()


def progress_thread(stats: Stats, stop_event: threading.Event) -> None:
    """
    Thread that periodically prints progress updates.

    Args:
        stats: Shared statistics object
        stop_event: Event to signal thread shutdown
    """
    while not stop_event.is_set():
        time.sleep(10)  # Update every 10 seconds
        progress = stats.get_progress()

        if progress["total"] > 0:
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(progress["elapsed"]))
            print(
                f"\nProgress: {progress['processed']}/{progress['total']} "
                f"({progress['percent']:.1f}%) - "
                f"Rate: {progress['rate']:.1f}/s - "
                f"Elapsed: {elapsed_str}"
            )
            print(
                f"  Cached: {progress['cached']}, "
                f"Success: {progress['success']}, "
                f"Failed: {progress['failed']}, "
                f"Rate limits: {progress['errors_429']}"
            )


def process_csv(filename: str, db_path: str = "google_links.db", num_threads: int = 5) -> None:
    """
    Process a CSV file containing uris with Google shortened links using multiple threads.

    Args:
        filename: Path to the CSV file
        db_path: Path to the SQLite database file
        num_threads: Number of worker threads to use
    """
    # Create/connect to database
    conn = create_database(db_path)

    # Queues and shared state
    work_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
    result_queue: queue.Queue[Tuple[str, Optional[str], int]] = queue.Queue()
    stats = Stats()
    stop_event = threading.Event()

    try:
        # Read CSV and populate work queue
        print(f"Loading URIs from {filename}...")
        with open(filename, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            # Check if uri column exists
            fieldnames = reader.fieldnames or []
            if "uri" not in fieldnames:
                print(f"Error: No 'uri' column found in CSV. Available columns: {fieldnames}")
                return

            # First pass: load all work items and check cache
            work_items = []
            for _row_num, row in enumerate(reader, start=2):
                uri = row.get("uri", "").strip()

                if not uri:
                    stats.increment("failed")
                    continue

                # Extract fragment from URI
                if uri.startswith("/g/"):
                    fragment = uri[3:]
                else:
                    print(f"Warning: URI doesn't match expected format: {uri}")
                    stats.increment("failed")
                    continue

                # Check if already in database
                found, cached_url = get_cached_url(conn, fragment)
                if found:
                    stats.increment("cached")
                    if cached_url is None:
                        print(f"Cached (invalid): {uri}")
                    # Don't print successful cached entries to reduce noise
                    continue

                work_items.append((uri, fragment))

            stats.total = stats.cached + stats.failed + len(work_items)
            print(
                f"Found {stats.total} total URIs: {stats.cached} cached, "
                f"{len(work_items)} to process, {stats.failed} invalid"
            )

            # Add work items to queue
            for item in work_items:
                work_queue.put(item)

        # Start threads
        print(f"Starting {num_threads} worker threads...")

        # Writer thread
        writer = threading.Thread(target=writer_thread, args=(result_queue, db_path, stop_event))
        writer.start()

        # Progress thread
        progress = threading.Thread(target=progress_thread, args=(stats, stop_event))
        progress.daemon = True  # Dies when main thread dies
        progress.start()

        # Worker threads
        workers = []
        for i in range(num_threads):
            t = threading.Thread(target=worker_thread, args=(work_queue, result_queue, stats, i + 1))
            t.start()
            workers.append(t)

        # Wait for all work to complete
        work_queue.join()

        # Wait for workers to finish
        for t in workers:
            t.join()

        # Signal writer to stop after processing remaining items
        result_queue.join()
        stop_event.set()
        writer.join()

        # Final statistics
        final_stats = stats.get_progress()
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(final_stats["elapsed"]))

        print(f"\n{'=' * 60}")
        print("Summary:")
        print(f"Total URIs: {final_stats['total']}")
        print(f"Already cached: {final_stats['cached']}")
        print(f"Successfully expanded: {final_stats['success']}")
        print(f"Failed to expand: {final_stats['failed']}")
        print(f"Rate limit errors: {final_stats['errors_429']}")
        print(f"Total time: {elapsed_str}")
        print(f"Average rate: {final_stats['rate']:.1f} URIs/second")

    except FileNotFoundError:
        print(f"Error: File '{filename}' not found")
    except csv.Error as e:
        print(f"Error reading CSV: {e}")
    except Exception as e:
        print(f"Unexpected error: {type(e).__name__}: {e}")
        stop_event.set()
    finally:
        conn.close()


# Main entry point removed - this module is now used by the ce CLI tool
