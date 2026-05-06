-- ==================== CONSTANTS & CONFIGURATION ====================
local PLACE_ID = 8737602449                            -- Please Donate place ID
local MIN_PLAYERS = 4                                  -- Minimum players in server (overridable from dashboard)
local MAX_PLAYERS_ALLOWED = 24                         -- Maximum players in server (overridable from dashboard)
local SERVER_COOLDOWN_MINS = 150                       -- Minutes to avoid rejoining a visited server (overridable)
local TELEPORT_RETRY_DELAY = 8                         -- Delay between teleport attempts
local TELEPORT_COOLDOWN = 30                           -- Cooldown between failed servers
local SCRIPT_URL = "https://raw.githubusercontent.com/jekklofol/boticifane/main/botplsdonate.lua"
local DASH_URL   = "https://dash.212.113.99.78.nip.io"

local BOOTH_CHECK_POSITION = Vector3.new(165, 0, 311)  -- Center point to search for booths
local MAX_BOOTH_DISTANCE = 92                          -- Max studs from check position
local TYPO_CHANCE = 0.45                               -- 15% chance to send message with typo

local MESSAGES = {
    "hey! donate pls? :)",
    "hi! can u donate?",
    "hello! donation? :D",
    "hey donate maybe?",
    "hi! pls donate im trying to save up",
    "heyy any donations?",
    "hello donate pls",
    "hi! help me out? any robux appreciated",
    "hey! donate? :)",
    "hii pls donate ty",
    "hey can u donate im close to my goal",
    "hello! robux pls?",
    "hi donate pls :D",
    "heyy donation? would mean a lot",
    "hey! pls help",
    "hi! any robux? trying to get something cool",
    "hello donate ty",
    "hey! can u help? even small amount helps",
    "hi pls donate :)",
    "heyy robux pls",
    "hey donate? ty appreciate it",
    "hi! help pls",
    "hello donation pls working towards smth",
    "hey! donate ty :D",
    "hi can u donate?",
    "heyy pls help out any amount works",
    "hey donate pls :)",
    "hi! any donations? been grinding all day",
    "hello robux pls",
    "hey! pls donate",
    -- more realistic / how players actually type
    "pls donate me",
    "any robux? pls",
    "donate plz ty",
    "trying to save for something donate?",
    "need robux fr can u help",
    "spare some r$?",
    "could use a donation ngl",
    "any donation helps fr",
    "donate if u can :)",
    "broke rn donate pls lol",
    "pls donate even 1 helps",
    "hey donate ty",
    "anyone donate?",
    "donations appreciated",
    "yo donate pls",
    "hi im tryna save up donate?",
    "donate pls trying to get a gamepass",
    "hey could u spare any?",
    "any r$ helps pls",
    "pls donate for my goal",
    "donate? would mean sm",
    "hi need some robux pls",
    "hey any amount works",
    "donate pls im poor lol",
    "trying to reach my goal donate?",
    "yo anyone wanna donate",
    "pls donate me ty",
    "could u donate? tryna save",
    "donate pls :(",
    "hey spare some robux?",
    "any donations? pls",
}

-- Typo variations (3 per message, realistic keyboard mistakes)
local MESSAGE_TYPOS = {
    {"hry! donate pls? :)", "hey! dinate pls? :)", "hey! donate pld? :)"},
    {"hi! csn u donate?", "hi! can u dknate?", "hi! can u donatw?"},
    {"hrllo! donation? :D", "hello! donatiob? :D", "hello! donatipn? :D"},
    {"heu donate maybe?", "hey dontae maybe?", "hey donate maybr?"},
    {"hi! pks donate im trying to save up", "hi! pls donsre im trying to save up", "hi! pls donate im tryinf to save up"},
    {"heyy anu donations?", "heyy any donatiins?", "heyy any donatuons?"},
    {"hrllo donate pls", "hello dinate pls", "hello donate pld"},
    {"hi! hwlp me out? any robux appreciated", "hi! help me oit? any robux appreciated", "hi! help me out? any robix appreciated"},
    {"hry! donate? :)", "hey! dinate? :)", "hey! donatr? :)"},
    {"hii pks donate ty", "hii pls dknate ty", "hii pls donate ry"},
    {"hry can u donate im close to my goal", "hey csn u donate im close to my goal", "hey can u donsre im close to my goal"},
    {"hrllo! robux pls?", "hello! robix pls?", "hello! robux pld?"},
    {"hi dinate pls :D", "hi donate pld :D", "hi donate pla :D"},
    {"heyy donatiom? would mean a lot", "heyy donation? woulf mean a lot", "heyy donatiin? would mean a lot"},
    {"hry! pls help", "hey! pld help", "hey! pls hwlp"},
    {"hi! any robix? trying to get something cool", "hi! any robux? tryinf to get something cool", "hi! any robux? trying to grt something cool"},
    {"hrllo donate ty", "hello dknate ty", "hello donate ry"},
    {"hry! can u help? even small amount helps", "hey! csn u help? even small amount helps", "hey! can u hwlp? even small amount helps"},
    {"hi pld donate :)", "hi pls dknate :)", "hi pls donate :0"},
    {"heyy robix pls", "hryy robux pls", "heyy robux pld"},
    {"hry donate? ty appreciate it", "hey dknate? ty appreciate it", "hey donate? ty apprexiate it"},
    {"hi! hwlp pls", "hi! help pld", "hi! gelp pls"},
    {"hrllo donation pls working towards smth", "hello donatiom pls working towards smth", "hello donation pls workibg towards smth"},
    {"hry! donate ty :D", "hey! dknate ty :D", "hey! donate ry :D"},
    {"hi csn u donate?", "hi can u dinate?", "hi can u donatw?"},
    {"heyy pld help out any amount works", "hryy pls help out any amount works", "heyy pls hwlp out any amount works"},
    {"hry donate pls :)", "hey dknate pls :)", "hey donate pld :)"},
    {"hi! any donatioms? been grinding all day", "hi! any donations? bren grinding all day", "hi! any donations? been grindibg all day"},
    {"hrllo robux pls", "hello robix pls", "hello robux pld"},
    {"hry! pls donate", "hey! pld donate", "hey! pls dknate"}
}
-- Extra typo rows for MESSAGES 32+ (same count as extra MESSAGES)
local MESSAGE_TYPOS_EXTRA = {
    {"pld donate me", "pls dinate me", "pls donate ne"},
    {"any robix? pls", "any robux? pld", "any robux? pls"},
    {"dinate plz ty", "donate plz ry", "donate plx ty"},
    {"tryinf to save for something donate?", "trying to save for somethibg donate?", "trying to save for something dinate?"},
    {"need robux fr can u hwlp", "need robix fr can u help", "need robux fr csn u help"},
    {"spare some r$?", "spare sme r$?", "spare some r$?"},
    {"could use a donatiom ngl", "could use a donation ngl", "could use a donaton ngl"},
    {"any donation helps fr", "any donatiom helps fr", "any donation hwlps fr"},
    {"donate if u can :)", "dinate if u can :)", "donate if u csn :)"},
    {"broke rn donate pls lol", "broke rn dinate pls lol", "broke rn donate pld lol"},
    {"pls donate even 1 helps", "pld donate even 1 helps", "pls dinate even 1 helps"},
    {"hey dinate ty", "hey donate ry", "hry donate ty"},
    {"anyone donate?", "anyone dinate?", "anyone donate?"},
    {"donations appreciated", "donatioms appreciated", "donations apprexiated"},
    {"yo dinate pls", "yo donate pld", "yo donate pls"},
    {"hi im tryna save up donate?", "hi im tryna save up dinate?", "hi im tryna sav eup donate?"},
    {"donate pls trying to get a gamepass", "dinate pls trying to get a gamepass", "donate pld trying to get a gamepass"},
    {"hey could u spare any?", "hry could u spare any?", "hey could u spare any?"},
    {"any r$ helps pls", "any r$ hwlps pls", "any r$ helps pld"},
    {"pls donate for my goal", "pld donate for my goal", "pls dinate for my goal"},
    {"donate? would mean sm", "dinate? would mean sm", "donate? woulf mean sm"},
    {"hi need some robux pls", "hi need some robix pls", "hi need sme robux pls"},
    {"hey any amount works", "hry any amount works", "hey any amouny works"},
    {"donate pls im poor lol", "dinate pls im poor lol", "donate pld im poor lol"},
    {"trying to reach my goal donate?", "tryinf to reach my goal donate?", "trying to reach my goal dinate?"},
    {"yo anyone wanna donate", "yo anyone wann donate", "yo anyone wanna dinate"},
    {"pls donate me ty", "pld donate me ty", "pls dinate me ty"},
    {"could u donate? tryna save", "could u dinate? tryna save", "could u donate? tryna sav e"},
    {"donate pls :(", "dinate pls :(", "donate pld :("},
    {"hey spare some robux?", "hry spare some robux?", "hey spare some robix?"},
    {"any donations? pls", "any donatioms? pls", "any donations? pld"},
}

local WAIT_FOR_ANSWER_TIME = 7        -- seconds to wait for reply
local MAX_WAIT_DISTANCE = 10              -- max distance before following player while waiting
-- YES: full words or substrings for longer phrases
local YES_LIST = {
    "yes", "yeah", "yep", "yea", "ya", "yh", "sure", "ok", "okay", "k",
    "bet", "aight", "alright", "fine", "of course", "why not", "ight", "ig",
    "follow", "come", "lead", "lets go", "go", "show me", "where", "lets",
    "ill donate", "im donating", "sure thing", "no problem",
}
-- NO: full words or substrings
local NO_LIST = {
    "no", "nope", "nah", "naur", "n", "pass", "busy", "not now", "not rn",
    "no ty", "no thx", "no thanks", "no thank", "nty", "nah ty",
    "leave", "stop", "go away", "gtfo", "dont", "don't", "never",
    "no way", "im good", "i'm good", "leave me",
}

local MSG_FOLLOW_ME = "follow me!"
local MSG_HERE_IS_HOUSE = "here is my booth!"
local MSG_OK_FINE_POOL = {"ok fine :(", "aw ok :(", "dang ok lol", "oh ok :(", "ok :("}

local SECOND_ATTEMPT_CHANCE = 0.30
local FRUSTRATION_THRESHOLD = 5

local NO_RESPONSE_MSGS = {
    "okay no response...",
    "alright moving on lol",
    "probably afk okay",
    "no answer guess moving on",
    "silence... alright then",
    "not responding, next!",
    "guess they busy okay",
    "okay bye then lol",
    "no reply ok",
    "afk probably",
    "alright next person",
    "ok moving on",
}

-- Guilt-trip second message (sent after refusal, no wait for response)
local MSGS_SECOND = {
    "aw ok no worries i guess",
    "oh ok ill keep trying",
    "damn okay maybe next time",
    "np i understand just tryna get some",
    "ok fine sorry for asking lol",
    "alright :( maybe someone else",
    "ok np",
    "aw alright",
    "okay no worries",
    "damn ok",
    "alright maybe next time",
    "np gl anyway",
}

-- Contextual message pools by target's Raised amount
local MSGS_EMPTY = {
    "hey can u donate? tryna save up",
    "hi donate pls i have nothing yet",
    "anyone donate? literally anything helps",
    "plss donate im so close to my goal",
    "hey could u donate? saving up for something",
    "umm hi could u spare some robux",
    "donate pls im just starting out",
    "hey! help me out? even a little is fine",
    "pls donate 0 raised rn lol",
    "any robux? i have nothing",
    "donate pls tryna get my first r$",
    "hey im new here donate?",
    "could use any donation rn",
    "anyone spare some? just started",
    "donate pls goal is like 50 r$",
    "hi literally any amount",
    "pls donate me im broke",
    "trying to save from 0 donate?",
}
local MSGS_LOW = {
    "hey we both grinding, support each other?",
    "donate? even like 5 would help fr",
    "hi small donation? any amount is fine",
    "hey could u help me out a bit",
    "we both starting out, donate pls?",
    "bro donate pls i need robux",
    "hey spare some? tryna catch up",
    "yo we both low on r$ donate?",
    "even 10 r$ would help pls",
    "donate? tryna get where u at",
    "hey small donation? pls",
    "we in the same boat donate pls",
    "could u spare a bit? tryna save",
    "donate pls we both grinding",
}
local MSGS_MID = {
    "yo ur doing well, spare some for me?",
    "hey nice booth! could u donate?",
    "hi donate pls u seem generous lol",
    "hey looks like ur doing good, help me out?",
    "u got donations u know how it feels, donate?",
    "damn nice raised, share some? lol",
    "ur booth doing good donate?",
    "hey u got some to spare",
    "nice numbers could u donate?",
    "u know the grind donate pls?",
    "hey share the wealth lol",
    "ur doing good help me out?",
}
local MSGS_RICH = {
    "yo ur rich donate pls",
    "hey ur clearly generous, help me out?",
    "bro u got so much help me lol",
    "ok ur booth doing great mine isnt, donate?",
    "hey big numbers on ur booth share some?",
    "ur doing amazing, spare a lil for me?",
    "damn ur loaded donate pls",
    "yo u got heaps spare some?",
    "ur raised is insane donate?",
    "hey rich person donate lol",
    "u dont need it all donate?",
    "spare some of that r$? pls",
}
local MSGS_LEAVING = {
    "leaving this server soon if anyone wants to donate",
    "bout to hop, anyone wanna donate quick",
    "last chance before i leave lol",
    "changing server soon quick donate?",
    "gonna leave in a sec donate?",
    "hopping soon anyone donate quick",
    "last call for donations lol",
    "bout to switch servers donate?",
    "leaving in a min quick donate pls",
    "server hop soon donate if u can",
}
local COMPLIMENTS = {
    "ur fit goes hard ngl",
    "ok ur avatar is actually so clean",
    "love the fit fr",
    "ur style lowkey fire",
    "ur look is actually cool tho",
    "ur avatar is so cute omg",
    "bro ur outfit slaps",
    "ur fit is bussin fr",
    "ngl i fw ur style",
    "ur drip different fr",
    "ok i fw the fit",
    "ur avatar aesthetic is clean",
    "no way ur fit goes that hard",
    "ok ur look is actually clean",
    "ur avatar goes crazy",
    "fire fit ngl",
    "ur style is so good",
    "love ur avatar fr",
    "ur outfit is fire",
    "that fit hits different",
}

-- Donation asks that flow AFTER a compliment — no re-greeting, natural transition
local MSGS_POST_COMPLIMENT = {
    "anyways could u donate? lol",
    "btw wanna donate? tryna save up",
    "ngl could u spare some robux?",
    "also help me out? any amount fr",
    "on a diff note donate? tryna grind",
    "speaking of which donate? lol",
    "btw could u help me out? even a lil",
    "also im so broke rn donate pls lol",
    "anyways u got any robux to spare?",
    "ik its random but pls donate lol",
    "btw donate? would actually help me so much",
    "random but can u donate? would mean a lot",
    "anyway do u have spare robux? lol",
    "also tryna get some robux donate?",
    "ngl could use some help donate pls",
    "anyways donate? tryna save",
    "btw spare some r$? pls",
    "also could u donate? would help",
    "random ask but donate pls",
    "anyway tryna get donations lol",
}
local MSGS_GOODBYE = {
    "no worries gl with ur booth",
    "all good have fun",
    "np good luck today",
    "ok no worries enjoy the game",
    "all g have a good one",
    "its fine gl",
    "alright gl",
    "np have a good one",
    "ok gl dude",
    "no prob gl",
}
local MSGS_THANKS = {
    "hey just wanted to say thank u for the donation!! that was really nice",
    "bro i had to come back and say THANK YOU means a lot",
    "omg thank you so much!! u made my day fr",
    "seriously thank you ur the best",
    "hey ty so much for the donation!! really appreciate it",
    "ty!! that was so nice of u",
    "thank u sm!!",
    "bro ty fr that helped a lot",
    "omg ty!! u didnt have to",
    "thank u!! means a lot fr",
}

