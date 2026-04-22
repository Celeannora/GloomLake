import csv

# Read original pool
with open('Decks/2026-04-20_Frog_Tribal_Panel/candidate_pool.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    original_data = {row['name']: row for row in reader}

# Read scored pool
with open('Decks/2026-04-20_Frog_Tribal_Panel/top_100.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    scored_data = {row['name']: row for row in reader}

# Merge and write
with open('Decks/2026-04-20_Frog_Tribal_Panel/pool_for_mythic.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['name','mana_cost','cmc','type_line','colors','rarity','keywords','oracle_text','tags','pool','synergy_score','is_creature','is_removal','is_anthem','tribe','power','toughness'])
    
    for name, row in scored_data.items():
        orig = original_data.get(name, {})
        cmc = row.get('cmc', '')
        try:
            mana_cost = int(float(cmc)) if cmc else 0
        except:
            mana_cost = 0
        is_creature = 'Creature' in row.get('type_line', '')
        is_removal = 'destroy' in row.get('oracle_text', '').lower() or 'exile' in row.get('oracle_text', '').lower()
        is_anthem = '+1/+1' in row.get('oracle_text', '') and 'counter' in row.get('oracle_text', '')
        tribe = 'Frog' if 'Frog' in row.get('type_line', '') else ''
        writer.writerow([
            name,
            mana_cost,
            cmc,
            row.get('type_line', ''),
            row.get('colors', ''),
            row.get('rarity', ''),
            row.get('keywords', ''),
            row.get('oracle_text', ''),
            row.get('tags', ''),
            row.get('pool', ''),
            row.get('synergy_score', ''),
            'true' if is_creature else '',
            'true' if is_removal else '',
            'true' if is_anthem else '',
            tribe,
            '',
            ''
        ])

print('Written merged pool')