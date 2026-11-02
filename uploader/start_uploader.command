#!/bin/bash
# Double-click to start the NickHub uploader in Terminal.
cd "$(dirname "$0")"
python3 nickhub_uploader.py
echo
read -n 1 -s -r -p "Uploader stopped. Press any key to close."
