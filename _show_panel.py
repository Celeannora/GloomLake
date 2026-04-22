import json
with open('Decks/2026-04-22_Esper_Angel_Mill/panel_report.json') as f:
    d = json.load(f)
print('EV:', d['ev'])
print('Consensus:', d['consensus'])
print('Variance:', d['variance'])
print('Active bottlenecks:', d['active_bottlenecks'])
print()
print('Panel scores:')
for k, v in d['panel_scores'].items():
    print(f'  {k}: {v}')
print()
print('Top cards:')
for c in d['top_cards']:
    print(f'  {c["card"]} ({c["role"]}): {c["score"]}')
