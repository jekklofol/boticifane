local API = "https://api.212.113.99.78.nip.io"

local Players          = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local TweenService     = game:GetService("TweenService")
local player           = Players.LocalPlayer

-- ── Colors ──────────────────────────────────────────────────────────────
local C = {
    bg       = Color3.fromRGB(14, 14, 22),
    surface  = Color3.fromRGB(20, 20, 32),
    card     = Color3.fromRGB(26, 26, 40),
    input    = Color3.fromRGB(18, 18, 30),
    border   = Color3.fromRGB(50, 45, 90),
    accent   = Color3.fromRGB(108, 92, 231),
    accent2  = Color3.fromRGB(130, 115, 255),
    text     = Color3.fromRGB(230, 225, 250),
    muted    = Color3.fromRGB(100, 95, 145),
    success  = Color3.fromRGB(72, 210, 130),
    warn     = Color3.fromRGB(230, 180, 60),
    error    = Color3.fromRGB(220, 75, 75),
    white    = Color3.fromRGB(255, 255, 255),
}

local function tween(obj, dur, props, style, dir)
    TweenService:Create(obj, TweenInfo.new(dur, style or Enum.EasingStyle.Quint, dir or Enum.EasingDirection.Out), props):Play()
end

-- ── GUI root ────────────────────────────────────────────────────────────
local root = Instance.new("ScreenGui")
root.Name           = "RoBeggr_Loader"
root.ResetOnSpawn   = false
root.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
root.DisplayOrder   = 999
pcall(function() root.Parent = game:GetService("CoreGui") end)
if not root.Parent then root.Parent = player.PlayerGui end

-- ── Overlay (fade in) ───────────────────────────────────────────────────
local overlay = Instance.new("Frame", root)
overlay.Size                = UDim2.new(1, 0, 1, 0)
overlay.BackgroundColor3    = Color3.fromRGB(0, 0, 0)
overlay.BackgroundTransparency = 1
overlay.BorderSizePixel     = 0
overlay.ZIndex              = 0

tween(overlay, 0.4, {BackgroundTransparency = 0.5})

-- ── Main frame ──────────────────────────────────────────────────────────
local W, H = 380, 340
local frame = Instance.new("Frame", root)
frame.AnchorPoint       = Vector2.new(0.5, 0.5)
frame.Size              = UDim2.new(0, W, 0, 0)
frame.Position          = UDim2.new(0.5, 0, 0.5, 0)
frame.BackgroundColor3  = C.bg
frame.BorderSizePixel   = 0
frame.ClipsDescendants  = true
frame.ZIndex            = 1
Instance.new("UICorner", frame).CornerRadius = UDim.new(0, 16)

-- outer glow stroke
local stroke = Instance.new("UIStroke", frame)
stroke.Color       = C.accent
stroke.Thickness   = 1.2
stroke.Transparency = 0.4

-- open animation
tween(frame, 0.5, {Size = UDim2.new(0, W, 0, H)}, Enum.EasingStyle.Back)

-- ── Accent line at top ──────────────────────────────────────────────────
local topLine = Instance.new("Frame", frame)
topLine.Size             = UDim2.new(1, 0, 0, 2)
topLine.Position         = UDim2.new(0, 0, 0, 0)
topLine.BackgroundColor3 = C.accent
topLine.BorderSizePixel  = 0
topLine.ZIndex           = 5

local topGrad = Instance.new("UIGradient", topLine)
topGrad.Color = ColorSequence.new{
    ColorSequenceKeypoint.new(0, C.accent),
    ColorSequenceKeypoint.new(0.5, C.accent2),
    ColorSequenceKeypoint.new(1, C.accent),
}
-- shimmer animation on top line
task.spawn(function()
    while topLine.Parent do
        tween(topGrad, 2, {Offset = Vector2.new(1, 0)}, Enum.EasingStyle.Linear)
        task.wait(2)
        topGrad.Offset = Vector2.new(-1, 0)
    end
end)

-- ── Header ──────────────────────────────────────────────────────────────
local header = Instance.new("Frame", frame)
header.Size             = UDim2.new(1, 0, 0, 70)
header.Position         = UDim2.new(0, 0, 0, 2)
header.BackgroundTransparency = 1
header.BorderSizePixel  = 0

