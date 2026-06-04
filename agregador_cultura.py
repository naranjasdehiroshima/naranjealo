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

    # ── TV / RADIO UNIVERSIDAD ────────────────────────────────────────────────
    # TV UNAM: YouTube RSS (canal verificado jun-2026, mezcla cultura/ciencia/UNAM)
    {
        "url":      "https://www.youtube.com/feeds/videos.xml?channel_id=UCrnbT_nd9Dvg87PXefx7pQA",
        "cat_pref": "cultura",
        "nombre":   "TV UNAM",
        "idioma":   "es",
    },
    # Horizonte 107.9: WordPress sin feed de posts activo (jun-2026).
    # Su contenido vive en la web pero no publican artículos en CMS.
    # Pendiente: si activan blog, URL sería https://horizonte.fm/feed/
    # Radio UNAM: servidor con timeout persistente (jun-2026).
    # Pendiente reintento cuando restauren servicio.

    # ── FILMOTECAS MUNDIALES / RESTAURACIONES ────────────────────────────────
    # BFI (British Film Institute) — noticias, restauraciones, retrospectivas
    {
        "url":      "https://www.bfi.org.uk/rss-feed",
        "cat_pref": "cine",
        "nombre":   "BFI (British Film Institute)",
        "idioma":   "en",
    },
    # Museum of the Moving Image NYC — archivo, tecnología, exhibición
    {
        "url":      "https://movingimage.org/feed/",
        "cat_pref": "cine",
        "nombre":   "Museum of the Moving Image",
        "idioma":   "en",
    },

    # ── PERIODISMO CULTURAL (ESPAÑA) ─────────────────────────────────────────
    # El Salto Diario: periodismo cooperativo, sección cultura/global activa
    {
        "url":      "https://www.elsaltodiario.com/general/feed",
        "cat_pref": "cultura",
        "nombre":   "El Salto Diario",
        "idioma":   "es",
    },

    # ── RADIO ─────────────────────────────────────────────────────────────────
    # Horizonte Jazz 107.9 FM (IMER) — noticias y conciertos de jazz/world music
    # Sitio real: imer.mx/horizonte (no horizonte.fm, que es una radio argentina)
    {
        "url":      "https://www.imer.mx/horizonte/feed/",
        "cat_pref": "música",
        "nombre":   "Horizonte Jazz 107.9",
        "idioma":   "es",
    },

    # S8 Cinema — festival de cine experimental de Galicia, crítica y entrevistas
    {
        "url":      "https://s8cinema.com/feed/",
        "cat_pref": "cine",
        "nombre":   "S8 Cinema",
        "idioma":   "es",
    },

    # Radio UNAM — noticias, cultura, ciencia (feed confirmado jun-2026)
    # Nota: el servidor bloquea requests desde IPs externas pero el feed
    # es accesible desde navegador. GitHub Actions puede tener el mismo problema;
    # si falla silenciosamente, usar feedparser con headers de navegador completos.
    {
        "url":      "https://www.radio.unam.mx/?feed=rss2",
        "cat_pref": "cultura",
        "nombre":   "Radio UNAM",
        "idioma":   "es",
    },


    # ── CANALES YOUTUBE — CRÍTICA Y ANÁLISIS DE CINE EN ESPAÑOL ────────────────────
    {"url":"https://www.youtube.com/feeds/videos.xml?channel_id=UC_tTK6d5PI3u4IMf39TIRZA",
     "cat_pref":"cine","nombre":"Subterráneo",     "idioma":"es","filtro":"cine"},
    {"url":"https://www.youtube.com/feeds/videos.xml?channel_id=UCHFuv4lXAboKNH9Uu84hKjw",
     "cat_pref":"cine","nombre":"Fuera de Foco",   "idioma":"es","filtro":"cine"},
    {"url":"https://www.youtube.com/feeds/videos.xml?channel_id=UCU-3M9L6PuahR--g2TN03pA",
     "cat_pref":"cine","nombre":"Zep Films",       "idioma":"es","filtro":"cine"},
    {"url":"https://www.youtube.com/feeds/videos.xml?channel_id=UCVahH6dIcO_pI2yZyqYhF0w",
     "cat_pref":"cine","nombre":"Álvaro Wasabi",   "idioma":"es","filtro":"cine"},
    {"url":"https://www.youtube.com/feeds/videos.xml?channel_id=UCukfhmwOCX_LMlldg9gO9NQ",
     "cat_pref":"cine","nombre":"SensaCine México","idioma":"es","filtro":"cine"},


    # ── DOCUMENTAL ────────────────────────────────────────────────────────────
    {
        "url":      "https://documentary.org/rss.xml",
        "cat_pref": "documental",
        "nombre":   "IDA (International Documentary Assoc.)",
        "idioma":   "en",
        "filtro":   "cine",
    },
    {
        "url":      "https://blog.nfb.ca/feed/",
        "cat_pref": "documental",
        "nombre":   "NFB Blog (National Film Board Canada)",
        "idioma":   "en",
        "filtro":   "cine",
    },
    {
        "url":      "https://filmmakermagazine.com/feed/",
        "cat_pref": "cine",
        "nombre":   "Filmmaker Magazine",
        "idioma":   "en",
        "filtro":   "cine",
    },

    # ── ARCHIVOS / PRESERVACIÓN / DOMINIO PÚBLICO ─────────────────────────────
    {
        "url":      "https://blog.archive.org/feed/",
        "cat_pref": "archivos",
        "nombre":   "Internet Archive Blog",
        "idioma":   "en",
    },
    {
        "url":      "https://publicdomainreview.org/feed/",
        "cat_pref": "dominio público",
        "nombre":   "Public Domain Review",
        "idioma":   "en",
    },
    {
        "url":      "https://www.openculture.com/feed",
        "cat_pref": "cultura",
        "nombre":   "Open Culture",
        "idioma":   "en",
    },

    # ── FILMOTECAS ────────────────────────────────────────────────────────────
    {
        "url":      "https://cinemateca.org.br/feed/",
        "cat_pref": "archivos",
        "nombre":   "Cinemateca Brasileira",
        "idioma":   "pt",
    },

    # ── MÚSICA ESPECIALIZADA ──────────────────────────────────────────────────
    {
        "url":      "https://www.youtube.com/feeds/videos.xml?channel_id=UCcp-HjtmTMeIJ-0RrSHSGLA",
        "cat_pref": "música",
        "nombre":   "Rick Beato",
        "idioma":   "en",
        "filtro":   "musica",
    },
    {
        "url":      "https://www.gladyspalmera.com/feed/",
        "cat_pref": "música",
        "nombre":   "Radio Gladys Palmera",
        "idioma":   "es",
    },

    # ── NARANJAS DE HIROSHIMA ─────────────────────────────────────────────────
    {
        "url":      "https://www.naranjasdehiroshima.com/feeds/posts/default?alt=rss",
        "cat_pref": "cine",
        "nombre":   "Naranjas de Hiroshima",
        "idioma":   "es",
    },

    # ── MEDIOS ALTERNATIVOS / PERIODISMO ──────────────────────────────────────
    {
        "url":      "https://www.periodismodebarrio.org/feed/",
        "cat_pref": "cultura",
        "nombre":   "Periodismo de Barrio",
        "idioma":   "es",
    },


    # ── RESTAURACIÓN / ARCHIVOS FÍLMICOS ADICIONALES ─────────────────────
    {
        "url":      "https://silentlondon.co.uk/feed/",
        "cat_pref": "archivos",
        "nombre":   "Silent London",
        "idioma":   "en",
    },
    {
        "url":      "https://www.eastman.org/rss.xml",
        "cat_pref": "archivos",
        "nombre":   "George Eastman Museum",
        "idioma":   "en",
    },
    {
        "url":      "https://www.cclm.cl/feed/",
        "cat_pref": "cine",
        "nombre":   "Cineteca Nacional de Chile",
        "idioma":   "es",
    },
    # ── PENDIENTES (sin RSS funcional a jun-2026) ─────────────────────────────
    # Canal 14 / Once TV: timeouts persistentes — su YouTube (@OnceMexico)
    #   tiene contenido variado sin foco cultural claro.
    # Horizonte 107.9: sin feed de posts. Considerar scraping manual de agenda.
    # Radio UNAM: timeout persistente. Monitorear.
    # Cinémathèque Française, Eye Filmmuseum, Eastman: sin RSS accesible.
    #   Alternativa: suscribirse a sus newsletters y forwardear a un RSS propio.

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
    "documental": [
        "documental", "documentary", "documentaire", "non-fiction",
        "reportaje", "cronista", "periodismo", "testimonio",
        "doc film", "doc series", "nfb", "hot docs", "idfa",
    ],
    "archivos": [
        "archivo", "archiv", "preservación", "preservation", "restauración",
        "restoration", "filmoteca", "cinemateca", "patrimonio fílmico",
        "moving image archive", "film archive", "audiovisual heritage",
        "nitrate", "nitrato", "digitization", "digitalización",
        "amia", "fiaf", "fiat", "memoria audiovisual",
    ],
    "dominio público": [
        "dominio público", "public domain", "creative commons",
        "libre acceso", "open access", "copyleft", "licencia libre",
        "commons", "open culture", "cultura libre", "free culture",
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

# ─── FILTRO DE CONTENIDO IRRELEVANTE ─────────────────────────────────────────
_BASURA = [
    "futbol","fútbol","mundial","gol","partido","liga mx","nfl","nba","mlb",
    "boxeo","mma","f1","formula 1","playera","jersey","fichaje",
    "reality","got talent","gran hermano","la casa de los famosos",
    "masterchef","survivor","tiktok viral","influencer",
    "asesinato","narcotráfico","cártel","secuestro","elecciones",
    "candidato","partido político","senado","diputado",
    "kardashian","#shorts","#short","#viral",
]

_TRANS = str.maketrans("áéíóúàèìòùäëïöüñ", "aeiouaeiouaeioun")

def _tn(s: str) -> str:
    return s.lower().translate(_TRANS)

def es_valido(titulo: str, filtro: str = "") -> bool:
    tn = _tn(titulo)
    if "#short" in tn:
        return False
    hits = sum(1 for w in _BASURA if _tn(w) in tn)
    if hits >= 2:
        return False
    if filtro == "cine":
        ok = ["pelicul","film","cine","serie","director","guion","estreno",
              "critica","reseña","analisis","oscar","festival","actor","actriz",
              "documental","trailer","clasico","historia","nuevo","mejor",
              "cinemat","produccion"]
        if not any(_tn(k) in tn for k in ok):
            return False
    if filtro == "musica":
        ok = ["music","guitar","piano","jazz","album","song","record","chord",
              "musician","composer","vinyl","band","teoria","armonia","ritmo",
              "instrumento","technique","producer","studio","tour","concierto"]
        if not any(_tn(k) in tn for k in ok):
            return False
    return True

# ─── CLASIFICACIÓN ────────────────────────────────────────────────────────────
def clasificar(titulo: str, resumen: str, cat_pref: str) -> str:
    texto = _tn(titulo + " " + (resumen or ""))
    scores = {}
    for cat, kws in KEYWORDS.items():
        scores[cat] = sum(1 for k in kws if _tn(k) in texto)
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
        # Usamos headers de navegador real para evitar bloqueos (ej. Radio UNAM)
        feed = feedparser.parse(f["url"], request_headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        })
    except Exception as e:
        print(f"  ✗ {e}")
        return []

    filtro = f.get("filtro", "")
    items = []
    for entry in feed.entries[:20]:
        url = entry.get("link", "")
        if not url:
            continue
        titulo  = limpiar_html(entry.get("title", "Sin título"))
        if not es_valido(titulo, filtro):
            continue
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

