"""
bot_brain.py — Server-side bot state machine for Please Donate bot.

All decision logic, message pools, and conversation flow live here.
The Lua client is a thin executor that only reads game state and performs
physical actions (walk, chat, interact). It contains zero bot logic.
"""

import random
import time
import threading

# ── Message pools ──────────────────────────────────────────────────────────

MESSAGES = [
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
]

MESSAGE_TYPOS = [
    ["hry! donate pls? :)", "hey! dinate pls? :)", "hey! donate pld? :)"],
    ["hi! csn u donate?", "hi! can u dknate?", "hi! can u donatw?"],
    ["hrllo! donation? :D", "hello! donatiob? :D", "hello! donatipn? :D"],
    ["heu donate maybe?", "hey dontae maybe?", "hey donate maybr?"],
    ["hi! pks donate im trying to save up", "hi! pls donsre im trying to save up", "hi! pls donate im tryinf to save up"],
    ["heyy anu donations?", "heyy any donatiins?", "heyy any donatuons?"],
    ["hrllo donate pls", "hello dinate pls", "hello donate pld"],
    ["hi! hwlp me out? any robux appreciated", "hi! help me oit? any robux appreciated", "hi! help me out? any robix appreciated"],
    ["hry! donate? :)", "hey! dinate? :)", "hey! donatr? :)"],
    ["hii pks donate ty", "hii pls dknate ty", "hii pls donate ry"],
    ["hry can u donate im close to my goal", "hey csn u donate im close to my goal", "hey can u donsre im close to my goal"],
    ["hrllo! robux pls?", "hello! robix pls?", "hello! robux pld?"],
    ["hi dinate pls :D", "hi donate pld :D", "hi donate pla :D"],
    ["heyy donatiom? would mean a lot", "heyy donation? woulf mean a lot", "heyy donatiin? would mean a lot"],
    ["hry! pls help", "hey! pld help", "hey! pls hwlp"],
    ["hi! any robix? trying to get something cool", "hi! any robux? tryinf to get something cool", "hi! any robux? trying to grt something cool"],
    ["hrllo donate ty", "hello dknate ty", "hello donate ry"],
    ["hry! can u help? even small amount helps", "hey! csn u help? even small amount helps", "hey! can u hwlp? even small amount helps"],
    ["hi pld donate :)", "hi pls dknate :)", "hi pls donate :0"],
    ["heyy robix pls", "hryy robux pls", "heyy robux pld"],
    ["hry donate? ty appreciate it", "hey dknate? ty appreciate it", "hey donate? ty apprexiate it"],
    ["hi! hwlp pls", "hi! help pld", "hi! gelp pls"],
    ["hrllo donation pls working towards smth", "hello donatiom pls working towards smth", "hello donation pls workibg towards smth"],
    ["hry! donate ty :D", "hey! dknate ty :D", "hey! donate ry :D"],
    ["hi csn u donate?", "hi can u dinate?", "hi can u donatw?"],
    ["heyy pld help out any amount works", "hryy pls help out any amount works", "heyy pls hwlp out any amount works"],
    ["hry donate pls :)", "hey dknate pls :)", "hey donate pld :)"],
    ["hi! any donatioms? been grinding all day", "hi! any donations? bren grinding all day", "hi! any donations? been grindibg all day"],
    ["hrllo robux pls", "hello robix pls", "hello robux pld"],
    ["hry! pls donate", "hey! pld donate", "hey! pls dknate"],
]

