"""Start the Aether backend on the configured port.

Plain English: the same as `uvicorn app.main:app --reload`, but the port comes from the settings —
AETHER_API_PORT in backend/.env (default 8000). The website reads that same line, so both always agree.
Handy when another program already uses port 8000.

Run from backend/:   python -m scripts.serve              (auto-restarts when code changes)
                     python -m scripts.serve --no-reload
                     python -m scripts.serve --port 8002  (one-off override)
"""

import argparse
import sys

from app.config import Settings, get_settings


def server_options(settings: Settings, reload: bool, port: int | None = None) -> dict:
    # 127.0.0.1 (not "localhost"): on Windows "localhost" tries IPv6 first and costs ~2 s per request.
    return {"app": "app.main:app", "host": "127.0.0.1", "port": port or settings.api_port, "reload": reload}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, help="override AETHER_API_PORT for this run")
    parser.add_argument("--no-reload", action="store_true", help="don't restart when code changes")
    args = parser.parse_args(argv)
    import uvicorn

    options = server_options(get_settings(), reload=not args.no_reload, port=args.port)
    print(f"Aether backend on http://127.0.0.1:{options['port']}  (docs: /docs, health: /health)")
    uvicorn.run(**options)
    return 0


if __name__ == "__main__":
    sys.exit(main())
