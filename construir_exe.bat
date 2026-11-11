@echo off
rem Construye el ejecutable para el laboratorio (sin instalar nada en el PC del laboratorio).
rem Doble clic en este fichero. Usa el entorno conda "ur3e" (Python 3.12 + PyBullet + visualizador).
rem Resultado: carpeta dist\visualizador_ur3e (y el zip dist\visualizador_ur3e.zip) para llevar en un USB.
cd /d "%~dp0"
call "%USERPROFILE%\miniforge3\Scripts\activate.bat" ur3e
if errorlevel 1 (
    echo No se encuentra Miniforge en %USERPROFILE%\miniforge3 o el entorno ur3e.
    pause
    exit /b 1
)

echo.
echo [1/4] Instalando PyInstaller en el entorno ur3e...
python -m pip install --quiet pyinstaller
if errorlevel 1 goto error

echo [2/4] Empaquetando (tarda unos minutos)...
rem --collect-all: incluye los ficheros de datos (URDF y mallas del robot) y todos los submodulos.
python -m PyInstaller --noconfirm --clean --console --name visualizador_ur3e ^
    --collect-all UR3e_rg2 --collect-all pybullet_planning ^
    --hidden-import primaria --hidden-import tiempo_real --hidden-import varios_robots ^
    --hidden-import ensenar_reproducir --hidden-import herramientas.robot_falso ^
    lanzador.py
if errorlevel 1 goto error

echo [3/4] Copiando configuracion junto al ejecutable (secuencias vacia)...
xcopy /e /i /y config dist\visualizador_ur3e\config >nul
rem secuencias\ va vacia a proposito: las secuencias de URSim (demo.json) no deben llegar al robot real.
rem En el laboratorio los puntos se ensenan sobre el propio robot.
if not exist dist\visualizador_ur3e\secuencias mkdir dist\visualizador_ur3e\secuencias
copy /y docs\CHULETA_LABORATORIO.md dist\visualizador_ur3e\ >nul

echo [4/4] Comprimiendo en dist\visualizador_ur3e.zip...
powershell -NoProfile -Command "Compress-Archive -Force -Path dist\visualizador_ur3e -DestinationPath dist\visualizador_ur3e.zip"
if errorlevel 1 goto error

echo.
echo LISTO. Copia dist\visualizador_ur3e.zip a un USB.
echo En el laboratorio: descomprimir y doble clic en visualizador_ur3e\visualizador_ur3e.exe
pause
exit /b 0

:error
echo.
echo ERROR: algo ha fallado. Copia el texto de esta ventana y pegalo en el chat.
pause
exit /b 1
