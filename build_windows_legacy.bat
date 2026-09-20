@echo off
setlocal
py -3.11 -m pip install --upgrade pip
py -3.11 -m pip install -r requirements.txt pyinstaller
py -3.11 -m PyInstaller --noconfirm --clean --windowed --name "MiniCut Studio Agent" --collect-all PySide6 --hidden-import PySide6.QtMultimedia --hidden-import PySide6.QtMultimediaWidgets src\minicut_studio_agent.py
py -3.11 -m PyInstaller --noconfirm --clean --console --name "MiniCut MCP" --collect-all mcp src\minicut_mcp.py
echo.
echo Selesai: dist\MiniCut Studio Agent
pause
