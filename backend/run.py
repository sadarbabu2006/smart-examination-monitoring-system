"""Development server entry point.

The backend and computer_vision packages are siblings under the project root.
When this file is run directly, Python otherwise adds only ``backend/`` to the
module search path, so make the project root available before importing Flask.
"""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
