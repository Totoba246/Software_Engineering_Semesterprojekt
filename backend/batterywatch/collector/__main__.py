"""Entry point: `python -m batterywatch.collector` runs this file.

It only starts main() from main.py, where everything is explained.
"""
import sys

from .main import main

sys.exit(main())
