#!/usr/bin/env python3
"""
make_carousel.py — Genera un carrusel de Instagram para un coche en subasta con Nano Banana (Gemini image).

Toma las fotos + datos que produjo boe_extract.py (carpeta con foto_*.jpg y data.json) y, por cada
slide, llama a Nano Banana con UN prompt que hace todo: difumina cualquier matricula visible (la del
coche y las de terceros) y compone un slide de Instagram (4:5) con la foto del coche, el precio y un
dato interesante, con un diseno limpio y marca "buscosubastas.es".

IMPORTANTE (legal): el difuminado de matriculas lo hace el modelo via prompt. Revisa SIEMPRE los
slides generados antes de publicar para confirmar que no queda ninguna matricula legible.

Uso:
    python make_carousel.py <carpeta_extract> [--out DIR] [--model NOMBRE] [--max-slides N] [--brand "buscosubastas.es"]

Ejemplos:
    python make_carousel.py ./boe_SUB-AT-2026-26R4686002018
    python make_carousel.py ./fotos --model gemini-3-pro-image --max-slides 5

Modelos (Nano Banana):
    gemini-2.5-flash-image   -> Nano Banana clasico (rapido, barato) [por defecto]
    gemini-3-pro-image       -> Nano Banana Pro (mejor texto en imagen, recomendado para precios)
"""
import os
import re
import sys
import json
import base64
import argparse

try:
    import httpx
except ImportError:
    sys.exit("Falta httpx: pip install httpx")

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def load_key():
    key = os.getenv("GEMINI_API_KEY")
    if key:
        return key
    # buscar en .env del proyecto (subiendo desde el script)
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        env = os.path.join(here, ".env")
        if os.path.exists(env):
            for line in open(env, encoding="utf-8"):
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=", 1)[1].strip()
        here = os.path.dirname(here)
    sys.exit("Falta GEMINI_API_KEY (env o .env del proyecto).")


def euro(v):
    """'4.199,00 €' -> '4.199 €'. Devuelve None si no hay numero."""
    if not v:
        return None
    m = re.search(r"[\d.]+", v.replace(" ", ""))
    if not m:
        return None
    entero = m.group(0).split(",")[0]
    return f"{entero} €"


def anio(d):
    if d.get("fecha_matriculacion"):
        m = re.search(r"(\d{4})", d["fecha_matriculacion"])
        if m:
            return m.group(1)
    return None


def fmt_km(km):
    """141563 -> '141.563 km'."""
    if not km:
        return None
    try:
        return f"{int(km):,}".replace(",", ".") + " km"
    except (ValueError, TypeError):
        return None


def detect_km_from_photos(key, photo_paths, model="gemini-2.5-flash"):
    """Lee el cuentakilometros de las fotos (fallback cuando el BOE no lo da en texto)."""
    parts = [{"text":
        "Estas son fotos de un coche en subasta. Si ALGUNA muestra el cuadro de instrumentos "
        "o el cuentakilometros, devuelve SOLO el numero de kilometros que marca, como entero sin "
        "puntos ni texto (ej: 141563). Si ninguna lo muestra con claridad, devuelve exactamente: null."}]
    for p in photo_paths[:14]:
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                      "data": base64.b64encode(open(p, "rb").read()).decode()}})
    url = API.format(model=model)
    try:
        r = httpx.post(url, params={"key": key}, json={"contents": [{"parts": parts}]}, timeout=120.0)
        if r.status_code != 200:
            return None
        txt = ""
        for part in r.json().get("candidates", [{}])[0].get("content", {}).get("parts", []):
            txt += part.get("text", "")
        m = re.search(r"\d{3,7}", txt.replace(".", ""))
        if m:
            km = int(m.group(0))
            if 100 <= km <= 1_000_000:
                return km
    except Exception:
        pass
    return None


