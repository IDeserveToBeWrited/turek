@echo off

:: Skrypt do skopiowania ULTRA FIXA

SET HOME_ATS=%HOME%\Documents\American Truck Simulator
SET HOME_eTS=%HOME%\Documents\Euro Truck Simulator 2

:check_ats
if exist "%HOME_ATS%" goto install_ats

:check_ets
if exist "%HOME_ETS%" goto install_ets

:install_ats
for /D %%b in ("%HOME_ATS%\profiles\*")	do for %%a in (quicksave/*) do if exist "%%b\save\quicksave\" copy quicksave/%%a "%%b\save\quicksave\" >nul 2>&1
echo Zainstalowano w ATS
goto check_ets

:install_ets
for /D %%b in ("%HOME_ETS%\profiles\*")	do for %%a in (quicksave/*) do if exist "%%b\save\quicksave\" copy quicksave/%%a "%%b\save\quicksave\" >nul 2>&1
echo Zainstalowano w ETS2
goto end

:end