local icon = Instance.new("TextLabel", header)
icon.AnchorPoint        = Vector2.new(0, 0.5)
icon.Size               = UDim2.new(0, 44, 0, 44)
icon.Position           = UDim2.new(0, 20, 0.5, 0)
icon.BackgroundColor3   = C.card
icon.BorderSizePixel    = 0
icon.Text               = "💎"
icon.TextSize           = 22
icon.Font               = Enum.Font.Gotham
Instance.new("UICorner", icon).CornerRadius = UDim.new(0, 12)
local iconStroke = Instance.new("UIStroke", icon)
iconStroke.Color       = C.border
iconStroke.Thickness   = 1
iconStroke.Transparency = 0.3

local title = Instance.new("TextLabel", header)
title.Size                 = UDim2.new(1, -80, 0, 22)
title.Position             = UDim2.new(0, 74, 0, 16)
title.BackgroundTransparency = 1
title.Text                 = "ROBEGGR"
title.TextColor3           = C.text
title.TextSize             = 17
title.Font                 = Enum.Font.GothamBold
title.TextXAlignment       = Enum.TextXAlignment.Left

local sub = Instance.new("TextLabel", header)
sub.Size                   = UDim2.new(1, -80, 0, 16)
sub.Position               = UDim2.new(0, 74, 0, 40)
sub.BackgroundTransparency = 1
sub.Text                   = "Please Donate Auto-Farm"
sub.TextColor3             = C.muted
sub.TextSize               = 11
sub.Font                   = Enum.Font.Gotham
sub.TextXAlignment         = Enum.TextXAlignment.Left

-- version badge
local ver = Instance.new("TextLabel", header)
ver.AnchorPoint         = Vector2.new(1, 0)
ver.Size                = UDim2.new(0, 42, 0, 20)
ver.Position            = UDim2.new(1, -16, 0, 16)
ver.BackgroundColor3    = C.card
ver.BorderSizePixel     = 0
ver.Text                = "v2.3"
ver.TextColor3          = C.accent2
ver.TextSize            = 10
ver.Font                = Enum.Font.GothamBold
Instance.new("UICorner", ver).CornerRadius = UDim.new(0, 6)

-- ── Divider ─────────────────────────────────────────────────────────────
local div1 = Instance.new("Frame", frame)
div1.Size             = UDim2.new(1, -40, 0, 1)
div1.Position         = UDim2.new(0, 20, 0, 76)
div1.BackgroundColor3 = C.border
div1.BackgroundTransparency = 0.6
div1.BorderSizePixel  = 0

-- ── Key input ───────────────────────────────────────────────────────────
local inputLabel = Instance.new("TextLabel", frame)
inputLabel.Size                 = UDim2.new(1, -40, 0, 16)
inputLabel.Position             = UDim2.new(0, 22, 0, 86)
inputLabel.BackgroundTransparency = 1
inputLabel.Text                 = "ЛИЦЕНЗИОННЫЙ КЛЮЧ"
inputLabel.TextColor3           = C.muted
inputLabel.TextSize             = 9
inputLabel.Font                 = Enum.Font.GothamBold
inputLabel.TextXAlignment       = Enum.TextXAlignment.Left

local inputBg = Instance.new("Frame", frame)
inputBg.Size             = UDim2.new(1, -40, 0, 44)
inputBg.Position         = UDim2.new(0, 20, 0, 105)
inputBg.BackgroundColor3 = C.input
inputBg.BorderSizePixel  = 0
Instance.new("UICorner", inputBg).CornerRadius = UDim.new(0, 10)
local inputStroke = Instance.new("UIStroke", inputBg)
inputStroke.Color       = C.border
inputStroke.Thickness   = 1
inputStroke.Transparency = 0.3

local keyBox = Instance.new("TextBox", inputBg)
keyBox.Size                = UDim2.new(1, -20, 1, 0)
keyBox.Position            = UDim2.new(0, 12, 0, 0)
keyBox.BackgroundTransparency = 1
keyBox.PlaceholderText     = "Вставь ключ из Telegram бота..."
keyBox.PlaceholderColor3   = Color3.fromRGB(60, 55, 100)
keyBox.Text                = ""
keyBox.TextColor3          = C.text
keyBox.TextSize            = 13
keyBox.Font                = Enum.Font.Code
keyBox.ClearTextOnFocus    = false
keyBox.TextXAlignment      = Enum.TextXAlignment.Left

