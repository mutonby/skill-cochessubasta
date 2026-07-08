#!/usr/bin/env python3
"""
boe_extract.py — Extrae fotos + info de un vehiculo en subasta del BOE (zona autenticada).

Las fotos del vehiculo (pestana "Bienes") solo son visibles con sesion iniciada en
subastas.boe.es. La sesion se identifica con la cookie `SESSID`, que es legible desde
el navegador logado (no es httpOnly). Esta cookie es lo unico que necesita el script.

Uso:
    python boe_extract.py <idSub_o_url> --sessid <SESSID> [--out DIR] [--json]

Ejemplos:
    python boe_extract.py SUB-AT-2026-26R4686002018 --sessid 224f114926b92132b64abe900377b8
    python boe_extract.py "https://subastas.boe.es/reg/detalleSubasta.php?idSub=SUB-AT-...&ver=3" --sessid XXXX --out ./fotos

Salida: imprime un informe Markdown por stdout y guarda las fotos en --out (por defecto ./boe_<idSub>/).
Con --json imprime ademas un bloque JSON con todos los datos estructurados.
"""
import os
import re
import sys
import html
import json
import argparse

try:
    import httpx
except ImportError:
    sys.exit("Falta httpx: pip install httpx")

DETAIL_URL = "https://subastas.boe.es/reg/detalleSubasta.php"
DOC_URL = "https://subastas.boe.es/reg/verDocumento.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
    "Accept-Language": "es-ES,es;q=0.9",
}


def clean(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_id(arg):
    m = re.search(r"idSub=([A-Z0-9\-]+)", arg)
    if m:
        return m.group(1)
    return arg.strip()


def parse_table(html_text):
    """Pares <th>/<td> de las tablas de detalle del BOE."""
    fields = {}
    for th, td in re.findall(r"<th>(.*?)</th>\s*<td>(.*?)</td>", html_text, re.DOTALL):
        label = clean(th).lower()
        value = clean(td)
        if value and value not in ("-", "No consta"):
            fields[label] = value
    return fields


def extract_km(*texts):
    """Extrae el kilometraje del texto del BOE (descripcion, pliego, peritaje...).
    Devuelve un int o None. La mayoria de subastas lo indican en el texto."""
    text = " ".join(t for t in texts if t)
    if not text:
        return None
    patrones = [
        r'[Kk]ilometraje[:\s]+(?:de\s+)?([\d.]+)',
        r'[Kk]il[oó]metros[:\s]+(?:de\s+)?([\d.]+)',
        r'(?:ITV|itv)[^.]*?(\d[\d.]{3,})\s*(?:km|kil)',
        r'(\d[\d.]{3,})\s*(?:km\b|kms\b|kil[oó]metros)',
        r'[Cc]uentakil[oó]metros[^\d]{0,20}(\d[\d.]{3,})',
    ]
    for pat in patrones:
        m = re.search(pat, text)
        if m:
            try:
                km = int(m.group(1).replace('.', ''))
                if 100 <= km <= 1_000_000:  # rango plausible
                    return km
            except ValueError:
                pass
    return None


def get(client, params):
    r = client.get(DETAIL_URL, params=params, headers=HEADERS)
    r.raise_for_status()
    return r


def session_ok(resp):
    """True si seguimos en la zona autenticada (/reg/) y sin prompt de login."""
    if "/reg/" not in str(resp.url):
        return False
    if "iniciar sesi" in resp.text.lower():
        return False
    return True


def find_photo_ids(html_text):
    """idDoc de imagenes (thumbnails) en la pestana Bienes / complementaria."""
    return re.findall(
        r"verDocumento\.php\?idSub=[^&]+&(?:amp;)?idDoc=(\d+-[a-f0-9]+)[^>]*>\s*<img[^>]*imgThumbnail",
        html_text,
    )


def find_pdf_ids(html_text):
    """idDoc de PDFs (pliegos, condiciones, etc.)."""
    return re.findall(
        r'class="puntoPDF"[^>]*>\s*<a\s+href="verDocumento\.php\?idSub=[^&]+&(?:amp;)?idDoc=(\d+-[a-f0-9]+)"',
        html_text,
    )


def sniff(content):
    """Detecta el tipo real por magic bytes (el BOE a veces miente en content-type)."""
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:4] == b"%PDF":
        return "pdf"
    return None


