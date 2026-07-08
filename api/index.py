import os
import sys

# Make the project root (one level up from /api) importable so `import app`
# finds app.py that lives at the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Vercel's @vercel/python builder looks for a WSGI-compatible `app` object
# in this module - nothing else to do here.
from app import app
