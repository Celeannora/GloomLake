import sys
sys.path.insert(0,'scripts/analysis')
sys.path.insert(0,'scripts/utils')
sys.path.insert(0,'scripts/cli')
from synergy_engine import load_cards_from_db, score_pairwise, extract_names_from_session, attach_card_data
from mtg_utils import RepoPaths
content = open('Decks/2026-04-22_Esper_Angel_Mill/session.md', encoding='utf-8').read()
names = extract_names_from_session(content)
paths = RepoPaths()
card_data = load_cards_from_db(names, paths)
entries = [{'name': n, 'qty': 1, 'section': 'pool'} for n in names]
annotated, _ = attach_card_data(entries, card_data)
scores = score_pairwise(annotated, primary_axis='lifegain')
target = scores.get('haliya, guided by light')
if target:
    p = target.profile
    print(f'composite={target.composite_score:.2f}')
    print(f'dep={target.dependency}')
    print(f'synergy_count={target.synergy_count}')
    print(f'role={target.role}')
    print(f'source_tags={set(p.source_tags)}')
    print(f'payoff_tags={set(p.payoff_tags)}')
    print(f'broad_tags={set(p.broad_tags)}')
    print(f'keywords={set(p.keywords)}')
    print(f'cmc={p.cmc}')
    print(f'in_session={"haliya" in content.lower()}')
else:
    print('NOT IN POOL - card was not extracted from session.md')
    print('Checking if card is in DB...')
    all_data = load_cards_from_db(['Haliya, Guided by Light'], paths)
    print(f'In DB: {"haliya, guided by light" in {k.lower() for k in all_data}}')
