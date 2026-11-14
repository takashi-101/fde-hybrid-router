"""Run the demo without installing the package: python run_demo.py [--db FILE] [--model NAME]"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from hybrid_router.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