keyBox.Focused:Connect(function()
    tween(inputStroke, 0.25, {Color = C.accent, Transparency = 0})
end)
keyBox.FocusLost:Connect(function()
    tween(inputStroke, 0.25, {Color = C.border, Transparency = 0.3})
end)

-- ── Run button ──────────────────────────────────────────────────────────
local btn = Instance.new("TextButton", frame)
btn.Size             = UDim2.new(1, -40, 0, 44)
btn.Position         = UDim2.new(0, 20, 0, 162)
btn.BackgroundColor3 = C.accent
btn.BorderSizePixel  = 0
btn.Text             = "⚡  ЗАПУСТИТЬ"
btn.TextColor3       = C.white
btn.TextSize         = 14
btn.Font             = Enum.Font.GothamBold
btn.AutoButtonColor  = false
Instance.new("UICorner", btn).CornerRadius = UDim.new(0, 10)

-- button gradient
local btnGrad = Instance.new("UIGradient", btn)
btnGrad.Color = ColorSequence.new{
    ColorSequenceKeypoint.new(0, Color3.fromRGB(255, 255, 255)),
    ColorSequenceKeypoint.new(1, Color3.fromRGB(200, 200, 220)),
}
btnGrad.Rotation = 90

btn.MouseEnter:Connect(function()
    tween(btn, 0.2, {BackgroundColor3 = C.accent2})
end)
btn.MouseLeave:Connect(function()
    tween(btn, 0.2, {BackgroundColor3 = C.accent})
end)

-- ── Status ──────────────────────────────────────────────────────────────
local statusBg = Instance.new("Frame", frame)
statusBg.Size             = UDim2.new(1, -40, 0, 32)
statusBg.Position         = UDim2.new(0, 20, 0, 216)
statusBg.BackgroundColor3 = C.card
statusBg.BorderSizePixel  = 0
statusBg.BackgroundTransparency = 0.5
Instance.new("UICorner", statusBg).CornerRadius = UDim.new(0, 8)

local statusDot = Instance.new("Frame", statusBg)
statusDot.AnchorPoint       = Vector2.new(0, 0.5)
statusDot.Size              = UDim2.new(0, 6, 0, 6)
statusDot.Position          = UDim2.new(0, 12, 0.5, 0)
statusDot.BackgroundColor3  = C.muted
statusDot.BorderSizePixel   = 0
Instance.new("UICorner", statusDot).CornerRadius = UDim.new(1, 0)

local status = Instance.new("TextLabel", statusBg)
status.Size                 = UDim2.new(1, -30, 1, 0)
status.Position             = UDim2.new(0, 24, 0, 0)
status.BackgroundTransparency = 1
status.Text                 = "Введи ключ и нажми Запустить"
status.TextColor3           = C.muted
status.TextSize             = 11
status.Font                 = Enum.Font.Gotham
status.TextXAlignment       = Enum.TextXAlignment.Left

-- ── Divider 2 ───────────────────────────────────────────────────────────
local div2 = Instance.new("Frame", frame)
div2.Size             = UDim2.new(1, -40, 0, 1)
div2.Position         = UDim2.new(0, 20, 0, 260)
div2.BackgroundColor3 = C.border
div2.BackgroundTransparency = 0.6
div2.BorderSizePixel  = 0

-- ── Social links ────────────────────────────────────────────────────────
local socials = Instance.new("Frame", frame)
socials.Size                = UDim2.new(1, -40, 0, 50)
socials.Position            = UDim2.new(0, 20, 0, 270)
socials.BackgroundTransparency = 1
socials.BorderSizePixel     = 0

