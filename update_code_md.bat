@echo off
:: update_code_md.bat - Refresh the project code Markdown file
:: Runs consolidate_code.py with default settings (current directory, output: project_code.md)

:: Try to use 'python' first, fall back to 'py -3'
set "PY_CMD="
where python >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" py -3 >nul 2>&1 && set "PY_CMD=py -3"

if "%PY_CMD%"=="" (
    echo Error: Neither 'python' nor 'py' found in PATH.
    pause
    exit /b 1
)

%PY_CMD% consolidate_code.py

if %errorlevel% neq 0 (
    echo.
    echo The Python script exited with error level %errorlevel%.
    pause
    exit /b %errorlevel%
)

echo.
echo Markdown file has been successfully updated.
echo Output: project_code.md
pause