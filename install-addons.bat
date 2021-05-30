@echo off

:: Skrypt do zainstalowania dodatków

SET HOME_ATS=%HOME%\Documents\American Truck Simulator
SET HOME_eTS=%HOME%\Documents\Euro Truck Simulator 2

:check_ats
if exist "%HOME_ATS%" if exist ATS goto install_ats
goto end

:check_ets
if exist "%HOME_ETS%" if exist ETS goto install_ets
goto end

:install_ats
if exist "%HOME_ATS%\babed" (
	del "%HOME_ATS%\babed" > nul & robocopy ATS\babed "%HOME_ATS%\babed" /E >nul 2>&1 
) else ( 
	mkdir "%HOME_ATS%\babed" & robocopy ATS\babed "%HOME_ATS%\babed" /E >nul 2>&1 
) 
echo Zainstalowano w ATS
goto check_ets

:install_ets
if exist "%HOME_ETS%\babed" (
	del "%HOME_ETS%\babed" > nul & robocopy ATS\babed "%HOME_ETS%\babed" /E >nul 2>&1 
) else ( 
	mkdir "%HOME_ETS%\babed" & robocopy ATS\babed "%HOME_ETS%\babed" /E >nul 2>&1 
) 
echo Zainstalowano w ETS2
goto end

:end
pause