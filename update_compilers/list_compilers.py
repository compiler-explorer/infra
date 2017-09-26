#!/usr/bin/env python

import sys
from urllib2 import urlopen
from argparse import ArgumentParser
import xml.etree.ElementTree as ET


def main(args):
    result = urlopen(args.s3url + "?prefix=" + args.prefix).read()
    root = ET.fromstring(result)
    print "\n".join(
        sorted(key.text[len(args.prefix):] for key in
               root.findall('.//ns:Key', {'ns': 'http://s3.amazonaws.com/doc/2006-03-01/'})))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--s3url', help='S3 repo', default='https://s3.amazonaws.com/compiler-explorer')
    parser.add_argument('--prefix', help='List only using prefix', default='opt/')
    sys.exit(main(parser.parse_args()))
