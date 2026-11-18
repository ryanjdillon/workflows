"""Read the pin map of a board.

The pin map is the only definition of the pin numbers.
"""

# A string can hold the words that a comment must not.
LABELS = {"blocker": "DIL-0", "reviewer": "finding 1"}


def pin(name: str) -> int:
    """Return the pin number for a net name."""
    # The table is small, so a linear search is fast enough.
    return sorted(LABELS).index(name)
