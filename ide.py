#!/usr/bin/env python3
"""
UnitLang IDE Launcher.
Start the local UnitLang Web IDE by running:
    python ide.py
"""
import sys
from ide_server import start_server

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="UnitLang Web IDE")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    start_server(port=args.port, open_browser=not args.no_browser)
