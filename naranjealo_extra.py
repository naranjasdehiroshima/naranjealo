#!/usr/bin/env python3
"""
naranjealo_extra.py
Scraper para dos fuentes especiales de Naranjealo:

  1. MX Nuestro Cine (Canal 22.2)
     canal22.org.mx/mx_nuestro_cine.html
     No tiene RSS. Scrapea el carrusel de programación semanal:
     ciclos, estrenos, recomendaciones, con fechas y descripciones.
     Genera artículos sintéticos compatibles con articulos.json.

  2. La Filmoteca Maldita (YouTube)
     Canal: @Lafilmotecamaldita  ID: UCe81jZxbCPX8PilT3IQKxFw
     Feed RSS nativo de YouTube. Filtra solo videos relacionados
     con cine, historia del cine o análisis cinematográfico
     (el canal deriva periódicamente hacia contenido político).

Uso:
  python3 naranjealo_extra.py            # scrape ambas fuentes
  python3 naranjealo_extra.py --show     # imprime resultados
  python3 naranjealo_extra.py --merge articulos.json
                                         # fusiona con el JSON principal
"""

import requests, feedparser, json, re, hashlib, argparse
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from pathlib import Path

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36',
    'Accept-Language': 'es-MX,es;q=0.9',
}

# ─── MX NUESTRO CINE ─────────────────────────────────────────────────────────

MX_URL  = "https://www.canal22.org.mx/mx_nuestro_cine.html"
MX_BASE = "https://www.canal22.org.mx"

# Meses en español para parsear fechas del HTML
MESES = {
    'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
    'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12,
}

def _parse_fecha_mx(texto: str) -> str:
    """
    Intenta extraer una fecha ISO de strings como:
    'Del martes 2 al jueves 4 de junio, 20 h'
    'ESTRENO | Jueves 4 de junio, 19 h'
    Devuelve YYYY-MM-DD o '' si no puede.
    """
    texto = texto.lower()
    # Busca patrones: 'N de mes' o 'del N al N de mes'
    m = re.search(r'(\d{1,2})\s+de\s+(' + '|'.join(MESES) + r')', texto)
    if m:
        day  = int(m.group(1))
        mon  = MESES[m.group(2)]
        year = datetime.now().year
        try:
            return f"{year}-{mon:02d}-{day:02d}"
        except Exception:
            pass
    return ''

def _uid(texto: str) -> str:
    return 'mx22_' + hashlib.md5(texto.encode()).hexdigest()[:10]

