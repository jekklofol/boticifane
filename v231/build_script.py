"""
Сборщик финального скрипта для PD Bot v2.

Архитектура двух слоёв:
  - inner.lua   : полная VM-обфускация (Vmify+ConstantArray), логика бота.
                  Получает ключ/uid/api/token через vararg (...).
  - wrapper     : ~15 строк чистого Lua без логики. Сервер инжектит
                  ключ/uid/api/token сюда. Вызывает inner через loadstring.

Итог: obfuscated_script.lua = wrapper_template + "\n" + inner (как long string).
Сервер инжектит только в wrapper — _G.* паттерны в нём гарантированно выживают,
потому что он НЕ обфусцируется.
"""

import sys, os

INNER_FILE  = "inner.lua"
OUTPUT_FILE = "obfuscated_script.lua"

WRAPPER_TEMPLATE = """\
-- PD Bot v2 | wrapper (not obfuscated — server injects key/uid/api/token/secret here)
local _k = _G.__LICENSE_KEY or ""
local _u = _G.__BOUND_UID   or ""
local _a = _G.__API_URL     or ""
local _t = _G.__SESSION_TOKEN or ""
local _s = _G.__RESP_SECRET or ""
local _d = _G.__DASH_URL or ""
local _h = _G.__DEVICE_HWID or ""
_G.__LICENSE_KEY=nil
_G.__BOUND_UID=nil
_G.__API_URL=nil
_G.__SESSION_TOKEN=nil
_G.__RESP_SECRET=nil
_G.__DASH_URL=nil
_G.__DEVICE_HWID=nil
-- Pass values via short-lived global table — more reliable than vararg through VM bytecode.
rawset(_G, '__PD_DATA', {_k, _u, _a, _t, _s, _d, _h})
local _fn=loadstring([=====[
{inner}]=====])
if not _fn then print("[PD] inner load error") return end
pcall(_fn)
"""

def main():
    if not os.path.exists(INNER_FILE):
        print(f"[ERROR] {INNER_FILE} not found. Run obfuscate.bat first.")
        sys.exit(1)

    with open(INNER_FILE, encoding="utf-8") as f:
        inner = f.read().strip()

    # Safety: the chosen long-string level [=====[ ... ]=====] would break if
    # the inner script somehow contains ]=====]. Check and abort if so.
    CLOSING = "]=====]"
    if CLOSING in inner:
        print(f"[ERROR] inner.lua contains {CLOSING!r} — increase long-string level in build_script.py!")
        sys.exit(1)

    result = WRAPPER_TEMPLATE.replace("{inner}", inner)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(result)

    lines = result.count("\n") + 1
    print(f"[OK] {OUTPUT_FILE} built ({lines} lines, inner = {len(inner)} chars)")

if __name__ == "__main__":
    main()
