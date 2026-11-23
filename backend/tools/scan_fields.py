import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2] / 'app' / 'backend-pages'
mods = {}
for path in sorted(root.glob('*.html')):
    if path.name.endswith('.mobile.html'):
        continue
    key = path.stem
    if any(x in key for x in ['-add', '-edit', '-tougao', '-settle', '-configure', 'shell']):
        continue
    html = path.read_text(encoding='utf-8', errors='ignore')
    fields = re.findall(r'data-field="([^"]*)"', html)
    seen = []
    for field in fields:
        if field not in seen:
            seen.append(field)
    mods[key] = seen[:15]
print(json.dumps(mods, ensure_ascii=False, indent=2))
