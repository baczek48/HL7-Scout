@echo off
echo Instalowanie PyInstaller...
pip install pyinstaller --quiet

echo.
echo Generowanie ikony...
python generate_icon.py

echo.
echo Budowanie HL7Scout.exe...
pyinstaller --onefile --windowed ^
    --name "HL7Scout" ^
    --icon "icon.ico" ^
    --add-data "ui;ui" ^
    main.py

echo.
if not exist "dist\HL7Scout.exe" (
    echo BLAD - sprawdz logi powyzej
    pause
    exit /b 1
)

echo Tworzenie paczki HL7Scout.zip...
if exist "dist\HL7Scout.zip" del "dist\HL7Scout.zip"
powershell -NoProfile -Command ^
    "Compress-Archive -Path 'dist\HL7Scout.exe','README.md' -DestinationPath 'dist\HL7Scout.zip'"

echo.
if exist "dist\HL7Scout.zip" (
    echo SUKCES!
    echo   EXE : dist\HL7Scout.exe
    echo   ZIP : dist\HL7Scout.zip
) else (
    echo BLAD przy tworzeniu ZIP
)
pause
