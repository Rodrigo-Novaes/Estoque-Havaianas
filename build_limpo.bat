@echo off
echo ================================
echo CRIANDO EXECUTAVEL HAVAIANAS
echo ================================
echo.

cd /d D:\COMPILAR\havaianas_BUILD

call .\.venv\Scripts\activate

pyinstaller ^
    --name="Havaianas Estoque" ^
    --windowed ^
    --onefile ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --hidden-import flask ^
    --hidden-import sqlalchemy ^
    --hidden-import webview ^
    --hidden-import webview.platforms.winforms ^
    desktop.py

echo.
echo ================================
echo ✅ PRONTO! Executavel em: dist\
echo ================================
pause