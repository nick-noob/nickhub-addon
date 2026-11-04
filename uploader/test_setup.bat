@echo off
cd /d "%~dp0"
python nickhub_app.py --test --config config.json
pause
