#!/usr/bin/env python3
"""
Agregador automático — Arte, Cultura, Cine, Música, Arqueología, Ciencia
Fuentes verificadas: México · LATAM · España · EEUU (archivos fílmicos/museos)

Uso:
  python3 agregador_cultura.py             # scraping + guarda en BD
  python3 agregador_cultura.py --export-json
  python3 agregador_cultura.py --show
  python3 agregador_cultura.py --stats
"""

import sqlite3, json, hashlib, argparse, re, sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests

DB_PATH   = "cultura.db"
JSON_PATH = "articulos.json"

# ─── FUENTES VERIFICADAS ──────────────────────────────────────────────────────
# Todas probadas en junio 2026. cat_pref = categoría por defecto si keywords no
# logran clasificar el artículo.

FUENTES = [

    # ── ARQUEOLOGÍA / PATRIMONIO MEXICANO ─────────────────────────────────────
    {
        "url":      "http://www.arqueologiamexicana.mx/rss.xml",
        "cat_pref": "arqueología",
        "nombre":   "Arqueología Mexicana",
        "idioma":   "es",
    },
    {
        "url":      "https://www.inah.gob.mx/boletines?format=feed&type=rss",
        "cat_pref": "arqueología",
        "nombre":   "INAH Boletines",
        "idioma":   "es",
    },
    {
        "url":      "https://www.jornada.com.mx/rss/cultura.xml",
        "cat_pref": "cultura",
        "nombre":   "La Jornada Cultura",
        "idioma":   "es",
    },
    {
        "url":      "https://www.jornada.com.mx/rss/ciencias.xml",
        "cat_pref": "ciencia",
        "nombre":   "La Jornada Ciencias",
        "idioma":   "es",
    },

    # ── CULTURA / ENSAYO MÉXICO ───────────────────────────────────────────────
    {
        "url":      "https://www.nexos.com.mx/?feed=rss2",
        "cat_pref": "cultura",
        "nombre":   "Nexos",
        "idioma":   "es",
    },
    {
        "url":      "https://letraslibres.com/feed/",
        "cat_pref": "cultura",
        "nombre":   "Letras Libres",
        "idioma":   "es",
    },
    {
        "url":      "https://estepais.com/feed/",
        "cat_pref": "cultura",
        "nombre":   "Este País",
        "idioma":   "es",
    },
    {
        "url":      "https://www.gaceta.unam.mx/feed/",
        "cat_pref": "ciencia",
        "nombre":   "Gaceta UNAM",
        "idioma":   "es",
    },

    # ── CINE / ARCHIVOS FÍLMICOS ──────────────────────────────────────────────
    {
        "url":      "https://www.filmoteca.unam.mx/feed",  # 301 → sigue
        "cat_pref": "cine",
        "nombre":   "Filmoteca UNAM",
        "idioma":   "es",
    },
    {
        "url":      "https://blog.archive.org/category/movie-archive/feed/",
        "cat_pref": "cine",
        "nombre":   "Internet Archive (cine)",
        "idioma":   "en",
    },
    {
        "url":      "https://blogs.loc.gov/now-see-hear/feed/",
        "cat_pref": "cine",
        "nombre":   "Library of Congress (film/audio)",
        "idioma":   "en",
    },
    {
        "url":      "https://mubi.com/notebook/posts.atom",
        "cat_pref": "cine",
        "nombre":   "MUBI Notebook",
        "idioma":   "en",
    },
    {
        "url":      "https://filmquarterly.org/feed/",
        "cat_pref": "cine",
        "nombre":   "Film Quarterly",
        "idioma":   "en",
    },
    {
        "url":      "https://cineuropa.org/es/rss/news.aspx",
        "cat_pref": "cine",
        "nombre":   "Cineuropa (ES)",
        "idioma":   "es",
    },
    {
        "url":      "https://variety.com/v/film/feed/",
        "cat_pref": "cine",
        "nombre":   "Variety Film",
        "idioma":   "en",
    },

    # ── ARTE / MUSEOS ─────────────────────────────────────────────────────────
    {
        "url":      "https://hyperallergic.com/feed/",
        "cat_pref": "arte",
        "nombre":   "Hyperallergic",
        "idioma":   "en",
    },
    {
        "url":      "https://www.artnews.com/feed/",
        "cat_pref": "arte",
        "nombre":   "ARTnews",
        "idioma":   "en",
    },
    {
        "url":      "https://www.artforum.com/feed",
        "cat_pref": "arte",
        "nombre":   "Artforum",
        "idioma":   "en",
    },
    {
        "url":      "https://www.smithsonianmag.com/rss/latest_articles/",
        "cat_pref": "cultura",
        "nombre":   "Smithsonian Magazine",
        "idioma":   "en",
    },

    # ── MÚSICA LATAM / ESPECIALIZADA ─────────────────────────────────────────
    {
        "url":      "https://soundsandcolours.com/feed/",
        "cat_pref": "música",
        "nombre":   "Sounds and Colours (LATAM)",
        "idioma":   "en",
    },

    # ── CIENCIA / NATURALEZA ──────────────────────────────────────────────────
    {
        "url":      "https://www.sciencedaily.com/rss/top/science.xml",
        "cat_pref": "ciencia",
        "nombre":   "Science Daily",
        "idioma":   "en",
    },
    {
        "url":      "https://phys.org/rss-feed/",
        "cat_pref": "ciencia",
        "nombre":   "Phys.org",
        "idioma":   "en",
    },
]

