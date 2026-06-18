@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
streamlit run scout_analyzer.py
pause