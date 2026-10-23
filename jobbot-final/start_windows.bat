@echo off
cd /d "%~dp0"
echo === JobBot: first run installs everything (3-5 minutes), later runs start in seconds ===
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt
playwright install chromium
echo Opening JobBot in your browser ...
streamlit run app.py
pause
