#!/usr/bin/env python3
"""
build_index.py
Lee articulos.json y cartelera.json y genera index.html.
Lo llama GitHub Actions después de cada scraping.
También puedes correrlo tú manualmente:
  python3 build_index.py
"""
import json, re
from pathlib import Path

def clean(s):
    if not s: return ''
    s = re.sub(r'&#\d+;', ' ', s)
    s = re.sub(r'&[a-zA-Z]+;', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def build():
    with open('articulos.json', encoding='utf-8') as f:
        articulos = json.load(f)
    with open('cartelera.json', encoding='utf-8') as f:
        cartelera = json.load(f)

    for a in articulos:
        a['titulo']  = clean(a['titulo'])
        a['resumen'] = clean(a.get('resumen',''))

    articulos = [a for a in articulos if a.get('categoria') != 'espectáculos']

    art_json  = json.dumps(articulos, ensure_ascii=False)
    cart_json = json.dumps(cartelera, ensure_ascii=False)

    template = Path('index.template.html').read_text(encoding='utf-8')
    html = template.replace('__ART_JSON__', art_json).replace('__CART_JSON__', cart_json)
    Path('index.html').write_text(html, encoding='utf-8')
    print(f"✓ index.html generado  ({len(articulos)} artículos, {len(cartelera)} películas)")

if __name__ == '__main__':
    build()
