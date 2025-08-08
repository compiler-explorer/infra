#!/usr/bin/env python3

import glob
import os
import subprocess
import sys
import time
from datetime import datetime
from multiprocessing import Pool

IMG_DIR = "/efs/squash-images"
MOUNT_DIR = "/opt/compiler-explorer"
LOG_FILE = f"/tmp/mount-all-img-{datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
# let's not overwhelm
PARALLEL_WORKERS = 1
SLEEP_AFTER_MOUNT = 0.25


def log_message(message):
    """Log a message with timestamp to both file and stdout"""
    timestamp = time.time()
    log_entry = f"{timestamp:.6f} {message}"
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")
    print(message)


def is_mounted(path):
    """Check if a path is already mounted"""
    result = subprocess.run(["mountpoint", "-q", path], capture_output=True)
    return result.returncode == 0


def mount_image(args):
    """Mount a single squashfs image and return timing info"""
    img_file, dst_path = args
    img_name = os.path.basename(img_file)
    dst_name = os.path.basename(dst_path)

    start_time = time.time()

    # Create mount point directory if it doesn't exist
    os.makedirs(dst_path, exist_ok=True)

    try:
        # Log start
        with open(LOG_FILE, "a") as f:
            f.write(f"{start_time:.6f} MOUNT_START: {img_name} -> {dst_name}\n")

        # Execute mount command
        cmd = ["mount", "-v", "-t", "squashfs", img_file, dst_path, "-o", "ro,nodev,relatime"]
        result = subprocess.run(cmd, capture_output=True, text=True)

        end_time = time.time()
        mount_time = end_time - start_time

        # Log end
        with open(LOG_FILE, "a") as f:
            f.write(f"{end_time:.6f} MOUNT_END: {img_name} took {mount_time:.3f}s\n")
            if mount_time > 1.0:
                f.write(f"{end_time:.6f} SLOW: Mount took {mount_time:.3f}s for {img_name}\n")

        if result.returncode != 0:
            return {"success": False, "image": img_name, "time": mount_time, "error": result.stderr}

        time.sleep(SLEEP_AFTER_MOUNT)

        return {"success": True, "image": img_name, "time": mount_time}

    except RuntimeError as e:
        end_time = time.time()
        mount_time = end_time - start_time
        return {"success": False, "image": img_name, "time": mount_time, "error": str(e)}


def main():
    """Main function to mount all squashfs images in parallel"""
    # Log startup info
    log_message("Starting mount-all-img.py")
    log_message(f"Kernel: {os.uname().release}")

    # Get Ubuntu version
    try:
        result = subprocess.run(["lsb_release", "-d"], capture_output=True, text=True)
        ubuntu_version = result.stdout.split("\t")[1].strip() if result.returncode == 0 else "Unknown"
    except Exception:
        ubuntu_version = "Unknown"
    log_message(f"Ubuntu: {ubuntu_version}")
    log_message(f"Parallel workers: {PARALLEL_WORKERS}")
    log_message(f"Log file: {LOG_FILE}")

    # Scan for images
    log_message(f"Scanning for images in {IMG_DIR}")
    scan_start = time.time()

    # Find all .img files recursively
    img_files = glob.glob(f"{IMG_DIR}/**/*.img", recursive=True)

    # Build list of images to mount
    to_mount = []
    already_mounted = 0

    for img_file in img_files:
        # Convert path: /efs/squash-images/foo/bar.img -> /opt/compiler-explorer/foo/bar
        dst_path = img_file.replace(IMG_DIR, MOUNT_DIR)
        dst_path = dst_path[:-4]  # Remove .img extension

        if is_mounted(dst_path):
            print(f"{dst_path} is mounted already, skipping")
            already_mounted += 1
        else:
            to_mount.append((img_file, dst_path))

    # Sort by creation time (newest first) so recent compilers get mounted first
    log_message("Sorting images by creation time...")
    to_mount.sort(key=lambda x: os.path.getctime(x[0]), reverse=True)

    scan_time = time.time() - scan_start
    log_message(f"Scan completed in {scan_time:.2f}s")
    log_message(f"Found {len(img_files)} total images, {already_mounted} already mounted, {len(to_mount)} to mount")

    if not to_mount:
        log_message("Nothing to do, stopping")
        return 0

    # Mount images in parallel
    print(f"Mounting {len(to_mount)} squashfs images in parallel ({PARALLEL_WORKERS} workers)...")
    mount_start = time.time()

    with Pool(PARALLEL_WORKERS) as pool:
        results = pool.map(mount_image, to_mount)

    mount_time = time.time() - mount_start

    # Analyze results
    successful = sum(1 for r in results if r["success"])
    failed = sum(1 for r in results if not r["success"])
    slow_mounts = [r for r in results if r["time"] > 1.0]

    # Log summary
    log_message(f"All mounts completed in {mount_time:.2f}s")
    log_message(f"Successful: {successful}, Failed: {failed}")

    # Write detailed summary to log file
    with open(LOG_FILE, "a") as f:
        f.write("\n=== Summary ===\n")
        f.write(f"Total mounts attempted: {len(to_mount)}\n")
        f.write(f"Successful: {successful}\n")
        f.write(f"Failed: {failed}\n")
        f.write(f"Total time: {mount_time:.2f}s\n")
        if successful > 0:
            f.write(f"Average time per mount: {mount_time / len(to_mount):.3f}s\n")

        if failed > 0:
            f.write("\n=== Failed mounts ===\n")
            for r in results:
                if not r["success"]:
                    f.write(f"  {r['image']}: {r.get('error', 'Unknown error')}\n")

        if slow_mounts:
            f.write(f"\n=== Slow mounts (>1s) === [{len(slow_mounts)} total]\n")
            # Sort by time, slowest first
            slow_mounts.sort(key=lambda x: x["time"], reverse=True)
            for r in slow_mounts[:20]:  # Show top 20
                f.write(f"  {r['image']}: {r['time']:.3f}s\n")
            if len(slow_mounts) > 20:
                f.write(f"  ... and {len(slow_mounts) - 20} more\n")

    print(f"Log file: {LOG_FILE}")

    # Print summary of slow mounts to console
    if slow_mounts:
        print(f"Found {len(slow_mounts)} slow mounts (>1s), slowest was {max(r['time'] for r in slow_mounts):.2f}s")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
