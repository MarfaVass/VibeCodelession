@echo off
rem ============================================================
rem  PDF Studio - запуск приложения двойным кликом из Проводника.
rem  Файл работает из любого места (в т.ч. с Рабочего стола):
rem  пути определяются от своей папки.
rem ============================================================
setlocal
set "STUDIO_DIR=%~dp0"
set "PYTHON=%STUDIO_DIR%..\venv\Scripts\pythonw.exe"
set "APP=%STUDIO_DIR%app.py"

if not exist "%PYTHON%" (
    echo Не найден Python-интерпретатор:
    echo   %PYTHON%
    echo.
    echo Запустите через PowerShell из корня репозитория:
    echo   .\venv\Scripts\python.exe pdf_studio\app.py
    pause
    exit /b 1
)
if not exist "%APP%" (
    echo Не найдено приложение:
    echo   %APP%
    pause
    exit /b 1
)
start "" "%PYTHON%" "%APP%"
endlocal
exit /b 0