MESSAGE_TYPOS_EXTRA = [
    ["pld donate me", "pls dinate me", "pls donate ne"],
    ["any robix? pls", "any robux? pld", "any robux? pls"],
    ["dinate plz ty", "donate plz ry", "donate plx ty"],
    ["tryinf to save for something donate?", "trying to save for somethibg donate?", "trying to save for something dinate?"],
    ["need robux fr can u hwlp", "need robix fr can u help", "need robux fr csn u help"],
    ["spare some r$?", "spare sme r$?", "spare some r$?"],
    ["could use a donatiom ngl", "could use a donation ngl", "could use a donaton ngl"],
    ["any donation helps fr", "any donatiom helps fr", "any donation hwlps fr"],
    ["donate if u can :)", "dinate if u can :)", "donate if u csn :)"],
    ["broke rn donate pls lol", "broke rn dinate pls lol", "broke rn donate pld lol"],
    ["pls donate even 1 helps", "pld donate even 1 helps", "pls dinate even 1 helps"],
    ["hey dinate ty", "hey donate ry", "hry donate ty"],
    ["anyone donate?", "anyone dinate?", "anyone donate?"],
    ["donations appreciated", "donatioms appreciated", "donations apprexiated"],
    ["yo dinate pls", "yo donate pld", "yo donate pls"],
    ["hi im tryna save up donate?", "hi im tryna save up dinate?", "hi im tryna sav eup donate?"],
    ["donate pls trying to get a gamepass", "dinate pls trying to get a gamepass", "donate pld trying to get a gamepass"],
    ["hey could u spare any?", "hry could u spare any?", "hey could u spare any?"],
    ["any r$ helps pls", "any r$ hwlps pls", "any r$ helps pld"],
    ["pls donate for my goal", "pld donate for my goal", "pls dinate for my goal"],
    ["donate? would mean sm", "dinate? would mean sm", "donate? woulf mean sm"],
    ["hi need some robux pls", "hi need some robix pls", "hi need sme robux pls"],
    ["hey any amount works", "hry any amount works", "hey any amouny works"],
    ["donate pls im poor lol", "dinate pls im poor lol", "donate pld im poor lol"],
    ["trying to reach my goal donate?", "tryinf to reach my goal donate?", "trying to reach my goal dinate?"],
    ["yo anyone wanna donate", "yo anyone wann donate", "yo anyone wanna dinate"],
    ["pls donate me ty", "pld donate me ty", "pls dinate me ty"],
    ["could u donate? tryna save", "could u dinate? tryna save", "could u donate? tryna sav e"],
    ["donate pls :(", "dinate pls :(", "donate pld :("],
    ["hey spare some robux?", "hry spare some robux?", "hey spare some robix?"],
    ["any donations? pls", "any donatioms? pls", "any donations? pld"],
]

YES_LIST = [
    "yes", "yeah", "yep", "yea", "ya", "yh", "sure", "ok", "okay", "k",
    "bet", "aight", "alright", "fine", "of course", "why not", "ight", "ig",
    "follow", "come", "lead", "lets go", "go", "show me", "where", "lets",
    "ill donate", "im donating", "sure thing", "no problem",
]

NO_LIST = [
    "no", "nope", "nah", "naur", "n", "pass", "busy", "not now", "not rn",
    "no ty", "no thx", "no thanks", "no thank", "nty", "nah ty",
    "leave", "stop", "go away", "gtfo", "dont", "don't", "never",
    "no way", "im good", "i'm good", "leave me",
]

MSGS_EMPTY = [
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
]

MSGS_LOW = [
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
]

MSGS_MID = [
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
]

MSGS_RICH = [
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
]

MSGS_LEAVING = [
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
]

COMPLIMENTS = [
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
]

MSGS_POST_COMPLIMENT = [
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
]

MSGS_SECOND = [
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
]

MSGS_GOODBYE = [
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
]

MSGS_THANKS = [
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
]

NO_RESPONSE_MSGS = [
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
]

FRUSTRATION_MSGS = [
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
]

MSG_FOLLOW_ME    = "follow me!"
MSG_HERE_IS_HOUSE = "here is my booth!"

DREAM_ITEMS = [
    {"name": "this cute hat i saw",    "price": 50},
    {"name": "a hoodie i want",        "price": 100},
    {"name": "this jacket i rly want", "price": 50},
    {"name": "a ugc hat i found",      "price": 100},
    {"name": "this fit i saw",         "price": 50},
    {"name": "a beanie i want",        "price": 10},
    {"name": "this cool shirt",        "price": 10},
    {"name": "an outfit i found",      "price": 100},
    {"name": "a gamepass i want",      "price": 50},
    {"name": "this accessory",         "price": 5},
    {"name": "bloxburg",               "price": 100},
    {"name": "a limited i like",       "price": 100},
    {"name": "this hair i want",       "price": 50},
    {"name": "some ugc i saw",         "price": 10},
    {"name": "a face i want",          "price": 10},
]

# Known bot accounts to never approach
BOT_ACCOUNTS = {
    "ExplorerCrusher292", "ColorCrusher292", "AquaCrusher292",
    "PillageCrusher292", "BeeCrusher292", "NetherCrusher292",
    "CaveCrusher292", "CliffCrusher292", "WildCrusher292",
    "TrailCrusher292",
}

# ── Timing constants ───────────────────────────────────────────────────────

TYPO_CHANCE          = 0.45
WAIT_FOR_ANSWER_TIME = 11.0   # seconds to wait for player response
SECOND_ATTEMPT_CHANCE = 0.30
FRUSTRATION_THRESHOLD = 5
PLAYER_COOLDOWN_SECS = 9999   # never re-approach same player on this server
APPROACH_TIMEOUT_SECS = 25    # abandon walking if takes too long
COOLDOWN_AFTER_INTERACTION = 0.3
THANKS_DELAY_SECS    = 150    # thank donor 2.5 min after donation

