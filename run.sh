#!/bin/bash
# Start ComfyUI in a new tab
gnome-terminal --tab -- bash -c "cd ~/Agents/ComfyUI && source .venv/bin/activate && python3 main.py; exec bash"

# NOTE: if you build a headless auto-run script in the future,
# add a sleep here to let ComfyUI bind to 8188 before dispatching jobs

# Start the pipeline
source .venv/bin/activate
python3 main.py
