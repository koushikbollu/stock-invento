#!/bin/sh
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3.10 or newer is required. Install Python, then run this launcher again."
    read -r _inventory_wait
    exit 1
fi
python3 run_demo.py "$@"
_inventory_status=$?
if [ "$_inventory_status" -ne 0 ]; then
    echo "See the error above. Press Return to close."
    read -r _inventory_wait
fi
exit "$_inventory_status"
