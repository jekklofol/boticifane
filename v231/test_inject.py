import sys, re
sys.path.insert(0, '.')
import server_v2

code = open('obfuscated_script.lua', encoding='utf-8').read()
result = server_v2._inject_into_code(code, 'TEST-KEY-1234', '123456789', 'https://example.com', 'tok123')

pd_calls = re.findall(r'_pd\(\{[^\}]+\}\)', result)
print('_pd() injections found:', len(pd_calls))
for i, c in enumerate(pd_calls):
    print(f'  {i+1}:', c[:100])

# Decode using server's own encoder logic
for i, c in enumerate(pd_calls):
    m = re.match(r'_pd\((\{[^\}]+\})\)', c)
    if m:
        nums = list(map(int, re.findall(r'\d+', m.group(1))))
        KEY = 0x5A
        decoded = ''.join(chr(b ^ (idx % 256) ^ KEY) for idx, b in enumerate(nums))
        print(f'  decoded[{i+1}]:', repr(decoded))

# Check no _G.__ reads remain
remaining = re.findall(r'_G\.__\w+\s*or', result)
print('\nRemaining _G.__ reads:', remaining if remaining else 'none - injection clean!')