# ─── ENRIQUECIMIENTO DE IMÁGENES ─────────────────────────────────────────────

def enriquecer_imagenes(conn, limite: int = 200):
    """Busca og:image para artículos que no tienen imagen."""
    import requests as req
    from concurrent.futures import ThreadPoolExecutor, as_completed

    hdrs = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36'}

    rows = conn.execute("""
        SELECT id, url FROM articulos
        WHERE (imagen IS NULL OR imagen = '')
        ORDER BY fecha_scrape DESC LIMIT ?
    """, (limite,)).fetchall()

    if not rows:
        return 0

    def fetch(id_url):
        uid, url = id_url
        try:
            r = req.get(url, headers=hdrs, timeout=6, allow_redirects=True)
            m = re.search(r'og:image[^>]*content=["\']([^"\']+)', r.text) or re.search(r'content=["\']([^"\']+)[^>]*og:image', r.text)
            if not m:
                m = None  # already handled above
            if m:
                img = m.group(1).strip()
                if img.startswith('http'):
                    return uid, img
        except Exception:
            pass
        return uid, None

    found = 0
    with ThreadPoolExecutor(max_workers=15) as ex:
        for uid, img in ex.map(fetch, rows):
            if img:
                conn.execute("UPDATE articulos SET imagen=? WHERE id=?", (img, uid))
                found += 1
    conn.commit()
    return found

