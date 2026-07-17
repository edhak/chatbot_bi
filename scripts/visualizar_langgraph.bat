@echo off
REM Regenera diagramas LangGraph desde el grafo compilado (multi-agente).
cd /d "%~dp0.."
python scripts\visualizar_langgraph.py %*
