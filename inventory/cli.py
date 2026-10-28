"""Small, scriptable command interface. Run from the repository root."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import Inventory, PipelineError


def parser():
    app = argparse.ArgumentParser(description="Auditable daily inventory pipeline (Python standard library only)")
    sub = app.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create database and add validated item/location catalogs")
    init.add_argument("--db", required=True)
    init.add_argument("--items", required=True)
    init.add_argument("--locations", required=True)
    run = sub.add_parser("run", help="ingest CSV and atomically publish balances")
    run.add_argument("--db", required=True)
    run.add_argument("--input", required=True)
    run.add_argument("--through", help="inclusive YYYY-MM-DD reporting horizon")
    report = sub.add_parser("report", help="print a JSON report")
    report.add_argument("--db", required=True)
    export = sub.add_parser("export", help="export all ledger and audit rows plus a report")
    export.add_argument("--db", required=True)
    export.add_argument("--out", required=True)
    serve = sub.add_parser("serve", help="open a local dashboard with guarded CSV imports")
    serve.add_argument("--db", required=True)
    serve.add_argument("--port", type=int, default=8765)
    password = sub.add_parser("set-password", help="change the local admin password with a hidden prompt; restart the server afterward")
    password.add_argument("--db", required=True)
    generate = sub.add_parser("generate", help="generate reproducible synthetic catalogs and events")
    generate.add_argument("--out", required=True)
    generate.add_argument("--rows", type=int, default=100000)
    generate.add_argument("--seed", type=int, default=42)
    demo = sub.add_parser("demo", help="run the 50-event demonstration and sample correction, then export")
    demo.add_argument("--out", default="var/demo")
    return app


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parser().parse_args(argv)
    try:
        if args.command == "generate":
            from .generate import generate
            result = generate(args.out, rows=args.rows, seed=args.seed)
        elif args.command == "demo":
            data = Path(__file__).resolve().parent.parent / "data"
            demo = data / "demo"
            output = Path(args.out)
            inventory = Inventory(output / "inventory.db")
            inventory.load_catalogs(demo / "items.csv", demo / "locations.csv")
            first = inventory.ingest(demo / "movements.csv", through="2026-01-04")
            second = inventory.ingest(data / "sample" / "corrections.csv", through="2026-01-04")
            from .demo import seed_demo_examples
            examples = seed_demo_examples(inventory, first, second, demo)
            result = dict(runs=[first, second], export=inventory.export(output / "export"),
                          demo_examples=examples,
                          dashboard=f"python3 -m inventory serve --db {output / 'inventory.db'} --port 8765")
        else:
            if args.command != "init" and not Path(args.db).is_file():
                raise ValueError("database does not exist; run init or demo first")
            inventory = Inventory(args.db)
            if args.command == "init":
                result = inventory.load_catalogs(args.items, args.locations)
            elif args.command == "run":
                result = inventory.ingest(args.input, through=args.through)
            elif args.command == "report":
                result = inventory.report()
            elif args.command == "export":
                result = inventory.export(args.out)
            elif args.command == "serve":
                from .web import serve
                serve(args.db, port=args.port)
                return 0
            elif args.command == "set-password":
                from getpass import getpass
                from .auth import set_password
                password = getpass("New admin password: ")
                if password != getpass("Confirm password: "):
                    raise ValueError("Passwords do not match")
                set_password(inventory, password)
                result = {"username": "admin", "password_updated": True,
                          "next_step": "Restart the local server to revoke existing sessions"}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2 if result.get("status") == "succeeded_with_rejects" else 0
    except (PipelineError, ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