# ─── EXPORT JSON ──────────────────────────────────────────────────────────────

def exportar_json(conn, path: str = JSON_PATH):
    import random
    rows = conn.execute("""
        SELECT id,titulo,url,resumen,imagen,fuente,idioma,categoria,fecha_pub
        FROM articulos
        ORDER BY fecha_pub DESC, fecha_scrape DESC
        LIMIT 800
    """).fetchall()
    cols = ["id","titulo","url","resumen","imagen","fuente","idioma","categoria","fecha_pub"]
    data = [dict(zip(cols, r)) for r in rows]

    # Separar por idioma: español tiene el doble de peso en el mix
    es  = [a for a in data if a.get("idioma") == "es"]
    en  = [a for a in data if a.get("idioma") == "en"]
    oth = [a for a in data if a.get("idioma") not in ("es","en")]

    random.shuffle(es)
    random.shuffle(en)
    random.shuffle(oth)

    # Intercalar: 2 en español por cada 1 en inglés
    mezclado = []
    i_es, i_en = 0, 0
    while i_es < len(es) or i_en < len(en):
        if i_es < len(es): mezclado.append(es[i_es]); i_es += 1
        if i_es < len(es): mezclado.append(es[i_es]); i_es += 1
        if i_en < len(en): mezclado.append(en[i_en]); i_en += 1
    mezclado += oth

    with open(path, "w", encoding="utf-8") as f:
        json.dump(mezclado, f, ensure_ascii=False, indent=2)
    print(f"✓ JSON exportado → {path}  ({len(mezclado)} artículos, proporción 2:1 ES/EN)")

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

    print(f"\n  Buscando imágenes faltantes...", end="", flush=True)
    n_imgs = enriquecer_imagenes(conn)
    print(f" {n_imgs} nuevas")

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
