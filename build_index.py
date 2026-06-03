#!/usr/bin/env python3
"""
build_index.py — inyecta articulos.json y cartelera.json en index.html.
No necesita template — lee el index.html existente y reemplaza los datos.
GitHub Actions lo corre después de los scrapers.
También funciona localmente: python3 build_index.py
"""
import json, re
from pathlib import Path

def clean(s):
    if not s: return ""
    s = re.sub(r"&#\d+;", " ", s)
    s = re.sub(r"&[a-zA-Z]+;", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def build():
    # Cargar datos
    with open("articulos.json", encoding="utf-8") as f:
        art = json.load(f)
    with open("cartelera.json", encoding="utf-8") as f:
        cart = json.load(f)

    for a in art:
        a["titulo"]  = clean(a["titulo"])
        a["resumen"] = clean(a.get("resumen", ""))
    art = [a for a in art if a.get("categoria") != "espectáculos"]

    AJ = json.dumps(art,  ensure_ascii=False)
    CJ = json.dumps(cart, ensure_ascii=False)

    # Leer index.html actual
    html = Path("index.html").read_text(encoding="utf-8")

    # Reemplazar los bloques de datos — busca las líneas const ART = ... y const CART = ...
    # y las reemplaza con los datos frescos
    html = re.sub(
        r'const ART\s*=\s*\[.*?\];',
        f'const ART  = {AJ};',
        html, flags=re.DOTALL
    )
    html = re.sub(
        r'const CART\s*=\s*\[.*?\];',
        f'const CART = {CJ};',
        html, flags=re.DOTALL
    )

    Path("index.html").write_text(html, encoding="utf-8")
    print(f"✓ index.html actualizado — {len(art)} artículos, {len(cart)} películas")

if __name__ == "__main__":
    build()
