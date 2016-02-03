#!/usr/bin/python3

import argparse
import ctypes
import json
import os
import pwd
import subprocess
import sys
import tempfile
import time
import urllib.request as request

def handle_options():
    """Setup option parsing
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store", default=None,
                        help="More verbose output.")
    args = parser.parse_args()
    return args

def validate_ister():
    


def main():
    """Start the installer
    """
    args = handle_options()
    try:
        validate_ister(args)
    except Exception as exep:
        print("Failed: {}".format(exep))
        sys.exit(-1)

    sys.exit(0)

if __name__ == '__main__':
    main()

