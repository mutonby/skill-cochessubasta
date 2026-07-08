# skill-cochessubasta

Pipeline completo para convertir una **subasta de coche del BOE** en un **post de carrusel de
Instagram** con funnel de mensajes directos. Pensado como *skill* autónoma para Claude Code, pero
los scripts funcionan por sí solos desde la terminal.

Perfil de destino de ejemplo: Instagram **@subasta.motor**.

> ⚠️ **Aviso legal / privacidad.** Es una herramienta para difundir subastas **públicas** del BOE,
> no para vender coches. Difumina SIEMPRE las matrículas (propias y de terceros) antes de publicar,
> mantén el disclaimer del caption y cita la fuente. Los datos textuales del BOE son reutilizables
> (Ley 37/2007) sin alterarlos. Las carpetas con fotos y datos extraídos (`boe_*/`) **no** se suben
> al repo (ver `.gitignore`): contienen matrículas reales y datos personales.

---

## Cómo funciona (5 fases)

```
BOE (búsqueda pública)
  → 0. boe_search.py      candidatos en subasta (sin login)     → tabla con idSub + precios
BOE (idSub)
  → 1. boe_extract.py     fotos reales + datos + pliego         → carpeta con foto_*.jpg + data.json
  → 2. make_carousel.py   carrusel IG (Nano Banana)             → carrusel/slide_*.png
  → 3. Upload-Post (MCP)  publica el carrusel en Instagram      → post_url
  → 4. manage_autodms     comentar "subasta" → DM con link BOE  → monitor_id
```

Cada script es independiente y solo necesita `httpx` (y `PyMuPDF` opcional para leer el pliego PDF).

---

## Requisitos

- **Python 3.9+** con `httpx` (`pip install httpx`). Opcional: `PyMuPDF` para el texto del pliego.
- **Clave de Gemini** (`GEMINI_API_KEY`) para generar el carrusel con Nano Banana (fase 2).
- **Servidor MCP de Upload-Post** conectado en Claude Code, con un perfil que tenga Instagram
  vinculado (fases 3-4). Cuenta de Upload-Post: https://upload-post.com
- Para las **fotos** de las subastas (fase 1): una **sesión iniciada en subastas.boe.es**
  (Cl@ve / certificado) desde la que obtener la cookie `SESSID`.

---

## Configuración

### 1. Variables de entorno (`.env`)

Copia `.env.example` a `.env` y rellena tu clave. **El `.env` no se sube al repo** (`.gitignore`).

```bash
cp .env.example .env
# edita .env y pon tu clave:
# GEMINI_API_KEY=AI...tu_clave...
```

`make_carousel.py` busca la clave en este orden: variable de entorno `GEMINI_API_KEY` →
fichero `.env` del proyecto (subiendo carpetas).

### 2. La parte del BOE (búsqueda y extracción)

**Búsqueda (fase 0) — pública, sin login ni base de datos.** Usa la búsqueda avanzada del portal
de subastas (`BIEN.TIPO=V`, subtipo turismos) y el detalle público de cada subasta:

```bash
python3 scripts/boe_search.py --sort precio
python3 scripts/boe_search.py --sort precio --max-precio 8000 --provincia 28
python3 scripts/boe_search.py --subtipo industriales --estado PU --json
```

Devuelve una tabla con `idSub`, vehículo, valor de subasta, puja mínima y fecha de conclusión.
Copia el `idSub` del coche elegido para la fase 1.

**Extracción de fotos + datos (fase 1) — requiere `SESSID`.** Las fotos del vehículo solo son
visibles con sesión iniciada en subastas.boe.es. Esa sesión se identifica con la cookie **`SESSID`**
(legible desde `document.cookie`, no es httpOnly). Para conseguirla:

1. Inicia sesión en https://subastas.boe.es con tu Cl@ve o certificado.
2. Abre la consola del navegador (F12 → *Console*) y ejecuta `document.cookie`.
3. Copia el valor que empieza por `SESSID=` (solo la parte del valor).

```bash
python3 scripts/boe_extract.py "SUB-AT-2026-..." --sessid "<SESSID>" --out "./boe_<idSub>" --json
```

Guarda `foto_*.jpg` + `data.json` en la carpeta de salida. Si el BOE trae los km en el texto,
`data.json` los incluye; si no, se pueden leer de la foto del cuadro. La cookie `SESSID` es efímera
y personal: **no la guardes en el repo ni en ficheros versionados.**

### 3. El carrusel (fase 2 — Nano Banana)

```bash
GEMINI_API_KEY=<key> python3 scripts/make_carousel.py "./boe_<idSub>" --max-slides 6
```

- Modelo por defecto: **`gemini-3-pro-image`** (Nano Banana Pro). Difumina matrículas de forma
  fiable y renderiza bien el texto. No uses `gemini-2.5-flash-image` para contenido público.
- Cada slide lleva **Precio · Año · KM** + un dato rotando. Salida en `boe_<idSub>/carrusel/slide_*.png`.
- **Revisa siempre** los slides antes de publicar: confirma que ninguna matrícula queda legible y
  que el coche generado se parece al real (Nano Banana a veces recrea el vehículo; descarta esos slides).

### 4. La parte de Upload-Post (fases 3-4)

Upload-Post es un servicio remoto (MCP) que publica en redes; **no puede leer ficheros locales**,
así que cada slide se sube antes a un *staging* temporal:

1. `create_media_upload` → devuelve `upload_url` presignado (PUT).
2. `python3 scripts/stage_put.py <slide.png> "<upload_url>"` → sube los bytes.
3. `complete_media_upload` → devuelve `media_url` descargable.
4. `upload_photos({ user, platforms:["instagram"], photosPathsOrUrls:[media_url...], title, description })`.
5. `get_status({requestId})` hasta `completed` → coge `post_url`.
6. `manage_autodms({ action:"start", profile_username, post_url, trigger_keywords:"subasta", reply_message, monitoring_interval:15 })`.

El **AutoDM** responde por privado a quien comente la keyword (`"subasta"`) con el **enlace público**
del BOE: `https://subastas.boe.es/detalleSubasta.php?idSub=<idSub>`. Sondea cada 15 min (mínimo).
Plantillas de caption y de DM en `reference/caption.md`; procedimiento detallado en `reference/publicar.md`.

Para parar el funnel: `manage_autodms({ action:"stop", monitor_id })`.

---

## Estructura del repo

```
SKILL.md              Instrucciones de la skill para Claude Code (las 5 fases)
README.md             Este archivo
.env.example          Plantilla de variables de entorno (copiar a .env)
.gitignore            Excluye .env, boe_*/ (fotos con matrículas), backups
scripts/
  boe_search.py       Fase 0 — busca candidatos en el portal público del BOE
  boe_extract.py      Fase 1 — extrae fotos + datos (necesita SESSID)
  make_carousel.py    Fase 2 — genera el carrusel con Nano Banana
  stage_put.py        Helper — PUT de bytes al staging de Upload-Post
reference/
  caption.md          Plantilla de caption + mensaje del AutoDM
  publicar.md         Procedimiento paso a paso de publicación
```

---

## Notas

- El bot no completa CAPTCHAs ni gestiona credenciales. La cookie `SESSID` la aporta el usuario.
- Publicar en redes es irreversible: hazlo solo con revisión y visto bueno explícito.
- Esta skill es autónoma: no depende de ninguna base de datos ni software externo, solo del portal
  público del BOE, tu clave de Gemini y tu cuenta de Upload-Post.
