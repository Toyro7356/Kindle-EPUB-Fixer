import json

with open('tools/epub_analysis_report_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print("=== MISSING IMAGE REFS ===")
for d in data['details']:
    if d['issues'].get('missing_image_refs'):
        print(f"\n--- {d['file']} ---")
        for ref in d['issues']['missing_image_refs']:
            print(' ', ref)

print("\n\n=== CSS KINDLE UNSAFE (samples) ===")
for d in data['details']:
    if d['issues'].get('css_kindle_unsafe'):
        print(f"\n--- {d['file']} ---")
        for ref in d['issues']['css_kindle_unsafe'][:2]:
            print(' ', ref)

print("\n\n=== LARGE IMAGES ===")
for d in data['details']:
    if d['issues'].get('large_images'):
        print(f"\n--- {d['file']} ---")
        for ref in d['issues']['large_images']:
            print(' ', ref)
