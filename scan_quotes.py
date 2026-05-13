with open('src/rtc/connection.py', 'rb') as f:
    lines = f.readlines()

in_triple_dq = False
in_triple_sq = False

for i, raw in enumerate(lines):
    txt = raw.decode('utf-8', errors='replace')
    # Very simple triple-quote tracker
    stripped = txt.strip()
    count_tdq = txt.count('"""')
    count_tsq = txt.count("'''")
    
    if count_tdq % 2 != 0:
        state_before = in_triple_dq
        in_triple_dq = not in_triple_dq
        print(f"Line {i+1}: triple-DQ toggle {state_before}->{in_triple_dq}  | {stripped[:80]}")
    if count_tsq % 2 != 0:
        state_before = in_triple_sq
        in_triple_sq = not in_triple_sq
        print(f"Line {i+1}: triple-SQ toggle {state_before}->{in_triple_sq}  | {stripped[:80]}")

print(f"\nFinal state: in_triple_dq={in_triple_dq}, in_triple_sq={in_triple_sq}")
print(f"Total lines: {len(lines)}")