def datos_interesantes(d):
    """Datos utiles ROTATIVOS (ademas de precio/anio/km que van fijos en cada slide)."""
    out = []
    if d.get("cargas") and re.search(r"0[,.]00", d["cargas"]):
        out.append("Sin cargas")
    pm = euro(d.get("puja_minima"))
    if pm:
        out.append(f"Puja minima {pm}")
    if d.get("fecha_conclusion"):
        f = re.search(r"(\d{2}-\d{2}-\d{4})", d["fecha_conclusion"])
        if f:
            out.append(f"Termina el {f.group(1)}")
    dep = euro(d.get("deposito"))
    if dep:
        out.append(f"Deposito {dep}")
    return out or ["Subasta publica del BOE"]


def build_prompt(slide_idx, total, d, brand, dato):
    marca = d.get("marca") or "Vehiculo"
    modelo = d.get("modelo") or ""
    precio = euro(d.get("valor_subasta")) or "Consultar"
    titulo = f"{marca} {modelo}".strip()
    ano = anio(d)
    km = fmt_km(d.get("km"))
    # Ficha fija que va SIEMPRE en cada slide: precio, anio, km
    ficha = [f"Precio {precio}"]
    if ano:
        ficha.append(f"Ano {ano}")
    if km:
        ficha.append(km)
    ficha_str = "  ·  ".join(ficha)

    base_reglas = (
        "REGLA LEGAL PRIORITARIA E INNEGOCIABLE: TODAS las matriculas de coche de la imagen deben "
        "quedar TOTALMENTE ILEGIBLES. Cubre con un rectangulo pixelado/difuminado opaco la matricula "
        "del coche protagonista Y las de TODOS los coches del fondo, incluso las parciales o lejanas. "
        "El difuminado debe tapar la matricula por si mismo: NO uses un logo, badge o texto como unica "
        "forma de ocultarla. Antes de terminar, verifica que no se lee ningun caracter de ninguna "
        "matricula. No inventes ni cambies el coche: manten el vehiculo real de la foto, su color, "
        "forma y estado tal cual. "
        "Formato vertical de Instagram, relacion 4:5 (1080x1350). Estilo limpio, moderno y premium, "
        "tipografia sans-serif bien legible, buen contraste. Idioma espanol con tildes y la letra ñ "
        "correctas (España, Vehículos, públicas, mínima, Más, Depósito). "
        "MUY IMPORTANTE: cada texto aparece UNA SOLA VEZ. No dupliques el precio, ni el nombre del "
        "modelo, ni ningun rotulo. Un unico badge de precio y un unico titulo por slide. "
    )

    if slide_idx == 0:
        # Portada
        return (
            base_reglas +
            f"Crea la PORTADA de un carrusel de Instagram para una subasta de vehiculo. "
            f"Usa la foto del coche como fondo a sangre con un degradado oscuro abajo para legibilidad. "
            f"Texto grande arriba: '{titulo}'. "
            f"Una franja/ficha clara y legible, abajo, con estos tres datos: '{ficha_str}'. "
            f"Una etiqueta pequena tipo sello: 'SUBASTA BOE'. "
            f"NO incluyas ninguna web, marca, logo ni url. "
            f"Composicion atractiva que invite a deslizar."
        )
    elif slide_idx >= total - 1:
        # Cierre / recap (sin web)
        return (
            base_reglas +
            f"Crea el SLIDE FINAL (resumen) del carrusel para '{titulo}'. "
            f"Fondo con la foto del coche difuminada/oscurecida. "
            f"En el centro, una ficha resumen grande y legible con: '{ficha_str}'. "
            f"Debajo, destacado: '{dato}'. "
            f"Abajo del todo, en pequeno: 'Toda la info en la descripcion'. "
            f"NO incluyas ninguna web, marca, logo ni url. Diseno premium y limpio."
        )
    else:
        # Slide intermedio: foto + ficha fija (precio/anio/km) + un dato rotativo
        return (
            base_reglas +
            f"Crea un SLIDE intermedio del carrusel para '{titulo}'. "
            f"La foto real del coche ocupa la mayor parte. "
            f"Arriba, una franja/ficha legible con estos tres datos: '{ficha_str}'. "
            f"Ademas, un badge destacando un dato clave: '{dato}'. "
            f"NO incluyas ninguna web, marca, logo ni url. "
            f"Diseno coherente, premium, tipo ficha de subasta."
        )


