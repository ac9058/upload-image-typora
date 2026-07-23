@echo off
setlocal EnableExtensions
REM Force UTF-8 so Typora can parse Chinese/error output correctly
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PYEXE="

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
  set "PYEXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else if exist "%SCRIPT_DIR%venv\Scripts\python.exe" (
  set "PYEXE=%SCRIPT_DIR%venv\Scripts\python.exe"
) else if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Python\bin\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
  set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if defined PYEXE (
  "%PYEXE%" "%SCRIPT_DIR%upload.py" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT_DIR%upload.py" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%SCRIPT_DIR%upload.py" %*
  exit /b %ERRORLEVEL%
)

where python3 >nul 2>&1
if %ERRORLEVEL%==0 (
  python3 "%SCRIPT_DIR%upload.py" %*
  exit /b %ERRORLEVEL%
)

echo 未找到 Python 3，请先安装。当前机器可用路径示例: 1>&2
echo   %LOCALAPPDATA%\Python\bin\python.exe 1>&2
echo 安装依赖请用: 1>&2
echo   "%LOCALAPPDATA%\Python\bin\python.exe" -m pip install -r requirements.txt 1>&2
exit /b 1
