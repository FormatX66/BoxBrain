from __future__ import annotations

import argparse
import json
from .resolver import choose_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve a BoxBrain task using the memory priority stack.")
    parser.add_argument("context", help="Path to a task context JSON file.")
    args = parser.parse_args()
    print(json.dumps(choose_file(args.context), indent=2))


if __name__ == "__main__":
    main()