# ── State constants ────────────────────────────────────────────────────────

ST_IDLE              = "idle"
ST_APPROACHING       = "approaching"
ST_CHATTING          = "chatting"          # sent compliment, about to ask
ST_WAITING_RESPONSE  = "waiting_response"
ST_FOLLOWING         = "following"         # player said yes, walking to booth
ST_WAITING_DONATION  = "waiting_donation"  # at booth, waiting
ST_SECOND_ATTEMPT    = "second_attempt"
ST_COOLDOWN          = "cooldown"


# ── Per-user state ─────────────────────────────────────────────────────────

class UserBotState:
    __slots__ = (
        "state", "target_uid", "target_name",
        "message_sent", "state_entered_at",
        "approached_set", "frustration_count",
        "consecutive_refusals", "leaving_soon",
        "dream_item", "recent_donors", "compliment_sent",
        "last_nearby_uids", "last_player_reply",
        "no_target_since", "last_job_id",
    )

    def __init__(self):
        self.state             = ST_IDLE
        self.target_uid        = None
        self.target_name       = None
        self.message_sent      = None
        self.state_entered_at  = time.time()
        self.approached_set    = {}    # uid → timestamp
        self.frustration_count = 0
        self.consecutive_refusals = 0
        self.leaving_soon      = False
        self.dream_item        = random.choice(DREAM_ITEMS)
        self.recent_donors     = {}    # uid → {"ts": ..., "thanked": bool}
        self.compliment_sent   = False
        self.last_nearby_uids  = set()
        self.last_player_reply = ""
        self.no_target_since   = 0.0
        self.last_job_id       = ""

    def time_in_state(self) -> float:
        return time.time() - self.state_entered_at

    def set_state(self, new_state: str):
        self.state            = new_state
        self.state_entered_at = time.time()


# ── Brain ──────────────────────────────────────────────────────────────────

