@echo off

setlocal EnableExtensions

cd /d "%~dp0"

set PYTHONIOENCODING=utf-8

python -X utf8 "%~dp0supervisor.py" --daemon --interval 60

exit /b %errorlevel%

