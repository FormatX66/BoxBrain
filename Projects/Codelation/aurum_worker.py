#!/usr/bin/env python3
"""Aurum persistent worker: resumes Slush and performs bounded development cycles."""
import sqlite3, json, time
from pathlib import Path
from aurum_hive import AurumHive

ROOT = Path(__file__).resolve().parent
DB = ROOT / "slush.db"


def cycle(node_name="Aurum-Worker"):
    hive = AurumHive(node_name, ["slush", "python", "worker", "event-driven"])
    wakes = hive.receive()
    return wakes


def run_forever(idle_seconds=5):
    while True:
        wakes = cycle()
        for wake in wakes:
            print("Aurum wake:", json.dumps(wake, sort_keys=True), flush=True)
        time.sleep(idle_seconds)


if __name__ == "__main__":
    run_forever()
