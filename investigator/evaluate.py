"""Command line for the optional live evaluation.

The implementation lives in investigator.evaluation. This module exists so
`python -m investigator.evaluate` matches the documented command.
"""

from investigator.evaluation import main

if __name__ == "__main__":
    raise SystemExit(main())