def gen_slide(key, model, prompt, image_bytes, out_path):
    parts = [{"text": prompt}]
    if image_bytes:
        parts.append({"inline_data": {"mime_type": "image/jpeg",
                                      "data": base64.b64encode(image_bytes).decode()}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": "4:5"},
        },
    }
    url = API.format(model=model)
    r = httpx.post(url, params={"key": key}, json=body, timeout=180.0)
    if r.status_code != 200:
        # Reintento sin imageConfig (modelos que no lo soportan)
        body["generationConfig"].pop("imageConfig", None)
        r = httpx.post(url, params={"key": key}, json=body, timeout=180.0)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:300]}", file=sys.stderr)
        return False
    data = r.json()
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                with open(out_path, "wb") as fh:
                    fh.write(base64.b64decode(inline["data"]))
                return True
    print(f"  ERROR: sin imagen en la respuesta: {json.dumps(data)[:300]}", file=sys.stderr)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="Carpeta de boe_extract (con foto_*.jpg y data.json)")
    ap.add_argument("--out", default=None, help="Carpeta de salida (por defecto <folder>/carrusel)")
    ap.add_argument("--model", default="gemini-3-pro-image",
                    help="Modelo Nano Banana (gemini-3-pro-image = Pro, mejor texto y difuminado; "
                         "gemini-2.5-flash-image = clasico, mas barato)")
    ap.add_argument("--max-slides", type=int, default=6, help="Maximo de slides")
    ap.add_argument("--brand", default="", help="(opcional) handle/web a mostrar; vacio = sin branding")
    ap.add_argument("--no-km-vision", action="store_true",
                    help="No intentar leer los km de las fotos si no estan en el texto del BOE")
    args = ap.parse_args()

    folder = args.folder
    data_path = os.path.join(folder, "data.json")
    if not os.path.exists(data_path):
        sys.exit(f"No encuentro {data_path}. Ejecuta antes boe_extract.py --out {folder}")
    d = json.load(open(data_path, encoding="utf-8"))

    photos = sorted(
        [os.path.join(folder, f) for f in os.listdir(folder)
         if re.match(r"foto_\d+\.(jpg|png)$", f)],
        key=lambda p: int(re.search(r"foto_(\d+)", p).group(1)),
    )
    if not photos:
        sys.exit("No hay fotos foto_*.jpg en la carpeta.")

    out_dir = args.out or os.path.join(folder, "carrusel")
    os.makedirs(out_dir, exist_ok=True)
    key = load_key()

    # km: del texto del BOE (data.json); si no, intentar leerlo de las fotos.
    if not d.get("km") and not args.no_km_vision:
        km = detect_km_from_photos(key, photos)
        if km:
            d["km"] = km
            print(f"  km leido de las fotos: {fmt_km(km)}")
    print(f"  ficha fija -> Precio {euro(d.get('valor_subasta'))} · Ano {anio(d)} · {fmt_km(d.get('km')) or 'km s/d'}")

    datos = datos_interesantes(d)
    # Plan: portada (foto1) + intermedios (resto de fotos con un dato) + cierre
    n_inter = min(len(photos), args.max_slides - 2)
    total = n_inter + 2
    print(f"Generando carrusel de {total} slides con {args.model}...")

    saved = []
    for i in range(total):
        photo_idx = min(i, len(photos) - 1)
        img = open(photos[photo_idx], "rb").read()
        dato = datos[(i - 1) % len(datos)] if datos else (d.get("marca") or "")
        prompt = build_prompt(i, total, d, args.brand, dato)
        out_path = os.path.join(out_dir, f"slide_{i+1}.png")
        ok = gen_slide(key, args.model, prompt, img, out_path)
        if ok:
            saved.append(out_path)
            print(f"  slide {i+1}/{total} -> {out_path}")
        else:
            print(f"  slide {i+1}/{total} FALLO", file=sys.stderr)

    print(f"\nCarrusel: {len(saved)}/{total} slides en {os.path.abspath(out_dir)}")
    for s in saved:
        print(f"- {s}")
    print("\n⚠️  Revisa los slides y confirma que NINGUNA matricula queda legible antes de publicar.")


if __name__ == "__main__":
    main()