-- Dream item goal (chosen once at script start, used in getFirstMsg)
local DREAM_ITEMS = {
    {name = "this cute hat i saw",    price = 50},
    {name = "a hoodie i want",        price = 100},
    {name = "this jacket i rly want", price = 50},
    {name = "a ugc hat i found",      price = 100},
    {name = "this fit i saw",         price = 50},
    {name = "a beanie i want",        price = 10},
    {name = "this cool shirt",       price = 10},
    {name = "an outfit i found",      price = 100},
    {name = "a gamepass i want",      price = 50},
    {name = "this accessory",        price = 5},
    {name = "bloxburg",               price = 100},
    {name = "a limited i like",       price = 100},
    {name = "this hair i want",       price = 50},
    {name = "some ugc i saw",         price = 10},
    {name = "a face i want",          price = 10},
}
local dreamItem = DREAM_ITEMS[math.random(#DREAM_ITEMS)]
-- NOTE: getNeeded() is defined later (after Stats) to avoid upvalue bug

local FRUSTRATION_MSGS = {
    "today is not my day...",
    "everyone saying no today :(",
    "nobody wants to help today",
    "tough crowd today",
    "sad times...",
    "where are all the kind people?",
    "having bad luck today lol",
    "why everyone say no :(",
    "no luck today",
    "everyone said no lol",
    "rough server",
    "nobody donating rn",
}

local JUMP_TIME         = 5
local CIRCLE_COOLDOWN   = 4
local NORMAL_COOLDOWN   = 5
local CIRCLE_STEP_TIME  = 0.1
local TARGET_DISTANCE   = 12
local STUCK_THRESHOLD   = 3
local STUCK_CHECK_TIME  = 4
local MAX_JUMP_TRIES    = 3
local JUMP_DURATION     = 0.8
local MAX_RANDOM_TRIES  = 5
local MAX_STUCK_BEFORE_HOP = math.random(4, 7)         -- Random per session; predictable "hop after 3 stucks" is a flagged pattern
local SPRINT_KEY        = Enum.KeyCode.LeftShift

-- Track consecutive stuck failures
local consecutiveStuckCount = 0
local lastActivityTime      = tick()  -- watchdog: time of last meaningful action
local lastBeggingTime       = tick()  -- watchdog: time of last actual donation request sent
-- Track refusal/no-response streak for frustration messages
local refusalStreak = 0
-- Leaving-soon flag (set ~90s before watchdog-triggered server hop)
local leavingSoon   = false
-- Congrats cooldown: don't spam when many donations fire at once
local lastCongratTs = 0
-- Donors to thank after 2-3 min: { [name] = {ts, thanked} }
local recentDonors  = {}

-- ==================== STATISTICS ====================
local Stats = {
    approached      = 0,
    agreed          = 0,
    refused         = 0,
    no_response     = 0,
    hops            = 0,
    mods_met        = 0,   -- number of moderators/admins detected (triggered server hop)
    donations       = 0,   -- number of donation events (each time Raised grew)
    robux_gross     = 0,   -- total R$ raised (before Roblox 40% cut)
    raised_current  = 0,   -- current absolute Raised value shown on our booth
}
local sessionStart = os.time()  -- Unix epoch so dashboard timestamps are correct

-- getNeeded() must be AFTER Stats (upvalue lookup at definition time in Lua)
local function getNeeded()
    return math.max(dreamItem.price - Stats.robux_gross, 50)
end

-- ==================== INTERACTION LOG ====================
-- Buffer of per-player conversations; flushed to dashboard every report cycle.
local interactionLog = {}

local function logInteraction(targetName, botMsg, playerReply, outcome)
    table.insert(interactionLog, {
        ts      = os.time(),
        name    = targetName,
        bot     = botMsg,
        reply   = playerReply or "",
        outcome = outcome,    -- "agreed" | "refused" | "no_response" | "left" | "chase_fail"
    })
end

-- ==================== FILE LOGGING SET  ====================
local logLines = {}
local MAX_LOG_LINES = 500
local function log(msg)
    local timestamp = os.date("[%Y-%m-%d %H:%M:%S]")
    local logMsg = timestamp .. " " .. msg
    print(logMsg)
    table.insert(logLines, logMsg)
    if #logLines > MAX_LOG_LINES then
        table.remove(logLines, 1)
    end
end

local function saveLog()
    if not player then return end
    local content = table.concat(logLines, "\n")
    writefile("donation_bot_" .. tostring(player.UserId) .. ".log", content)
end

-- Auto-save log every 30 seconds
task.spawn(function()
    while true do
        task.wait(30)
        saveLog()
    end
end)

-- ==================== SERVICES & HTTP SETUP ====================
local Players               = game:GetService("Players")
local PathfindingService    = game:GetService("PathfindingService")
local TextChatService       = game:GetService("TextChatService")
local ReplicatedStorage     = game:GetService("ReplicatedStorage")
local VirtualInputManager   = game:GetService("VirtualInputManager")
local VirtualUser           = game:GetService("VirtualUser")
local TeleportService       = game:GetService("TeleportService")
local HttpService           = game:GetService("HttpService")
local player                = Players.LocalPlayer
local ignoreList = {}

-- Bot accounts to always ignore
local BOT_ACCOUNTS = {
    ["ExplorerCrusher292"] = true,
    ["ColorCrusher292"] = true,
    ["AquaCrusher292"] = true,
    ["PillageCrusher292"] = true,
    ["BeeCrusher292"] = true,
    ["NetherCrusher292"] = true,
    ["CaveCrusher292"] = true,
    ["CliffCrusher292"] = true,
    ["WildCrusher292"] = true,
    ["TrailCrusher292"] = true,
}

local httprequest = (syn and syn.request) or http and http.request or http_request or (fluxus and fluxus.request) or request
local queueFunc = queueonteleport or queue_on_teleport or (syn and syn.queue_on_teleport) or function() log("[HOP] Queue not supported!") end

-- ==================== SINGLETON GUARD ====================
-- Защита от двух источников дублей:
--   1. queueFunc() мог вызваться несколько раз за hop (main + watchdog).
--      Решение: PD_HAS_QUEUED — queueFunc срабатывает максимум 1 раз за Roblox-сессию.
--   2. Юзер инжектит скрипт повторно (рукой через executor).
--      Решение: heartbeat — активный instance каждую секунду обновляет PD_HEARTBEAT.
--      Новый инжект видит свежий heartbeat (<HEARTBEAT_DEAD_AFTER) и тихо выходит.
--      Если предыдущий instance умер (crash/teleport без queue) — heartbeat протухнет,
--      новый инжект захватит контроль.
local myInstanceId = tick() + math.random()  -- + random чтобы tick-collision были невозможны
local HEARTBEAT_DEAD_AFTER = 4  -- секунд: если PD_HEARTBEAT старше — старый instance считается мёртвым

local _rawQueueFunc = queueFunc
queueFunc = function(code)
    if getgenv and getgenv().PD_HAS_QUEUED then
        log("[SINGLETON] queueFunc already called this session — skipping duplicate")
        return
    end
    if getgenv then getgenv().PD_HAS_QUEUED = true end
    _rawQueueFunc(code)
end

if getgenv then
    local prevId = getgenv().PD_RUNNING_ID
    local prevHB = getgenv().PD_HEARTBEAT or 0
    local age = tick() - prevHB
    if prevId and prevId ~= 0 and age < HEARTBEAT_DEAD_AFTER then
        log(string.format(
            "[SINGLETON] Active instance %s alive (heartbeat %.1fs ago) — this re-inject is a no-op",
            tostring(prevId), age))
        return  -- тихо выходим, не трогаем глобалы
    end
    if prevId and prevId ~= 0 then
        log(string.format("[SINGLETON] Previous instance %s stale (%.1fs old) — taking over",
            tostring(prevId), age))
    end
    getgenv().PD_RUNNING_ID = myInstanceId
    getgenv().PD_HEARTBEAT = tick()
    getgenv().PD_HAS_QUEUED = false
    log("[SINGLETON] Active instance id=" .. tostring(myInstanceId))
end

local function isActiveInstance()
    if not getgenv then return true end
    return getgenv().PD_RUNNING_ID == myInstanceId
end

-- Heartbeat: пока этот instance активен, обновляем PD_HEARTBEAT. Если скрипт зависнет
-- или будет убит — heartbeat протухнет за HEARTBEAT_DEAD_AFTER, и следующий инжект
-- сможет взять контроль.
task.spawn(function()
    while isActiveInstance() do
        if getgenv then getgenv().PD_HEARTBEAT = tick() end
        task.wait(1)
    end
end)

-- ==================== VISITED SERVERS (persistent across hops) ====================
local VISITED_FOLDER = "ServerHop"
local VISITED_FILE   = VISITED_FOLDER .. "/pd_visited_" .. tostring(PLACE_ID) .. "_" .. tostring(player.UserId) .. ".json"

local function loadVisited()
    pcall(function() if not isfolder(VISITED_FOLDER) then makefolder(VISITED_FOLDER) end end)
    if pcall(function() return isfile(VISITED_FILE) end) and isfile(VISITED_FILE) then
        local ok, data = pcall(function() return HttpService:JSONDecode(readfile(VISITED_FILE)) end)
        if ok and type(data) == "table" then return data end
    end
    return {}
end

local function saveVisited(data)
    pcall(function() writefile(VISITED_FILE, HttpService:JSONEncode(data)) end)
end

local function pruneVisited(data, cooldownMins)
    local cutoff = tick() - (cooldownMins * 60)
    local pruned = {}
    for jobId, ts in pairs(data) do
        if ts > cutoff then pruned[jobId] = ts end
    end
    return pruned
end

local function wasVisited(data, jobId, cooldownMins)
    local ts = data[jobId]
    return ts ~= nil and (tick() - ts) < (cooldownMins * 60)
end

-- ==================== JUST-LEFT SERVER (avoid same server for 5 min) ====================
-- So we never rejoin the server we just left (e.g. after matchmaking or API returning same server).
local JUST_LEFT_FILE   = VISITED_FOLDER .. "/pd_just_left_" .. tostring(player.UserId) .. ".json"
local JUST_LEFT_MINS   = 5

local function loadJustLeft()
    pcall(function() if not isfolder(VISITED_FOLDER) then makefolder(VISITED_FOLDER) end end)
    if pcall(function() return isfile(JUST_LEFT_FILE) end) and isfile(JUST_LEFT_FILE) then
        local ok, data = pcall(function() return HttpService:JSONDecode(readfile(JUST_LEFT_FILE)) end)
        if ok and type(data) == "table" then
            local cutoff = tick() - (JUST_LEFT_MINS * 60)
            local pruned = {}
            for jobId, ts in pairs(data) do
                if ts > cutoff then pruned[jobId] = ts end
            end
            return pruned
        end
    end
    return {}
end

local function saveJustLeft(data)
    pcall(function() writefile(JUST_LEFT_FILE, HttpService:JSONEncode(data)) end)
end

local function wasJustLeft(justLeftData, jobId)
    local ts = justLeftData[jobId]
    return ts ~= nil and (tick() - ts) < (JUST_LEFT_MINS * 60)
end

-- ==================== OCCUPIED SERVERS FETCH ====================
-- Returns a set { [serverId] = true } of servers already occupied by our bots.
-- Used during server hop to avoid putting two bots on the same server.
local function fetchOccupiedServers()
    local occupied = {}
    if DASH_URL == "" then return occupied end
    local ok, resp = pcall(function()
        return httprequest({ Url = DASH_URL .. "/pd_occupied_servers" })
    end)
    if ok and resp and resp.StatusCode == 200 and resp.Body then
        local parseOk, data = pcall(function() return HttpService:JSONDecode(resp.Body) end)
        if parseOk and type(data) == "table" and type(data.occupied) == "table" then
            for serverId, botName in pairs(data.occupied) do
                occupied[tostring(serverId)] = true
            end
            local count = 0
            for _ in pairs(occupied) do count = count + 1 end
            log("[HOP] Occupied servers from dashboard: " .. count)
        end
    end
    return occupied
end

-- ==================== DASHBOARD CONFIG FETCH ====================
local function fetchDashConfig()
    if DASH_URL == "" then return end
    local ok, resp = pcall(function()
        return httprequest({ Url = DASH_URL .. "/pd_config/" .. tostring(player.UserId) })
    end)
    if ok and resp and resp.StatusCode == 200 and resp.Body then
        local parseOk, cfg = pcall(function() return HttpService:JSONDecode(resp.Body) end)
        if parseOk and type(cfg) == "table" then
            if type(cfg.min_players) == "number" then MIN_PLAYERS = cfg.min_players end
            if type(cfg.max_players) == "number" then MAX_PLAYERS_ALLOWED = cfg.max_players end
            if type(cfg.server_cooldown) == "number" then SERVER_COOLDOWN_MINS = cfg.server_cooldown end
            if cfg.clear_history then
                saveVisited({})
                log("[CONFIG] Server visit history cleared from dashboard")
            end
            log(string.format("[CONFIG] Loaded from dashboard: min=%d max=%d cooldown=%dmin",
                MIN_PLAYERS, MAX_PLAYERS_ALLOWED, SERVER_COOLDOWN_MINS))
        end
    end
end

-- Fetch config at startup
fetchDashConfig()

-- Wait for character to fully load
if not player.Character then
    log("Waiting for character to load...")
    player.CharacterAdded:Wait()
end
player.Character:WaitForChild("HumanoidRootPart")
log("Character loaded!")

-- Multi-bot startup desync: spread bots so first hops don't hit Roblox API simultaneously
do
    local desync = math.random(5, 90)
    log(string.format("[INIT] Startup desync: %ds (prevents synchronized hops on shared IP)", desync))
    task.wait(desync)
end

-- ==================== MEMORY MANAGEMENT: Prevent crashes from GC pressure ====================
-- Multiple monitors call GetDescendants() every 2-3s, creating huge temporary tables.
-- Periodic collectgarbage reduces memory spikes that crash the Roblox client.
task.spawn(function()
    while true do
        task.wait(30)
        pcall(function() collectgarbage("collect") end)
    end
end)

-- ==================== ANTI-AFK: Error 278 prevention ====================
-- Error 278 = "Disconnected for being idle 20 minutes"
-- VirtualUser simulates controller input so Roblox never considers the bot idle.
player.Idled:Connect(function()
    VirtualUser:CaptureController()
    VirtualUser:ClickButton2(Vector2.new())
    log("[AFK] Anti-AFK fired — idle kick prevented (Error 278)")
end)

-- Backup: simulate input every 3 minutes (much more aggressive than old 10-min interval)
-- Uses the full Button2Down→Button2Up cycle which is more reliable than ClickButton2 alone
task.spawn(function()
    while true do
        task.wait(180)
        pcall(function()
            VirtualUser:CaptureController()
            VirtualUser:Button2Down(Vector2.new(0, 0), workspace.CurrentCamera.CFrame)
            task.wait(0.1)
            VirtualUser:Button2Up(Vector2.new(0, 0), workspace.CurrentCamera.CFrame)
            VirtualUser:ClickButton2(Vector2.new())
        end)
    end
end)
log("[AFK] Anti-AFK running (VirtualUser, 3-min interval)")

-- ==================== HUMAN-LOOK: camera + idle wander ====================
-- Real players constantly nudge their camera and wiggle. Bots that stand
-- frozen looking the same direction stand out hard to manual moderators.
task.spawn(function()
    task.wait(math.random(8, 25))
    while true do
        local cam = workspace.CurrentCamera
        if cam then
            pcall(function()
                local yaw   = math.rad((math.random() - 0.5) * 30)  -- ±15°
                local pitch = math.rad((math.random() - 0.5) * 10)  -- ±5°
                cam.CFrame = cam.CFrame * CFrame.Angles(pitch, yaw, 0)
            end)
        end
        task.wait(math.random(7, 28))
    end
end)

-- Background passive wander: occasional WASD twitch so the avatar isn't
-- a frozen statue between begging cycles. Mouse-jiggle isn't replicated
-- by Roblox, but humanoid keyboard input is.
local _WANDER_KEYS = {Enum.KeyCode.W, Enum.KeyCode.A, Enum.KeyCode.S, Enum.KeyCode.D}
task.spawn(function()
    task.wait(math.random(45, 150))
    while true do
        pcall(function()
            -- Skip while bot is actively chasing/begging; only twitch when idle
            local timeSinceBeg = tick() - lastBeggingTime
            if timeSinceBeg > 12 then
                local key = _WANDER_KEYS[math.random(#_WANDER_KEYS)]
                local dur = 0.15 + math.random() * 0.45
                VirtualInputManager:SendKeyEvent(true,  key, false, game)
                task.wait(dur)
                VirtualInputManager:SendKeyEvent(false, key, false, game)
            end
        end)
        task.wait(math.random(25, 90))
    end
end)

-- ==================== AUTO-RECONNECT QUEUE: Error 277 recovery ====================
-- Error 277 = lost connection / network drop.
-- queueonteleport queues a script to run after ANY next join/teleport,
-- including when the player clicks "Reconnect" on the 277 screen.
-- So pressing Reconnect automatically restarts the bot — no manual reinjection needed.
local _reconnectScript = [[
local _req = (syn and syn.request) or http and http.request or http_request or (fluxus and fluxus.request) or request
local _ok, _res = pcall(_req, {Url = "]] .. SCRIPT_URL .. [["})
if _ok and _res and _res.Body and _res.Body ~= "" then
    loadstring(_res.Body)()
else
    pcall(function() loadstring(game:HttpGet("]] .. SCRIPT_URL .. [[", true))() end)
end
]]
pcall(function() queueFunc(_reconnectScript) end)
log("[RECONNECT] Script queued — clicking Reconnect on 277 screen will auto-restart bot")

-- ==================== AUTO-RECONNECT: Error 277 (Lost Connection) active monitor ====================
-- Error 277 = "Please check your internet connection and try again."
-- Strategy (based on open-source auto-rejoin patterns):
--   1. Scan CoreGui every 2s for the 277 disconnect dialog
--   2. Click "Reconnect" button (queueonteleport fires → script auto-restarts on new server)
--   3. If Reconnect click doesn't leave game within 8s, fall back to TeleportService:Teleport()
task.spawn(function()
    local recovering277 = false
    local firstSeen277  = 0
    local DEBOUNCE_277  = 2

    local function clickBtn277(cg, ...)
        local targets = {...}
        for _, btn in pairs(cg:GetDescendants()) do
            if btn:IsA("TextButton") then
                local bt = string.lower(tostring(btn.Text or ""))
                for _, t in ipairs(targets) do
                    if string.find(bt, t, 1, true) then
                        pcall(function() btn.MouseButton1Click:Fire() end)
                        pcall(function() btn:Activate() end)
                        if firebutton then pcall(function() firebutton(btn) end) end
                        -- VirtualInputManager: более надёжный клик для защищённых CoreGui кнопок
                        pcall(function()
                            local vim = game:GetService("VirtualInputManager")
                            local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                            task.wait(0.05)
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                        end)
                        return true
                    end
                end
            end
        end
        return false
    end

    while true do
        task.wait(3)
        if recovering277 then continue end
        pcall(function()
            local cg = game:GetService("CoreGui")

            -- Two-pass scan: first check for Reconnect button (cheap), then collect text only if needed
            local hasReconnectBtn = false
            local descendants = cg:GetDescendants()
            for _, elem in pairs(descendants) do
                if elem:IsA("TextButton") and string.lower(tostring(elem.Text or "")) == "reconnect" then
                    hasReconnectBtn = true
                    break
                end
            end
            if not hasReconnectBtn then
                firstSeen277 = 0
                descendants = nil
                return
            end

            -- Collect text using table.concat (O(n) vs O(n²) string concat)
            local textParts = {}
            for _, elem in pairs(descendants) do
                if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                    textParts[#textParts + 1] = string.lower(tostring(elem.Text or ""))
                end
            end
            descendants = nil  -- release reference for GC
            local allText = table.concat(textParts, " ")
            textParts = nil

            local found277 = (
                string.find(allText, "277") or
                string.find(allText, "check your internet connection") or
                string.find(allText, "lost connection")
            )

            if not found277 then
                firstSeen277 = 0
                return
            end

            local now = tick()
            if firstSeen277 == 0 then
                firstSeen277 = now
                log("[277] Disconnect dialog detected — acting in " .. DEBOUNCE_277 .. "s...")
                return
            end
            if now - firstSeen277 < DEBOUNCE_277 then return end

            recovering277 = true
            firstSeen277  = 0
            log("[277] Clicking Reconnect button...")

            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)

            local clicked = clickBtn277(cg, "reconnect")
            if clicked then
                log("[277] Reconnect clicked — waiting 8s for teleport...")
                task.wait(8)
                log("[277] Reconnect didn't fire — forcing TeleportService:Teleport...")
            else
                log("[277] Reconnect button not found — forcing TeleportService:Teleport...")
            end

            -- Fallback — повторяем без ограничения попыток, никогда не сдаёмся
            local _277attempt = 0
            while true do
                _277attempt += 1
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                log("[277] Teleport attempt #" .. _277attempt)
                task.wait(15)
                -- Каждые 3 попытки пробуем кликнуть Reconnect снова
                if _277attempt % 3 == 0 then
                    if getgenv then getgenv().PD_HAS_QUEUED = false end
                    pcall(function() queueFunc(_reconnectScript) end)
                    clickBtn277(cg, "reconnect")
                    log("[277] Re-clicking Reconnect (attempt " .. _277attempt .. ")...")
                end
            end
        end)
    end
end)
log("[277] Error 277 active recovery monitor started (auto-click Reconnect + teleport fallback)")

-- ==================== AUTO-RECONNECT: Error 267 (Kick) recovery ====================
-- Error 267 = "You have been kicked by this experience or its moderators"
-- Unlike Error 277 (has "Reconnect" button), Error 267 only has a "Leave" button.
-- Strategy: detect the kick dialog via CoreGui the moment it appears,
-- immediately call TeleportService:Teleport() to "escape" before the kick
-- fully closes the connection — this fires queueonteleport so the script
-- auto-restarts on the new server without any manual action.
local function startKickRecovery()
    task.spawn(function()
        local recovering = false
        while true do
            task.wait(2.5)
            if recovering then continue end
            pcall(function()
                local cg = game:GetService("CoreGui")
                -- Scan all GUI text for Error 267 / kicked indicators
                -- Note: "267" alone can appear in chat; require full phrase
                local kicked267 = false
                for _, elem in pairs(cg:GetDescendants()) do
                    if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                        local t = string.lower(tostring(elem.Text or ""))
                        if string.find(t, "kicked by this experience")
                        or string.find(t, "kicked by its moderators")
                        or (string.find(t, "267") and string.find(t, "experience")) then
                            kicked267 = true
                            break
                        end
                    end
                end
                if not kicked267 then return end

                recovering = true
                log("[267] Kick detected — attempting teleport escape before disconnect...")

                -- Re-queue script in case prior queue was consumed (singleton guard
                -- resets PD_HAS_QUEUED each new server, but we force it here just in case)
                if getgenv then getgenv().PD_HAS_QUEUED = false end
                pcall(function() queueFunc(_reconnectScript) end)

                -- Immediately teleport — if this fires before Roblox closes the
                -- connection it behaves like a normal server hop and the queued
                -- script will auto-execute on the next server.
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                task.wait(3)

                -- Fallback: if teleport didn't fire in 3s, click the Leave button.
                -- The queued script won't fire via queueonteleport in this case,
                -- but the user will return to Roblox home and can manually rejoin.
                for _, btn in pairs(cg:GetDescendants()) do
                    if btn:IsA("TextButton") then
                        local bt = string.lower(tostring(btn.Text or ""))
                        if bt == "leave" or bt == "ok" or bt == "okay" then
                            btn.MouseButton1Click:Fire()
                            pcall(function() btn:Activate() end)
                            log("[267] Fallback: clicked Leave button")
                            break
                        end
                    end
                end
            end)
        end
    end)
end

startKickRecovery()
log("[267] Kick recovery monitor started (Error 267 auto-teleport)")

-- ==================== AUTO-RECONNECT: Error 2 (Connection Failed — Please Try Again) ====================
-- Error 2 = "Failed to connect to the experience. Please try again."
-- Transient generic error, NOT the same as 279 ("no response from server").
-- Strategy: click Retry with VIM + infinite teleport fallback. Never gives up.
-- IMPORTANT: pattern must match EXACTLY "error code: 2)" to avoid matching 267/276/277/279.
task.spawn(function()
    local acting2    = false
    local firstSeen2 = 0
    local retries2   = 0
    local DEBOUNCE2  = 2

    local function isError2(text)
        -- Exact match: "error code: 2" followed by ")" or end-of-string, NOT "27" etc.
        local pos = string.find(text, "error code: 2", 1, true)
        if pos then
            local after = string.sub(text, pos + 13, pos + 13)
            if after == "" or after == ")" or after == " " or after == "." then return true end
        end
        if string.find(text, "connection failed", 1, true) and string.find(text, "please try again", 1, true)
           and not string.find(text, "no response", 1, true) then
            return true
        end
        return false
    end

    local function clickBtn2(cg, ...)
        local targets = {...}
        for _, btn in pairs(cg:GetDescendants()) do
            if btn:IsA("TextButton") then
                local bt = string.lower(tostring(btn.Text or ""))
                for _, t in ipairs(targets) do
                    if string.find(bt, t, 1, true) then
                        pcall(function() btn.MouseButton1Click:Fire() end)
                        pcall(function() btn:Activate() end)
                        if firebutton then pcall(function() firebutton(btn) end) end
                        -- VirtualInputManager: more reliable for CoreGui buttons
                        pcall(function()
                            local vim = game:GetService("VirtualInputManager")
                            local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                            task.wait(0.05)
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                        end)
                        return true
                    end
                end
            end
        end
        return false
    end

    while true do
        task.wait(3)
        if acting2 then continue end
        pcall(function()
            local cg = game:GetService("CoreGui")
            local foundErr2 = false
            for _, elem in pairs(cg:GetDescendants()) do
                if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                    local t = string.lower(tostring(elem.Text or ""))
                    if isError2(t) then
                        foundErr2 = true
                        break
                    end
                end
            end

            if not foundErr2 then
                firstSeen2 = 0
                retries2   = 0
                return
            end

            local now = tick()
            if firstSeen2 == 0 then
                firstSeen2 = now
                log("[E2] Error 2 dialog detected — acting in " .. DEBOUNCE2 .. "s...")
                return
            end
            if now - firstSeen2 < DEBOUNCE2 then return end

            acting2    = true
            firstSeen2 = 0
            retries2   = retries2 + 1
            log(string.format("[E2] Error 2 attempt #%d — clicking Retry...", retries2))

            local clicked = clickBtn2(cg, "retry")
            if clicked then
                log("[E2] Clicked Retry (VIM) — waiting 12s for connect...")
                task.wait(12)
                -- Check if dialog still present
                local stillHere = false
                pcall(function()
                    for _, elem in pairs(game:GetService("CoreGui"):GetDescendants()) do
                        if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                            local t2 = string.lower(tostring(elem.Text or ""))
                            if isError2(t2) then
                                stillHere = true
                                break
                            end
                        end
                    end
                end)
                if not stillHere then
                    log("[E2] Dialog gone after Retry — success!")
                    acting2 = false
                    return
                end
                log("[E2] Retry clicked but dialog still here — entering recovery loop...")
            else
                log("[E2] Retry button not found — entering recovery loop...")
            end

            -- Infinite recovery loop — never gives up (same pattern as 277)
            clickBtn2(game:GetService("CoreGui"), "cancel", "leave", "ok")
            task.wait(2)
            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)

            local _e2attempt = 0
            while true do
                _e2attempt += 1
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                log("[E2] Teleport attempt #" .. _e2attempt)
                task.wait(15)
                -- Every 3 attempts: re-click Retry, re-queue script
                if _e2attempt % 3 == 0 then
                    if getgenv then getgenv().PD_HAS_QUEUED = false end
                    pcall(function() queueFunc(_reconnectScript) end)
                    clickBtn2(game:GetService("CoreGui"), "retry")
                    clickBtn2(game:GetService("CoreGui"), "cancel", "leave", "ok")
                    log("[E2] Re-clicking buttons + re-queuing (attempt " .. _e2attempt .. ")...")
                end
            end
        end)
    end
end)
log("[E2] Error 2 recovery monitor started (exact match + VIM + infinite retry)")

-- ==================== AUTO-RECONNECT: Error 276 (Same Account Different Device) ====================
-- Error 276 = "Same account launched experience from different device."
-- This error has a "Reconnect" button. Strategy:
--   1. Detect the 276 dialog via CoreGui scan
--   2. Click "Reconnect" (queueonteleport fires → script auto-restarts)
--   3. If Reconnect doesn't work within 8s, force TeleportService:Teleport()
--   4. If teleport also fails, keep retrying every 30s (never give up)
task.spawn(function()
    local recovering276 = false

    local function clickBtnGeneric(cg, ...)
        local targets = {...}
        for _, btn in pairs(cg:GetDescendants()) do
            if btn:IsA("TextButton") then
                local bt = string.lower(tostring(btn.Text or ""))
                for _, t in ipairs(targets) do
                    if string.find(bt, t, 1, true) then
                        pcall(function() btn.MouseButton1Click:Fire() end)
                        pcall(function() btn:Activate() end)
                        if firebutton then pcall(function() firebutton(btn) end) end
                        return true
                    end
                end
            end
        end
        return false
    end

    while true do
        task.wait(4)
        if recovering276 then continue end
        pcall(function()
            local cg = game:GetService("CoreGui")
            local found276 = false
            for _, elem in pairs(cg:GetDescendants()) do
                if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                    local t = string.lower(tostring(elem.Text or ""))
                    if string.find(t, "276")
                    or string.find(t, "same account")
                    or string.find(t, "different device") then
                        found276 = true
                        break
                    end
                end
            end
            if not found276 then return end

            recovering276 = true
            log("[276] Same-account disconnect detected — recovering...")

            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)

            local clicked = clickBtnGeneric(cg, "reconnect")
            if clicked then
                log("[276] Reconnect clicked — waiting 8s...")
                task.wait(8)
                log("[276] Still here — forcing teleport...")
            else
                log("[276] Reconnect button not found — forcing teleport...")
            end

            for attempt = 1, 5 do
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                log("[276] Teleport attempt #" .. attempt)
                task.wait(12)
            end

            recovering276 = false
        end)
    end
end)
log("[276] Error 276 recovery monitor started (same-account auto-reconnect)")

-- ==================== AUTO-RECONNECT: Error 773 (Teleport Failed) recovery ====================
-- Error 773 = "Reconnect was unsuccessful. Please try again."
-- This happens when a teleport/reconnect attempt fails — the target server may be
-- full, crashed, or no longer exists. Unlike 277 (network drop), 773 means the
-- reconnect itself failed, so retrying the same server is pointless.
-- Strategy: detect the dialog, teleport to a NEW server via matchmaking (not same JobId).
task.spawn(function()
    local recovering773 = false

    local function clickBtn773(cg, ...)
        local targets = {...}
        for _, btn in pairs(cg:GetDescendants()) do
            if btn:IsA("TextButton") then
                local bt = string.lower(tostring(btn.Text or ""))
                for _, t in ipairs(targets) do
                    if string.find(bt, t, 1, true) then
                        pcall(function() btn.MouseButton1Click:Fire() end)
                        pcall(function() btn:Activate() end)
                        if firebutton then pcall(function() firebutton(btn) end) end
                        pcall(function()
                            local vim = game:GetService("VirtualInputManager")
                            local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                            task.wait(0.05)
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                        end)
                        return true
                    end
                end
            end
        end
        return false
    end

    while true do
        task.wait(3.5)
        if recovering773 then continue end
        pcall(function()
            local cg = game:GetService("CoreGui")

            -- Two-pass: check Leave button first (cheap), then collect text
            local hasLeaveBtn = false
            local descendants = cg:GetDescendants()
            for _, elem in pairs(descendants) do
                if elem:IsA("TextButton") and string.lower(tostring(elem.Text or "")) == "leave" then
                    hasLeaveBtn = true
                    break
                end
            end
            if not hasLeaveBtn then descendants = nil; return end

            local textParts = {}
            for _, elem in pairs(descendants) do
                if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                    textParts[#textParts + 1] = string.lower(tostring(elem.Text or ""))
                end
            end
            descendants = nil
            local allText = table.concat(textParts, " ")
            textParts = nil

            local found773 = (
                string.find(allText, "773") or
                string.find(allText, "reconnect was unsuccessful")
            )

            if not found773 then return end

            recovering773 = true
            log("[773] Teleport-failed dialog detected — teleporting to new server...")

            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)

            -- Click Leave first to dismiss the dialog
            clickBtn773(cg, "leave")
            task.wait(2)

            -- Teleport to a new server via matchmaking (infinite retry)
            local _773attempt = 0
            while true do
                _773attempt += 1
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                log("[773] Teleport attempt #" .. _773attempt)
                task.wait(15)
                -- Every 3 attempts, re-queue the script and re-click Leave if dialog reappeared
                if _773attempt % 3 == 0 then
                    if getgenv then getgenv().PD_HAS_QUEUED = false end
                    pcall(function() queueFunc(_reconnectScript) end)
                    clickBtn773(cg, "leave")
                    log("[773] Re-clicking Leave + re-queuing (attempt " .. _773attempt .. ")...")
                end
            end
        end)
    end
end)
log("[773] Error 773 recovery monitor started (teleport-failed auto-rejoin)")

-- ==================== UNIVERSAL CATCH-ALL: Any unknown disconnect dialog ====================
-- Catches ANY disconnect dialog that isn't already handled by specific monitors above.
-- Looks for the "Disconnected" title in CoreGui ErrorPrompt and acts on it.
-- Strategy: click Reconnect if available, otherwise click Leave, then force teleport.
-- This ensures the bot NEVER gets stuck on any disconnect screen.
task.spawn(function()
    local catchAllActing = false
    local KNOWN_CODES = {"276", "267", "279", "278", "773", "error code: 2)"}

    while true do
        task.wait(5)
        if catchAllActing then continue end
        pcall(function()
            local cg = game:GetService("CoreGui")
            -- Single GetDescendants call — reuse for both button check and text scan
            local descendants = cg:GetDescendants()
            local hasDisconnectBtn = false
            for _, btn in pairs(descendants) do
                if btn:IsA("TextButton") then
                    local bt = string.lower(tostring(btn.Text or ""))
                    if bt == "reconnect" or bt == "leave" or bt == "retry" then
                        hasDisconnectBtn = true
                        break
                    end
                end
            end
            if not hasDisconnectBtn then descendants = nil; return end

            local foundUnknown = false
            local dialogText = ""

            for _, elem in pairs(descendants) do
                if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                    local t = string.lower(tostring(elem.Text or ""))
                    if string.find(t, "disconnected")
                    or string.find(t, "connection lost")
                    or string.find(t, "kicked")
                    or string.find(t, "error code")
                    or string.find(t, "teleport failed")
                    or string.find(t, "lost connection") then
                        local isKnown = false
                        for _, code in ipairs(KNOWN_CODES) do
                            if string.find(t, code, 1, true) then
                                isKnown = true
                                break
                            end
                        end
                        if string.find(t, "same account") then isKnown = true end
                        if string.find(t, "reconnect was unsuccessful") then isKnown = true end
                        if string.find(t, "connection failed") and string.find(t, "please try again") then isKnown = true end
                        if string.find(t, "no response from server") then isKnown = true end
                        if string.find(t, "been kicked") then isKnown = true end
                        -- Ignore OS/hardware notifications (e.g. "headset disconnected")
                        -- Real Roblox dialogs always contain one of these context words
                        local hasRobloxCtx = string.find(t, "experience") or string.find(t, "error code")
                            or string.find(t, "internet") or string.find(t, "roblox")
                            or string.find(t, "try again") or string.find(t, "reconnect")
                            or string.find(t, "server") or string.find(t, "kicked by")
                        if not hasRobloxCtx then isKnown = true end

                        if not isKnown then
                            foundUnknown = true
                            dialogText = t
                            break
                        end
                    end
                end
            end
            descendants = nil  -- release for GC
            if not foundUnknown then return end

            catchAllActing = true
            log("[CATCH-ALL] Unknown disconnect dialog: " .. string.sub(dialogText, 1, 80))

            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)

            local function tryClickBtn(cg2, ...)
                local targets = {...}
                for _, btn in pairs(cg2:GetDescendants()) do
                    if btn:IsA("TextButton") then
                        local bt = string.lower(tostring(btn.Text or ""))
                        for _, t in ipairs(targets) do
                            if string.find(bt, t, 1, true) then
                                pcall(function() btn.MouseButton1Click:Fire() end)
                                pcall(function() btn:Activate() end)
                                if firebutton then pcall(function() firebutton(btn) end) end
                                pcall(function()
                                    local vim = game:GetService("VirtualInputManager")
                                    local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                                    vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                                    task.wait(0.05)
                                    vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                                end)
                                return true
                            end
                        end
                    end
                end
                return false
            end

            tryClickBtn(cg, "reconnect")
            task.wait(8)
            tryClickBtn(cg, "retry")
            task.wait(5)
            tryClickBtn(cg, "leave", "ok", "cancel")
            task.wait(3)

            -- Infinite retry — never give up
            local _caAttempt = 0
            while true do
                _caAttempt += 1
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
                log("[CATCH-ALL] Teleport attempt #" .. _caAttempt)
                task.wait(15)
                if _caAttempt % 3 == 0 then
                    if getgenv then getgenv().PD_HAS_QUEUED = false end
                    pcall(function() queueFunc(_reconnectScript) end)
                    tryClickBtn(cg, "reconnect")
                    tryClickBtn(cg, "retry")
                    tryClickBtn(cg, "leave", "ok", "cancel")
                    log("[CATCH-ALL] Re-clicking buttons + re-queuing (attempt " .. _caAttempt .. ")...")
                end
            end
        end)
    end
end)
log("[CATCH-ALL] Universal disconnect catch-all monitor started")

-- ==================== AUTO-RECONNECT: Error 279 (Connection Failed) recovery ====================
-- Error 279 = "Failed to connect to the experience. No response from server."
-- Root causes: target server OOM/crashed, Roblox rate-limiting teleports after long sessions.
--
-- Strategy (learned from DevForum + long-session behavior):
--   Attempts 0-1 → click RETRY (fires TeleportInitFailed reliably → matchmaking path)
--   Attempts 2-3 → click Cancel + matchmaking with short wait
--   Attempts 4+  → click Cancel + exponential backoff (up to 5 min) before retrying
--   After 6+ consecutive failures → 6-minute cooldown (Roblox rate-limit reset)
--
-- NOTE: player:Kick() is a server-side function and DOES NOT WORK from LocalScript/executor.
-- The only real client-side escapes are TeleportService:Teleport and clicking dialog buttons.
local function startError279Recovery()
    task.spawn(function()
        local acting       = false
        local firstDetect  = 0
        local DEBOUNCE     = 3
        -- Per-stuck-episode retry tracking (resets once dialog goes away)
        local episodeRetry = 0
        -- Global consecutive failure counter (never resets until success)
        if getgenv and not getgenv().PD_279_CONSEC then
            getgenv().PD_279_CONSEC = 0
        end
        -- Backoff table (seconds to wait before attempting matchmaking each time)
        local BACKOFF = {2, 5, 15, 45, 120, 300}
        local COOLDOWN_AFTER = 6       -- enter cooldown after this many consec failures
        local COOLDOWN_DUR   = 360     -- 6 minutes (clears Roblox rate limits)

        local function clickBtn(btn)
            pcall(function() btn.MouseButton1Click:Fire() end)
            pcall(function() btn:Activate() end)
            if firebutton then pcall(function() firebutton(btn) end) end
        end

        local function findBtn(cg, ...)
            local targets = {...}
            for _, btn in pairs(cg:GetDescendants()) do
                if btn:IsA("TextButton") then
                    local bt = string.lower(tostring(btn.Text or ""))
                    for _, t in ipairs(targets) do
                        if string.find(bt, t, 1, true) then return btn, bt end
                    end
                end
            end
            return nil
        end

        local function tryMatchmaking(waitSecs)
            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)
            log("[279] Matchmaking teleport (wait=" .. waitSecs .. "s)...")
            pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
            task.wait(waitSecs)
            -- Second attempt if still here
            pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
            task.wait(math.max(waitSecs, 10))
        end

        while true do
            task.wait(1.5)
            if acting then continue end
            pcall(function()
                local cg = game:GetService("CoreGui")

                local found279 = false
                for _, elem in pairs(cg:GetDescendants()) do
                    if elem:IsA("TextLabel") or elem:IsA("TextBox") then
                        local t = string.lower(tostring(elem.Text or ""))
                        if string.find(t, "279")
                        or string.find(t, "no response from server")
                        or (string.find(t, "failed to connect to the experience")
                            and not string.find(t, "please try again")) then
                            found279 = true
                            break
                        end
                    end
                end

                if not found279 then
                    if firstDetect ~= 0 then
                        -- Dialog disappeared on its own — success, reset episode
                        firstDetect  = 0
                        episodeRetry = 0
                        if getgenv then getgenv().PD_279_CONSEC = 0 end
                    end
                    return
                end

                local now = tick()
                if firstDetect == 0 then
                    firstDetect = now
                    log("[279] Dialog detected — acting in " .. DEBOUNCE .. "s...")
                    return
                end
                if now - firstDetect < DEBOUNCE then return end

                acting = true
                firstDetect = 0

                if getgenv then
                    getgenv().PD_279_RECENT = (getgenv().PD_279_RECENT or 0) + 1
                    getgenv().PD_279_LAST_T = now
                    getgenv().PD_279_CONSEC = (getgenv().PD_279_CONSEC or 0) + 1
                end
                local consec = getgenv and getgenv().PD_279_CONSEC or episodeRetry + 1
                log(string.format("[279] Attempt #%d (consec=%d)", episodeRetry + 1, consec))

                -- Cooldown mode: too many consecutive failures = likely Roblox rate-limit
                if consec >= COOLDOWN_AFTER then
                    log(string.format("[279] %d consec failures — entering %ds cooldown (rate-limit reset)...", consec, COOLDOWN_DUR))
                    -- Click Cancel to dismiss dialog so we're not fully frozen
                    local cancelBtn = findBtn(cg, "cancel", "leave", "ok")
                    if cancelBtn then clickBtn(cancelBtn) end
                    task.wait(COOLDOWN_DUR)
                    if getgenv then getgenv().PD_279_CONSEC = 0 end
                    episodeRetry = 0
                    acting = false
                    return
                end

                -- Attempts 0-1: click RETRY (fires TeleportInitFailed → its handler does matchmaking)
                -- TeleportInitFailed is more reliable than calling TeleportService:Teleport directly
                -- from an uncertain client state.
                if episodeRetry < 2 then
                    local retryBtn = findBtn(cg, "retry")
                    if retryBtn then
                        log("[279] Clicking Retry (fires TeleportInitFailed → matchmaking)...")
                        clickBtn(retryBtn)
                        episodeRetry = episodeRetry + 1
                        -- TeleportInitFailed handler will run; give it time
                        task.wait(20)
                        acting = false
                        return
                    end
                end

                -- Attempts 2+: Cancel + direct matchmaking with backoff
                local cancelBtn = findBtn(cg, "cancel", "leave")
                if cancelBtn then
                    clickBtn(cancelBtn)
                    log("[279] Clicked Cancel")
                end
                task.wait(2)

                local backoffIdx = math.min(episodeRetry + 1, #BACKOFF)
                local waitSecs   = BACKOFF[backoffIdx]
                log(string.format("[279] Backoff=%ds (attempt %d)...", waitSecs, episodeRetry + 1))
                task.wait(waitSecs)

                tryMatchmaking(15)
                episodeRetry = episodeRetry + 1
                acting = false
            end)
        end
    end)
end

startError279Recovery()
log("[279] Error 279 recovery monitor started (Retry-first + exponential backoff)")

-- ==================== TELEPORT INIT FAILED: early 279 intercept ====================
-- TeleportInitFailed fires BEFORE the 279 dialog appears (not always — OOM servers may skip it).
-- We track consecutive failures and apply backoff to handle Roblox rate-limiting.
-- NOTE: player:Kick() does NOT work from LocalScript — removed.
do
    local _tpfailCount = 0
    local _tpfailLast  = 0
    local _TPFAIL_BACKOFF = {3, 8, 20, 60, 180}  -- seconds before matchmaking retry

    TeleportService.TeleportInitFailed:Connect(function(plr, result, errMsg)
        local now = tick()
        log(string.format("[TPFail] TeleportInitFailed: %s / %s", tostring(result), tostring(errMsg or "")))

        if getgenv then
            getgenv().PD_279_RECENT = (getgenv().PD_279_RECENT or 0) + 1
            getgenv().PD_279_LAST_T = now
            getgenv().PD_279_CONSEC = (getgenv().PD_279_CONSEC or 0) + 1
        end

        -- Count consecutive failures (reset if last failure was >10min ago)
        if now - _tpfailLast > 600 then _tpfailCount = 0 end
        _tpfailCount = _tpfailCount + 1
        _tpfailLast  = now

        local backoffIdx = math.min(_tpfailCount, #_TPFAIL_BACKOFF)
        local waitSecs   = _TPFAIL_BACKOFF[backoffIdx]
        log(string.format("[TPFail] Failure #%d — waiting %ds before matchmaking...", _tpfailCount, waitSecs))

        if getgenv then getgenv().PD_HAS_QUEUED = false end
        pcall(function() queueFunc(_reconnectScript) end)
        task.wait(waitSecs)

        log("[TPFail] Matchmaking teleport...")
        pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
        task.wait(12)
        -- Second attempt if still here (teleport can silently fail in rate-limited state)
        log("[TPFail] Still here — second matchmaking attempt...")
        pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
        task.wait(20)
        -- If both failed: 279 dialog scanner will catch the visible dialog and handle it
        log("[TPFail] Both matchmaking attempts stalled — 279 dialog scanner will take over")
    end)
end
log("[TPFail] TeleportInitFailed early-intercept connected (with backoff)")

-- ==================== EVENT-DRIVEN ERROR INTERCEPT: GuiService + ErrorPrompt ====================
-- Two instant-detection layers that fire on ANY error without waiting for polling cycles.
-- These act as a safety net — if any specific monitor above missed the error, these catch it.

-- Layer 1: GuiService.ErrorMessageChanged — fires instantly when any error dialog appears
pcall(function()
    local GuiService = game:GetService("GuiService")
    GuiService.ErrorMessageChanged:Connect(function(msg)
        log("[GuiService] ErrorMessageChanged: " .. tostring(msg))
        if msg == "" then return end

        -- Don't interfere if a specific monitor is already handling
        task.wait(5)

        -- If we're still in the game after 5s and there's an error, force teleport
        if getgenv then getgenv().PD_HAS_QUEUED = false end
        pcall(function() queueFunc(_reconnectScript) end)

        -- Try clicking any visible button
        pcall(function()
            local cg = game:GetService("CoreGui")
            for _, btn in pairs(cg:GetDescendants()) do
                if btn:IsA("TextButton") then
                    local bt = string.lower(tostring(btn.Text or ""))
                    if bt == "reconnect" or bt == "retry" then
                        pcall(function() btn.MouseButton1Click:Fire() end)
                        pcall(function()
                            local vim = game:GetService("VirtualInputManager")
                            local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                            task.wait(0.05)
                            vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                        end)
                        break
                    end
                end
            end
        end)

        task.wait(10)
        -- If still here after clicking, force teleport
        log("[GuiService] Still here after button click — forcing teleport...")
        pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
    end)
    log("[GuiService] ErrorMessageChanged listener connected")
end)

-- Layer 2: CoreGui ErrorPrompt ChildAdded — fires when Roblox adds any error prompt
pcall(function()
    local cg = game:GetService("CoreGui")
    local promptGui = cg:WaitForChild("RobloxPromptGui", 10)
    if promptGui then
        local overlay = promptGui:WaitForChild("promptOverlay", 10)
        if overlay then
            overlay.ChildAdded:Connect(function(child)
                if child.Name ~= "ErrorPrompt" then return end
                log("[ErrorPrompt] ErrorPrompt appeared — waiting 6s for specific monitors...")

                -- Give specific monitors time to handle first
                task.wait(6)

                -- Safety net: queue script and force teleport if still here
                if getgenv then getgenv().PD_HAS_QUEUED = false end
                pcall(function() queueFunc(_reconnectScript) end)

                -- Click any available button
                pcall(function()
                    for _, btn in pairs(child:GetDescendants()) do
                        if btn:IsA("TextButton") then
                            local bt = string.lower(tostring(btn.Text or ""))
                            if bt == "reconnect" or bt == "retry" or bt == "leave" then
                                pcall(function() btn.MouseButton1Click:Fire() end)
                                pcall(function()
                                    local vim = game:GetService("VirtualInputManager")
                                    local pos = btn.AbsolutePosition + btn.AbsoluteSize / 2
                                    vim:SendMouseButtonEvent(pos.X, pos.Y, 0, true, game, 0)
                                    task.wait(0.05)
                                    vim:SendMouseButtonEvent(pos.X, pos.Y, 0, false, game, 0)
                                end)
                                break
                            end
                        end
                    end
                end)

                task.wait(10)
                log("[ErrorPrompt] Forcing teleport as safety net...")
                pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
            end)
            log("[ErrorPrompt] ChildAdded listener connected on promptOverlay")
        end
    end
end)

-- Layer 3: OnTeleport — ensure script is ALWAYS queued when any teleport starts
pcall(function()
    TeleportService:SetTeleportSetting("IsTeleporting", true)
    player.OnTeleport:Connect(function(state)
        if state == Enum.TeleportState.Started then
            if getgenv then getgenv().PD_HAS_QUEUED = false end
            pcall(function() queueFunc(_reconnectScript) end)
            log("[OnTeleport] Teleport started — script re-queued")
        elseif state == Enum.TeleportState.Failed then
            log("[OnTeleport] Teleport FAILED — will retry...")
            task.wait(5)
            pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
        end
    end)
    log("[OnTeleport] Player.OnTeleport listener connected")
end)

-- Forward declaration so moderator detection (below) and performMove can call serverHop
local serverHop

-- ==================== MODERATOR DETECTION ====================
-- Checks every player's rank in the official PLS DONATE group (Quataun, id=12121240).
-- Rank >= 254 = Owner / Co-Owner / Admin level → bot hops immediately.
-- Based on pattern from open-source PD bots (tzechco-PlsDonateAutofarmBackup).
do
    local modHopping = false
    local MOD_GROUP  = 12121240
    local MOD_RANK   = 254

    local function checkPlayer(p)
        if modHopping then return end
        local ok, rank = pcall(function()
            return p:GetRankInGroup(MOD_GROUP)
        end)
        if ok and rank and rank >= MOD_RANK then
            modHopping = true
            Stats.mods_met += 1
            log(string.format("[MOD] ⚠️ Moderator detected: %s (rank %d) — hopping server!", p.Name, rank))
            task.wait(1)
            serverHop()
        end
    end

    task.spawn(function()
        -- Wait until character is in game before scanning
        task.wait(15)
        while true do
            task.wait(1)
            if modHopping then task.wait(30); modHopping = false end
            pcall(function()
                for _, p in ipairs(Players:GetPlayers()) do
                    if p ~= player then
                        checkPlayer(p)
                    end
                end
            end)
        end
    end)

    -- Also check players who join mid-session
    Players.PlayerAdded:Connect(function(p)
        task.wait(3)  -- small delay so rank API is reliable
        checkPlayer(p)
    end)
end
log("[MOD] Moderator detection started (group=12121240, minRank=254)")

-- ==================== BOOTH CLAIMER ====================
-- Wait longer for UI to load after join (game can be slow)
local BOOTH_UI_WAIT = 12

local function getBoothLocation()
    local boothLocation = nil
    pcall(function()
        boothLocation = player:WaitForChild('PlayerGui', BOOTH_UI_WAIT)
            :WaitForChild('MapUIContainer', BOOTH_UI_WAIT)
            :WaitForChild('MapUI', BOOTH_UI_WAIT)
    end)
    if not boothLocation then
        boothLocation = workspace:WaitForChild('MapUI', BOOTH_UI_WAIT)
    end
    return boothLocation
end

-- includeAll: if true, return ALL unclaimed booths (no distance filter) so we always have a target
local function findUnclaimedBooths(boothLocation, includeAll)
    local unclaimed = {}
    local boothUI = boothLocation:WaitForChild("BoothUI", BOOTH_UI_WAIT)
    local interactions = workspace:WaitForChild("BoothInteractions", BOOTH_UI_WAIT)
    if not boothUI or not interactions then return unclaimed end
    local mainPos2D = Vector3.new(BOOTH_CHECK_POSITION.X, 0, BOOTH_CHECK_POSITION.Z)
    for _, uiFrame in ipairs(boothUI:GetChildren()) do
        if uiFrame:FindFirstChild("Details") and uiFrame.Details:FindFirstChild("Owner") then
            if uiFrame.Details.Owner.Text == "unclaimed" then
                local boothNum = tonumber(uiFrame.Name:match("%d+"))
                if boothNum then
                    for _, interact in ipairs(interactions:GetChildren()) do
                        if interact:GetAttribute("BoothSlot") == boothNum then
                            local pos2D = Vector3.new(interact.Position.X, 0, interact.Position.Z)
                            local distance = (pos2D - mainPos2D).Magnitude
                            if includeAll or distance < MAX_BOOTH_DISTANCE then
                                table.insert(unclaimed, {
                                    number = boothNum,
                                    position = interact.Position,
                                    cframe = interact.CFrame,
                                    distance = distance
                                })
                            end
                            break
                        end
                    end
                end
            end
        end
    end
    table.sort(unclaimed, function(a, b) return a.distance < b.distance end)
    return unclaimed
end

local function teleportTo(cframe)
    local root = player.Character:FindFirstChild("HumanoidRootPart")
    if root then
        root.CFrame = cframe
        task.wait(0.1)
    end
end

local function verifyClaim(boothLocation, boothNum)
    local boothUI = boothLocation.BoothUI or boothLocation:FindFirstChild("BoothUI")
    if not boothUI then return false end
    local boothFrame = boothUI:FindFirstChild("BoothUI" .. boothNum)
        or boothUI:FindFirstChild("BoothUI " .. boothNum)
    if not boothFrame then
        for _, f in ipairs(boothUI:GetChildren()) do
            if tonumber(f.Name:match("%d+")) == boothNum then
                boothFrame = f
                break
            end
        end
    end
    if not boothFrame then return false end
    local details = boothFrame:FindFirstChild("Details")
    if not details then return false end
    local owner = details:FindFirstChild("Owner")
    if not owner then return false end
    local ownerText = tostring(owner.Text or "")
    -- plain=true: имя может содержать Lua-pattern символы (. ( ) [ ] - + * ? ^ $ %)
    -- из-за чего поиск без plain=true мог ложно говорить "claim не прошёл" и
    -- приводить к бесконечной попытке re-claim уже взятой стойки.
    return string.find(ownerText, tostring(player.DisplayName or ""), 1, true) ~= nil
        or string.find(ownerText, tostring(player.Name or ""), 1, true) ~= nil
end

local function walkRandomDirection(studs, waitTime)
    local root = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
    local humanoid = player.Character and player.Character:FindFirstChild("Humanoid")
    if root and humanoid then
        local angle = math.random() * math.pi * 2
        local movePos = root.Position + Vector3.new(math.cos(angle)*studs, 0, math.sin(angle)*studs)
        humanoid:MoveTo(movePos)
        task.wait(waitTime)
    end
end

-- Alternative claim method 1: set HoldDuration = 0 so prompt triggers instantly (used by many PD scripts)
local function tryClaimViaPromptInstant(claimPrompt)
    local oldHold = nil
    pcall(function()
        if claimPrompt:IsA("ProximityPrompt") then
            oldHold = claimPrompt.HoldDuration
            claimPrompt.HoldDuration = 0
        end
    end)
    pcall(function() fireproximityprompt(claimPrompt) end)
    task.wait(1.5)
    pcall(function()
        if claimPrompt:IsA("ProximityPrompt") and oldHold ~= nil then
            claimPrompt.HoldDuration = oldHold
        end
    end)
end

-- Alternative claim method 2: try RemoteEvents (game may use Remotes for claim instead of/alongside ProximityPrompt)
local function tryClaimViaRemote(boothNum)
    local possibleNames = {"ClaimBooth", "Claim", "BoothClaim", "RequestBooth", "TakeBooth", "ClaimStand"}
    local containers = {}
    local events = ReplicatedStorage:FindFirstChild("Events")
    if events then table.insert(containers, events) end
    table.insert(containers, ReplicatedStorage)
    for _, container in ipairs(containers) do
        for _, name in ipairs(possibleNames) do
            local remote = container:FindFirstChild(name)
            if remote and (remote:IsA("RemoteEvent") or remote:IsA("RemoteFunction")) then
                local ok = pcall(function()
                    if remote:IsA("RemoteEvent") then
                        remote:FireServer(boothNum)
                    else
                        remote:InvokeServer(boothNum)
                    end
                end)
                if ok then
                    log("[BOOTH] Fired remote " .. name .. "(" .. tostring(boothNum) .. ")")
                end
            end
        end
    end
end

local claimedBoothNum = nil  -- set once per script session when booth is claimed

-- Safely get the world position of a booth interaction object (Part or Model)
local function getInteractPos(interact)
    local ok, pos = pcall(function()
        if interact:IsA("BasePart") then
            return interact.Position
        elseif interact.PrimaryPart then
            return interact.PrimaryPart.Position
        else
            return interact:GetPivot().Position
        end
    end)
    return ok and pos or nil
end

-- Check BoothUI to see if this player already owns a booth; returns position or nil
local function findOwnedBooth(boothLocation)
    local boothUI = boothLocation and (boothLocation.BoothUI or boothLocation:FindFirstChild("BoothUI"))
    if not boothUI then return nil end
    local interactions = workspace:FindFirstChild("BoothInteractions")
    if not interactions then return nil end
    local myName    = tostring(player.Name)
    local myDisplay = tostring(player.DisplayName)
    for _, uiFrame in ipairs(boothUI:GetChildren()) do
        if uiFrame:IsA("Frame") then
            local details = uiFrame:FindFirstChild("Details")
            local owner   = details and details:FindFirstChild("Owner")
            if owner then
                local txt = tostring(owner.Text or "")
                -- plain=true: no Lua pattern issues with special chars in names
                local isOwner = string.find(txt, myName, 1, true)
                               or string.find(txt, myDisplay, 1, true)
                if isOwner then
                    local boothNum = tonumber(uiFrame.Name:match("%d+"))
                    if boothNum then
                        for _, interact in ipairs(interactions:GetChildren()) do
                            if interact:GetAttribute("BoothSlot") == boothNum then
                                local pos = getInteractPos(interact)
                                if pos then
                                    log("[BOOTH] Already own booth #" .. boothNum .. " — reusing")
                                    claimedBoothNum = boothNum
                                    return Vector3.new(pos.X, pos.Y, pos.Z)
                                end
                            end
                        end
                    end
                end
            end
        end
    end
    return nil
end

local BOOTH_CLAIM_DEADLINE = nil  -- set on first call

local function claimBooth(retryCount)
    retryCount = retryCount or 0
    if not isActiveInstance() then
        log("[BOOTH] Не активный instance — выходим из claimBooth")
        return nil
    end
    -- Global deadline: max 180s total for booth claiming across all retries
    if retryCount == 0 then BOOTH_CLAIM_DEADLINE = tick() + 180 end
    if BOOTH_CLAIM_DEADLINE and tick() > BOOTH_CLAIM_DEADLINE then
        log("[BOOTH] ⏰ 180s deadline exceeded — skipping booth, will hop")
        return nil
    end
    log("=== BOOTH CLAIMER ===")

    -- Fast path: booth already claimed in this Lua session
    if claimedBoothNum then
        log("[BOOTH] Booth #" .. claimedBoothNum .. " already claimed this session — skipping")
        local boothLocation = getBoothLocation()
        if boothLocation then
            local existing = findOwnedBooth(boothLocation)
            if existing then return existing end
            -- claim was lost somehow (edge case) — fall through to re-claim
            claimedBoothNum = nil
            log("[BOOTH] Booth was lost — re-claiming...")
        end
    end

    local boothLocation = getBoothLocation()
    if not boothLocation then
        log("[BOOTH] ERROR: Could not find booth UI!")
        return nil
    end

    -- Double-check via UI scan
    local existing = findOwnedBooth(boothLocation)
    if existing then
        log("[BOOTH] Already own a booth — reusing it")
        return existing
    end

    local unclaimed = findUnclaimedBooths(boothLocation)
    if #unclaimed == 0 then
        unclaimed = findUnclaimedBooths(boothLocation, true)
        if #unclaimed > 0 then
            log("[BOOTH] No booths in range — using all unclaimed booths on map")
        end
    end
    log("[BOOTH] Found " .. #unclaimed .. " unclaimed booth(s)")
    
    if #unclaimed == 0 then
        log("[BOOTH] ERROR: No booths available!")
        return nil
    end
    
    -- Get BoothInteractions reference
    local boothInteractions = workspace:FindFirstChild("BoothInteractions")
    if not boothInteractions then
        log("[BOOTH] ERROR: BoothInteractions not found in Workspace!")
        return nil
    end
    
    -- Try each booth one by one
    for i, booth in ipairs(unclaimed) do
        if not isActiveInstance() then
            log("[BOOTH] Lost active flag mid-loop — abort claim")
            return nil
        end
        -- Before trying another booth: if we already own one, stop and use it (don't claim a second)
        local alreadyOwn = findOwnedBooth(boothLocation)
        if alreadyOwn then
            log("[BOOTH] Already own a booth — stopping, not claiming another")
            return alreadyOwn
        end

        -- Check deadline on every booth attempt
        if BOOTH_CLAIM_DEADLINE and tick() > BOOTH_CLAIM_DEADLINE then
            log("[BOOTH] ⏰ Deadline hit mid-loop — aborting, will hop")
            return nil
        end
        log("═══════════════════════════════════════")
        log("[BOOTH] Attempt " .. i .. "/" .. #unclaimed .. " - Trying Booth #" .. booth.number)
        
        -- Find the ProximityPrompt for THIS specific booth
        local myBoothInteraction = nil
        for _, interact in ipairs(boothInteractions:GetChildren()) do
            if interact:GetAttribute("BoothSlot") == booth.number then
                myBoothInteraction = interact
                break
            end
        end
        
        if not myBoothInteraction then
            log("[BOOTH] ERROR: Couldn't find interaction object for booth #" .. booth.number)
            continue
        end
        
        -- Find ProximityPrompt in this booth's interaction
        local claimPrompt = nil
        for _, child in ipairs(myBoothInteraction:GetChildren()) do
            if child:IsA("ProximityPrompt") and child.Name == "Claim" then
                claimPrompt = child
                break
            end
        end
        
        if not claimPrompt then
            log("[BOOTH] ERROR: No Claim ProximityPrompt found for booth #" .. booth.number)
            continue
        end
        
        local claimed = false
        local returnPos = nil
        
        -- Phase 1: ALWAYS try the fast method first (HoldDuration=0, ~1 sec claim) — several times before fallbacks
        log("[BOOTH] Phase 1: fast method (instant trigger) — up to 4 attempts")
        for attempt = 1, 4 do
            local targetCFrame = myBoothInteraction.CFrame * CFrame.new(0, 0, 2)
            teleportTo(targetCFrame)
            task.wait(0.8)
            tryClaimViaPromptInstant(claimPrompt)
            task.wait(2)
            claimed = verifyClaim(boothLocation, booth.number)
            if not claimed then
                task.wait(1)
                claimed = verifyClaim(boothLocation, booth.number)
            end
            if not claimed then
                local existing = findOwnedBooth(boothLocation)
                if existing then claimed = true; returnPos = existing end
            end
            if claimed then
                claimedBoothNum = booth.number
                log("╔═══════════════════════════════════════")
                log("║ [SUCCESS] CLAIMED BOOTH #" .. booth.number .. " (fast method)!")
                log("╚═══════════════════════════════════════")
                saveLog()
                return (returnPos or booth.position)
            end
            if attempt < 4 then log("[BOOTH] Fast method attempt " .. attempt .. " — retrying...") end
        end
        
        -- Phase 2: Fallback — RemoteEvent(s)
        log("[BOOTH] Phase 2: fallback remote(s)")
        for attempt = 1, 2 do
            teleportTo(myBoothInteraction.CFrame * CFrame.new(0, 0, 2))
            task.wait(0.5)
            tryClaimViaRemote(booth.number)
            task.wait(2)
            claimed = verifyClaim(boothLocation, booth.number)
            if not claimed then
                local existing = findOwnedBooth(boothLocation)
                if existing then claimed = true; returnPos = existing end
            end
            if claimed then
                if not claimedBoothNum then claimedBoothNum = booth.number end
                log("╔═══════════════════════════════════════")
                log("║ [SUCCESS] CLAIMED BOOTH #" .. booth.number .. " (remote)!")
                log("╚═══════════════════════════════════════")
                saveLog()
                return (returnPos or booth.position)
            end
        end
        
        -- Phase 3: Fallback — multi-fire ProximityPrompt (hold E style, slower)
        log("[BOOTH] Phase 3: fallback multi-fire prompt")
        for attempt = 1, 4 do
            teleportTo(myBoothInteraction.CFrame * CFrame.new(0, 0, 2))
            task.wait(0.8)
            for _ = 1, 5 do
                pcall(function() fireproximityprompt(claimPrompt) end)
                task.wait(0.35)
            end
            task.wait(4.5)
            for v = 1, 5 do
                claimed = verifyClaim(boothLocation, booth.number)
                if claimed then break end
                if v < 5 then task.wait(1.2) end
            end
            if not claimed then
                local existing = findOwnedBooth(boothLocation)
                if existing then claimed = true; returnPos = existing end
            end
            if claimed then
                claimedBoothNum = booth.number
                log("╔═══════════════════════════════════════")
                log("║ [SUCCESS] CLAIMED BOOTH #" .. booth.number .. " (multi-fire)!")
                log("╚═══════════════════════════════════════")
                saveLog()
                return (returnPos or booth.position)
            end
            if attempt < 4 then log("[BOOTH] Multi-fire attempt " .. attempt .. " — retrying...") end
        end
        
        log("[BOOTH] All methods failed for this booth, moving to next...")
        walkRandomDirection(20, 2)
        log("[BOOTH] Moving to next booth...")
    end
    
    log("[BOOTH] All booths tried, moving away before retrying...")
    walkRandomDirection(30, 3)
    retryCount = (retryCount or 0) + 1
    if retryCount >= 5 then
        log("[BOOTH] ⚠️ Failed after 5 full cycles — will hop to another server")
        return nil
    end
    log("[BOOTH] Retrying from start (cycle " .. retryCount .. "/5)...")
    return claimBooth(retryCount)
end

-- ── Startup server viability check ───────────────────────────────────────────
-- Skip booth claim entirely if the server has too few players.
-- This prevents wasting 180s on an empty server arrived via matchmaking.
do
    task.wait(3)  -- give PlayerList a moment to populate after join
    local startupCount = #Players:GetPlayers()
    local currentJobId = tostring(game.JobId)
    if startupCount < MIN_PLAYERS then
        log(string.format("[STARTUP] Only %d players (min=%d) — server too empty, hopping now!", startupCount, MIN_PLAYERS))
        local RELOAD = [[
local httprequest = (syn and syn.request) or http and http.request or http_request or (fluxus and fluxus.request) or request
local response = httprequest({Url = "]] .. SCRIPT_URL .. [["})
if response and response.Body then loadstring(response.Body)()
else loadstring(game:HttpGet("]] .. SCRIPT_URL .. [["))() end
]]
        queueFunc(RELOAD)
        pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
        task.wait(5)
        pcall(function() player:Kick("Joining better server...") end)
        task.wait(60)
    end
    log(string.format("[STARTUP] Server OK: %d players — proceeding", startupCount))
end

-- Give BoothUI/MapUI time to load after join before claiming
log("[BOOTH] Waiting 5s for booth UI to load...")
task.wait(5)

-- CLAIM BOOTH AND SET HOME POSITION
local HOME_POSITION = claimBooth()
if not HOME_POSITION then
    log("[BOOTH] Failed to claim booth! Hopping to another server (no begging without booth).")
    pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
    return  -- teleport will trigger queued script on new server
end
log("=== HOME SET TO: " .. tostring(HOME_POSITION) .. " ===")
saveLog()

-- ==================== BOOTH POSITION SYNC ====================
-- Periodically refreshes HOME_POSITION from BoothUI in case the position
-- shifted. Does NOT re-claim — booth is claimed exactly once at startup.
task.spawn(function()
    task.wait(30)
    while isActiveInstance() do
        task.wait(30)
        if not isActiveInstance() then break end
        pcall(function()
            local boothLocation = getBoothLocation()
            if not boothLocation then return end
            local existing = findOwnedBooth(boothLocation)
            if existing then
                HOME_POSITION = existing
            end
            -- Note: if findOwnedBooth returns nil we do nothing —
            -- the BoothUI may not have loaded yet; we trust claimedBoothNum.
        end)
    end
end)

-- ==================== SOCIAL BOT LOGIC ====================
-- ========= CHAT LOGGER + RESPONSE DETECTION =========
local lastSpeaker = nil
local lastMessage = nil
local responseReceived = false

local function resetResponse()
    lastSpeaker = nil
    lastMessage = nil
    responseReceived = false
end

-- Shared handler: runs on every chat message from any player
local function onAnyChat(speakerName, msgLower)
    if speakerName == player.Name then return end
    -- Response detection (for active waitForResponse)
    lastSpeaker      = speakerName
    lastMessage      = msgLower
    responseReceived = true
    -- Mention detection: did they write our name?
    local myNameLow     = string.lower(player.Name)
    local myDisplayLow  = string.lower(player.DisplayName)
    if string.find(msgLower, myNameLow, 1, true)
    or (myDisplayLow ~= myNameLow and string.find(msgLower, myDisplayLow, 1, true)) then
        onMentioned(speakerName)
    end
end

-- Hook Legacy Chat
spawn(function()
    local legacy = ReplicatedStorage:WaitForChild("DefaultChatSystemChatEvents", 5)
    if legacy then
        local ev = legacy:FindFirstChild("OnMessageDoneFiltering")
        if ev then
            ev.OnClientEvent:Connect(function(data)
                local speaker = data.FromSpeaker
                local msg = (data.Message or data.OriginalMessage or ""):lower()
                log(speaker .. ": " .. msg)
                onAnyChat(speaker, msg)
            end)
        end
    end
end)

-- Hook TextChatService
spawn(function()
    if TextChatService.ChatVersion == Enum.ChatVersion.TextChatService then
        local channels = TextChatService:WaitForChild("TextChannels", 10)
        if channels then
            local function hook(ch)
                if ch:IsA("TextChannel") then
                    ch.MessageReceived:Connect(function(msgObj)
                        local source = msgObj.TextSource
                        if source then
                            local speaker = source.Name
                            local text = (msgObj.Text or ""):lower()
                            log(speaker .. ": " .. text)
                            onAnyChat(speaker, text)
                        end
                    end)
                end
            end
            for _, ch in pairs(channels:GetChildren()) do hook(ch) end
            channels.ChildAdded:Connect(hook)
        end
    end
end)

-- Your own chat (just in case)
player.Chatted:Connect(function(msg)
    log(player.Name .. ": " .. msg)
end)

-- ========= MOVEMENT & DANCE =========
local DIRECTION_KEYS = {
    {Enum.KeyCode.W}, {Enum.KeyCode.W, Enum.KeyCode.D}, {Enum.KeyCode.D},
    {Enum.KeyCode.D, Enum.KeyCode.S}, {Enum.KeyCode.S}, {Enum.KeyCode.S, Enum.KeyCode.A},
    {Enum.KeyCode.A}, {Enum.KeyCode.A, Enum.KeyCode.W},
}

local function startCircleDance(duration)
    log("[CIRCLE] Starting circle dance...")
    VirtualInputManager:SendKeyEvent(true, Enum.KeyCode.Space, false, game)
    local startTime = tick()
    local step = 1
    task.spawn(function()
        while tick() - startTime < duration do
            for _, k in DIRECTION_KEYS[step] do VirtualInputManager:SendKeyEvent(true, k, false, game) end
            task.wait(CIRCLE_STEP_TIME)
            for _, k in DIRECTION_KEYS[step] do VirtualInputManager:SendKeyEvent(false, k, false, game) end
            step = step % 8 + 1
        end
        VirtualInputManager:SendKeyEvent(false, Enum.KeyCode.Space, false, game)
        log("[CIRCLE] Done")
    end)
end

-- Wait with anti-AFK movement (circle dance every 10 seconds)
local function waitWithMovement(duration)
    local elapsed = 0
    while elapsed < duration do
        local waitTime = math.min(10, duration - elapsed)
        task.wait(waitTime)
        elapsed = elapsed + waitTime
        
        -- Do a quick circle dance if we have more time to wait
        if elapsed < duration then
            startCircleDance(3)
            task.wait(3)
            elapsed = elapsed + 3
        end
    end
end

local isSprinting = false

-- serverHop forward-declared above (before moderator detection block)

local function startSprinting()
    if isSprinting then return end
    VirtualInputManager:SendKeyEvent(true, SPRINT_KEY, false, game)
    isSprinting = true
end

local function stopSprinting()
    if not isSprinting then return end
    VirtualInputManager:SendKeyEvent(false, SPRINT_KEY, false, game)
    isSprinting = false
end

-- FIXED performMove & chasePlayer to handle target disappearing mid-chase
local function performMove(humanoid, root, getPos, sprint)
    if sprint then startSprinting() end
    local lastPos   = root.Position
    local stuckTime = 0
    local jumpTries = 0
    local randTries = 0
    local moveStart = tick()  -- total move timeout

    while true do
        task.wait(0.1)
        -- Hard timeout: give up chasing after 60 seconds to avoid infinite loops
        if tick() - moveStart > 60 then
            log("[MOVE] Chase timeout (60s) — giving up on target")
            if sprint then stopSprinting() end
            return false
        end
        local pos = getPos()
        if not pos then  -- Target lost mid-move
            log("[MOVE] Target lost mid-chase! Stopping movement.")
            if sprint then stopSprinting() end
            return false
        end
        if (root.Position - pos).Magnitude <= TARGET_DISTANCE then
            if sprint then stopSprinting() end
            -- Reset stuck counter on successful movement
            consecutiveStuckCount = 0
            return true
        end

        humanoid:MoveTo(pos)
        local moved = (root.Position - lastPos).Magnitude
        if moved < STUCK_THRESHOLD then 
            stuckTime += 0.1 
        else 
            stuckTime = 0
            lastPos = root.Position 
        end

        if stuckTime >= STUCK_CHECK_TIME then
            if jumpTries < MAX_JUMP_TRIES then
                jumpTries += 1
                log("[ANTI-STUCK] Jump unstuck #"..jumpTries)
                VirtualInputManager:SendKeyEvent(true, Enum.KeyCode.Space, false, game)
                task.wait(JUMP_DURATION)
                VirtualInputManager:SendKeyEvent(false, Enum.KeyCode.Space, false, game)
                task.wait(0.5)
            else
                randTries += 1
                log("[ANTI-STUCK] Random dodge #"..randTries)
                local a = math.random() * math.pi * 2
                local dodge = pos + Vector3.new(math.cos(a)*80, 0, math.sin(a)*80)
                humanoid:MoveTo(dodge)
                task.wait(3)
                if randTries >= MAX_RANDOM_TRIES then
                    log("[ANTI-STUCK] Failed to unstuck after all attempts!")
                    consecutiveStuckCount = consecutiveStuckCount + 1
                    log("[ANTI-STUCK] Consecutive stuck count: " .. consecutiveStuckCount .. "/" .. MAX_STUCK_BEFORE_HOP)
                    
                    if consecutiveStuckCount >= MAX_STUCK_BEFORE_HOP then
                        log("[ANTI-STUCK] Too many stuck failures! Initiating server hop...")
                        log("[ANTI-STUCK] Saving log before hop...")
                        pcall(saveLog)  -- Use pcall in case it errors
                        log("[ANTI-STUCK] Stopping sprint...")
                        if sprint then stopSprinting() end
                        log("[ANTI-STUCK] Calling serverHop(true) now...")
                        -- Don't return! Let serverHop's infinite loop take over
                        serverHop(true)
                        -- Should never reach here since serverHop never returns
                        log("[ANTI-STUCK] ERROR: serverHop returned unexpectedly!")
                        return false
                    end
                    
                    if sprint then stopSprinting() end
                    return false
                end
            end
            stuckTime = 0
            lastPos = root.Position
        end
    end
end

local function chasePlayer(t)
    if not t.Character or not t.Character:FindFirstChild("HumanoidRootPart") then return false end
    if not player.Character then player.CharacterAdded:Wait(); task.wait(2) end
    local h = player.Character:FindFirstChild("Humanoid")
    local r = player.Character:FindFirstChild("HumanoidRootPart")
    if not h or not r then return false end
    log("[CHASE] Going to " .. t.Name .. " (approaching from front)")

    local function safeGetPos()
        local targetHRP = t.Character and t.Character:FindFirstChild("HumanoidRootPart")
        if not targetHRP then return nil end
        -- Aim for a position 4 studs in front of the target's face
        return targetHRP.Position + targetHRP.CFrame.LookVector * 4
    end

    return performMove(h, r, safeGetPos, true)
end

local function returnHome()
    if not player.Character then player.CharacterAdded:Wait(); task.wait(2) end
    local h = player.Character:FindFirstChild("Humanoid")
    local r = player.Character:FindFirstChild("HumanoidRootPart")
    if not h or not r then return false end
    log("[HOME] Returning home...")
    return performMove(h, r, function() return HOME_POSITION end, false)
end

local function faceTargetBriefly(t)
    if not player.Character or not t.Character or not t.Character:FindFirstChild("HumanoidRootPart") then return end
    local hrp = player.Character:FindFirstChild("HumanoidRootPart")
    if not hrp then return end
    local p = t.Character.HumanoidRootPart.Position
    local look = Vector3.new(p.X, hrp.Position.Y, p.Z)
    hrp.CFrame = CFrame.new(hrp.Position, look)
end

-- ==================== PERSONALITY (deterministic by UserId) ====================
-- Each account gets a stable "personality" that controls chat style, intervals, etc.
-- This is THE main anti-detect lever: 50 bots stop looking like 50 clones.
local PERSONA = (function()
    local seed = 0
    local uid  = tostring(player.UserId or "0")
    for i = 1, #uid do seed = (seed * 31 + string.byte(uid, i)) % 2147483647 end
    local rng = Random.new(seed)
    local function r(lo, hi) return lo + rng:NextNumber() * (hi - lo) end
    return {
        chat_speed_mult       = r(0.7, 1.5),    -- typing-delay multiplier
        emoji_chance          = r(0.05, 0.35),  -- chance to add emoji
        typo_chance           = r(0.04, 0.16),  -- chance to introduce typo
        cap_drop_chance       = r(0.10, 0.40),  -- chance to lowercase msg
        punc_drop_chance      = r(0.20, 0.55),  -- chance to drop terminal !?.
        ellipsis_chance       = r(0.05, 0.20),  -- chance to add ... at end
        mention_resp_chance   = r(0.85, 0.95),  -- ~5-15% silently ignored per-bot
        mention_min_delay     = r(0.8, 1.8),    -- short, still slower than 0.4s tell
        mention_max_delay     = r(2.5, 4.5),
        silence_period_min    = r(55 * 60, 80 * 60),   -- rare: 55-80 min floor
        silence_period_max    = r(95 * 60, 130 * 60),  -- 95-130 min ceiling
        silence_dur_min       = r(60, 120),     -- short break: 1-2 min floor
        silence_dur_max       = r(150, 240),    -- 2.5-4 min ceiling
        prefer_short          = rng:NextNumber() < 0.5,
        seed                  = seed,
    }
end)()

-- ==================== SILENT MODE (random AFK windows) ====================
-- Real humans don't beg every 10 seconds for hours. Bot goes silent for several
-- minutes, randomly. While silent: chat is dropped, idle wander runs, that's it.
local SILENT_MODE = false
task.spawn(function()
    -- Initial wait so bots don't all silence at the same script-startup mark
    task.wait(math.random(120, 600))
    while true do
        local activeFor = math.random(
            math.floor(PERSONA.silence_period_min),
            math.floor(PERSONA.silence_period_max))
        task.wait(activeFor)
        local silentFor = math.random(
            math.floor(PERSONA.silence_dur_min),
            math.floor(PERSONA.silence_dur_max))
        SILENT_MODE = true
        task.wait(silentFor)
        SILENT_MODE = false
    end
end)

-- ==================== HUMANIZER ====================
-- Mutates outgoing chat: random typos, capitalisation, punctuation, emoji.
-- Each bot's mutation rates are pinned to PERSONA so it stays consistent
-- per-account (a bot that drops emojis isn't suddenly emoji-spamming).
local CHAT_EMOJIS = {":)", ":D", " :)", " :D", " lol", " ngl", " fr", " :(", " 😭", " 🥺", " ✨", ""}
local NEAR_KEY = {
    a = "sq", s = "ad", d = "sf", f = "dg", g = "fh", h = "gj", j = "hk",
    k = "jl", l = "k", q = "wa", w = "qe", e = "wr", r = "et", t = "ry",
    y = "tu", u = "yi", i = "uo", o = "ip", p = "ol", z = "x", x = "zc",
    c = "xv", v = "cb", b = "vn", n = "bm", m = "n",
}

local function maybeTypo(s)
    if math.random() >= PERSONA.typo_chance then return s end
    if #s < 4 then return s end
    -- pick a random alpha char and either swap with neighbour, drop a letter,
    -- or replace with adjacent key
    local chars = {}
    for i = 1, #s do chars[i] = s:sub(i, i) end
    local idx = math.random(2, #chars - 1)
    local roll = math.random(3)
    if roll == 1 then
        -- swap with next
        chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
    elseif roll == 2 then
        -- drop one letter
        table.remove(chars, idx)
    else
        -- replace with adjacent qwerty key
        local lower = chars[idx]:lower()
        local repl  = NEAR_KEY[lower]
        if repl then
            local newCh = repl:sub(math.random(#repl), math.random(#repl))
            if chars[idx]:match("[A-Z]") then newCh = newCh:upper() end
            chars[idx] = newCh
        end
    end
    return table.concat(chars)
end

local function maybeLower(s)
    if math.random() < PERSONA.cap_drop_chance then return s:lower() end
    return s
end

local function maybeDropPunc(s)
    if math.random() < PERSONA.punc_drop_chance then
        return (s:gsub("[%.!%?]+%s*$", ""))
    end
    return s
end

local function maybeEllipsis(s)
    if math.random() < PERSONA.ellipsis_chance then
        if not s:match("[%.!%?]$") and not s:match("%.%.%.$") then
            return s .. "..."
        end
    end
    return s
end

local function maybeEmoji(s)
    if math.random() < PERSONA.emoji_chance then
        local e = CHAT_EMOJIS[math.random(#CHAT_EMOJIS)]
        if e ~= "" and not s:find(e:gsub("^%s+", ""), 1, true) then
            return s .. e
        end
    end
    return s
end

local function humanize(msg)
    if type(msg) ~= "string" or msg == "" then return msg end
    local out = msg
    out = maybeTypo(out)
    out = maybeLower(out)
    out = maybeDropPunc(out)
    out = maybeEllipsis(out)
    out = maybeEmoji(out)
    -- Trim trailing/leading spaces that may have been introduced
    out = out:gsub("^%s+", ""):gsub("%s+$", "")
    if out == "" then return msg end
    return out
end

local function sendChat(msg)
    -- Drop chat during silence windows (bot stays in-game but quiet)
    if SILENT_MODE then return end
    msg = humanize(msg)
    -- Make chat non-blocking to prevent hangs from SendAsync
    task.spawn(function()
        if TextChatService.ChatVersion == Enum.ChatVersion.TextChatService then
            local ch = TextChatService.TextChannels.RBXGeneral
            if ch then pcall(function() ch:SendAsync(msg) end) end
        end
        local say = ReplicatedStorage:FindFirstChild("DefaultChatSystemChatEvents")
                    and ReplicatedStorage.DefaultChatSystemChatEvents:FindFirstChild("SayMessageRequest")
        if say then pcall(function() say:FireServer(msg, "All") end) end
    end)
end

-- Count words in a string
local function countWords(s)
    local count = 1
    for _ in s:gmatch("%s+") do count = count + 1 end
    return count
end

-- Send chat with typing delay (simulates human typing speed)
local function sendChatTyped(msg)
    if SILENT_MODE then return end
    local words = countWords(msg)
    local delay
    if words <= 3 then
        delay = math.random() * 0.3 + 0.5   -- 0.5–0.8s
    elseif words <= 8 then
        delay = math.random() * 0.8 + 1.0   -- 1.0–1.8s
    else
        delay = math.random() * 1.0 + 2.0   -- 2.0–3.0s
    end
    -- per-bot speed: some bots type faster, some slower
    delay = delay * PERSONA.chat_speed_mult
    task.wait(delay)
    sendChat(msg)
end

-- Occasional natural movement between targets (no dance)
local function doIdleAction()
    local roll = math.random()
    if roll < 0.12 then
        -- short jump
        VirtualInputManager:SendKeyEvent(true, Enum.KeyCode.Space, false, game)
        task.wait(0.3)
        VirtualInputManager:SendKeyEvent(false, Enum.KeyCode.Space, false, game)
    elseif roll < 0.18 then
        -- brief pause
        task.wait(math.random() * 0.8 + 0.3)
    end
end

-- ========= MENTION SYSTEM =========
-- If someone writes the bot's name in chat, bot replies quickly and approaches them
local mentionQueue   = {}  -- { [userId] = true }
local mentionReplyCd = {}  -- { [userId] = tick() } per-player cooldown

-- Big pool of varied replies. Splits intentionally short/medium/long so the
-- distribution of reply lengths varies between accounts (PERSONA.prefer_short).
local MENTION_REPLIES_SHORT = {
    "yeah?", "hi!", "yes?", "hey!", "yea?", "yo", "huh?", "ya?",
    "sup", "hm?", "?", "yh?", "what", "hii", "hey hey",
}
local MENTION_REPLIES_MED = {
    "u called?", "what's up", "yeah what's up", "oh hey!", "yes?",
    "you talking to me?", "wsg", "u talking to me?", "im here",
    "what u need", "yeah you", "huh whats up", "yo yes", "im listening",
    "whats good", "you say something?",
}
local MENTION_REPLIES_LONG = {
    "yeah whats up lol", "oh hi yeah whats good", "you talkin to me lol",
    "yeah im here whats up", "huh you said my name?",
    "wait did u call me lol", "yeah whats good", "oh me? whats up",
    "hi yeah?", "im here lol whats up",
}

local function pickMentionReply()
    local pools
    if PERSONA.prefer_short then
        pools = { MENTION_REPLIES_SHORT, MENTION_REPLIES_SHORT, MENTION_REPLIES_MED }
    else
        pools = { MENTION_REPLIES_MED, MENTION_REPLIES_LONG, MENTION_REPLIES_SHORT }
    end
    local pool = pools[math.random(#pools)]
    return pool[math.random(#pool)]
end

local function onMentioned(speakerName)
    if speakerName == player.Name then return end
    if SILENT_MODE then return end
    local mentioned = nil
    for _, p in ipairs(Players:GetPlayers()) do
        if p.Name == speakerName then mentioned = p; break end
    end
    if not mentioned then return end
    local uid = mentioned.UserId
    -- Per-player cooldown, randomised so two consecutive mentions don't trigger
    -- exactly 30.0s apart (a tell-tale machine number).
    local now = tick()
    local cdLimit = 25 + math.random() * 20  -- 25-45s
    if mentionReplyCd[uid] and now - mentionReplyCd[uid] < cdLimit then return end
    mentionReplyCd[uid] = now

    -- Small chance to silently ignore (5-15% per-bot). Real players occasionally
    -- miss a mention or just don't respond. Bots that ALWAYS answer = pattern.
    if math.random() > PERSONA.mention_resp_chance then
        log("[MENTION] " .. speakerName .. " — skipping reply (rare ignore)")
        -- Still queue for approach so the lead isn't wasted
        mentionQueue[uid] = true
        ignoreList[uid]   = nil
        return
    end

    -- Prioritise this player for next approach
    mentionQueue[uid] = true
    ignoreList[uid]   = nil
    log("[MENTION] " .. speakerName .. " mentioned bot — queued + replying")

    -- Short, still-randomised delay (~1-4s). Instant 0.4s replies look bot-like;
    -- 1-4s reads as "saw it on screen, typed a quick reply" — natural enough.
    task.spawn(function()
        local d = math.random() * (PERSONA.mention_max_delay - PERSONA.mention_min_delay)
                + PERSONA.mention_min_delay
        task.wait(d)
        if SILENT_MODE then return end
        sendChat(pickMentionReply())
    end)
end

local function findClosest()
    if not player.Character then return nil end
    local root = player.Character:FindFirstChild("HumanoidRootPart")
    if not root then return nil end
    local allPlayers = Players:GetPlayers()
    if not allPlayers then return nil end

    -- Priority: players who mentioned the bot by name
    for uid, _ in pairs(mentionQueue) do
        for _, p in ipairs(allPlayers) do
            if p.UserId == uid and p ~= player and not BOT_ACCOUNTS[p.Name]
               and p.Character and p.Character:FindFirstChild("HumanoidRootPart") then
                mentionQueue[uid] = nil
                log(string.format("[FIND] Priority target (mentioned bot): %s", p.Name))
                return p
            end
        end
        mentionQueue[uid] = nil  -- player left, clean up
    end

    -- Normal: closest player not in ignoreList
    local best, bestDist = nil, math.huge
    for _, p in ipairs(allPlayers) do
        if p ~= player
            and p.UserId
            and not ignoreList[p.UserId]
            and not BOT_ACCOUNTS[p.Name]
            and p.Character
        then
            local hrp = p.Character:FindFirstChild("HumanoidRootPart")
            if hrp then
                local dist = (hrp.Position - root.Position).Magnitude
                if dist < bestDist then
                    bestDist = dist
                    best = p
                end
            end
        end
    end
    if best then
        log(string.format("[FIND] Closest: %s (%.1f studs)", best.Name, bestDist))
    end
    return best
end

-- ========= MESSAGE WITH TYPO CHANCE =========
-- Forward decl: real definition is in BEG PHRASE COMBINATOR section below.
local genBegPhrase
local function getRandomMessage()
    -- 50% generated on the fly via combinator (unique strings every time),
    -- 50% from the static MESSAGES pool (with original typo variants).
    if math.random() < 0.5 then
        local cats = {"empty", "low", "mid", "rich"}
        return genBegPhrase(cats[math.random(#cats)])
    end
    local msgIndex = math.random(#MESSAGES)
    if math.random() < TYPO_CHANCE then
        if msgIndex <= #MESSAGE_TYPOS then
            return MESSAGE_TYPOS[msgIndex][math.random(3)]
        else
            local extraIdx = msgIndex - #MESSAGE_TYPOS
            if MESSAGE_TYPOS_EXTRA and MESSAGE_TYPOS_EXTRA[extraIdx] then
                return MESSAGE_TYPOS_EXTRA[extraIdx][math.random(3)]
            end
        end
    end
    return MESSAGES[msgIndex]
end

-- ========= CONTEXT-AWARE FIRST MESSAGE =========

-- Read the Raised amount from a target player's booth (from our own PlayerGui copy of the BoothUI)
local function getPlayerRaised(t)
    local ok, result = pcall(function()
        local gui = player.PlayerGui
        local mc = gui:FindFirstChild("MapUIContainer") or workspace:FindFirstChild("MapUIContainer")
        if not mc then return nil end
        local mapUI = mc:FindFirstChild("MapUI")
        if not mapUI then return nil end
        local bui = mapUI:FindFirstChild("BoothUI")
        if not bui then return nil end
        local tName    = tostring(t.Name)
        local tDisplay = tostring(t.DisplayName)
        for _, frame in ipairs(bui:GetChildren()) do
            local det   = frame:FindFirstChild("Details")
            local owner = det and det:FindFirstChild("Owner")
            if owner then
                local txt = tostring(owner.Text or "")
                if string.find(txt, tName, 1, true) or string.find(txt, tDisplay, 1, true) then
                    local raised = det:FindFirstChild("Raised")
                    if raised then
                        local num = tostring(raised.Text or "0"):split(" ")[1]:gsub(",", "")
                        return tonumber(num) or 0
                    end
                end
            end
        end
        return nil
    end)
    return ok and result or nil
end

local function getMsgCategory(raised)
    if raised == nil or raised == 0 then return "empty" end
    if raised <= 500  then return "low"   end
    if raised <= 2000 then return "mid"   end
    return "rich"
end

-- ==================== BEG PHRASE COMBINATOR ====================
-- Built fresh each call from small word-list parts. Keeps the wire
-- distribution of strings huge so detectors that hash full phrases
-- against known-bot pools see a constant churn of unseen lines.
local _gen_open = {
    empty = {"hey", "hi", "yo", "umm", "hmm", "psst", "hii", "ay", "heyy"},
    low   = {"hey", "hi", "yo", "bro", "dude", "ay"},
    mid   = {"yo", "hey", "hi", "ngl"},
    rich  = {"yo", "ngl", "damn", "wow", "ok"},
}
local _gen_hook = {
    empty = {
        "im just starting", "got nothing yet", "im so broke",
        "0 raised rn", "literally 0 r$", "no donations yet",
        "tryna start", "i need r$", "im new",
    },
    low   = {
        "we both grinding", "we both low", "we tryna save",
        "we both startin", "we in the same boat", "i need a boost",
        "tryna catch up", "small goal pls",
    },
    mid   = {
        "u doing well", "ur booth lookin good", "u got donations",
        "u know the grind", "u got some saved",
    },
    rich  = {
        "ur rich", "u loaded", "ur booth doing great",
        "u got heaps", "ur raised insane", "u got so much",
    },
}
local _gen_ask = {
    "donate?", "donate pls", "spare some?", "help me out?",
    "any robux?", "share some?", "donate ty", "donate plz",
    "could u donate?", "spare a lil?", "donate pls?",
    "any donation works", "even 5 r$ helps", "help?",
}
local _gen_tail = {
    "", "", "", "lol", "ty", "fr", "pls", "ngl", ":)", "lmao", "tysm",
}

local function _pick(t) return t[math.random(#t)] end

genBegPhrase = function(cat)
    local opens = _gen_open[cat] or _gen_open.empty
    local hooks = _gen_hook[cat] or _gen_hook.empty
    local parts = {}
    -- 60% include opener
    if math.random() < 0.6 then table.insert(parts, _pick(opens)) end
    -- 75% include hook
    if math.random() < 0.75 then table.insert(parts, _pick(hooks)) end
    -- always include the ask
    table.insert(parts, _pick(_gen_ask))
    -- 40% include tail
    if math.random() < 0.4 then
        local t = _pick(_gen_tail)
        if t ~= "" then table.insert(parts, t) end
    end
    return table.concat(parts, " ")
end

-- 35% chance to include player's name in message (varied prefixes)
local function addName(msg, t)
    if math.random(20) <= 7 then
        local prefixes = {"hey " .. t.Name .. " ", t.Name .. " ", "yo " .. t.Name .. " "}
        return prefixes[math.random(#prefixes)] .. msg
    end
    return msg
end

-- Build the opening donation request (context-aware pool + optional dream-item line)
local function getFirstMsg(t)
    local raised = getPlayerRaised(t)
    local cat    = getMsgCategory(raised)

    -- Dream-item line appears ~25% of the time instead of pool message
    local useDreamLine = math.random(4) == 1
    local pool
    if cat == "empty" then pool = MSGS_EMPTY
    elseif cat == "low" then pool = MSGS_LOW
    elseif cat == "mid" then pool = MSGS_MID
    else                     pool = MSGS_RICH
    end

    local base
    if leavingSoon and math.random(2) == 1 then
        base = MSGS_LEAVING[math.random(#MSGS_LEAVING)]
    elseif useDreamLine then
        local dreamLines = {
            "saving up for " .. dreamItem.name .. " donate pls",
            "trying to get " .. dreamItem.name .. " any help appreciated",
            "so close to getting " .. dreamItem.name .. " help me out?",
            "want " .. dreamItem.name .. " so bad, any donation helps",
            "tryna save for " .. dreamItem.name .. " donate?",
            "goal is " .. dreamItem.name .. " pls donate",
            "need r$ for " .. dreamItem.name .. " help?",
            "grinding for " .. dreamItem.name .. " any robux helps",
        }
        base = dreamLines[math.random(#dreamLines)]
    else
        -- Mix combinator with fixed pool — half the lines are unique generated
        -- strings so detectors that signature on the public pool see a moving target.
        if math.random() < 0.5 then
            base = genBegPhrase(cat)
        else
            base = pool[math.random(#pool)]
        end
    end

    return addName(base, t)
end

-- ========= MAIN LOGIC WITH CHAT RESPONSE =========
local function nextPlayer()
    local target = findClosest()
    if not target then
        log("[MAIN] Everyone greeted — going home")
        returnHome()
        return false
    end

    log("[MAIN] Target → " .. target.Name)
    lastActivityTime = tick()  -- bot is actively working

    doIdleAction()

    if chasePlayer(target) then
        -- Compliment first, then donation ask that naturally follows (no re-greeting)
        local compliment = COMPLIMENTS[math.random(#COMPLIMENTS)]
        sendChatTyped(compliment)
        task.wait(math.random() * 0.6 + 1.2)   -- 1.2–1.8s pause

        -- 25% chance: dream-item line; otherwise post-compliment ask or leavingSoon
        local openingMsg
        if leavingSoon and math.random(2) == 1 then
            openingMsg = MSGS_LEAVING[math.random(#MSGS_LEAVING)]
        elseif math.random(4) == 1 then
            local dreamLines = {
                "ngl saving for " .. dreamItem.name .. " could u donate?",
                "btw trying to get " .. dreamItem.name .. " help me out?",
                "also.. want " .. dreamItem.name .. " so bad donate pls lol",
                "tryna save for " .. dreamItem.name .. " any robux?",
                "goal is " .. dreamItem.name .. " donate pls",
                "need r$ for " .. dreamItem.name .. " spare some?",
                "grinding for " .. dreamItem.name .. " could u help?",
            }
            openingMsg = dreamLines[math.random(#dreamLines)]
        else
            openingMsg = MSGS_POST_COMPLIMENT[math.random(#MSGS_POST_COMPLIMENT)]
        end
        -- 30% chance: prefix with player's name for personal touch
        if math.random(10) <= 3 then
            openingMsg = target.Name .. " " .. openingMsg
        end

        sendChatTyped(openingMsg)
        Stats.approached += 1
        lastBeggingTime = tick()
        leavingSoon = false
        -- Brief 2s face-and-follow before waiting for reply
        do
            local elapsed = 0
            while elapsed < 2 do
                task.wait(0.2)
                elapsed += 0.2
                faceTargetBriefly(target)
                local r = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
                local tr = target.Character and target.Character:FindFirstChild("HumanoidRootPart")
                local h = player.Character and player.Character:FindFirstChild("Humanoid")
                if r and tr and h then
                    local fp = Vector3.new(
                        (tr.Position + tr.CFrame.LookVector * 2).X,
                        tr.Position.Y,
                        (tr.Position + tr.CFrame.LookVector * 2).Z)
                    if (r.Position - fp).Magnitude > 3 then h:MoveTo(fp) end
                end
            end
        end

        -- ── Wait for response helper ──────────────────────────────
        -- Bot ALWAYS follows the target for the full wait duration (sprint + stuck recovery).
        -- Only returns "left" if the character actually disappears (quit / respawned).
        local function waitForResponse(waitTime)
            resetResponse()
            local start = tick()
            startSprinting()
            local lastDist = 9999
            local stuckFollowTime = 0
            local FOLLOW_STUCK_SEC = 2.5
            -- Smart match: single-char words must be entire message; longer = substring
            local function matches(text, word)
                if #word <= 1 then
                    return text:match("^%s*" .. word .. "%s*$") ~= nil
                end
                return text:find(word, 1, true) ~= nil
            end
            while tick() - start < waitTime do
                -- Check if player actually left the game
                if not target.Character or not target.Character:FindFirstChild("HumanoidRootPart") then
                    log("[WAIT] Target left the game")
                    stopSprinting()
                    return "left", ""
                end
                local root       = player.Character and player.Character:FindFirstChild("HumanoidRootPart")
                local targetRoot = target.Character:FindFirstChild("HumanoidRootPart")
                local humanoid   = player.Character and player.Character:FindFirstChild("Humanoid")
                if root and targetRoot and humanoid then
                    local dist = (root.Position - targetRoot.Position).Magnitude
                    if dist > 80 then
                        log("[WAIT] Target unreachable (>80 studs) — giving up")
                        stopSprinting()
                        return "left", ""
                    end
                    -- Chase: stay 2 studs in front of player's face — always move if > 4 studs so we keep following
                    local frontPos = Vector3.new(
                        (targetRoot.Position + targetRoot.CFrame.LookVector * 2).X,
                        targetRoot.Position.Y,
                        (targetRoot.Position + targetRoot.CFrame.LookVector * 2).Z)
                    if (root.Position - frontPos).Magnitude > 4 then
                        humanoid:MoveTo(frontPos)
                    end
                    faceTargetBriefly(target)
                    
                    -- Stuck detection: not getting closer for FOLLOW_STUCK_SEC
                    if dist >= lastDist - 0.5 then
                        stuckFollowTime = stuckFollowTime + 0.2
                    else
                        stuckFollowTime = 0
                    end
                    lastDist = dist
                    
                    if stuckFollowTime >= FOLLOW_STUCK_SEC then
                        stuckFollowTime = 0
                        -- 1) Jump several times
                        for _ = 1, 4 do
                            VirtualInputManager:SendKeyEvent(true, Enum.KeyCode.Space, false, game)
                            task.wait(0.25)
                            VirtualInputManager:SendKeyEvent(false, Enum.KeyCode.Space, false, game)
                            task.wait(0.2)
                        end
                        task.wait(0.5)
                        local stillStuck = root and targetRoot and (root.Position - targetRoot.Position).Magnitude > 8
                        if stillStuck then
                            -- 2) Random dodge then back to target
                            local a = math.random() * math.pi * 2
                            local dodgePos = targetRoot.Position + Vector3.new(math.cos(a)*15, 0, math.sin(a)*15)
                            humanoid:MoveTo(dodgePos)
                            task.wait(1.5)
                        end
                        stillStuck = root and targetRoot and (root.Position - targetRoot.Position).Magnitude > 10
                        if stillStuck then
                            -- 3) Teleport near target (5 studs in front)
                            pcall(function()
                                root.CFrame = targetRoot.CFrame * CFrame.new(0, 0, 5)
                                task.wait(0.2)
                            end)
                            log("[WAIT] Unstuck: teleported near " .. target.Name)
                        end
                    end
                end
                if responseReceived and lastSpeaker == target.Name then
                    local msg = lastMessage
                    lastActivityTime = tick()
                    log("[RESPONSE] " .. target.Name .. " said: " .. msg)
                    local saidYes = false
                    for _, word in ipairs(YES_LIST) do
                        if matches(msg, word) then saidYes = true; break end
                    end
                    local saidNo = false
                    for _, word in ipairs(NO_LIST) do
                        if matches(msg, word) then saidNo = true; break end
                    end
                    if saidYes then stopSprinting(); return "yes", msg end
                    if saidNo  then stopSprinting(); return "no",  msg end
                end
                task.wait(0.2)
            end
            stopSprinting()
            return "timeout", ""
        end
        -- ─────────────────────────────────────────────────────────

        log("[WAIT] Waiting " .. WAIT_FOR_ANSWER_TIME .. "s for " .. target.Name .. "'s reply...")
        local result, playerReply = waitForResponse(WAIT_FOR_ANSWER_TIME)

        if result == "yes" then
            -- ── Agreed ──
            sendChat(MSG_FOLLOW_ME)
            -- Refresh HOME_POSITION from BoothUI before guiding the player there.
            pcall(function()
                local boothLocation = getBoothLocation()
                if not boothLocation then return end
                local existing = findOwnedBooth(boothLocation)
                if existing then HOME_POSITION = existing end
            end)
            returnHome()
            sendChat(MSG_HERE_IS_HOUSE)
            ignoreList[target.UserId] = true
            Stats.agreed += 1
            refusalStreak = 0
            logInteraction(target.Name, openingMsg, playerReply, "agreed")
            task.wait(2)
            return true

        elseif result == "no" then
            -- ── Refused ──
            sendChat(MSG_OK_FINE_POOL[math.random(#MSG_OK_FINE_POOL)])
            task.wait(math.random() * 0.7 + 0.8)

            -- 30% chance: guilt-trip second message (no wait — just write and walk away)
            if math.random() < SECOND_ATTEMPT_CHANCE then
                local attempt2 = MSGS_SECOND[math.random(#MSGS_SECOND)]
                sendChatTyped(attempt2)
                log("[RETRY] Guilt-trip: " .. attempt2)
                task.wait(0.5)
                logInteraction(target.Name,
                    openingMsg .. " → [refused] → " .. attempt2,
                    playerReply, "refused")
            else
                logInteraction(target.Name, openingMsg, playerReply, "refused")
            end

            -- 60% chance: dignified goodbye
            if math.random() < 0.60 then
                task.wait(0.5)
                sendChatTyped(MSGS_GOODBYE[math.random(#MSGS_GOODBYE)])
            end

            ignoreList[target.UserId] = true
            Stats.refused += 1
            refusalStreak += 1
            if refusalStreak >= FRUSTRATION_THRESHOLD then
                task.wait(1)
                sendChat(FRUSTRATION_MSGS[math.random(#FRUSTRATION_MSGS)])
                log("[FRUSTRATION] " .. refusalStreak .. " refusals in a row!")
            end
            task.wait(1)
            return true

        else
            -- ── No response / left ──
            local noRespMsg = NO_RESPONSE_MSGS[math.random(#NO_RESPONSE_MSGS)]
            sendChatTyped(noRespMsg)
            -- 60% chance: goodbye (only if they didn't physically leave)
            if result ~= "left" and math.random() < 0.60 then
                task.wait(0.5)
                sendChatTyped(MSGS_GOODBYE[math.random(#MSGS_GOODBYE)])
            end
            log("[WAIT] No valid reply from " .. target.Name .. " — moving on")
            ignoreList[target.UserId] = true
            Stats.no_response += 1
            refusalStreak += 1
            logInteraction(target.Name, openingMsg, "",
                result == "left" and "left" or "no_response")
            if refusalStreak >= FRUSTRATION_THRESHOLD then
                task.wait(1)
                sendChat(FRUSTRATION_MSGS[math.random(#FRUSTRATION_MSGS)])
                log("[FRUSTRATION] " .. refusalStreak .. " refusals/no-responses in a row!")
            end
        end
    else
        -- Chase failed (player moved away / unreachable)
        logInteraction(target.Name, "", "", "chase_fail")
        ignoreList[target.UserId] = true
    end

    task.wait(1)
    return true
end

-- ==================== SERVER HOP FUNCTION ====================
function serverHop(skipReturnHome)
    lastActivityTime = tick()
    lastBeggingTime  = tick()
    Stats.hops += 1
    log("[HOP] Starting server hop...")

    -- Pre-queue the script so it auto-starts after rejoin/teleport
    local RELOAD_CODE = [[
local httprequest = (syn and syn.request) or http and http.request or http_request or (fluxus and fluxus.request) or request
local response = httprequest({Url = "]] .. SCRIPT_URL .. [["})
if response and response.Body then loadstring(response.Body)()
else loadstring(game:HttpGet("]] .. SCRIPT_URL .. [["))() end
]]
    queueFunc(RELOAD_CODE)

    -- Go home if not stuck
    if not skipReturnHome then
        pcall(returnHome)
        task.wait(1)
    end

    -- Hop lock: max 2 bots hop at the same time from one IP (rate-limit prevention)
    if DASH_URL ~= "" then
        local lockWaited = 0
        while lockWaited < 300 do
            local lockOk, lockResp = pcall(function()
                return httprequest({
                    Url     = DASH_URL .. "/pd_hop_acquire",
                    Method  = "POST",
                    Headers = {["Content-Type"] = "application/json"},
                    Body    = HttpService:JSONEncode({id = tostring(player.UserId)}),
                })
            end)
            if not lockOk or not lockResp or lockResp.StatusCode ~= 200 then
                log("[HOP] Hop lock unreachable — proceeding without lock")
                break
            end
            local parseOk, lockData = pcall(function() return HttpService:JSONDecode(lockResp.Body) end)
            if parseOk and lockData and lockData.ok then
                log(string.format("[HOP] Hop lock acquired (%d active)", lockData.active or 1))
                break
            end
            local waitFor = (parseOk and lockData and lockData.wait) or 20
            log(string.format("[HOP] Hop locked (%d active) — waiting %ds...",
                (parseOk and lockData and lockData.active) or 0, waitFor))
            task.wait(waitFor)
            lockWaited += waitFor
        end
    end

    -- Stagger so multiple bots on same IP don't hit API at the exact same millisecond
    local stagger = math.random(3, 15)
    log("[HOP] Stagger " .. stagger .. "s...")
    waitWithMovement(stagger)

    -- Re-fetch config (cooldown/min/max may have changed from dashboard)
    fetchDashConfig()

    -- Load visited servers list and mark current server as visited
    local visited = loadVisited()
    visited = pruneVisited(visited, SERVER_COOLDOWN_MINS)
    visited[tostring(game.JobId)] = tick()  -- mark current as visited
    saveVisited(visited)
    log(string.format("[HOP] Visited server list: %d entries (cooldown=%dmin)",
        (function() local n=0 for _ in pairs(visited) do n=n+1 end return n end)(),
        SERVER_COOLDOWN_MINS))

    -- Mark current server as "just left" so we don't rejoin it for 5 min
    local justLeft = loadJustLeft()
    justLeft[tostring(game.JobId)] = tick()
    saveJustLeft(justLeft)
    log("[HOP] Current server added to just-left list (5 min exclusion)")

    -- ── Step 1: ONE API call to find a populated server ──────────────────────
    -- Excludes: current server, recently visited, servers with our bots already.
    local occupied = fetchOccupiedServers()

    local foundServer = nil
    local apiOk, apiResp = pcall(function()
        return httprequest({
            Url = string.format(
                "https://games.roblox.com/v1/games/%d/servers/Public?sortOrder=Desc&limit=100&excludeFullGames=true",
                PLACE_ID
            )
        })
    end)

    if apiOk and apiResp and apiResp.StatusCode == 200 and apiResp.Body then
        local parseOk, body = pcall(function() return HttpService:JSONDecode(apiResp.Body) end)
        if parseOk and body and body.data then
            local candidates = {}
            for _, s in ipairs(body.data) do
                if type(s) == "table" and s.id
                   and s.id ~= tostring(game.JobId)                        -- not current
                   and not wasVisited(visited, s.id, SERVER_COOLDOWN_MINS)  -- not recently visited
                   and not wasJustLeft(justLeft, s.id)                     -- not server we just left
                   and not occupied[tostring(s.id)]                         -- no other bot there
                   and tonumber(s.playing) and tonumber(s.playing) >= MIN_PLAYERS
                   and tonumber(s.playing) <= MAX_PLAYERS_ALLOWED then
                    table.insert(candidates, s)
                end
            end
            if #candidates > 0 then
                -- Pick randomly from top-5 candidates so bots don't all pile into same server
                table.sort(candidates, function(a, b) return (a.playing or 0) > (b.playing or 0) end)
                local pickFrom = math.min(5, #candidates)
                foundServer = candidates[math.random(pickFrom)]
                log(string.format("[HOP] %d candidates (bot-free), picked server with %d players",
                    #candidates, foundServer.playing or 0))
            else
                log("[HOP] API: no suitable bot-free servers found — using matchmaking")
            end
        end
    elseif apiOk and apiResp then
        log("[HOP] API status " .. tostring(apiResp.StatusCode) .. " — skipping to direct teleport")
    else
        log("[HOP] API call failed — skipping to direct teleport")
    end

    -- ── Step 2: Teleport ─────────────────────────────────────────────────────
    local teleported = false

    -- Check if TeleportToPlaceInstance has been causing repeated 279s recently.
    -- If 2+ failures in the last 5 minutes, skip specific-server teleport entirely
    -- and fall straight through to matchmaking (which never 279s).
    local recentFails = 0
    if getgenv then
        local f = getgenv().PD_279_RECENT or 0
        local t = getgenv().PD_279_LAST_T or 0
        if tick() - t < 300 then recentFails = f end  -- only count failures in last 5 min
    end
    local skip279Server = (recentFails >= 2)
    if skip279Server then
        log(string.format("[HOP] %d recent 279 failures — skipping TeleportToPlaceInstance, using matchmaking directly", recentFails))
    end

    -- Release hop lock NOW so next waiting bot can start immediately
    -- (must happen before any teleport since teleport = instant game leave)
    pcall(function()
        httprequest({
            Url     = DASH_URL .. "/pd_hop_release",
            Method  = "POST",
            Headers = {["Content-Type"] = "application/json"},
            Body    = HttpService:JSONEncode({id = tostring(player.UserId)}),
        })
    end)
    log("[HOP] Hop lock released")

    if foundServer and not skip279Server then
        -- Try TeleportToPlaceInstance (specific populated server)
        local tpOk = pcall(function()
            TeleportService:TeleportToPlaceInstance(PLACE_ID, foundServer.id, player)
        end)
        if tpOk then
            log("[HOP] TeleportToPlaceInstance initiated — waiting 12s...")
            waitWithMovement(12)
            log("[HOP] TeleportToPlaceInstance didn't fire, using direct teleport")
        else
            log("[HOP] TeleportToPlaceInstance failed, using direct teleport")
        end
    end

    -- Direct teleport (Roblox matchmaking picks server)
    log("[HOP] ⚡ Direct teleport to random server via matchmaking...")
    pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
    task.wait(15)
    -- Second attempt with backoff (rate-limit recovery)
    log("[HOP] Still here — second matchmaking attempt (30s backoff)...")
    task.wait(30)
    pcall(function() TeleportService:Teleport(PLACE_ID, player) end)
    task.wait(45)
    -- If all teleport attempts stalled, 279 dialog scanner will handle the visible dialog.
    log("[HOP] All teleport attempts stalled — 279 scanner active")
    task.wait(60)
end

-- ==================== DONATION MONITOR ====================
-- Tries three methods in order, uses the first one that works.
-- No double-counting: only one method runs at a time.
--
-- Method 1 (best): leaderstats.Raised.Changed  — event-driven, instant, exact delta
-- Method 2 (good): ChatDonationAlert RemoteEvent — event-driven, gives tipper info
-- Method 3 (fallback): BoothUI Raised text polling — works even without leaderstats

local function onDonation(delta, source)
    if delta <= 0 then return end
    Stats.donations   += 1
    Stats.robux_gross += delta
    log(string.format(
        "[DONATE/%s] +R$%d | Session total: R$%d gross / R$%d net | %d donations",
        source, delta, Stats.robux_gross, math.floor(Stats.robux_gross * 0.6), Stats.donations))
end

local function monitorDonations()
    task.spawn(function()
        local tracked = false

        -- ── METHOD 1: leaderstats.Raised (WaitForChild, best) ─────────────
        -- Sets Stats.raised_current immediately at startup (e.g. 85 R$)
        -- and updates it on every donation. No FindFirstChild races.
        pcall(function()
            local ls = player:WaitForChild("leaderstats", 25)
            if not ls then log("[DONATE] leaderstats missing"); return end
            local rs = ls:WaitForChild("Raised", 15)
            if not rs then log("[DONATE] leaderstats.Raised missing"); return end

            -- ★ Set the absolute current value right away
            Stats.raised_current = tonumber(rs.Value) or 0
            log(string.format("[DONATE] Method 1 active: leaderstats.Raised = R$%d", Stats.raised_current))

            local last = rs.Value
            rs.Changed:Connect(function(newVal)
                Stats.raised_current = tonumber(newVal) or 0  -- keep in sync
                onDonation(newVal - last, "LS")
                last = newVal
            end)
            tracked = true
        end)
        if tracked then return end

        -- ── METHOD 2: ChatDonationAlert RemoteEvent ────────────────────────
        -- Doesn't give us starting balance, but catches new donations.
        -- Also reads initial balance from BoothUI text as fallback for raised_current.
        pcall(function()
            local Events = ReplicatedStorage:WaitForChild("Events", 15)
            if not Events then return end
            local alertEvent = Events:WaitForChild("ChatDonationAlert", 10)
            if not alertEvent then return end
            alertEvent.OnClientEvent:Connect(function(tipper, receiver, amount)
                local isUs = (type(receiver) == "string")
                    and (receiver == player.Name or receiver == player.DisplayName)
                    or (receiver == player)
                local tipName = (type(tipper) == "string" and tipper)
                             or (typeof(tipper) == "Instance" and tipper.Name) or "?"
                if isUs then
                    local amt = tonumber(amount) or 0
                    Stats.raised_current += amt
                    onDonation(amt, "CDA:" .. tipName)
                    -- Queue for deferred thank-you approach (2–3 min later)
                    recentDonors[tipName] = {ts = os.time(), thanked = false}
                else
                    -- Someone else received a donation — react with congrats (max once/30s)
                    local now = os.time()
                    if now - lastCongratTs >= 30 then
                        lastCongratTs = now
                        local CONGRATS = {
                            "omg congrats!! 🎉",
                            "yoo nice donation!! 🎉",
                            "aww that's so sweet 💙",
                            "goals fr 🔥",
                            "love to see it!! 🎉",
                        }
                        task.spawn(function()
                            task.wait(math.random(5, 20) / 10)
                            sendChat(CONGRATS[math.random(#CONGRATS)])
                        end)
                    end
                end
            end)
            tracked = true
            log("[DONATE] Method 2: ChatDonationAlert RemoteEvent")
        end)
        -- Method 2 doesn't stop fallback — also launch BoothUI for initial value
        -- (even if ChatDonationAlert works we still need the starting balance)
        task.spawn(function()
            pcall(function()
                local boothUI = player.PlayerGui
                    :WaitForChild("MapUIContainer", 20)
                    :WaitForChild("MapUI", 15)
                    :WaitForChild("BoothUI", 15)
                if not boothUI then return end
                local ourBooth
                for _ = 1, 40 do
                    for _, v in ipairs(boothUI:GetChildren()) do
                        local det = v:FindFirstChild("Details")
                        if det and det:FindFirstChild("Owner") then
                            local ownerName = det.Owner.Text:split("'")[1]
                            if ownerName == player.DisplayName or ownerName == player.Name then
                                ourBooth = v; break
                            end
                        end
                    end
                    if ourBooth then break end
                    task.wait(1)
                end
                if not ourBooth then log("[DONATE] BoothUI: our booth not found"); return end

                local function readRaised()
                    local txt = ourBooth.Details.Raised.Text or "0"
                    return tonumber(txt:split(" ")[1]:gsub(",", "")) or 0
                end

                -- ★ Capture starting balance from BoothUI right away
                local initVal = readRaised()
                if Stats.raised_current == 0 and initVal > 0 then
                    Stats.raised_current = initVal
                    log(string.format("[DONATE] raised_current from BoothUI: R$%d", initVal))
                end

                if not tracked then
                    -- Use BoothUI polling as primary donation detection
                    local last = initVal
                    tracked = true
                    log(string.format("[DONATE] Method 3: BoothUI polling (current: R$%d)", last))
                    while true do
                        task.wait(5)
                        local ok, cur = pcall(readRaised)
                        if ok then
                            Stats.raised_current = cur
                            onDonation(cur - last, "UI")
                            last = cur
                        end
                    end
                else
                    -- Method 1 or 2 already active — just keep raised_current synced from UI
                    while true do
                        task.wait(10)
                        local ok, cur = pcall(readRaised)
                        if ok and cur > Stats.raised_current then
                            Stats.raised_current = cur
                        end
                    end
                end
            end)
        end)

        if not tracked then
            log("[DONATE] All methods failed — donation tracking disabled")
        end
    end)
end

-- ==================== DASHBOARD REPORTING ====================
local function startReporting()
    if DASH_URL == "" then return end
    task.spawn(function()
        local consecutiveFails = 0
        while true do
            local logSnapshot = interactionLog
            interactionLog = {}

            local ok, err = pcall(function()
                local body = HttpService:JSONEncode({
                    id              = tostring(player.UserId),
                    name            = player.Name,
                    approached      = Stats.approached,
                    agreed          = Stats.agreed,
                    refused         = Stats.refused,
                    no_response     = Stats.no_response,
                    hops            = Stats.hops,
                    mods_met        = Stats.mods_met,
                    donations       = Stats.donations,
                    robux_gross     = Stats.robux_gross,
                    raised_current  = Stats.raised_current,
                    status          = "Active",
                    job_id          = tostring(game.JobId),
                    session_start   = sessionStart,
                    interactions    = logSnapshot,
                })
                local resp = request({
                    Url     = DASH_URL .. "/pd_update",
                    Method  = "POST",
                    Headers = {["Content-Type"] = "application/json"},
                    Body    = body,
                })
                -- Treat non-2xx as failure so we know the server rejected it
                if resp and resp.StatusCode and resp.StatusCode >= 300 then
                    error("HTTP " .. tostring(resp.StatusCode))
                end
            end)

            if ok then
                if consecutiveFails > 0 then
                    log("[REPORT] ✅ Dashboard reconnected after " .. consecutiveFails .. " failed reports")
                end
                consecutiveFails = 0
            else
                consecutiveFails += 1
                -- Log every 6th fail (~30 seconds) so console isn't spammed
                if consecutiveFails == 1 or consecutiveFails % 6 == 0 then
                    log("[REPORT] ⚠️ Dashboard unreachable (x" .. consecutiveFails .. "): " .. tostring(err))
                    log("[REPORT] URL: " .. DASH_URL)
                end
                -- Return undelivered interactions to buffer so they're not lost
                for _, entry in ipairs(logSnapshot) do
                    table.insert(interactionLog, entry)
                end
            end

            task.wait(5)
        end
    end)
end

-- ========= NEW PLAYER DETECTION =========
-- When a new player joins mid-session, remove them from ignoreList so the bot
-- will approach them in the next nextPlayer() cycle.
Players.PlayerAdded:Connect(function(newPlayer)
    task.wait(3)  -- Wait for character to load
    if ignoreList[newPlayer.UserId] then
        ignoreList[newPlayer.UserId] = nil
        log("[NEW] Removed " .. newPlayer.Name .. " from ignoreList (new arrival)")
    else
        log("[NEW] Player joined: " .. newPlayer.Name)
    end
end)

-- ========= START =========
log("=== SOCIAL GREETER BOT – ULTIMATE EDITION ===")
log("=== AUTO BOOTH CLAIM + SERVER HOP ===")
if not player.Character or not player.Character:FindFirstChild("HumanoidRootPart") then
    player.CharacterAdded:Wait()
    task.wait(2)
end

monitorDonations()
startReporting()

-- ── Watchdog: if bot hasn't actually begged in N minutes, force server hop ──
-- Hop interval randomised per-bot (8-15 min) so 50 bots aren't all hopping
-- on the same 3-minute clock — that pattern shows up in the game telemetry.
task.spawn(function()
    local BEG_IDLE_LIMIT  = math.random(240, 420)  -- 4-7 min, randomised
    local LEAVING_WARN_AT = BEG_IDLE_LIMIT - math.random(45, 90)
    log(string.format("[WATCHDOG] Hop after %ds idle (warn at %ds)", BEG_IDLE_LIMIT, LEAVING_WARN_AT))
    task.wait(60)
    while isActiveInstance() do
        task.wait(30)
        if not isActiveInstance() then break end
        local sinceLastBeg = tick() - lastBeggingTime
        if sinceLastBeg > LEAVING_WARN_AT and not leavingSoon then
            leavingSoon = true
            log(string.format("[WATCHDOG] Idle %.0fs — leavingSoon enabled", sinceLastBeg))
        end
        if sinceLastBeg > BEG_IDLE_LIMIT then
            leavingSoon = false
            log(string.format("[WATCHDOG] No begging for %.0fs — force hopping!", sinceLastBeg))
            serverHop(true)
        end
    end
    log("[SINGLETON] Watchdog exiting (new instance took over)")
end)

-- ── Thank-you loop: approach donors 2–3 min after they donated ──
task.spawn(function()
    while isActiveInstance() do
        task.wait(30)
        if not isActiveInstance() then break end
        local now = os.time()
        for tipName, info in pairs(recentDonors) do
            if not info.thanked and (now - info.ts) >= math.random(120, 180) then
                -- Find the donor on this server
                local donor = nil
                for _, p in ipairs(Players:GetPlayers()) do
                    if p.Name == tipName or p.DisplayName == tipName then
                        donor = p; break
                    end
                end
                if donor and donor.Character and donor.Character:FindFirstChild("HumanoidRootPart") then
                    info.thanked = true
                    task.spawn(function()
                        log("[THANKS] Going to thank " .. tipName)
                        if chasePlayer(donor) then
                            local msg = MSGS_THANKS[math.random(#MSGS_THANKS)]
                            sendChatTyped(msg)
                            logInteraction(tipName, msg, "", "thanked")
                        end
                    end)
                elseif (now - info.ts) > 300 then
                    recentDonors[tipName] = nil  -- donor left or 5min passed
                end
            end
        end
    end
end)

-- Main loop: greet everyone, then wait for new arrivals before hopping
-- Wrapped in pcall so Luau runtime errors never kill the script — it just retries
local _mainLoopCrashes = 0
while isActiveInstance() do
    local mainOk, mainErr = pcall(function()
        while isActiveInstance() do
            while isActiveInstance() and nextPlayer() do end

            if not isActiveInstance() then
                log("[SINGLETON] New instance detected — this instance is exiting")
                break
            end

            log("[MAIN] Everyone greeted! Waiting 2s for new arrivals...")
            returnHome()
            local waitStart = tick()
            local gotNewPlayer = false
            while tick() - waitStart < 2 do
                if not isActiveInstance() then break end
                if findClosest() then
                    gotNewPlayer = true
                    break
                end
                task.wait(0.5)
            end

            if not isActiveInstance() then
                log("[SINGLETON] New instance detected — this instance is exiting")
                break
            end

            if gotNewPlayer then
                log("[MAIN] New players found, continuing greeting loop...")
            else
                log("[MAIN] No new players in 20s — initiating server hop...")
                serverHop()
            end
        end
    end)

    if not mainOk then
        _mainLoopCrashes += 1
        log("[MAIN] Runtime error #" .. _mainLoopCrashes .. ": " .. tostring(mainErr))

        if _mainLoopCrashes >= 10 then
            log("[MAIN] Too many crashes (" .. _mainLoopCrashes .. ") — hopping to fresh server...")
            pcall(function()
                if getgenv then getgenv().PD_HAS_QUEUED = false end
                pcall(function() queueFunc(_reconnectScript) end)
                TeleportService:Teleport(PLACE_ID, player)
            end)
            task.wait(15)
        end

        task.wait(3)
    end
end