local function socialBtn(parent, text, icon_text, xPos, link)
    local bg = Instance.new("TextButton", parent)
    bg.AnchorPoint       = Vector2.new(0, 0.5)
    bg.Size              = UDim2.new(0.48, 0, 0, 38)
    bg.Position           = UDim2.new(xPos, 0, 0.5, 0)
    bg.BackgroundColor3  = C.card
    bg.BorderSizePixel   = 0
    bg.Text              = ""
    bg.AutoButtonColor   = false
    Instance.new("UICorner", bg).CornerRadius = UDim.new(0, 8)
    local s = Instance.new("UIStroke", bg)
    s.Color       = C.border
    s.Thickness   = 1
    s.Transparency = 0.5

    local ic = Instance.new("TextLabel", bg)
    ic.Size                 = UDim2.new(0, 24, 1, 0)
    ic.Position             = UDim2.new(0, 8, 0, 0)
    ic.BackgroundTransparency = 1
    ic.Text                 = icon_text
    ic.TextSize             = 14
    ic.Font                 = Enum.Font.Gotham

    local lbl = Instance.new("TextLabel", bg)
    lbl.Size                = UDim2.new(1, -36, 1, 0)
    lbl.Position            = UDim2.new(0, 32, 0, 0)
    lbl.BackgroundTransparency = 1
    lbl.Text                = text
    lbl.TextColor3          = C.muted
    lbl.TextSize            = 11
    lbl.Font                = Enum.Font.GothamMedium
    lbl.TextXAlignment      = Enum.TextXAlignment.Left

    bg.MouseEnter:Connect(function()
        tween(s, 0.2, {Color = C.accent, Transparency = 0})
        tween(lbl, 0.2, {TextColor3 = C.text})
    end)
    bg.MouseLeave:Connect(function()
        tween(s, 0.2, {Color = C.border, Transparency = 0.5})
        tween(lbl, 0.2, {TextColor3 = C.muted})
    end)
    bg.MouseButton1Click:Connect(function()
        pcall(function()
            if setclipboard then setclipboard(link)
            elseif toclipboard then toclipboard(link) end
        end)
        local old = lbl.Text
        lbl.Text = "Скопировано!"
        lbl.TextColor3 = C.success
        task.delay(1.5, function()
            lbl.Text = old
            lbl.TextColor3 = C.muted
        end)
    end)
    return bg
end

socialBtn(socials, "Telegram",  "✈️", 0,    "https://t.me/coldyz")
socialBtn(socials, "YouTube",   "▶️", 0.52, "https://www.youtube.com/@coldyz")

-- ── Footer ──────────────────────────────────────────────────────────────
local footer = Instance.new("TextLabel", frame)
footer.Size                 = UDim2.new(1, 0, 0, 16)
footer.Position             = UDim2.new(0, 0, 1, -18)
footer.BackgroundTransparency = 1
footer.Text                 = "robeggr © 2025"
footer.TextColor3           = Color3.fromRGB(40, 38, 60)
footer.TextSize             = 9
footer.Font                 = Enum.Font.Gotham

-- ── Drag ────────────────────────────────────────────────────────────────
local dragging, dragStart, startPos
header.InputBegan:Connect(function(inp)
    if inp.UserInputType == Enum.UserInputType.MouseButton1 then
        dragging  = true
        dragStart = inp.Position
        startPos  = frame.Position
    end
end)
UserInputService.InputChanged:Connect(function(inp)
    if dragging and inp.UserInputType == Enum.UserInputType.MouseMovement then
        local d = inp.Position - dragStart
        frame.Position = UDim2.new(
            startPos.X.Scale, startPos.X.Offset + d.X,
            startPos.Y.Scale, startPos.Y.Offset + d.Y)
    end
end)
UserInputService.InputEnded:Connect(function(inp)
    if inp.UserInputType == Enum.UserInputType.MouseButton1 then
        dragging = false
    end
end)

-- ── Helpers ─────────────────────────────────────────────────────────────
local httprequest = (syn and syn.request)
    or (http and http.request)
    or http_request
    or (fluxus and fluxus.request)
    or request

local function setStatus(text, color)
    status.Text       = text
    status.TextColor3 = color or C.muted
    statusDot.BackgroundColor3 = color or C.muted
end

local function setBusy(on)
    btn.Text             = on and "⏳  ЗАГРУЗКА..." or "⚡  ЗАПУСТИТЬ"
    btn.BackgroundColor3 = on and Color3.fromRGB(55, 50, 110) or C.accent
