"""
Генерирует v23/src/botplsdonate_v3.lua из ../../botplsdonate.lua.

Изменения vs оригинал:
  1. Добавляет блок защиты (чтение _G.__PD_DATA, проверка UID, валидация лицензии)
     сразу после строки "local PLACE_ID = 8737602449"
  2. Удаляет SCRIPT_URL (reconnect идёт через API_BASE_URL/v2/getscript)
  3. Заменяет блок _reconnectScript на вызов getscript
  4. Добавляет session_token = SESSION_TOK в тело pd_update
"""

import os, sys, re

SRC  = os.path.join(os.path.dirname(__file__), "..", "botplsdonate.lua")
DEST = os.path.join(os.path.dirname(__file__), "src", "botplsdonate_v3.lua")

PROTECT_BLOCK = """
-- ==================== PROTECTED: injected values ====================
local _pd_d        = rawget(_G, '__PD_DATA') or {}
local LICENSE_KEY  = _pd_d[1] or ""
local BOUND_UID    = _pd_d[2] or ""
local API_BASE_URL = (_pd_d[3] or ""):gsub("/$", "")
local SESSION_TOK  = _pd_d[4] or ""
rawset(_G, '__PD_DATA', nil)

if LICENSE_KEY == "" or API_BASE_URL == "" then return end

do
    local _cu = tostring(game:GetService("Players").LocalPlayer.UserId)
    if BOUND_UID ~= "" then
        local _sa, _sb = 0, 0
        for _i = 1, #_cu       do _sa = _sa + string.byte(_cu,       _i) * (_i % 7 + 1) end
        for _i = 1, #BOUND_UID do _sb = _sb + string.byte(BOUND_UID, _i) * (_i % 7 + 1) end
        if _sa ~= _sb or _cu ~= BOUND_UID then return end
    end
end

do
    local _hs  = game:GetService("HttpService")
    local _req = (syn and syn.request) or http_request or (fluxus and fluxus.request) or request
    local _uid = tostring(game:GetService("Players").LocalPlayer.UserId)
    local _ok, _r = pcall(function()
        return _req({
            Url    = API_BASE_URL .. "/v2/activate",
            Method = "POST",
            Headers = {["Content-Type"] = "application/json"},
            Body   = _hs:JSONEncode({
                key            = LICENSE_KEY,
                roblox_user_id = _uid,
                roblox_name    = game:GetService("Players").LocalPlayer.Name,
            }),
        })
    end)
    if not _ok or not _r or _r.StatusCode ~= 200 then return end
end
-- =====================================================================
"""

OLD_RECONNECT = '''\
local _reconnectScript = [[
local _req = (syn and syn.request) or http and http.request or http_request or (fluxus and fluxus.request) or request
local _ok, _res = pcall(_req, {Url = "]] .. SCRIPT_URL .. [["})
if _ok and _res and _res.Body and _res.Body ~= "" then
    loadstring(_res.Body)()
else
    pcall(function() loadstring(game:HttpGet("]] .. SCRIPT_URL .. [[", true))() end)
end
]]'''

NEW_RECONNECT = '''\
local _reconnectScript = [[
local _r=(syn and syn.request) or http_request or (fluxus and fluxus.request) or request
local _u=tostring(game:GetService("Players").LocalPlayer.UserId)
local _o,_p=pcall(_r,{Url="]] .. API_BASE_URL .. [[/v2/getscript?key=]] .. LICENSE_KEY .. [[&uid=".._u,Method="GET"})
if _o and _p and _p.StatusCode==200 and _p.Body and _p.Body~="" then
    local _f=loadstring(_p.Body)
    if _f then pcall(_f) end
end]]'''

OLD_SCRIPT_URL_LINE = 'local SCRIPT_URL = "https://raw.githubusercontent.com/ivankodaria5-ai/plsdonatebot/main/botplsdonate.lua"'

# строка в теле pd_update, после которой вставим session_token
PD_UPDATE_ANCHOR = '                    interactions    = logSnapshot,'
PD_UPDATE_INSERT = '                    session_token   = SESSION_TOK,'

with open(SRC, encoding="utf-8") as f:
    code = f.read()

# 1. Вставить PROTECT_BLOCK после "local PLACE_ID = 8737602449"
ANCHOR = "local PLACE_ID = 8737602449"
assert ANCHOR in code, f"Anchor not found: {ANCHOR!r}"
code = code.replace(ANCHOR, ANCHOR + "\n" + PROTECT_BLOCK, 1)

# 2. Удалить строку SCRIPT_URL (она больше не нужна — reconnect идёт через API)
assert OLD_SCRIPT_URL_LINE in code, "SCRIPT_URL line not found"
code = code.replace(OLD_SCRIPT_URL_LINE + "\n", "", 1)

# 3. Заменить _reconnectScript
assert OLD_RECONNECT in code, "OLD_RECONNECT block not found"
code = code.replace(OLD_RECONNECT, NEW_RECONNECT, 1)

# 4. Добавить session_token в pd_update body
assert PD_UPDATE_ANCHOR in code, "pd_update anchor not found"
code = code.replace(
    PD_UPDATE_ANCHOR,
    PD_UPDATE_INSERT + "\n" + PD_UPDATE_ANCHOR,
    1
)

os.makedirs(os.path.dirname(DEST), exist_ok=True)
with open(DEST, "w", encoding="utf-8", newline="\n") as f:
    f.write(code)

print(f"[OK] {DEST} — {len(code)} chars, {code.count(chr(10))+1} lines")
print("     Проверь что LICENSE_KEY, API_BASE_URL, SESSION_TOK используются правильно.")
