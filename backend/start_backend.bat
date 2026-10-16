@echo off
cd /d "%~dp0"
title YouTube AI 學習助手 v3.3 本機測試
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 第一次執行：建立 Python 虛擬環境...
    python -m venv .venv
    if errorlevel 1 goto error
    echo [2/2] 安裝套件 FastAPI 與 uvicorn...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto error
)
echo.
echo YouTube AI 學習助手 v3.3 本機測試：請用瀏覽器打開 http://localhost:5173
echo （一定要用 localhost，Google 登入不接受 127.0.0.1）
echo 這個視窗要一直開著；要停止請按 Ctrl+C 或直接關閉視窗。
echo.
".venv\Scripts\python.exe" -m uvicorn app:app --host 127.0.0.1 --port 5173
echo.
echo 後端已停止。如果不是你自己關的，請把上面的訊息截圖給 Claude。
pause
goto :eof

:error
echo.
echo 啟動失敗，請把上面的訊息截圖給 Claude。
pause