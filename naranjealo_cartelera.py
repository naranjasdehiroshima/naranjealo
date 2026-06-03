#!/usr/bin/env python3
"""
naranjealo_cartelera.py
Scraper de cartelera para salas alternativas CDMX.

Fuentes:
  - Cineteca Nacional (API AJAX interna, 3 sedes)
  - Cine Tonalá        (WordPress REST API — sin cartelera estructurada aún,
                        se monitorea; fallback: página manual)

Uso:
  python3 naranjealo_cartelera.py           # scrape y guarda en cartelera.json
  python3 naranjealo_cartelera.py --show    # imprime cartelera en terminal
"""

import requests, json, re, hashlib, argparse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path

JSON_PATH = "cartelera.json"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    'Accept-Language': 'es-MX,es;q=0.9',
}

# ─── CINETECA NACIONAL ────────────────────────────────────────────────────────
# API AJAX interna descubierta en ingeniería inversa. Funcional a jun-2026.
# Parámetros: vista=full, cinema=001|002|003, eventId=000

CINETECA_SEDES = {
    '001': 'Chapultepec',
    '002': 'Las Artes',
    '003': 'México',
}
CINETECA_AJAX  = "https://www.cinetecanacional.net/data/cartelera.php"
CINETECA_BASE  = "https://www.cinetecanacional.net"
CINETECA_CDN   = "https://rbvfcn.cinetecanacional.net/CDN/media/entity/get/FilmPosterGraphic"

def scrape_cineteca() -> list[dict]:
    """Devuelve lista de películas en cartelera de las 3 sedes."""
    films = {}

    ajax_headers = {**HEADERS,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': f'{CINETECA_BASE}/cartelera.php',
        'Origin': CINETECA_BASE,
    }

    for cinema_id, sede in CINETECA_SEDES.items():
        try:
            r = requests.post(CINETECA_AJAX, headers=ajax_headers, timeout=12,
                data={'vista':'full','fecha':'','cinema':cinema_id,'eventId':'000'})
            r.raise_for_status()
            html = r.json().get('html','')
        except Exception as e:
            print(f"  ✗ Cineteca {sede}: {e}")
            continue

        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.find_all('div', onclick=True)

        for card in cards:
            m = re.search(r'FilmId=(\w+)', card.get('onclick',''))
            if not m:
                continue
            film_id = m.group(1)

            img_tag = card.find('img')
            titulo  = img_tag.get('alt','').strip() if img_tag else ''
            poster  = f"{CINETECA_CDN}/{film_id}?referenceScheme=Cinema&allowPlaceHolder"

            # Clasificación (AA, B, B15, C) si aparece en el texto
            classif = ''
            for span in card.find_all(string=re.compile(r'^(AA|A|B\+?|B15|C)$')):
                classif = span.strip()
                break

            # Versión (DOB/SUB/ESP)
            version = ''
            for v in ['DOB','SUB','ESP','VO']:
                if titulo.upper().endswith(v) or f' {v}' in titulo.upper():
                    version = v
                    titulo  = titulo.replace(f' {v}','').replace(v,'').strip()
                    break

            if film_id not in films:
                films[film_id] = {
                    'id':         film_id,
                    'titulo':     titulo,
                    'poster':     poster,
                    'url':        f"{CINETECA_BASE}/detallePelicula.php?FilmId={film_id}",
                    'sala':       'Cineteca Nacional',
                    'sedes':      [],
                    'versiones':  [],
                    'clasificacion': classif,
                    'fecha_scrape': datetime.now(timezone.utc).isoformat(),
                }
            if sede not in films[film_id]['sedes']:
                films[film_id]['sedes'].append(sede)
            if version and version not in films[film_id]['versiones']:
                films[film_id]['versiones'].append(version)

    result = list(films.values())
    print(f"  ✓ Cineteca Nacional — {len(result)} películas "
          f"({', '.join(CINETECA_SEDES.values())})")
    return result


# ─── CINE TONALÁ ─────────────────────────────────────────────────────────────
# A jun-2026 su cartelera es image-based/manual sin API estructurada.
# Scrapeamos la página principal buscando títulos en imágenes y texto,
# y monitoreamos la WP REST API para cuando la activen.