def download_doc(client, id_sub, id_doc, retries=3):
    """Descarga un documento. Reintenta los fallos transitorios del BOE
    (a veces devuelve un html de ~40 bytes en vez de la imagen)."""
    import time
    for attempt in range(retries):
        r = client.get(DOC_URL, params={"idSub": id_sub, "idDoc": id_doc}, headers=HEADERS)
        r.raise_for_status()
        kind = sniff(r.content)
        if kind:
            return r.content, kind
        # respuesta no util (html de error / vacia) -> reintenta
        if attempt < retries - 1:
            time.sleep(1.0)
    return r.content, None


def extract_pdf_images(pdf_bytes, out_dir, start_idx):
    """Extrae imagenes grandes de un PDF (fotos servidas como PDF). Requiere PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return [], ""
    paths, text = [], ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text()
            for img in page.get_images(full=True):
                try:
                    pix = fitz.Pixmap(doc, img[0])
                    if pix.width >= 200 and pix.height >= 200:
                        if pix.n >= 5:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        idx = start_idx + len(paths) + 1
                        p = os.path.join(out_dir, f"foto_{idx}.png")
                        pix.save(p)
                        paths.append(p)
                    pix = None
                except Exception:
                    pass
        doc.close()
    except Exception:
        pass
    return paths, text.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("auction", help="idSub o URL de la subasta del BOE")
    ap.add_argument("--sessid", required=True, help="Cookie SESSID del navegador logado")
    ap.add_argument("--out", default=None, help="Carpeta de salida para las fotos")
    ap.add_argument("--json", action="store_true", help="Imprime tambien JSON estructurado")
    args = ap.parse_args()

    id_sub = parse_id(args.auction)
    out_dir = args.out or f"./boe_{id_sub}"
    os.makedirs(out_dir, exist_ok=True)

    cookies = {"SESSID": args.sessid.strip()}
    data = {"idSub": id_sub, "url": f"https://subastas.boe.es/reg/detalleSubasta.php?idSub={id_sub}"}

    with httpx.Client(timeout=40.0, follow_redirects=True, cookies=cookies) as client:
        # --- ver=1: informacion general (precios, fechas, complementaria) ---
        r1 = get(client, {"idSub": id_sub, "ver": "1"})
        if not session_ok(r1):
            sys.exit("ERROR: sesion del BOE no valida/caducada. Refresca el SESSID desde el navegador logado.")
        f1 = parse_table(r1.text)
        data["valor_subasta"] = f1.get("valor subasta") or f1.get("tasacion") or f1.get("tasación")
        data["puja_minima"] = f1.get("puja minima") or f1.get("puja mínima")
        data["deposito"] = f1.get("importe del deposito") or f1.get("importe del depósito")
        data["fecha_inicio"] = f1.get("fecha de inicio")
        data["fecha_conclusion"] = f1.get("fecha de conclusion") or f1.get("fecha de conclusión")
        data["tipo_subasta"] = f1.get("tipo de subasta")
        data["estado"] = f1.get("estado")

        # --- ver=3: pestana Bienes (datos del vehiculo + fotos) ---
        r3 = get(client, {"idSub": id_sub, "ver": "3"})
        f3 = parse_table(r3.text)
        data["matricula"] = f3.get("matricula") or f3.get("matrícula")
        data["marca"] = f3.get("marca")
        data["modelo"] = f3.get("modelo")
        data["bastidor"] = f3.get("numero de bastidor") or f3.get("número de bastidor")
        data["fecha_matriculacion"] = f3.get("fecha de matriculacion") or f3.get("fecha de matriculación")
        data["cargas"] = f3.get("cargas")
        desc = re.search(r'<div class="caja">(.*?)</div>', r3.text, re.DOTALL)
        data["descripcion"] = clean(desc.group(1)) if desc else None

        # --- Fotos (de ver=1 y ver=3) ---
        photo_ids = list(dict.fromkeys(find_photo_ids(r3.text) + find_photo_ids(r1.text)))
        pdf_ids = list(dict.fromkeys(find_pdf_ids(r1.text) + find_pdf_ids(r3.text)))

        saved, pdf_texts = [], []
        skipped = 0
        for doc_id in photo_ids:
            try:
                content, kind = download_doc(client, id_sub, doc_id)
            except Exception as e:
                print(f"  aviso: no se pudo bajar {doc_id}: {e}", file=sys.stderr)
                continue
            if kind in ("jpg", "png"):
                p = os.path.join(out_dir, f"foto_{len(saved)+1}.{kind}")
                with open(p, "wb") as fh:
                    fh.write(content)
                saved.append(p)
            elif kind == "pdf":
                imgs, txt = extract_pdf_images(content, out_dir, len(saved))
                saved.extend(imgs)
                if txt:
                    pdf_texts.append(txt)
            else:
                skipped += 1
                print(f"  aviso: {doc_id} no devolvio imagen tras reintentos", file=sys.stderr)

        # --- PDFs de condiciones/pliego: texto + posibles fotos ---
        for doc_id in pdf_ids:
            try:
                content, kind = download_doc(client, id_sub, doc_id)
            except Exception:
                continue
            if kind == "pdf":
                imgs, txt = extract_pdf_images(content, out_dir, len(saved))
                saved.extend(imgs)
                if txt and len(txt) > 100:
                    pdf_texts.append(txt)
            elif kind in ("jpg", "png"):
                p = os.path.join(out_dir, f"foto_{len(saved)+1}.{kind}")
                with open(p, "wb") as fh:
                    fh.write(content)
                saved.append(p)

        data["fotos_no_disponibles"] = skipped

        data["fotos"] = saved
        data["num_fotos"] = len(saved)
        full_docs_text = "\n\n---\n\n".join(pdf_texts) if pdf_texts else ""
        data["texto_documentos"] = full_docs_text[:8000] if full_docs_text else None

        # Kilometraje: primero del texto del BOE (descripcion + pliego/peritaje).
        # make_carousel.py intenta leerlo de las fotos si aqui sale None.
        data["km"] = extract_km(data.get("descripcion"), full_docs_text,
                                f3.get("kilometraje"), f3.get("kilometros"))

    # Volcar data.json en la carpeta de salida (lo consume make_carousel.py)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    # --- Informe Markdown ---
    def row(label, val):
        return f"| {label} | {val} |" if val else None

    titulo = " ".join(x for x in [data.get("marca"), data.get("modelo")] if x) or id_sub
    lines = [f"# 🚗 {titulo}", ""]
    lines.append(f"**Subasta BOE:** [{id_sub}]({data['url']})")
    lines.append("")
    lines.append("| Campo | Valor |")
    lines.append("|---|---|")
    for lbl, key in [
        ("Marca", "marca"), ("Modelo", "modelo"), ("Matrícula", "matricula"),
        ("Bastidor (VIN)", "bastidor"), ("Fecha matriculación", "fecha_matriculacion"),
        ("Estado subasta", "estado"), ("Valor subasta", "valor_subasta"),
        ("Puja mínima", "puja_minima"), ("Depósito", "deposito"), ("Cargas", "cargas"),
        ("Tipo subasta", "tipo_subasta"), ("Inicio", "fecha_inicio"),
        ("Conclusión", "fecha_conclusion"),
    ]:
        r = row(lbl, data.get(key))
        if r:
            lines.append(r)
    lines.append("")
    if data.get("descripcion"):
        lines.append(f"**Descripción:** {data['descripcion']}")
        lines.append("")
    lines.append(f"**📸 Fotos descargadas:** {data['num_fotos']} → `{os.path.abspath(out_dir)}`")
    for p in saved:
        lines.append(f"- `{p}`")
    if data.get("texto_documentos"):
        lines.append("")
        lines.append("**📄 Texto de documentos (pliego/condiciones):**")
        lines.append("")
        lines.append("```")
        lines.append(data["texto_documentos"][:2000])
        lines.append("```")

    print("\n".join(lines))

    if args.json:
        print("\n<!-- JSON -->")
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