def scrape_mx_nuestro_cine() -> list[dict]:
    """
    Extrae programación activa del carrusel de MX Nuestro Cine.
    Cada slide activo (no comentado) se convierte en un artículo:
      - ciclos con múltiples películas
      - estrenos individuales
      - recomendaciones semanales (banners)
    """
    print("  → MX Nuestro Cine (Canal 22.2)", end="", flush=True)
    articulos = []

    try:
        r = requests.get(MX_URL, headers=HEADERS, timeout=12, verify=False)
        r.encoding = 'utf-8'  # el servidor sirve UTF-8 pero headers mienten
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    hoy  = datetime.now(timezone.utc).isoformat()

    # ── 1. Slides del carrusel (ciclos y estrenos) ───────────────────────────
    for slide in soup.find_all('div', class_=lambda c: c and 'carousel-item' in c):
        h1   = slide.find('h1')
        h4s  = slide.find_all('h4')
        p    = slide.find('p')
        img  = slide.find('img')

        titulo = h1.get_text(strip=True) if h1 else ''
        # Si no hay h1, usar el alt de la imagen
        if not titulo and img:
            titulo = img.get('alt', '').strip()
        if not titulo:
            continue

        # h4[0] = subtítulo/ciclo, h4[1] = director/país, h4[2] = fecha
        subtitulo = h4s[0].get_text(strip=True) if len(h4s) > 0 else ''
        director  = h4s[1].get_text(strip=True) if len(h4s) > 1 else ''
        fecha_txt = h4s[2].get_text(strip=True) if len(h4s) > 2 else ''
        # a veces la fecha está en h4[1] si no hay director
        if not fecha_txt and director:
            # detectar si h4[1] parece una fecha
            if any(mes in director.lower() for mes in MESES) or 'estreno' in director.lower():
                fecha_txt = director
                director  = ''

        descripcion = p.get_text(separator=' ', strip=True) if p else ''
        img_src = img.get('src', '') if img else ''
        if img_src and not img_src.startswith('http'):
            img_src = f"{MX_BASE}/{img_src}"

        fecha_iso = _parse_fecha_mx(fecha_txt)
        if not fecha_iso:
            fecha_iso = datetime.now().strftime('%Y-%m-%d')

        # Clasificar como estreno o ciclo
        es_estreno = 'estreno' in fecha_txt.lower()
        categoria  = 'cine'

        # Construir resumen legible
        partes = []
        if subtitulo:
            partes.append(subtitulo)
        if director:
            partes.append(director)
        if fecha_txt:
            partes.append(fecha_txt)
        if descripcion:
            partes.append(descripcion[:250])
        resumen = ' · '.join(filter(None, partes))

        articulos.append({
            'id':           _uid(titulo + fecha_iso),
            'titulo':       ('ESTRENO | ' if es_estreno else '') + titulo,
            'url':          MX_URL,
            'resumen':      resumen,
            'imagen':       img_src,
            'fuente':       'MX Nuestro Cine · Canal 22.2',
            'idioma':       'es',
            'categoria':    categoria,
            'fecha_pub':    fecha_iso + 'T00:00:00+00:00',
            'fecha_scrape': hoy,
        })

    # ── 2. Banners de recomendaciones semanales ──────────────────────────────
    for img in soup.find_all('img'):
        src = img.get('src', '')
        alt = img.get('alt', '').strip()
        if 'banners' not in src or not alt or len(alt) < 4:
            continue
        # Intentar extraer fecha del path: /banners/2026/junio/jun02_titulo.jpg
        fecha_banner = ''
        m = re.search(r'/(\d{4})/(\w+)/(\w{3})(\d{2})_', src)
        if m:
            mes_str = m.group(2)
            day     = int(m.group(4))
            mon     = MESES.get(mes_str, 0)
            year    = int(m.group(1))
            if mon:
                fecha_banner = f"{year}-{mon:02d}-{day:02d}"
        if not fecha_banner:
            fecha_banner = datetime.now().strftime('%Y-%m-%d')

        img_url = src if src.startswith('http') else f"{MX_BASE}/{src}"

        articulos.append({
            'id':           _uid(alt + fecha_banner),
            'titulo':       alt,
            'url':          MX_URL,
            'resumen':      f'Recomendación semanal en MX Nuestro Cine · Canal 22.2',
            'imagen':       img_url,
            'fuente':       'MX Nuestro Cine · Canal 22.2',
            'idioma':       'es',
            'categoria':    'cine',
            'fecha_pub':    fecha_banner + 'T00:00:00+00:00',
            'fecha_scrape': hoy,
        })

    # Deduplicar por id
    seen = set()
    result = []
    for a in articulos:
        if a['id'] not in seen:
            seen.add(a['id'])
            result.append(a)

    print(f"  {len(result)} entradas")
    return result


# ─── LA FILMOTECA MALDITA (YouTube) ──────────────────────────────────────────

FM_CHANNEL_ID = "UCe81jZxbCPX8PilT3IQKxFw"
FM_FEED_URL   = f"https://www.youtube.com/feeds/videos.xml?channel_id={FM_CHANNEL_ID}"

# Keywords que indican contenido sobre CINE (no política/conspiración)
FM_CINE_KEYWORDS = [
    'cine', 'película', 'pelicula', 'film', 'director', 'cinema',
    'hitchcock', 'kubrick', 'godard', 'fellini', 'bunuel', 'buñuel',
    'neorrealismo', 'nouvelle vague', 'expresionismo', 'western',
    'noir', 'exploitation', 'serie b', 'culto', 'animación', 'anime',
    'documental', 'cortometraje', 'ciencia ficción', 'terror', 'suspense',
    'guión', 'montaje', 'fotografía cinematográfica', 'producción',
    'festival de cine', 'filmografía', 'remake', 'secuela', 'trilogía',
    'años 20', 'años 30', 'años 40', 'años 50', 'años 60', 'años 70',
    'mudo', 'silente', 'clásico', 'filmoteca', 'cinemateca', 'restauración',
    'technicolor', 'cinemascope', 'blanco y negro',
]

