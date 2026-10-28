"""Start the sample application from any working directory, on any laptop.

Python 3.10+ is required; no packages need installing. Ctrl+C stops the server.
"""

import sys

if sys.version_info < (3, 10):
    print("Stock Invento requires Python 3.10 or newer. Run it with a supported Python interpreter.", file=sys.stderr)
    raise SystemExit(1)

import argparse
import webbrowser
from pathlib import Path

from inventory.cli import main as cli_main
from inventory.web import create_server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="print the URL without opening a browser")
    parser.add_argument("--data-dir", default="var/demo",
                        help="local data folder; relative paths start at the project folder (default: var/demo)")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    root = Path(__file__).resolve().parent
    output = Path(args.data_dir).expanduser()
    output = (output if output.is_absolute() else root / output).resolve()
    result = cli_main(["demo", "--out", str(output)])
    if result:
        return result
    url = f"http://127.0.0.1:{args.port}"
    try:
        server = create_server(output / "inventory.db", port=args.port)
    except OSError as error:
        next_port = args.port + 1 if args.port < 65535 else 8765
        print(f"Could not start the dashboard: {error}. Try --port {next_port}.", file=sys.stderr)
        return 1
    with server:
        print(f"\nStock Invento is ready: {url}\nData folder: {output}\nPress Ctrl+C here to stop.\n", flush=True)
        if not args.no_browser:
            try:
                opened = webbrowser.open(url, new=2)
            except (webbrowser.Error, OSError):
                opened = False
            if not opened:
                print(f"Open {url} manually in your browser.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStock Invento stopped. Your local data is retained.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