end

-- ── Launch ──────────────────────────────────────────────────────────────
btn.MouseButton1Click:Connect(function()
    local key = keyBox.Text:match("^%s*(.-)%s*$")
    if key == "" then
        setStatus("Введи лицензионный ключ", C.warn)
        return
    end

    local uid = tostring(player.UserId)
    setBusy(true)
    setStatus("Проверяем ключ...", C.accent2)

    local ok, resp = pcall(function()
        return httprequest({
            Url    = API .. "/v2/getscript?key=" .. key .. "&uid=" .. uid,
            Method = "GET",
        })
    end)

    if not ok then
        setBusy(false)
        setStatus("Нет соединения. Попробуй VPN", C.error)
        return
    end

    if resp.StatusCode == 502 or resp.StatusCode == 503 or resp.StatusCode == 504 then
        setBusy(false)
        setStatus("Сервер временно недоступен", C.warn)
        return
    end

    if resp.StatusCode == 403 then
        setBusy(false)
        local body = tostring(resp.Body or "")
        if body:find("Лимит аккаунтов") then
            setStatus("Лимит аккаунтов исчерпан", C.warn)
        elseif body:find("заблокирован") then
            setStatus("Аккаунт заблокирован для этого ключа", C.error)
        elseif body:find("trial_expired") then
            setStatus("Пробный период истёк", C.warn)
        elseif body == "" or body:sub(1, 1) == "<" then
            setStatus("Cloudflare заблокирован. Включи VPN", C.error)
        else
            setStatus(body, C.error)
        end
        return
    end

    if resp.StatusCode ~= 200 or not resp.Body or resp.Body == "" then
        setBusy(false)
        setStatus("Ошибка сервера: " .. tostring(resp.StatusCode), C.error)
        return
    end

    local fn, compileErr = loadstring(resp.Body)
    resp = nil
    if not fn then
        setBusy(false)
        setStatus("Ошибка загрузки скрипта", C.error)
        return
    end

    local queueFunc = queueonteleport or queue_on_teleport
        or (syn and syn.queue_on_teleport) or function() end

    pcall(function()
        queueFunc([[
local _r=(syn and syn.request) or http_request or request
local _u=tostring(game:GetService("Players").LocalPlayer.UserId)
local function _cl(fn) local o,v=pcall(fn) if o and v and tostring(v)~="" then return tostring(v) end return "" end
local function _sh(s) local h=5381 for i=1,#s do h=((h*33)+string.byte(s,i))%4294967296 end return string.format("%08x",h) end
local _p1=_cl(function() return gethwid and gethwid() or getHWID and getHWID() or (syn and syn.hwid and syn.hwid()) or "" end)
local _p2=_cl(function() return game:GetService("RbxAnalyticsService"):GetClientId() end)
local _p3=_cl(function() return game:GetService("RbxAnalyticsService"):GetDeviceId() end)
local _p4=_cl(function() if identifyexecutor then local n,v=identifyexecutor() return (n or "").."|"..(v or "") end return "" end)
local _c="" for _,v in ipairs({_p1,_p2,_p3,_p4}) do if v~="" then _c=_c.._sh(v)..":" end end
local _fs="fp_v2:".._c..":pdbot"
local _h=_sh(_fs).._sh(string.reverse(_fs))
local _o,_pp=pcall(_r,{Url="]] .. API .. [[/v2/getscript?key=]] .. key .. [[&uid=".._u.."&hwid=".._h,Method="GET"})
if _o and _pp and _pp.StatusCode==200 and _pp.Body and _pp.Body~="" then
    local _f=loadstring(_pp.Body)
    if _f then pcall(_f) end
end
]])
    end)

    setStatus("Запускаем...", C.success)
    statusDot.BackgroundColor3 = C.success

    -- Close animation
    task.wait(0.3)
    tween(frame, 0.35, {Size = UDim2.new(0, W, 0, 0)}, Enum.EasingStyle.Back, Enum.EasingDirection.In)
    tween(overlay, 0.3, {BackgroundTransparency = 1})
    task.wait(0.4)
    root:Destroy()
    pcall(fn)
end)
