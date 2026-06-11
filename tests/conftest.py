# ==============================================================
# tests/conftest.py
# Shared pytest configuration and fixtures.
# Adds the project root to sys.path so all tests can import
# backend modules without installation.
# ==============================================================

import sys
from pathlib import Path

# Project root on path for all test files
sys.path.insert(0, str(Path(__file__).parent.parent))