FM_POLITICA_KEYWORDS = [
    'guerra', 'trump', 'biden', 'ukraine', 'ucrania', 'rusia', 'iran',
    'mencho', 'narco', 'cartel', 'asesinato', 'conspiración', 'teoría',
    'meme', 'twitter', 'estados unidos atacó', 'villano',
]

def _es_contenido_cine(titulo: str, descripcion: str = '') -> bool:
    texto = (titulo + ' ' + descripcion).lower()
    # Si contiene keywords políticas fuertes, descartar
    politico = sum(1 for k in FM_POLITICA_KEYWORDS if k in texto)
    if politico >= 2:
        return False
    # Si contiene keywords de cine, incluir
    cine = sum(1 for k in FM_CINE_KEYWORDS if k in texto)
    return cine >= 1

def scrape_filmoteca_maldita() -> list[dict]:
    """
    Extrae videos de La Filmoteca Maldita (YouTube) filtrando
    solo aquellos relacionados con análisis o historia del cine.
    """
    print("  → La Filmoteca Maldita (YouTube)", end="", flush=True)
    articulos = []
    hoy = datetime.now(timezone.utc).isoformat()

    try:
        feed = feedparser.parse(FM_FEED_URL)
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    for entry in feed.entries:
        titulo    = entry.get('title', '').strip()
        url       = entry.get('link', '')
        fecha_raw = entry.get('published', '')
        desc      = ''

        # YouTube feed incluye media:group con descripción
        if hasattr(entry, 'media_group'):
            desc = entry.media_group.get('media_description', '')
        elif hasattr(entry, 'summary'):
            desc = entry.get('summary', '')

        # Miniatura del video
        imagen = ''
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            imagen = entry.media_thumbnail[0].get('url', '')

        # Parsear fecha ISO
        fecha_iso = ''
        if fecha_raw:
            try:
                from email.utils import parsedate_to_datetime
                fecha_iso = parsedate_to_datetime(fecha_raw).isoformat()
            except Exception:
                fecha_iso = fecha_raw[:10] + 'T00:00:00+00:00'

        if not _es_contenido_cine(titulo, desc):
            continue

        articulos.append({
            'id':           'fm_' + hashlib.md5(url.encode()).hexdigest()[:10],
            'titulo':       titulo,
            'url':          url,
            'resumen':      desc[:300] if desc else '',
            'imagen':       imagen,
            'fuente':       'La Filmoteca Maldita',
            'idioma':       'es',
            'categoria':    'cine',
            'fecha_pub':    fecha_iso,
            'fecha_scrape': hoy,
        })

    total = len(feed.entries)
    print(f"  {len(articulos)} de {total} videos (filtro cine)")
    return articulos


# ─── MERGE CON articulos.json ─────────────────────────────────────────────────

def merge_into(json_path: str, nuevos: list[dict]) -> int:
    path = Path(json_path)
    existing = []
    if path.exists():
        with open(path, encoding='utf-8') as f:
            existing = json.load(f)
    ids_existing = {a['id'] for a in existing}
    added = [a for a in nuevos if a['id'] not in ids_existing]
    merged = added + existing  # nuevos primero
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return len(added)


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run() -> list[dict]:
    print(f"\n{'='*56}")
    print(f"  Naranjealo · Fuentes especiales  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*56}")
    result = []
    result += scrape_mx_nuestro_cine()
    result += scrape_filmoteca_maldita()
    print(f"\n  Total: {len(result)} entradas")

    with open('naranjealo_extra.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  Guardado: naranjealo_extra.json")
    return result


def show(items=None):
    if items is None:
        with open('naranjealo_extra.json', encoding='utf-8') as f:
            items = json.load(f)
    print(f"\n{'─'*72}")
    current = None
    for a in sorted(items, key=lambda x: x['fuente']):
        if a['fuente'] != current:
            current = a['fuente']
            print(f"\n  ▸ {current.upper()}")
        fecha = a['fecha_pub'][:10]
        print(f"    [{fecha}]  {a['titulo'][:60]}")
        if a.get('resumen'):
            print(f"             {a['resumen'][:90]}…")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--show',  action='store_true')
    ap.add_argument('--merge', metavar='JSON', help='Fusionar con este archivo JSON')
    args = ap.parse_args()

    items = run()
    if args.show:
        show(items)
    if args.merge:
        n = merge_into(args.merge, items)
        print(f"\n  Fusionados {n} artículos nuevos en {args.merge}")
