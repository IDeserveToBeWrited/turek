@echo off 
setlocal enableDelayedExpansion


:loop
for %%a in (game.sii) do set filetimesize=%%~tza
    :checkupdate
        ping 127.0.0.1 -n 3 > NUL
        for %%a in (game.sii) do if "!filetimesize!"=="%%~tza" goto checkupdate
    SII_Decrypt.exe game.sii
	sed -i -r "s/wear: .*/wear: 0/g" game.sii
	echo naprawiono twoje gowno
    goto loop