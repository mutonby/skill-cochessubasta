#!/usr/bin/env python3
"""
boe_search.py — Busca vehiculos en subasta en subastas.boe.es (sin login, sin BBDD).

Consulta la busqueda avanzada publica del portal de subastas del BOE y, para cada
resultado, lee el detalle publico (ver=1) para obtener valor de subasta, puja minima
y fecha de conclusion. No requiere sesion: solo httpx.

Uso:
    python boe_search.py [opciones]

Ejemplos:
    python boe_search.py                                  # turismos celebrandose
    python boe_search.py --max-precio 8000 --sort precio  # los mas baratos primero
    python boe_search.py --subtipo industriales --provincia 28
    python boe_search.py --estado PU --json               # proximas aperturas, con JSON

Opciones principales:
    --subtipo    turismos (defecto) | industriales | otros | todos
    --estado     EJ celebrandose (defecto) | PU proxima apertura
    --provincia  codigo INE de 2 digitos (28=Madrid, 46=Valencia, 30=Murcia...)
    --max-precio filtra por valor subasta maximo (EUR)
    --min-precio filtra por valor subasta minimo (EUR)
    --sort       fin (defecto, fecha de conclusion) | precio
    --limit      max resultados a detallar (defecto 60)
    --json       imprime ademas un bloque JSON estructurado

Salida: tabla Markdown por stdout. El idSub de cada fila se pasa a boe_extract.py.
"""
import re
import sys
import html
import json
import time
import argparse

try:
    import httpx
except ImportError:
    sys.exit("Falta httpx: pip install httpx")

BASE = "https://subastas.boe.es"
SEARCH_URL = f"{BASE}/subastas_ava.php"
DETAIL_URL = f"{BASE}/detalleSubasta.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "es-ES,es;q=0.9",
}

SUBTIPOS = {"turismos": "9101", "industriales": "9102", "otros": "9103", "todos": ""}


def clean(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_eur(value):
    """'6.130,00 €' -> 6130.0 (None si no parsea)."""
    if not value:
        return None
    m = re.search(r"([\d.]+),(\d{2})", value)
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "") + "." + m.group(2))
    except ValueError:
        return None


def parse_table(html_text):
    fields = {}
    for th, td in re.findall(r"<th>(.*?)</th>\s*<td>(.*?)</td>", html_text, re.DOTALL):
        label = clean(th).lower()
        value = clean(td)
        if value and value not in ("-", "No consta"):
            fields[label] = value
    return fields


def search_pages(client, estado, subtipo, provincia):
    """Itera las paginas de resultados de la busqueda avanzada publica."""
    params = [
        ("campo[0]", "SUBASTA.ORIGEN"), ("dato[0]", ""),
        ("campo[1]", "SUBASTA.AUTORIDAD"), ("dato[1]", ""),
        ("campo[2]", "SUBASTA.ESTADO.CODIGO"), ("dato[2]", estado),
        ("campo[3]", "BIEN.TIPO"), ("dato[3]", "V"),
        ("dato[4]", subtipo),
        ("campo[5]", "BIEN.DIRECCION"), ("dato[5]", ""),
        ("campo[6]", "BIEN.CODPOSTAL"), ("dato[6]", ""),
        ("campo[7]", "BIEN.LOCALIDAD"), ("dato[7]", ""),
        ("campo[8]", "BIEN.COD_PROVINCIA"), ("dato[8]", provincia),
        ("page_hits", "50"),
        ("sort_field[0]", "SUBASTA.FECHA_FIN"), ("sort_order[0]", "asc"),
        ("accion", "Buscar"),
    ]
    url, query = SEARCH_URL, params
    while True:
        r = client.get(url, params=query, headers=HEADERS)
        r.raise_for_status()
        yield r.text
        m = re.search(r'<a href="\.?/?(subastas_ava\.php\?[^"]*accion=Mas[^"]*)"[^>]*>\s*'
                      r'(?:<abbr[^>]*>[^<]*</abbr>)?\s*siguiente', r.text)
        if not m:
            break
        url, query = f"{BASE}/{html.unescape(m.group(1))}", None


def parse_results(page_html):
    """Bloques <li class="resultado-busqueda"> -> dicts basicos."""
    items = []
    for block in re.findall(r'<li class="resultado-busqueda">(.*?)</li>\s*</ul>\s*</li>',
                            page_html, re.DOTALL):
        id_m = re.search(r"idSub=(SUB-[A-Z0-9\-]+)", block)
        if not id_m:
            continue
        desc = re.findall(r"<p>(.*?)</p>", block, re.DOTALL)
        estado_txt = next((clean(d) for d in desc if clean(d).startswith("Estado:")), "")
        conclusion = ""
        m = re.search(r"Conclusi[oó]n prevista:\s*([\d/]+\s+a las\s+[\d:]+)", estado_txt)
        if m:
            conclusion = m.group(1)
        vehiculo = next((clean(d) for d in desc if not clean(d).startswith("Estado:")), "")
        autoridad = re.search(r"<h4>(.*?)</h4>", block, re.DOTALL)
        items.append({
            "idSub": id_m.group(1),
            "vehiculo": vehiculo,
            "autoridad": clean(autoridad.group(1)) if autoridad else "",
            "conclusion": conclusion,
        })
    return items


