"""Serve saved CLI jobs on loopback using the existing HTTP application."""

import argparse
from pathlib import Path

import uvicorn
from privacytrace.main import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.store_dir), host="127.0.0.1", port=args.port)
