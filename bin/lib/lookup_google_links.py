#!/usr/bin/env python3
"""
Script to expand Google shortened URLs from a CSV file or AWS Athena query.
Reads a CSV with uri column containing /g/* links and expands them.
Stores results in a SQLite database for idempotent operation.
Supports multi-threaded processing for faster operation.
"""

import csv
import http.client
import io
import logging
import queue
import random
import sqlite3
import threading
import time
import urllib.parse
from typing import Any, Dict, Optional, Tuple, Union

import boto3
import click

logger = logging.getLogger(__name__)


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
            click.echo(f"Warning: URL doesn't match expected format: {short_url}")
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
                    click.echo(f"Error: No Location header in redirect for {short_url}")
                    return None, response.status
            else:
                if response.status != 429:  # Don't spam logs with rate limit errors
                    click.echo(f"Error: Got status {response.status} for {short_url}")
                return None, response.status

        finally:
            conn.close()

    except Exception as e:
        click.echo(f"Error expanding {short_url}: {type(e).__name__}: {e}")
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
                    click.echo(f"Thread {thread_id}: Rate limited, backing off {backoff:.1f}s")
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
                    logger.debug(f"Thread {thread_id}: Success: {uri} -> {expanded}")
            else:
                stats.increment("failed")
                if status != 429:  # Don't double-count 429s
                    logger.debug(f"Thread {thread_id}: Failed: {uri} (status: {status})")

        except Exception as e:
            click.echo(f"Thread {thread_id}: Error processing {uri}: {type(e).__name__}: {e}")
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
            click.echo(f"Writer thread error: {type(e).__name__}: {e}")

    conn.close()


def execute_athena_query(query: str, database: str = "default", output_location: Optional[str] = None) -> str:
    """
    Execute an Athena query and return the S3 path to results.

    Args:
        query: SQL query to execute
        database: Athena database name
        output_location: S3 location for query results (optional)

    Returns:
        S3 path to the query results CSV file

    Raises:
        Exception: If query fails or times out
    """
    athena = boto3.client("athena")

    # Determine output location
    if not output_location:
        # Try to get default output location from Athena workgroup
        try:
            response = athena.get_work_group(WorkGroup="primary")
            output_location = response["WorkGroup"]["Configuration"]["ResultConfiguration"]["OutputLocation"]
        except Exception:
            # Get the AWS account ID and region for the default bucket name
            sts = boto3.client("sts")
            account_id = sts.get_caller_identity()["Account"]
            region = athena.meta.region_name or "us-east-1"
            # Use the standard Athena results bucket pattern (account_id-region order)
            output_location = f"s3://aws-athena-query-results-{account_id}-{region}/"

    # Start query execution
    response = athena.start_query_execution(
        QueryString=query,
        QueryExecutionContext={"Database": database},
        ResultConfiguration={"OutputLocation": output_location},
    )

    query_execution_id = response["QueryExecutionId"]

    # Poll for query completion
    max_attempts = 100
    for attempt in range(max_attempts):
        response = athena.get_query_execution(QueryExecutionId=query_execution_id)
        status = response["QueryExecution"]["Status"]["State"]

        if status == "SUCCEEDED":
            # Get the S3 path to results
            results_location = response["QueryExecution"]["ResultConfiguration"]["OutputLocation"]
            # OutputLocation already contains the full path to the CSV file
            logger.debug(f"Query succeeded, results at: {results_location}")
            return results_location
        elif status in ["FAILED", "CANCELLED"]:
            reason = response["QueryExecution"]["Status"].get("StateChangeReason", "Unknown error")
            raise Exception(f"Query {status}: {reason}")

        # Still running, wait before checking again
        time.sleep(2 if attempt < 10 else 5)  # Start with 2s, then 5s after 10 attempts

    raise Exception(f"Query timed out after {max_attempts} attempts")


def read_csv_from_s3(s3_path: str) -> io.StringIO:
    """
    Read a CSV file from S3 and return it as a StringIO object.

    Args:
        s3_path: Full S3 path (s3://bucket/key)

    Returns:
        StringIO object containing the CSV data
    """
    # Parse S3 path
    if not s3_path.startswith("s3://"):
        raise ValueError(f"Invalid S3 path: {s3_path}")

    parts = s3_path[5:].split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 path: {s3_path}")

    bucket, key = parts
    logger.debug(f"Attempting to read from bucket={bucket}, key={key}")

    # Read from S3
    s3 = boto3.client("s3")
    response = s3.get_object(Bucket=bucket, Key=key)

    # Read content and decode
    content = response["Body"].read().decode("utf-8")

    return io.StringIO(content)