def fetch_detail(client, id_sub, need_vehicle=False):
    """Detalle publico (ver=1): precios y fechas. Sin login.
    Con need_vehicle, lee tambien la pestana de bienes (ver=3, tambien publica)
    para sacar marca/modelo (las judiciales solo listan 'Expediente: ...')."""
    r = client.get(DETAIL_URL, params={"idSub": id_sub, "ver": "1"}, headers=HEADERS)
    r.raise_for_status()
    f = parse_table(r.text)
    valor = f.get("valor subasta") or f.get("tasacion") or f.get("tasación")
    data = {
        "valor_subasta": valor,
        "valor_eur": parse_eur(valor),
        "puja_minima": f.get("puja minima") or f.get("puja mínima"),
        "deposito": f.get("importe del deposito") or f.get("importe del depósito"),
        "fecha_conclusion": f.get("fecha de conclusion") or f.get("fecha de conclusión"),
        "lotes": f.get("lotes"),
        "url": f"{DETAIL_URL}?idSub={id_sub}",
    }
    if need_vehicle:
        r3 = client.get(DETAIL_URL, params={"idSub": id_sub, "ver": "3"}, headers=HEADERS)
        f3 = parse_table(r3.text)
        vehiculo = " ".join(x for x in [f3.get("marca"), f3.get("modelo")] if x) \
            or f3.get("descripcion") or f3.get("descripción")
        if vehiculo:
            data["vehiculo"] = vehiculo
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--subtipo", choices=sorted(SUBTIPOS), default="turismos")
    ap.add_argument("--estado", choices=["EJ", "PU"], default="EJ",
                    help="EJ=celebrandose (defecto), PU=proxima apertura")
    ap.add_argument("--provincia", default="", help="Codigo INE de 2 digitos (28=Madrid...)")
    ap.add_argument("--max-precio", type=float, default=None)
    ap.add_argument("--min-precio", type=float, default=None)
    ap.add_argument("--sort", choices=["fin", "precio"], default="fin")
    ap.add_argument("--limit", type=int, default=60, help="Max subastas a detallar")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    with httpx.Client(timeout=40.0, follow_redirects=True) as client:
        seen, items = set(), []
        for page in search_pages(client, args.estado, SUBTIPOS[args.subtipo], args.provincia):
            for it in parse_results(page):
                if it["idSub"] not in seen:
                    seen.add(it["idSub"])
                    items.append(it)
        total = len(items)
        items = items[:args.limit]

        for i, it in enumerate(items):
            no_vehiculo = not it["vehiculo"] or it["vehiculo"].startswith("Expediente")
            try:
                it.update(fetch_detail(client, it["idSub"], need_vehicle=no_vehiculo))
            except Exception as e:
                print(f"  aviso: sin detalle para {it['idSub']}: {e}", file=sys.stderr)
            if i < len(items) - 1:
                time.sleep(0.3)  # no castigar al BOE

    if args.min_precio is not None:
        items = [i for i in items if i.get("valor_eur") and i["valor_eur"] >= args.min_precio]
    if args.max_precio is not None:
        items = [i for i in items if i.get("valor_eur") and i["valor_eur"] <= args.max_precio]
    if args.sort == "precio":
        items.sort(key=lambda i: i.get("valor_eur") or float("inf"))

    print(f"# Vehiculos en subasta BOE ({args.subtipo}, estado {args.estado})")
    print(f"\n{len(items)} mostrados de {total} encontrados\n")
    print("| idSub | Vehiculo | Valor subasta | Puja minima | Conclusion | Autoridad |")
    print("|---|---|---|---|---|---|")
    for it in items:
        print("| {idSub} | {vehiculo} | {valor} | {puja} | {fin} | {aut} |".format(
            idSub=it["idSub"],
            vehiculo=(it.get("vehiculo") or "")[:60],
            valor=it.get("valor_subasta") or "?",
            puja=it.get("puja_minima") or "?",
            fin=it.get("fecha_conclusion") or it.get("conclusion") or "?",
            aut=(it.get("autoridad") or "")[:40],
        ))

    if args.json:
        print("\n<!-- JSON -->")
        print(json.dumps(items, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
