@echo off
cd /d %~dp0

echo [v3] Шаг 1/3 — VM-обфускация botplsdonate_v3.lua (PDInner preset)...
cd Prometheus
lua prometheus-main.lua --preset PDInner ..\src\botplsdonate_v3.lua --out ..\inner.lua
cd ..

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Обфускация Prometheus не удалась.
    echo Fallback: копируем исходник как inner.lua без обфускации...
    copy /Y src\botplsdonate_v3.lua inner.lua
)

echo.
echo [v3] Шаг 2/3 — Сборка obfuscated_script.lua (wrapper + inner)...
python build_script.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] build_script.py завершился с ошибкой.
    pause
    exit /b 1
)

echo.
echo [v3] Шаг 3/3 — Обфускация loader_v2.lua...
cd Prometheus
lua prometheus-main.lua --preset Minify ..\loader_v2.lua --out ..\loader_v2_obf.lua
cd ..

if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Обфускация лоадера не удалась — loader_v2.lua остаётся без обфускации.
    copy /Y loader_v2.lua loader_v2_obf.lua
) else (
    echo [OK] loader_v2_obf.lua готов.
    echo      Раздавай пользователям loader_v2_obf.lua (вместо loader_v2.lua).
)

echo.
echo ========================================
echo [OK] Готово!
echo   obfuscated_script.lua — замени на сервере
echo   loader_v2_obf.lua     — раздавай пользователям
echo   Перезапуск server_v2.py НЕ нужен.
echo ========================================
echo.
pause
