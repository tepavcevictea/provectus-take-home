"""Start the local investigation page and API.

The process listens on 127.0.0.1 and uses one worker. Live investigations
still require OPENAI_API_KEY. Listing and loading saved reports does not.
"""

from __future__ import annotations


def main() -> None:
    import uvicorn

    uvicorn.run("investigator.api:app", host="127.0.0.1", port=8000, workers=1)


if __name__ == "__main__":
    main()
