---
name: skill-cochessubasta
description: Pipeline completo para el Instagram @subasta.motor — dada una subasta de coche del BOE (idSub=SUB-... o URL), extrae fotos reales + datos, genera un carrusel de Instagram con Nano Banana (precio/año/km, matrículas difuminadas), lo publica en el perfil subastamotor vía Upload-Post y activa el AutoDM (comentar "subasta" → DM con el enlace del BOE). Usar cuando el usuario quiera "publicar/subir un coche", "montar el post de esta subasta", "contenido para subasta.motor", "el carrusel de este coche en Instagram", o pida buscar un coche de subasta y promocionarlo.
---

# subastamotor — de subasta del BOE a post de Instagram con funnel de DMs

Pipeline completo, ya validado, en 5 fases (0-4). Perfil destino: **subastamotor** (Instagram
**@subasta.motor**). Cada script es autónomo (solo necesita `httpx`; `PyMuPDF` opcional).

```
BOE (búsqueda pública)
  → 0. boe_search.py      candidatos en subasta (sin login)    → tabla con idSub + precios
BOE (idSub)
  → 1. boe_extract.py     fotos reales + datos + pliego        → carpeta con foto_*.jpg + data.json
  → 2. make_carousel.py   carrusel IG (Nano Banana, sin web)   → carpeta/carrusel/slide_*.png
  → 3. Upload-Post (MCP)  publica el carrusel en @subasta.motor → post_url
  → 4. manage_autodms     comentar "subasta" → DM con link BOE  → monitor_id
```

## Cuándo usar cada fase

- "busca un coche / los mejores coches de subasta" → fase 0 (boe_search.py, y mostrar tabla).
- "saca las fotos / la info de esta subasta" → fase 1 (y mostrar).
- "monta el carrusel" → fases 1-2 (y mostrar slides para aprobar).
- "publícalo / súbelo" → fases 1-4 (requiere OK del usuario para publicar, ver más abajo).

## Fase 0 — Buscar candidatos en el portal (público, sin login ni BBDD)

Para **elegir un buen coche**, busca directamente en la búsqueda avanzada pública
de subastas.boe.es:
```bash
python3 scripts/boe_search.py --sort precio [--max-precio 8000] [--provincia 28] [--subtipo industriales] [--json]
```
Devuelve una tabla con idSub, vehículo, valor de subasta, puja mínima y fecha de
conclusión (vehículos "celebrándose"; `--estado PU` para próximas aperturas).
Pasa el `idSub` elegido a `boe_extract.py`. Nota: el nº de fotos no es público;
se ve al extraer con SESSID en fase 1 (si un coche sale sin fotos, elige otro).

## Prerrequisito de fase 1 — SESSID del BOE (para las fotos)

Las fotos están tras login en subastas.boe.es; se identifican con la cookie **`SESSID`**
(legible desde `document.cookie`, no httpOnly). Ver memoria [[boe-auth-sessid]].
Consíguelo del navegador logado del usuario con `mcp__claude-in-chrome__*`:
`tabs_context_mcp` → `navigate` a `https://subastas.boe.es/reg/` → `javascript_tool` con
`document.cookie` → extrae `SESSID=...`. Si no aparece, el usuario no está logado (Cl@ve/cert.).

## Fase 1 — Extraer fotos + datos

```bash
python3 scripts/boe_extract.py "<idSub_o_url>" --sessid "<SESSID>" --out "./boe_<idSub>" --json
```
Guarda `foto_*.jpg` + `data.json`. `data.json` incluye `km` si el BOE lo trae en el texto
(la mayoría de las veces); si no, lo intenta leer la fase 2 desde la foto del cuadro.


## Fase 2 — Generar el carrusel (Nano Banana)

```bash
GEMINI_API_KEY=<key> python3 scripts/make_carousel.py "./boe_<idSub>" --max-slides 6
```
- Modelo por defecto **`gemini-3-pro-image`** (Nano Banana Pro): difumina matrículas de forma fiable
  y renderiza bien el texto. NO usar `gemini-2.5-flash-image` para contenido público (ignora el
  difuminado).
- Cada slide lleva SIEMPRE **Precio · Año · KM** + un dato útil rotando; **sin branding/web**.
- La `GEMINI_API_KEY` se toma del entorno o del `.env` del proyecto.
- Salida en `./boe_<idSub>/carrusel/slide_*.png`.

## Fase 3 — Revisar (OBLIGATORIO antes de publicar)

- Muestra los slides con `Read` y confirma visualmente que **NINGUNA matrícula queda legible**
  (la del coche ni las del fondo). Si alguna se lee, **regenera ese slide** antes de publicar.
- Enseña el carrusel + el caption al usuario y **espera su OK explícito** para publicar
  (publicar en redes es irreversible y requiere permiso por acción).

## Fase 4 — Publicar + AutoDM

Sigue paso a paso `reference/publicar.md` (staging → upload_photos → get_status → manage_autodms).
Caption y mensaje del DM: plantilla en `reference/caption.md`.
- Keyword del AutoDM = la palabra del CTA del caption (**"subasta"**).
- DM = enlace **público** del BOE: `https://subastas.boe.es/detalleSubasta.php?idSub=<idSub>`.
- Tras `manage_autodms start`, guarda el `monitor_id` (para pausar/parar después).

## Legal (resumen)

- Datos textuales del BOE: reutilizables (Ley 37/2007) citando fuente y sin alterarlos.
- Fotos: difuminar SIEMPRE todas las matrículas (propias y de terceros) — lo hace la fase 2, pero
  revisa en fase 3. Mantener el disclaimer en el caption ("subasta pública", "no vendemos",
  "verifica condiciones en el BOE").

## Notas operativas

- AutoDM sondea cada **15 min** (mínimo); los DMs no son instantáneos.
- Parar: `manage_autodms({action:"stop", monitor_id})`. Estado: `action:"status", include_inactive:true`.
- No publiques sin OK del usuario. El bot no completa CAPTCHAs ni gestiona credenciales.
- Esta skill sustituye y amplía a la antigua `boe-coche` (que solo llegaba al carrusel).
