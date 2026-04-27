code = open('obfuscated_script.lua', encoding='utf-8').read()

patterns = [
    '_G.__LICENSE_KEY or ""',
    '_G.__BOUND_UID or ""',
    '_G.__API_URL or ""',
    '_G.__SESSION_TOKEN or ""',
    '_G.__LICENSE_KEY',
    '_G.__BOUND_UID',
    '_G.__API_URL',
    '_G.__SESSION_TOKEN',
]

for p in patterns:
    found = p in code
    print(("FOUND " if found else "MISS  ") + repr(p))
    if found and len(p) > 16:
        idx = code.find(p)
        print("  ctx:", repr(code[max(0,idx-15):idx+len(p)+40]))
