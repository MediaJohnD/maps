"""Initializes the database and writes the investor profile from config.py
into the config table as the starting default config.

Run once after cloning:

    python3 seed.py

Safe to re-run — it overwrites the `investor_profile` config row with
whatever's currently in config.py, so re-run it after editing your numbers
there. It does not touch any saved deals.
"""

import json
from dataclasses import asdict

import db
from config import DEFAULT_INVESTOR_PROFILE


def main() -> None:
    db.init_db()
    db.set_config("investor_profile", json.dumps(asdict(DEFAULT_INVESTOR_PROFILE)))
    print(f"Initialized database at {db.DB_PATH}")
    print("Seeded investor profile config:")
    print(json.dumps(asdict(DEFAULT_INVESTOR_PROFILE), indent=2))


if __name__ == "__main__":
    main()
