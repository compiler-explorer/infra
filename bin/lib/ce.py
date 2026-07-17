#!/usr/bin/env python3

from __future__ import annotations

import logging

from lib.cli import cli

logger = logging.getLogger(__name__)


def main():
    try:
        cli(prog_name="ce")
    except KeyboardInterrupt:
        # print empty line so terminal prompt doesn't end up on the end of some
        # of our own program output
        print()
    except SystemExit:
        print()
        raise


if __name__ == "__main__":
    main()