TONALA_URL  = "https://www.cinetonala.mx"
TONALA_WPAPI = f"{TONALA_URL}/wp-json/wp/v2"

def scrape_tonala() -> list[dict]:
    films = []

    # 1. Intentar WP REST API (cuando tengan posts de cartelera)
    try:
        r = requests.get(f"{TONALA_WPAPI}/posts?per_page=20&categories=cartelera",
            headers=HEADERS, timeout=8)
        posts = r.json() if r.status_code == 200 else []
        if isinstance(posts, list):
            for p in posts:
                title = p.get('title',{}).get('rendered','').strip()
                if not title or title == 'Hello world!':
                    continue
                link    = p.get('link','')
                date    = p.get('date','')
                excerpt = BeautifulSoup(p.get('excerpt',{}).get('rendered',''), 'html.parser').get_text()
                img_url = ''
                if p.get('_embedded',{}).get('wp:featuredmedia'):
                    img_url = p['_embedded']['wp:featuredmedia'][0].get('source_url','')
                films.append({
                    'id':           hashlib.md5(link.encode()).hexdigest()[:10],
                    'titulo':       title,
                    'poster':       img_url,
                    'url':          link,
                    'sala':         'Cine Tonalá',
                    'sedes':        ['Tonalá'],
                    'versiones':    [],
                    'fecha_scrape': datetime.now(timezone.utc).isoformat(),
                })
    except Exception:
        pass

    # 2. Scraping directo de la página principal (cartelera visual)
    if not films:
        try:
            r = requests.get(TONALA_URL, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')

            # Buscar imágenes de películas (las que no son logo/banner)
            for img in soup.find_all('img'):
                src = img.get('src','')
                alt = img.get('alt','').strip()
                # Filtrar logos, iconos
                if not alt or len(alt) < 4:
                    continue
                if any(x in alt.lower() for x in ['tonalá','logo','fanxie','banner']):
                    continue
                if 'wp-content/uploads' in src and len(alt) > 5:
                    fid = hashlib.md5(src.encode()).hexdigest()[:10]
                    # Buscar enlace padre
                    parent_a = img.find_parent('a')
                    url = parent_a['href'] if parent_a and parent_a.get('href') else TONALA_URL
                    if not any(f['id'] == fid for f in films):
                        films.append({
                            'id':           fid,
                            'titulo':       alt,
                            'poster':       src,
                            'url':          url if url.startswith('http') else TONALA_URL + url,
                            'sala':         'Cine Tonalá',
                            'sedes':        ['Tonalá'],
                            'versiones':    [],
                            'fecha_scrape': datetime.now(timezone.utc).isoformat(),
                        })
        except Exception as e:
            print(f"  ✗ Cine Tonalá scraping: {e}")

    note = "(REST API)" if films and films[0].get('url','').startswith('http') else "(scraping visual)"
    print(f"  {'✓' if films else '~'} Cine Tonalá {note} — {len(films)} entradas")
    return films


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run() -> list[dict]:
    print(f"\n{'='*56}")
    print(f"  Naranjealo — Cartelera CDMX  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*56}")

    all_films = []
    all_films += scrape_cineteca()
    all_films += scrape_tonala()

    print(f"\n  Total en cartelera: {len(all_films)} películas")

    # Breakdown por sala
    from collections import Counter
    for sala, n in Counter(f['sala'] for f in all_films).items():
        print(f"    {sala:<25} {n:>3}")

    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(all_films, f, ensure_ascii=False, indent=2)
    print(f"\n  Guardado: {JSON_PATH}")
    return all_films


def show(films=None):
    if films is None:
        with open(JSON_PATH) as f:
            films = json.load(f)
    print(f"\n{'─'*70}")
    current_sala = None
    for fi in sorted(films, key=lambda x: (x['sala'], x['titulo'])):
        if fi['sala'] != current_sala:
            current_sala = fi['sala']
            print(f"\n  ▸ {current_sala.upper()}")
        sedes = ', '.join(fi.get('sedes',[]))
        vers  = '/'.join(fi.get('versiones',[])) or ''
        print(f"    {fi['titulo'][:50]:<52} {sedes:<22} {vers}")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--show', action='store_true')
    args = ap.parse_args()

    films = run()
    if args.show:
        show(films)
