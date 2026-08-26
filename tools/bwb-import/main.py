#!/usr/bin/env python3
"""Ingang zodat ``python main.py [BWB-id]`` werkt vanuit de projectwortel."""

from __future__ import annotations

import sys

from app.main import main

if __name__ == "__main__":
    sys.exit(main())
