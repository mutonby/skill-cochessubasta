#!/usr/bin/env python3
"""
stage_put.py — Sube los bytes de un fichero local a una URL de staging presignada (PUT).

Lo usa el paso de publicacion en Upload-Post: tras create_media_upload (tool MCP) obtienes un
`upload_url` presignado; este script hace el PUT de los bytes (el modelo no puede subir ficheros
locales al MCP remoto, pero si puede hacer este PUT por HTTP).

Uso:
    python stage_put.py <ruta_fichero> <upload_url> [--content-type image/png]

Imprime el codigo HTTP. 200 = OK.
"""
import sys
import argparse

try:
    import httpx
except ImportError:
    sys.exit("Falta httpx: pip install httpx")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("upload_url")
    ap.add_argument("--content-type", default="image/png")
    args = ap.parse_args()

    with open(args.file, "rb") as fh:
        data = fh.read()
    r = httpx.put(args.upload_url, content=data,
                  headers={"Content-Type": args.content_type}, timeout=120.0)
    print(f"{args.file} -> HTTP {r.status_code}")
    sys.exit(0 if r.status_code in (200, 201) else 1)


if __name__ == "__main__":
    main()
