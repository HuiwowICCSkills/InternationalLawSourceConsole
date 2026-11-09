@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "CATALOG=%~1"
if not defined CATALOG set "CATALOG=%~dp0..\source-catalog.json"

set "PYEXE="
where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto run

where py >nul 2>nul
if not errorlevel 1 set "PYEXE=py"
if defined PYEXE goto run

echo.
echo 找不到 Python。请先安装 Python 3，或把它加入 PATH，再双击本快捷方式。
echo.
pause
exit /b 1

:run
set PYTHONIOENCODING=utf-8
"%PYEXE%" -u "%~dp0server.py" --catalog "%CATALOG%"
echo.
pause