class BotBrain:
    """Thread-safe, per-user bot decision engine."""

    def __init__(self):
        self._states: dict[str, UserBotState] = {}
        self._lock   = threading.Lock()

    def reset_user(self, uid: str):
        with self._lock:
            self._states.pop(uid, None)

    def get_action(self, uid: str, payload: dict) -> dict:
        """
        Call every ~0.5 s from the client.

        payload keys:
          nearby     – list of {uid, name, distance, raised}
          chat       – list of {from_uid, from_name, message} since last call
          donated    – bool: did our Raised amount increase this tick?
          new_raised – int: current raised value
          at_target  – bool: within ~8 studs of current target
          stats      – {approached, agreed, refused, no_response, ...}
          leaving_soon – bool: server set this flag (watchdog near expiry)
        """
        with self._lock:
            if uid not in self._states:
                self._states[uid] = UserBotState()
            st = self._states[uid]
            return self._decide(uid, st, payload)

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _is_yes(msg: str) -> bool:
        m = msg.lower().strip()
        return any(w in m for w in YES_LIST)

    @staticmethod
    def _is_no(msg: str) -> bool:
        m = msg.lower().strip()
        return any(w in m for w in NO_LIST)

    @staticmethod
    def _on_cooldown(st: UserBotState, uid: str) -> bool:
        ts = st.approached_set.get(uid)
        return ts is not None and (time.time() - ts) < PLAYER_COOLDOWN_SECS

    @staticmethod
    def _pick_target(st: UserBotState, nearby: list) -> dict | None:
        candidates = []
        for p in nearby:
            p_uid = str(p.get("uid", ""))
            if not p_uid:
                continue
            if p.get("name", "") in BOT_ACCOUNTS:
                continue
            if BotBrain._on_cooldown(st, p_uid):
                continue
            dist = p.get("distance", 999)
            if dist < 3:
                continue
            candidates.append(p)
        if not candidates:
            return None
        candidates.sort(key=lambda p: p.get("distance", 999))
        return candidates[0]

    @staticmethod
    def _contextual_msg(target_raised: int, leaving_soon: bool) -> str:
        if leaving_soon and random.random() < 0.3:
            return random.choice(MSGS_LEAVING)
        if target_raised == 0:
            return random.choice(MSGS_EMPTY)
        elif target_raised < 50:
            return random.choice(MSGS_LOW)
        elif target_raised < 200:
            return random.choice(MSGS_MID)
        else:
            return random.choice(MSGS_RICH)

    @staticmethod
    def _maybe_typo(msg: str) -> str:
        """Return a typo variant if the message is in the indexed MESSAGES list."""
        if random.random() >= TYPO_CHANCE:
            return msg
        try:
            idx = MESSAGES.index(msg)
            if idx < len(MESSAGE_TYPOS):
                return random.choice(MESSAGE_TYPOS[idx])
            extra_idx = idx - len(MESSAGE_TYPOS)
            if 0 <= extra_idx < len(MESSAGE_TYPOS_EXTRA):
                return random.choice(MESSAGE_TYPOS_EXTRA[extra_idx])
        except ValueError:
            pass
        return msg

    # ── Main decision method ───────────────────────────────────────────────

    def _decide(self, uid: str, st: UserBotState, payload: dict) -> dict:
        nearby      = payload.get("nearby", [])
        chat_events = payload.get("chat", [])          # list of messages since last call
        donated     = payload.get("donated", False)
        new_raised  = int(payload.get("new_raised", 0))
        at_target   = payload.get("at_target", False)
        leaving     = payload.get("leaving_soon", False)
        job_id      = payload.get("job_id", "")

        # ── Detect server hop: reset per-server state ──────────────────────
        if job_id and job_id != st.last_job_id:
            st.last_job_id        = job_id
            st.approached_set     = {}
            st.no_target_since    = 0.0
            st.leaving_soon       = False
            st.consecutive_refusals = 0
            st.state              = ST_IDLE
            st.target_uid         = None
            st.target_name        = None

        if leaving:
            st.leaving_soon = True

        nearby_uids = {str(p.get("uid", "")) for p in nearby}

        # ── Thank recent donors ────────────────────────────────────────────
        now = time.time()
        for donor_uid, info in list(st.recent_donors.items()):
            if not info["thanked"] and (now - info["ts"]) >= THANKS_DELAY_SECS:
                donor_name = info.get("name", "")
                if donor_uid in nearby_uids:
                    st.recent_donors[donor_uid]["thanked"] = True
                    msg = random.choice(MSGS_THANKS)
                    return {"action": "send_chat", "message": msg}

        # ── If donated, track donor for later thanks ───────────────────────
        if donated and st.state == ST_WAITING_DONATION and st.target_uid:
            st.recent_donors[st.target_uid] = {
                "ts": now, "thanked": False,
                "name": st.target_name or "",
            }
            st.approached_set[st.target_uid] = now
            st.set_state(ST_COOLDOWN)
            return {
                "action": "idle", "wait": COOLDOWN_AFTER_INTERACTION, "event": "donated",
                "_ilog": {
                    "target": st.target_name,
                    "bot_msg": st.message_sent or "",
                    "player_reply": st.last_player_reply or "",
                },
            }

        # ── Target left the server ─────────────────────────────────────────
        if st.target_uid and st.target_uid not in nearby_uids:
            if st.state not in (ST_IDLE, ST_COOLDOWN):
                st.approached_set[st.target_uid] = now
                st.set_state(ST_IDLE)
                st.target_uid  = None
                st.target_name = None

        st.last_nearby_uids = nearby_uids

        # ── State machine ──────────────────────────────────────────────────

        if st.state == ST_IDLE:
            tgt = self._pick_target(st, nearby)
            if tgt is None:
                now_t = time.time()
                if st.no_target_since == 0.0:
                    st.no_target_since = now_t
                elif now_t - st.no_target_since > 60:
                    st.no_target_since = 0.0
                    return {"action": "server_hop"}
                return {"action": "idle", "wait": 1.5}
            st.no_target_since = 0.0
            st.target_uid      = str(tgt["uid"])
            st.target_name     = tgt.get("name", "Player")
            st.compliment_sent = False
            st.set_state(ST_APPROACHING)
            return {"action": "walk_to", "uid": st.target_uid, "name": st.target_name}

        elif st.state == ST_APPROACHING:
            if st.time_in_state() > APPROACH_TIMEOUT_SECS:
                st.approached_set[st.target_uid] = now
                st.set_state(ST_IDLE)
                return {"action": "idle", "wait": 1.0}

            if not at_target:
                return {"action": "walk_to", "uid": st.target_uid, "name": st.target_name}

            # Close enough — decide what to say
            tgt_info = next((p for p in nearby if str(p.get("uid")) == st.target_uid), {})
            tgt_raised = int(tgt_info.get("raised", 0))

            # Compliment chance
            if not st.compliment_sent and random.random() < 0.15:
                st.compliment_sent = True
                st.set_state(ST_CHATTING)
                return {"action": "send_chat", "message": random.choice(COMPLIMENTS)}

            msg = self._contextual_msg(tgt_raised, st.leaving_soon)
            msg = self._maybe_typo(msg)
            st.message_sent = msg
            st.set_state(ST_WAITING_RESPONSE)
            return {"action": "send_chat", "message": msg}

        elif st.state == ST_CHATTING:
            # Just sent compliment — now send the donation ask
            tgt_info = next((p for p in nearby if str(p.get("uid")) == st.target_uid), {})
            tgt_raised = int(tgt_info.get("raised", 0))
            msg = random.choice(MSGS_POST_COMPLIMENT)
            st.message_sent = msg
            st.set_state(ST_WAITING_RESPONSE)
            return {"action": "send_chat", "message": msg}

        elif st.state == ST_WAITING_RESPONSE:
            # Check incoming chat for a response from target
            for ev in chat_events:
                from_uid  = str(ev.get("from_uid", ""))
                from_name = ev.get("from_name", "")
                message   = ev.get("message", "")

                if from_uid != st.target_uid and from_name != st.target_name:
                    continue

                if self._is_yes(message):
                    st.last_player_reply = message
                    st.approached_set[st.target_uid] = now
                    st.set_state(ST_FOLLOWING)
                    return {
                        "action": "send_chat",
                        "message": MSG_FOLLOW_ME,
                        "next_action": "lead_to_booth",
                        "event": "agreed",
                        "_ilog": {
                            "target": st.target_name,
                            "bot_msg": st.message_sent or "",
                            "player_reply": message,
                        },
                    }

                if self._is_no(message):
                    st.last_player_reply = message
                    st.consecutive_refusals += 1
                    second = None
                    if st.consecutive_refusals >= FRUSTRATION_THRESHOLD:
                        second = random.choice(FRUSTRATION_MSGS)
                        st.consecutive_refusals = 0
                    elif random.random() < SECOND_ATTEMPT_CHANCE:
                        second = random.choice(MSGS_SECOND)

                    reply = second or random.choice(MSGS_GOODBYE)
                    st.approached_set[st.target_uid] = now
                    st.set_state(ST_COOLDOWN)
                    return {
                        "action": "send_chat", "message": reply, "event": "refused",
                        "_ilog": {
                            "target": st.target_name,
                            "bot_msg": st.message_sent or "",
                            "player_reply": message,
                        },
                    }

            # Timeout
            if st.time_in_state() > WAIT_FOR_ANSWER_TIME:
                nr_msg = random.choice(NO_RESPONSE_MSGS)
                st.approached_set[st.target_uid] = now
                st.set_state(ST_COOLDOWN)
                return {
                    "action": "send_chat", "message": nr_msg, "event": "no_response",
                    "_ilog": {
                        "target": st.target_name,
                        "bot_msg": st.message_sent or "",
                        "player_reply": "",
                    },
                }

            # Stay near the target while waiting — follow immediately if they walk away
            if st.target_uid in nearby_uids:
                tgt_info = next((p for p in nearby if str(p.get("uid")) == st.target_uid), {})
                dist = tgt_info.get("distance", 0)
                if dist > 10:
                    return {"action": "walk_to", "uid": st.target_uid, "name": st.target_name}
                return {"action": "fidget", "uid": st.target_uid}

            return {"action": "idle", "wait": 0.2}

        elif st.state == ST_FOLLOWING:
            # Player agreed — we said "follow me!", now lead them to our booth
            if at_target:
                # We're at the booth area
                st.set_state(ST_WAITING_DONATION)
                return {"action": "send_chat", "message": MSG_HERE_IS_HOUSE}
            return {"action": "lead_to_booth"}

        elif st.state == ST_WAITING_DONATION:
            if st.time_in_state() > 30:
                # Waited too long, move on
                if st.target_uid:
                    st.approached_set[st.target_uid] = now
                st.set_state(ST_IDLE)
                st.target_uid  = None
                st.target_name = None
            return {"action": "idle", "wait": 1.0}

        elif st.state == ST_COOLDOWN:
            if st.time_in_state() > COOLDOWN_AFTER_INTERACTION:
                st.set_state(ST_IDLE)
                st.target_uid  = None
                st.target_name = None
                # Immediately pick next target instead of waiting
                tgt = self._pick_target(st, nearby)
                if tgt:
                    st.target_uid      = str(tgt["uid"])
                    st.target_name     = tgt.get("name", "Player")
                    st.compliment_sent = False
                    st.set_state(ST_APPROACHING)
                    return {"action": "walk_to", "uid": st.target_uid, "name": st.target_name}
            return {"action": "idle", "wait": 0.2}

        return {"action": "idle", "wait": 1.0}


# Singleton instance imported by server_v2.py
brain = BotBrain()
