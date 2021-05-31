@echo off
setlocal enabledelayedexpansion

:: Skrypt do skopiowania ULTRA FIXA

:: skradzione z https://stackoverflow.com/questions/65874349/convert-hex-string-to-ascii-string-in-windows-batch-file


SET HOME_ATS=%HOME%\Documents\American Truck Simulator
SET HOME_ETS=%HOME%\Documents\Euro Truck Simulator 2

SET PROFILES_ATS=
SET PROFILES_ETS=

:check_ats
if exist "%HOME_ATS%" goto install_ats
goto end

:check_ets
if exist "%HOME_ETS%" goto install_ets
goto end

:install_ats
for /D %%b in ("%HOME_ATS%\profiles\*")	do ( if exist "%%b\save\quicksave\" (for %%a in (quicksave/*) do ( copy quicksave/%%a "%%b\save\quicksave\" >nul 2>&1 )) & set "hex=%%~nb" & echo !hex!> temp.hex & call certutil -decodehex temp.hex str.txt >nul & set /p str=<str.txt & set PROFILES_ATS=!str!, !PROFILES_ATS! & del temp.hex >nul & del str.txt >nul)
echo Zainstalowano w ATS na profilach: %PROFILES_ATS%
ping 127.0.0.1 -n 1 >nul
goto check_ets

:install_ets
for /D %%b in ("%HOME_ETS%\profiles\*")	do ( if exist "%%b\save\quicksave\" (for %%a in (quicksave/*) do ( copy quicksave/%%a "%%b\save\quicksave\" >nul 2>&1 )) & set "hex=%%~nb" & echo !hex!> temp.hex & call certutil -decodehex temp.hex str.txt >nul & set /p str=<str.txt & set PROFILES_ETS=!str!, !PROFILES_ETS! & del temp.hex >nul & del str.txt >nul)
echo Zainstalowano w ETS2 na profilach: %PROFILES_ETS%
goto end

:end
endlocal
pause