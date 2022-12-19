@echo off 
setlocal enableDelayedExpansion

REM Licznik użyc
set /a LICZNIK_FAILI=0
REM Licznik kilometrów
set /a LICZNIK1=0
set /a LICZNIK2=0
set /a LICZNIK=0


REM Zbierz pierwsze kilometry
SII_Decrypt.exe ..\..\profile.sii >nul
for /f %%i in ('sed -n "s/cached_distance: \([[:digit:]]\)/\1/p" ..\..\profile.sii') do set LICZNIK1=%%i
for /f %%i in ('sed -n "s/cached_distance: \([[:digit:]]\)/\1/p" ..\..\profile.sii') do set LICZNIK2=%%i

:loop
for %%a in (game.sii) do set filetimesize=%%~tza
    :checkupdate
REM Sprawdzenie czy czas pliku sie zmienił
        ping 127.0.0.1 -n 3 > NUL
        for %%a in (game.sii) do if "!filetimesize!"=="%%~tza" goto checkupdate
REM Naprawa gówna
    SII_Decrypt.exe game.sii >nul
REM TO GÓWNO NIŻEJ WYGLĄDA NA TRUDNIEJSZE NIŻ WYGLĄDA
    REM zamienia "wear: x" na "wear: 0"
	sed -i -r "s/wear: .*/wear: 0/g" game.sii
    REM zamienia "wear[y]: x" na "wear[y]: 0"					I JEST KURWA W PYTE POJEBANY
	sed -i "s/wear\[\([0-9]\+\)\]: .*/wear[\1]: 0/g" game.sii
REM weź nowe wskazanie
    SII_Decrypt.exe ..\..\profile.sii >nul
    for /f %%i in ('sed -n "s/cached_distance: \([[:digit:]]\)/\1/p" ..\..\profile.sii') do set LICZNIK1=%%i 
REM policz kikometry
    set /a LICZNIK=LICZNIK1-LICZNIK2  
REM Policz faile
    set /a LICZNIK_FAILI+=1
REM przestaw liczniki
    set /a LICZNIK2=LICZNIK1
REM zwyzywaj użytkownika
    echo %time:~0,8% Naprawa numer \!LICZNIK_FAILI!/ Od ostatniej naprawy minelo !LICZNIK! km 
REM I W KOŁO MACIEJU
    goto loop