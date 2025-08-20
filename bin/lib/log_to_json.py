#!/usr/bin/env python3

from __future__ import annotations

import datetime
import json
import logging
import os
from argparse import ArgumentParser
from pathlib import Path

import boto3

s3_client = boto3.client("s3")

logger = logging.getLogger("log_to_json")


def main():
    parser = ArgumentParser(
        prog="log_to_json", description="Copy a directory of outputs to a json file on an s3 bucket"
    )
    parser.add_argument("dir")
    parser.add_argument("base")
    args = parser.parse_args()
    base = args.base
    if base[-1] != "/":
        base += "/"
    expires = datetime.datetime.now() + datetime.timedelta(seconds=30)
    log_prefix = f"{base}logs/"
    root_obj = {}
    for root, dirs, files in os.walk(args.dir, topdown=True):
        obj_path = root[len(args.dir) :]
        obj = root_obj
        for sub in obj_path.split("/"):
            if sub:
                obj = obj[sub]
        for d in dirs:
            obj[d] = {}
        for f in files:
            file_path = Path(root) / f
            if f == "log":
                log_path = f"{log_prefix}{os.path.basename(root)}"
                with file_path.open("rb") as file_obj:
                    print(f"Uploading {log_path}...")
                    s3_client.put_object(
                        Bucket="compiler-explorer", Key=log_path, Body=file_obj, Expires=expires, ACL="public-read"
                    )
                obj[f] = f"logs/{os.path.basename(root)}"
            else:
                obj[f] = file_path.read_text(encoding="utf-8")
    key = f"{base}buildStatus.json"
    print(f"Uploading {key}...")
    s3_client.put_object(
        Bucket="compiler-explorer", Key=key, Body=json.dumps(root_obj), Expires=expires, ACL="public-read"
    )
