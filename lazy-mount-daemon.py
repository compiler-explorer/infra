#!/usr/bin/env python3
"""
Lazy Mount Daemon for Compiler Explorer

Monitors file access to /opt/compiler-explorer/ and mounts corresponding
squashfs images on-demand to improve boot performance.
"""

import argparse
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Set

# BPF character matching limit - verifier restricts complex character access chains
BPF_MATCH_LENGTH = 15

# BPF string length limit - for path remainder output after prefix matching
BPFTRACE_STRING_LENGTH = 100


class LazyMountDaemon:
    def __init__(
        self,
        mount_base: str = "/opt/compiler-explorer",
        image_dir: str = "/efs/squash-images",
        daemon: bool = False,
        verbose: bool = False,
    ):
        self.mount_base = mount_base
        self.image_dir = image_dir
        self.daemon = daemon
        self.verbose = verbose

        # Internal state tracking (sufficient for single-threaded design)
        # NOTE: If this daemon is ever made multi-process, external file
        # locking would be required to coordinate between processes.
        # However, since mounting is expensive (~50-200ms), sequential
        # mounting is likely optimal anyway.
        self.mounted_prefixes: Set[str] = set()

        self.process: Optional[subprocess.Popen] = None
        self.shutdown = threading.Event()

        # Image mapping: path_prefix -> image_file_path
        self.image_map: dict[str, str] = {}

        self.setup_logging()
        self.discover_images()

    def setup_logging(self):
        """Configure logging to syslog or console"""
        self.logger = logging.getLogger("lazy-mount-daemon")

        if self.daemon:
            handler = logging.handlers.SysLogHandler(address="/dev/log")
            handler.setFormatter(logging.Formatter("lazy-mount-daemon[%(process)d]: %(levelname)s: %(message)s"))
        else:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

        self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)

    def discover_images(self):
        """Scan image directory and build path prefix to image mapping"""
        self.logger.info(f"Scanning for squashfs images in {self.image_dir}...")

        try:
            image_dir_path = Path(self.image_dir)
            if not image_dir_path.exists():
                self.logger.error(f"Image directory does not exist: {self.image_dir}")
                return

            # Recursively find all .img files
            img_files = list(image_dir_path.rglob("*.img"))

            for img_file in img_files:
                # Get relative path from image_dir and remove .img extension
                rel_path = img_file.relative_to(image_dir_path)
                path_prefix = str(rel_path.with_suffix(""))  # Remove .img extension

                self.image_map[path_prefix] = str(img_file)

            self.logger.info(f"Discovered {len(self.image_map)} image files in {self.image_dir}")
            if self.verbose:
                for prefix, img_path in sorted(self.image_map.items()):
                    self.logger.debug(f"  {prefix} -> {img_path}")

        except Exception as e:
            self.logger.error(f"Failed to discover images: {e}")
            self.image_map = {}

    def daemonize(self):
        """Fork and detach from terminal"""
        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            self.logger.error(f"First fork failed: {e}")
            sys.exit(1)

        os.chdir("/")
        os.setsid()
        os.umask(0)

        try:
            pid = os.fork()
            if pid > 0:
                sys.exit(0)
        except OSError as e:
            self.logger.error(f"Second fork failed: {e}")
            sys.exit(1)

        # Redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        with open(os.devnull, "r") as null_in, open(os.devnull, "w") as null_out:
            os.dup2(null_in.fileno(), sys.stdin.fileno())
            os.dup2(null_out.fileno(), sys.stdout.fileno())
            os.dup2(null_out.fileno(), sys.stderr.fileno())

    def mount_image(self, image_file: str, mount_prefix: str) -> bool:
        """Mount a squashfs image at the specified mount prefix"""
        # Trust internal state - we're the only thing mounting squashfs images
        if mount_prefix in self.mounted_prefixes:
            return True

        mount_point = Path(self.mount_base) / mount_prefix
        self.logger.info(f"Mounting {mount_prefix} from {image_file} to {mount_point}")

        try:
            result = subprocess.run(
                ["mount", "-t", "squashfs", image_file, str(mount_point), "-o", "ro,nodev,relatime"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                self.mounted_prefixes.add(mount_prefix)
                self.logger.info(f"Successfully mounted {mount_prefix}")
                return True
            else:
                # Check if failure indicates already mounted
                stderr_lower = result.stderr.lower()
                if "already mounted" in stderr_lower or "busy" in stderr_lower:
                    self.logger.debug(f"Mount exists, updating state: {mount_prefix}")
                    self.mounted_prefixes.add(mount_prefix)
                    return True
                else:
                    self.logger.error(f"Mount failed: {result.stderr}")
                    return False

        except Exception as e:
            self.logger.error(f"Exception while mounting {mount_prefix}: {e}")
            return False

    def find_matching_image(self, path: str) -> tuple[Optional[str], Optional[str]]:
        """Find the best matching image for a given path.

        TODO: For better performance with many images, consider using binary search
        on a sorted list of prefixes for O(log n) instead of O(path_depth).

        Returns: (image_file_path, mount_prefix) or (None, None)
        """
        if not path.startswith(self.mount_base + "/"):
            return None, None

        # Strip the mount base to get relative path
        remainder = path[len(self.mount_base) + 1 :]
        if not remainder:
            return None, None

        # Split path into components for longest-to-shortest matching
        parts = remainder.split("/")

        # Try from longest to shortest prefix: "a/b/c", "a/b", "a"
        for i in range(len(parts), 0, -1):
            prefix = "/".join(parts[:i])
            if prefix in self.image_map:
                return self.image_map[prefix], prefix

        return None, None

    def handle_access(self, path: str):
        """Handle a file access event"""
        image_file, mount_prefix = self.find_matching_image(path)

        if image_file and mount_prefix and mount_prefix not in self.mounted_prefixes:
            self.logger.debug(f"Access detected for unmounted prefix: {mount_prefix}")
            self.mount_image(image_file, mount_prefix)

    def start_bpftrace(self):
        """Start the bpftrace subprocess to monitor file access"""
        # Ensure mount_base ends with '/' for consistent matching
        mount_base_with_slash = self.mount_base.rstrip("/") + "/"

        # Generate character-by-character comparison for mount_base (limited by BPF verifier)
        # Only check first BPF_MATCH_LENGTH characters to avoid verifier "modified ctx ptr" errors
        match_prefix = mount_base_with_slash[:BPF_MATCH_LENGTH]
        char_comparisons = []
        for i, char in enumerate(match_prefix):
            # Use ASCII decimal values for all characters to avoid bpftrace quote/syntax issues
            ascii_value = ord(char)
            char_comparisons.append(f"args->filename[{i}] == {ascii_value}")

        is_ce_path_condition = " && ".join(char_comparisons)

        # Monitor both exec and file open syscalls with kernel-space filtering
        # Note: Inline filtering logic since bpftrace doesn't support user-defined functions
        bpftrace_script = f"""
            tracepoint:syscalls:sys_enter_execve /pid != {os.getpid()} && ({is_ce_path_condition})/ {{
                printf("CEPATH:%s\\n", str(args->filename + {BPF_MATCH_LENGTH}, {BPFTRACE_STRING_LENGTH}));
            }}

            tracepoint:syscalls:sys_enter_execveat /pid != {os.getpid()} && ({is_ce_path_condition})/ {{
                printf("CEPATH:%s\\n", str(args->filename + {BPF_MATCH_LENGTH}, {BPFTRACE_STRING_LENGTH}));
            }}

            tracepoint:syscalls:sys_enter_openat /pid != {os.getpid()} && ({is_ce_path_condition})/ {{
                printf("CEPATH:%s\\n", str(args->filename + {BPF_MATCH_LENGTH}, {BPFTRACE_STRING_LENGTH}));
            }}
        """

        env = os.environ.copy()
        env["BPFTRACE_STRLEN"] = str(BPFTRACE_STRING_LENGTH)
        env["BPFTRACE_MAX_STRLEN"] = str(BPFTRACE_STRING_LENGTH)

        bpftrace_cmd = ["bpftrace", "-e", bpftrace_script]
        self.logger.info(f"Starting bpftrace monitoring with command: {' '.join(bpftrace_cmd)}")
        self.logger.info(f"bpftrace script: {bpftrace_script.strip()}")

        try:
            self.process = subprocess.Popen(
                bpftrace_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # Use binary mode to handle UTF-8 decode errors
                bufsize=0,
                env=env,
            )

            self.logger.info(f"bpftrace subprocess started with PID: {self.process.pid}")

            # Give bpftrace a moment to initialize
            time.sleep(1)

            # Check if process is still alive
            if self.process.poll() is not None:
                # Process has already exited
                stdout, stderr = self.process.communicate()
                stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
                stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
                self.logger.error(f"bpftrace exited immediately with code {self.process.returncode}")
                self.logger.error(f"bpftrace stdout: {stdout_str}")
                self.logger.error(f"bpftrace stderr: {stderr_str}")
                raise RuntimeError(f"bpftrace failed to start: {stderr_str}")

            self.logger.info("bpftrace appears to be running successfully")

            # Monitor stderr in a separate thread
            def log_stderr():
                try:
                    for line_bytes in self.process.stderr:
                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if line:
                            self.logger.error(f"bpftrace stderr: {line}")
                except Exception as e:
                    self.logger.debug(f"Error reading bpftrace stderr (likely process ended): {e}")

            stderr_thread = threading.Thread(target=log_stderr, daemon=True)
            stderr_thread.start()

            # Process stdout (the actual events)
            try:
                for line_bytes in self.process.stdout:
                    if self.shutdown.is_set():
                        break

                    # Decode with error handling for corrupted/binary data
                    try:
                        line = line_bytes.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        # Skip lines that can't be decoded - they're likely binary data
                        self.logger.debug(f"Skipping line with invalid UTF-8: {line_bytes[:50]}...")
                        continue

                    # Check for our custom prefix to filter out bpftrace status messages
                    if line and line.startswith("CEPATH:"):
                        # Strip the CEPATH: prefix
                        path_remainder = line[7:]  # len("CEPATH:") = 7

                        # Validate that the remainder starts with the expected suffix
                        # BPF matched first BPF_MATCH_LENGTH chars, we need to validate the rest
                        mount_base_with_slash = self.mount_base.rstrip("/") + "/"
                        expected_remainder = mount_base_with_slash[BPF_MATCH_LENGTH:]

                        if path_remainder.startswith(expected_remainder):
                            # Reconstruct full path from remainder (bpftrace outputs path after BPF_MATCH_LENGTH chars)
                            full_path = f"{mount_base_with_slash[:BPF_MATCH_LENGTH]}{path_remainder}"
                            self.handle_access(full_path)
                        else:
                            # False positive - path doesn't actually match our full prefix
                            self.logger.debug(f"Ignoring unexpected path: {path_remainder[:50]}...")
            except Exception as e:
                self.logger.error(f"Error processing bpftrace output: {e}")
                raise

            # If we get here, the monitoring loop ended
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
                stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""
                self.logger.warning(f"bpftrace process ended with code {self.process.returncode}")
                if stderr_str:
                    self.logger.error(f"bpftrace final stderr: {stderr_str}")

        except Exception as e:
            self.logger.error(f"bpftrace error: {e}")
            if hasattr(self, "process") and self.process:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            raise

    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down")
        self.shutdown.set()

        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

        sys.exit(0)

    def run(self):
        """Main daemon loop"""
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)

        if self.daemon:
            self.daemonize()

        self.logger.info(f"Lazy mount daemon starting (PID: {os.getpid()})")
        self.logger.info(f"Monitoring: {self.mount_base}")
        self.logger.info(f"Image directory: {self.image_dir}")

        # Detect existing mounts at startup (one-time /proc/mounts read)
        self.detect_existing_mounts()

        try:
            self.start_bpftrace()
        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            sys.exit(1)

        self.logger.info("Lazy mount daemon stopped")

    def detect_existing_mounts(self):
        """Read /proc/mounts once at startup to populate initial state"""
        mount_count = 0
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith(self.mount_base + "/"):
                        mount_path = parts[1][len(self.mount_base) + 1 :]
                        if mount_path in self.image_map:
                            self.mounted_prefixes.add(mount_path)
                            mount_count += 1
                            self.logger.debug(f"Found existing mount: {mount_path}")
        except Exception as e:
            self.logger.error(f"Error detecting existing mounts: {e}")

        self.logger.info(f"Found {mount_count} existing mounts")


def main():
    parser = argparse.ArgumentParser(description="Lazy Mount Daemon for Compiler Explorer")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as a daemon in the background")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--mount-base",
        default="/opt/compiler-explorer",
        help="Base directory for compiler mounts (default: /opt/compiler-explorer)",
    )
    parser.add_argument(
        "--image-dir",
        default="/efs/squash-images",
        help="Directory containing squashfs images (default: /efs/squash-images)",
    )

    args = parser.parse_args()

    # Check if bpftrace is available
    if not shutil.which("bpftrace"):
        print("Error: bpftrace is not installed or not in PATH")
        sys.exit(1)

    # Check if running as root (only required for actual daemon mode)
    if os.geteuid() != 0:
        print("Error: This daemon must be run as root (required for bpftrace and mounting)")
        sys.exit(1)

    daemon = LazyMountDaemon(
        mount_base=args.mount_base, image_dir=args.image_dir, daemon=args.daemon, verbose=args.verbose
    )

    daemon.run()


if __name__ == "__main__":
    main()
