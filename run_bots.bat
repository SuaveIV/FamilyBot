@echo off
rem This script launches both the FamilyBot (main bot + WebSocket server)
rem and the Token Sender bot in separate Command Prompt windows.
rem
rem Run this script from the FamilyBot/ project root directory.
rem Assumes 'uv' is installed globally or accessible in your PATH.
rem You must manually close the bot windows when you want to stop them.

echo --- Starting FamilyBot and Token Sender ---

rem Get the absolute path of the directory where this script is located
set "PROJECT_ROOT=%~dp0"

rem Check if virtual environment exists
if not exist "%PROJECT_ROOT%.venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found. Please run reinstall_bot.ps1 first.
    pause
    exit /b 1
)

rem Check if FamilyBot script exists
if not exist "%PROJECT_ROOT%src\familybot\FamilyBot.py" (
    echo ERROR: FamilyBot script not found: %PROJECT_ROOT%src\familybot\FamilyBot.py
    pause
    exit /b 1
)

rem Check if Token Sender script exists
if not exist "%PROJECT_ROOT%src\familybot\Token_Sender\getToken.py" (
    echo ERROR: Token Sender script not found: %PROJECT_ROOT%src\familybot\Token_Sender\getToken.py
    pause
    exit /b 1
)

echo Launching FamilyBot (main bot + WebSocket server)...
start "FamilyBot" cmd /k "cd /d "%PROJECT_ROOT%" && call "%PROJECT_ROOT%.venv\Scripts\activate.bat" && uv run python "%PROJECT_ROOT%src\familybot\FamilyBot.py""

echo Launching Token Sender bot...
start "Token Sender" cmd /k "cd /d "%PROJECT_ROOT%" && call "%PROJECT_ROOT%.venv\Scripts\activate.bat" && uv run python "%PROJECT_ROOT%src\familybot\Token_Sender\getToken.py""

echo --- Launch sequence complete ---
echo Check the newly opened Command Prompt windows for bot logs.
pause