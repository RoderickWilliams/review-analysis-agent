@echo off
title ReviewAgent
cd /d "E:\review-analysis-agent"
start "" "http://localhost:8501"
"E:\review-analysis-agent\venv\Scripts\python.exe" -m streamlit run app.py --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
pause
