@echo off
rem Abre una consola con el entorno conda "ur3e" (Python 3.12 + PyBullet) en la carpeta del proyecto.
rem Doble clic en este fichero. Para la ventana 3D: python primaria.py, python tiempo_real.py, python varios_robots.py ...
cd /d "%~dp0"
call "%USERPROFILE%\miniforge3\Scripts\activate.bat" ur3e
if errorlevel 1 echo No se encuentra Miniforge en %USERPROFILE%\miniforge3 o el entorno ur3e.
echo.
echo Consola lista: entorno ur3e en %CD%
echo.
cmd /k
