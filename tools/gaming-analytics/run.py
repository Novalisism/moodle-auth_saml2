#!/usr/bin/env python3
"""Entry point: python3 run.py <command>. See README.md."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gaming_analytics.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
