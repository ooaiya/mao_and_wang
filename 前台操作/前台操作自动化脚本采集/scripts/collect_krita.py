#!/usr/bin/env python3
"""Independent collector entry; does not call the legacy wrappers."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from oomlab_krita_collect.cli import main
if __name__=='__main__':raise SystemExit(main())
