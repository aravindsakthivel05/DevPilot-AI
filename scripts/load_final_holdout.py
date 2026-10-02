"""Pin a second, untouched Python/Java pair for the final generalization check."""

from pathlib import Path

from scripts.load_clean_holdout import main

SOURCES = {
    "urllib3": "https://github.com/urllib3/urllib3",
    "commons-collections": "https://github.com/apache/commons-collections",
}
OUTPUT = Path("evaluation/final-holdout-snapshots.json")


if __name__ == "__main__":
    main(SOURCES, OUTPUT)