# ─── KEYWORDS POR CATEGORÍA ───────────────────────────────────────────────────
# Añadidas variantes en inglés para fuentes en ese idioma.

KEYWORDS = {
    "arqueología": [
        "arqueolog", "excavac", "yacimiento", "hallazgo", "fósil", "prehispán",
        "mesoamér", "maya", "azteca", "olmeca", "teotihuac", "zapotec", "mixtec",
        "toltec", "inca", "moche", "nazca", "precolomb",
        "artifact", "burial", "ancient", "excavation", "fossil", "mummy",
        "prehistoric", "paleontolog", "neolithic", "bronze age", "iron age",
    ],
    "arte": [
        "museo", "exposición", "pintura", "escultura", "galería", "obra de arte",
        "artista", "bienal", "instalación", "grabado", "arte contemporáneo",
        "patrimonio artístico", "muralismo", "colección",
        "museum", "exhibition", "painting", "sculptor", "gallery", "artwork",
        "biennale", "installation", "contemporary art", "retrospective",
        "collection", "curator", "mural",
    ],
    "cine": [
        "película", "film", "cine", "director", "cineteca", "filmoteca",
        "archivo fílmico", "restauración fílmica", "nitrato", "35mm", "16mm",
        "dominio público", "patrimonio fílmico", "cinemateca",
        "film archive", "moving image", "restoration", "nitrate", "celluloid",
        "silent film", "documentary", "cinematheque", "film festival",
        "cannes", "berlín", "venecia", "sundance", "tribeca",
    ],
    "música": [
        "música", "álbum", "concierto", "festival", "banda", "compositor",
        "jazz", "ópera", "orquesta", "sinfónica", "grabación", "disco",
        "latin music", "cumbia", "bolero", "son", "folklor", "trova",
        "album", "concert", "musician", "composer", "symphony", "jazz",
        "recording", "vinyl", "soundtrack",
    ],
    "ciencia": [
        "científic", "investigación", "descubrimiento", "estudio", "universo",
        "física", "química", "biología", "genética", "inteligencia artificial",
        "astronomía", "partícula", "researcher", "discovery", "study",
        "physics", "chemistry", "biology", "genetics", "astronomy",
        "climate", "quantum", "space", "nasa", "telescope",
    ],
    "naturaleza": [
        "especie", "extinción", "biodiversidad", "ecosistema", "selva", "océano",
        "migración", "ave", "mamífero", "reptil", "flora", "fauna",
        "species", "extinction", "biodiversity", "ecosystem", "forest",
        "ocean", "migration", "bird", "mammal", "conservation", "wildlife",
        "coral reef", "climate change", "deforestation",
    ],
    "cultura": [
        "cultura", "literatura", "libro", "escritor", "poesía", "novela",
        "patrimonio cultural", "tradición", "festividad", "ceremonia",
        "ensayo", "universidad", "educación", "lengua indígena",
        "culture", "literature", "book", "writer", "poetry", "novel",
        "heritage", "tradition", "ceremony", "indigenous", "language",
    ],
}

CATEGORIAS = ["arqueología", "cine", "arte", "música", "ciencia", "naturaleza", "cultura"]

# ─── BASE DE DATOS ────────────────────────────────────────────────────────────

