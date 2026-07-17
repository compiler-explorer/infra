#!/usr/bin/env python3

from __future__ import annotations

from lib.amazon import list_compilers


def main():
    print(" ".join(list_compilers(with_extension=True)))
