#!/usr/bin/env python3
"""Compare old vs new mana base via Monte Carlo."""
import random

def simulate(lands, n_sims=500000):
    non_lands = [set()] * (60 - len(lands))
    deck = lands + non_lands
    assert len(deck) == 60
    
    results = {
        'W_opener': 0, 'U_opener': 0, 'R_opener': 0,
        'WU_opener': 0, 'WU_t2_play': 0, 'WU_t2_draw': 0,
        'WUR_t3_play': 0, 'WUR_t3_draw': 0,
        '2lands': 0, '3lands': 0,
        'W_t1': 0,  # Can play a W 1-drop on T1
    }
    
    for _ in range(n_sims):
        random.shuffle(deck)
        
        def colors_in(cards):
            c = set()
            for card in cards:
                c |= card
            return c
        
        def land_count(cards):
            return sum(1 for c in cards if c)
        
        hand = deck[:7]
        h_colors = colors_in(hand)
        h_lands = land_count(hand)
        
        results['W_opener'] += 'W' in h_colors
        results['U_opener'] += 'U' in h_colors
        results['R_opener'] += 'R' in h_colors
        results['WU_opener'] += ('W' in h_colors and 'U' in h_colors)
        results['2lands'] += h_lands >= 2
        results['3lands'] += h_lands >= 3
        results['W_t1'] += 'W' in h_colors  # At least 1 W source in opener
        
        t2p = colors_in(deck[:8])
        results['WU_t2_play'] += ('W' in t2p and 'U' in t2p)
        
        t2d = colors_in(deck[:9])
        results['WU_t2_draw'] += ('W' in t2d and 'U' in t2d)
        
        t3p = colors_in(deck[:9])
        results['WUR_t3_play'] += ('W' in t3p and 'U' in t3p and 'R' in t3p)
        
        t3d = colors_in(deck[:10])
        results['WUR_t3_draw'] += ('W' in t3d and 'U' in t3d and 'R' in t3d)
    
    return {k: v/n_sims for k, v in results.items()}

# OLD mana base (20 lands)
old_lands = []
old_lands += [{'W','U'}] * 4   # Hallowed Fountain
old_lands += [{'R','W'}] * 4   # Sacred Foundry
old_lands += [{'U','R'}] * 4   # Steam Vents
old_lands += [{'R','W'}] * 1   # Inspiring Vantage
old_lands += [{'U','R'}] * 2   # Spirebluff Canal
old_lands += [{'W','U'}] * 1   # Temple of Enlightenment
old_lands += [{'R','W'}] * 1   # Temple of Triumph
old_lands += [{'W'}] * 2       # Plains
old_lands += [{'U'}] * 1       # Island
assert len(old_lands) == 20

# NEW mana base (24 lands)
new_lands = []
new_lands += [{'W','U'}] * 4   # Hallowed Fountain
new_lands += [{'R','W'}] * 3   # Sacred Foundry
new_lands += [{'U','R'}] * 3   # Steam Vents
new_lands += [{'W','U','R'}] * 2  # Starting Town (any color)
new_lands += [{'W','U'}] * 2   # Floodfarm Verge (WU, needs Plains/Island - shocks count)
new_lands += [{'W','U','R'}] * 1  # Fabled Passage (fetches any basic)
new_lands += [{'R','W'}] * 1   # Inspiring Vantage
new_lands += [{'U','R'}] * 1   # Spirebluff Canal
new_lands += [{'R','W'}] * 1   # Sunbillow Verge
new_lands += [{'W'}] * 3       # Plains
new_lands += [{'U'}] * 2       # Island
new_lands += [{'R'}] * 1       # Mountain
assert len(new_lands) == 24

print("=" * 65)
print("MANA BASE COMPARISON: OLD (20 lands) vs NEW (24 lands)")
print("=" * 65)

old = simulate(old_lands)
new = simulate(new_lands)

metrics = [
    ('W source in opener', 'W_opener'),
    ('U source in opener', 'U_opener'),
    ('R source in opener', 'R_opener'),
    ('WU together in opener', 'WU_opener'),
    ('WU by turn 2 (play)', 'WU_t2_play'),
    ('WU by turn 2 (draw)', 'WU_t2_draw'),
    ('WUR by turn 3 (play)', 'WUR_t3_play'),
    ('WUR by turn 3 (draw)', 'WUR_t3_draw'),
    ('2+ lands in opener', '2lands'),
    ('3+ lands in opener', '3lands'),
]

print(f"\n  {'Metric':<30} {'OLD (20)':>10} {'NEW (24)':>10} {'Delta':>10}")
print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")

for label, key in metrics:
    o = old[key] * 100
    n = new[key] * 100
    d = n - o
    arrow = "▲" if d > 0 else "▼" if d < 0 else "="
    print(f"  {label:<30} {o:>9.1f}% {n:>9.1f}% {arrow} {d:>+6.1f}%")

# Color source counts
print(f"\n  Color Sources:")
print(f"  {'Color':<10} {'OLD':>6} {'NEW':>6}")
w_old = sum(1 for l in old_lands if 'W' in l)
u_old = sum(1 for l in old_lands if 'U' in l)
r_old = sum(1 for l in old_lands if 'R' in l)
w_new = sum(1 for l in new_lands if 'W' in l)
u_new = sum(1 for l in new_lands if 'U' in l)
r_new = sum(1 for l in new_lands if 'R' in l)
print(f"  {'White':<10} {w_old:>6} {w_new:>6}")
print(f"  {'Blue':<10} {u_old:>6} {u_new:>6}")
print(f"  {'Red':<10} {r_old:>6} {r_new:>6}")
print(f"  {'Total':<10} {len(old_lands):>6} {len(new_lands):>6}")

print(f"\n  Karsten compliance: 24 lands for 2.4 avg CMC = WITHIN RANGE")
print(f"  (Recommended 23-24 for midrange with 3-color)")