def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articulos (
            id           TEXT PRIMARY KEY,
            titulo       TEXT NOT NULL,
            url          TEXT NOT NULL,
            resumen      TEXT,
            imagen       TEXT,
            fuente       TEXT,
            idioma       TEXT,
            categoria    TEXT,
            fecha_pub    TEXT,
            fecha_scrape TEXT
        )
    """)
    # Add idioma column if upgrading from older DB
    try:
        conn.execute("ALTER TABLE articulos ADD COLUMN idioma TEXT")
    except Exception:
        pass
    conn.commit()

def url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

# ─── CLASIFICACIÓN ────────────────────────────────────────────────────────────

_TRANS = str.maketrans("áéíóúàèìòùäëïöüñ", "aeiouaeiouaeioun")

def clasificar(titulo: str, resumen: str, cat_pref: str) -> str:
    texto = (titulo + " " + (resumen or "")).lower().translate(_TRANS)
    scores = {}
    for cat, kws in KEYWORDS.items():
        scores[cat] = sum(1 for k in kws if k.translate(_TRANS) in texto)
    mejor = max(scores, key=scores.get)
    return mejor if scores[mejor] > 0 else cat_pref

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def limpiar_html(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&[a-z#0-9]+;", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:350]

def extraer_imagen(entry) -> str:
    for attr in ("media_thumbnail", "media_content"):
        v = getattr(entry, attr, None)
        if v:
            return v[0].get("url", "")
    if getattr(entry, "enclosures", None):
        for enc in entry.enclosures:
            if enc.get("type", "").startswith("image"):
                return enc.get("href", "")
    summary = entry.get("summary", "") or ""
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', summary)
    return m.group(1) if m else ""

def scrape_fuente(f: dict) -> list[dict]:
    print(f"  → {f['nombre']}", end="", flush=True)
    try:
        feed = feedparser.parse(f["url"])
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    items = []
    for entry in feed.entries[:20]:
        url = entry.get("link", "")
        if not url:
            continue
        titulo  = limpiar_html(entry.get("title", "Sin título"))
        resumen = limpiar_html(entry.get("summary", "") or entry.get("description", ""))
        imagen  = extraer_imagen(entry)
        fecha_pub = ""
        if getattr(entry, "published_parsed", None):
            try:
                fecha_pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
        items.append({
            "id":           url_hash(url),
            "titulo":       titulo,
            "url":          url,
            "resumen":      resumen,
            "imagen":       imagen,
            "fuente":       f["nombre"],
            "idioma":       f.get("idioma", "?"),
            "categoria":    clasificar(titulo, resumen, f["cat_pref"]),
            "fecha_pub":    fecha_pub,
            "fecha_scrape": datetime.now(timezone.utc).isoformat(),
        })
    print(f"  {len(items)} artículos")
    return items

def guardar(conn, items: list[dict]) -> int:
    nuevos = 0
    for a in items:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO articulos
                  (id,titulo,url,resumen,imagen,fuente,idioma,categoria,fecha_pub,fecha_scrape)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (a["id"],a["titulo"],a["url"],a["resumen"],a["imagen"],
                  a["fuente"],a["idioma"],a["categoria"],a["fecha_pub"],a["fecha_scrape"]))
            if conn.execute("SELECT changes()").fetchone()[0]:
                nuevos += 1
        except Exception as e:
            print(f"    ✗ DB: {e}")
    conn.commit()
    return nuevos

# ─── EXPORT JSON ──────────────────────────────────────────────────────────────

def exportar_json(conn, path: str = JSON_PATH):
    rows = conn.execute("""
        SELECT id,titulo,url,resumen,imagen,fuente,idioma,categoria,fecha_pub
        FROM articulos
        ORDER BY fecha_pub DESC, fecha_scrape DESC
        LIMIT 800
    """).fetchall()
    cols = ["id","titulo","url","resumen","imagen","fuente","idioma","categoria","fecha_pub"]
    data = [dict(zip(cols, r)) for r in rows]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✓ JSON exportado → {path}  ({len(data)} artículos)")

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_scraper():
    print(f"\n{'='*62}")
    print(f"  Agregador Cultura  ·  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*62}")
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    total = 0
    for fuente in FUENTES:
        items  = scrape_fuente(fuente)
        nuevos = guardar(conn, items)
        total += nuevos

    stats = conn.execute(
        "SELECT categoria, COUNT(*) FROM articulos GROUP BY categoria ORDER BY 2 DESC"
    ).fetchall()
    print(f"\n  Nuevos esta corrida: {total}")
    print(f"\n  BD acumulada por categoría:")
    for cat, n in stats:
        print(f"    {cat:<14} {n:>4}  {'█' * min(n//3,28)}")
    conn.close()

def show_recent(n=25):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT titulo,fuente,categoria,fecha_pub
        FROM articulos ORDER BY fecha_pub DESC, fecha_scrape DESC LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    print(f"\nÚltimos {n} artículos:")
    print("─"*82)
    for t, f, c, d in rows:
        print(f"[{c:<13}]  {(d or '?')[:10]}  {f:<28}  {t[:45]}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run",          action="store_true")
    ap.add_argument("--export-json",  action="store_true")
    ap.add_argument("--show",         action="store_true")
    args = ap.parse_args()

    if args.run or not any(vars(args).values()):
        run_scraper()
    if args.export_json:
        conn = sqlite3.connect(DB_PATH)
        init_db(conn)
        exportar_json(conn)
        conn.close()
    if args.show:
        show_recent()
