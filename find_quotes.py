with open('src/rtc/connection.py', 'rb') as f:
    lines = f.readlines()
for i in range(524, 600):
    raw = lines[i]
    txt = raw.decode('utf-8', errors='replace').rstrip()
    if '"""' in txt:
        print(f'Line {i+1}: {repr(txt)}')