def process_from_athena(
    db_path: str,
    num_threads: int = 5,
    athena_database: str = "default",
    athena_output_location: Optional[str] = None,
) -> None:
    """
    Process Google shortened links from CloudFront logs using Athena.

    Args:
        db_path: Path to the SQLite database file
        num_threads: Number of worker threads to use
        athena_database: Athena database to use
        athena_output_location: S3 location for Athena query results
    """
    # Hardcoded query for CloudFront logs
    athena_query = "SELECT DISTINCT(uri) FROM cloudfront_logs WHERE uri LIKE '/g/%'"
    # Create/connect to database
    conn = create_database(db_path)

    # Queues and shared state
    work_queue: queue.Queue[Tuple[str, str]] = queue.Queue()
    result_queue: queue.Queue[Tuple[str, Optional[str], int]] = queue.Queue()
    stats = Stats()
    stop_event = threading.Event()

    try:
        # Execute Athena query
        click.echo("Executing Athena query...")
        s3_path = execute_athena_query(athena_query, athena_database, athena_output_location)
        csv_source = read_csv_from_s3(s3_path)

        try:
            reader = csv.DictReader(csv_source)

            # Check if uri column exists
            fieldnames = reader.fieldnames or []
            if "uri" not in fieldnames:
                click.echo(f"Error: No 'uri' column found in CSV. Available columns: {fieldnames}")
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
                    click.echo(f"Warning: URI doesn't match expected format: {uri}")
                    stats.increment("failed")
                    continue

                # Check if already in database
                found, cached_url = get_cached_url(conn, fragment)
                if found:
                    stats.increment("cached")
                    if cached_url is None:
                        click.echo(f"Cached (invalid): {uri}")
                    # Don't print successful cached entries to reduce noise
                    continue

                work_items.append((uri, fragment))

            stats.total = stats.cached + stats.failed + len(work_items)
            click.echo(f"Found {stats.total} URIs ({stats.cached} cached, {len(work_items)} to process)")

            # Add work items to queue
            for item in work_items:
                work_queue.put(item)

        finally:
            # Close the StringIO object
            csv_source.close()

        # Process work items with progress bar
        if len(work_items) > 0:
            with click.progressbar(
                length=len(work_items),
                label="Processing URIs",
                show_eta=True,
                show_percent=True,
            ) as bar:
                _process_work_items_with_progress(
                    work_queue, result_queue, stats, stop_event, db_path, num_threads, bar
                )

        # Show summary
        final_stats = stats.get_progress()
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(final_stats["elapsed"]))

        click.echo("\nSummary:")
        click.echo(f"  Total: {final_stats['total']} URIs")
        click.echo(f"  Cached: {final_stats['cached']}")
        click.echo(f"  Expanded: {final_stats['success']}")
        click.echo(f"  Failed: {final_stats['failed']}")
        if final_stats["errors_429"] > 0:
            click.echo(f"  Rate limited: {final_stats['errors_429']}")
        click.echo(f"  Time: {elapsed_str} ({final_stats['rate']:.1f} URIs/s)")

    except Exception as e:
        click.echo(f"Error: {type(e).__name__}: {e}")
        stop_event.set()
    finally:
        conn.close()


def process_csv(filename: str, db_path: str = "google_links.db", num_threads: int = 5) -> None:
    """
    Process a CSV file containing uris with Google shortened links.

    This function is kept for backward compatibility but the main entry point
    is now process_from_athena() which queries CloudFront logs directly.

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
        click.echo(f"Loading URIs from {filename}...")
        with open(filename, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            # Check if uri column exists
            fieldnames = reader.fieldnames or []
            if "uri" not in fieldnames:
                click.echo(f"Error: No 'uri' column found in CSV. Available columns: {fieldnames}")
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
                    click.echo(f"Warning: URI doesn't match expected format: {uri}")
                    stats.increment("failed")
                    continue

                # Check if already in database
                found, cached_url = get_cached_url(conn, fragment)
                if found:
                    stats.increment("cached")
                    if cached_url is None:
                        click.echo(f"Cached (invalid): {uri}")
                    continue

                work_items.append((uri, fragment))

            stats.total = stats.cached + stats.failed + len(work_items)
            click.echo(f"Found {stats.total} URIs ({stats.cached} cached, {len(work_items)} to process)")

            # Add work items to queue
            for item in work_items:
                work_queue.put(item)

        # Common processing logic
        _process_work_items(work_queue, result_queue, stats, stop_event, db_path, num_threads)

    except FileNotFoundError:
        click.echo(f"Error: File '{filename}' not found")
    except csv.Error as e:
        click.echo(f"Error reading CSV: {e}")
    except Exception as e:
        click.echo(f"Unexpected error: {type(e).__name__}: {e}")
        stop_event.set()
    finally:
        conn.close()


def _process_work_items(
    work_queue: queue.Queue[Tuple[str, str]],
    result_queue: queue.Queue[Tuple[str, Optional[str], int]],
    stats: Stats,
    stop_event: threading.Event,
    db_path: str,
    num_threads: int,
) -> None:
    """Common logic for processing work items with multiple threads."""
    # Writer thread
    writer = threading.Thread(target=writer_thread, args=(result_queue, db_path, stop_event))
    writer.start()

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


def _process_work_items_with_progress(
    work_queue: queue.Queue[Tuple[str, str]],
    result_queue: queue.Queue[Tuple[str, Optional[str], int]],
    stats: Stats,
    stop_event: threading.Event,
    db_path: str,
    num_threads: int,
    progress_bar,
) -> None:
    """Process work items with multiple threads and update progress bar."""
    # Writer thread
    writer = threading.Thread(target=writer_thread, args=(result_queue, db_path, stop_event))
    writer.start()

    # Worker threads
    workers = []
    for i in range(num_threads):
        t = threading.Thread(target=worker_thread, args=(work_queue, result_queue, stats, i + 1))
        t.start()
        workers.append(t)

    # Monitor progress
    last_processed = 0
    while any(t.is_alive() for t in workers):
        progress = stats.get_progress()
        processed = progress["processed"]
        if processed > last_processed:
            progress_bar.update(processed - last_processed)
            last_processed = processed
        time.sleep(0.5)

    # Wait for all work to complete
    work_queue.join()

    # Wait for workers to finish
    for t in workers:
        t.join()

    # Final progress update
    progress = stats.get_progress()
    processed = progress["processed"]
    if processed > last_processed:
        progress_bar.update(processed - last_processed)

    # Signal writer to stop after processing remaining items
    result_queue.join()
    stop_event.set()
    writer.join()


# Main entry point removed - this module is now used by the ce CLI tool
