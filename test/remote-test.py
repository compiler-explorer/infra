#!/usr/bin/env python3
import glob
import json
import os
import requests
from argparse import ArgumentParser
from difflib import unified_diff

import re

import sys

parser = ArgumentParser()
parser.add_argument("url")
parser.add_argument("directory")
parser.add_argument("--update-compilers", action="store_true")
parser.add_argument("--disabled-by-default", action="store_true")
parser.add_argument("--bless", action="store_true")

FILTERS = [
    ["binary", "labels", "directives", "commentOnly", "intel"],
    ["binary", "labels", "directives", "commentOnly"],
    ["labels", "directives", "commentOnly", "intel"],
    ["labels", "directives", "commentOnly"],
]


def get(session, url, compiler, options, source, filters):
    r = requests.post(
        url + "api/compiler/" + compiler + "/compile",
        json={
            "source": source,
            "options": options,
            "filters": {key: True for key in filters},
        },
        headers={"Accept": "application/json"},
    )

    r.raise_for_status()

    def fixup(obj):
        try:
            if "text" in obj:
                obj["text"] = re.sub(r"/tmp/compiler-explorer-[^/]+", "/tmp", obj["text"])
            return obj
        except:
            print("Issues with obj '{}'".format(obj))
            raise

    result = r.json()
    if "asm" not in result:
        result["asm"] = []
    result["asm"] = [fixup(obj) for obj in result["asm"]]
    return result


def get_compilers(url):
    r = requests.get(url + "api/compilers", headers={"Accept": "application/json"})
    r.raise_for_status()
    return list(sorted([url["id"] for url in r.json()]))


def main(args):
    compilers = get_compilers(args.url)
    compiler_json = os.path.join(args.directory, "compilers.json")
    compiler_map = {}
    if os.path.exists(compiler_json):
        compiler_map = json.load(open(compiler_json))
    if args.update_compilers:
        for compiler in compilers:
            if compiler not in compiler_map:
                print("New compiler: " + compiler)
                compiler_map[compiler] = not args.disabled_by_default
        for compiler in list(compiler_map):
            if compiler not in compilers:
                print("Compiler removed: " + compiler)
                del compiler_map[compiler]
        with open(compiler_json, "w") as f:
            f.write(json.dumps(compiler_map, indent=2))
        print("Compilers updated to " + compiler_json)
        return 0
    else:
        compilers = list(sorted(compilers))
        expected = list(sorted(compiler_map.keys()))
        if expected != compilers:
            raise RuntimeError(
                "Compiler list changed:\n{}".format(
                    "\n".join(list(unified_diff(compilers, expected, fromfile="got", tofile="expected")))
                )
            )
    with requests.Session() as session:
        for test_dir in glob.glob(os.path.join(args.directory, "*")):
            if not os.path.isdir(test_dir):
                continue
            print("Testing " + test_dir)
            source_name = glob.glob(os.path.join(test_dir, "test.*"))[0]
            source = open(source_name).read()
            options = open(os.path.join(test_dir, "options")).read()
            for compiler, enabled in compiler_map.iteritems():
                if not enabled:
                    print(" Skipping compiler " + compiler)
                    continue
                print(" Compiler " + compiler)
                for filter_set in FILTERS:
                    print("  Filters " + "; ".join(filter_set))
                    expected_filename = [compiler]
                    expected_filename.extend(sorted(filter_set))
                    expected_filename.append("json")
                    expected_file = os.path.join(test_dir, ".".join(expected_filename))
                    result = get(session, args.url, compiler, options, source, filter_set)
                    if args.bless:
                        with open(expected_file, "w") as f:
                            f.write(json.dumps(result, indent=2))
                    else:
                        expected = json.load(open(expected_file))
                        if expected != result:
                            with open("/tmp/got.json", "w") as f:
                                f.write(json.dumps(result, indent=2))
                            raise RuntimeError("Differences in {}".format(expected_file))


if __name__ == "__main__":
    sys.exit(main(parser.parse_args()))
