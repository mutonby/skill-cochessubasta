# Publicar el carrusel en Instagram + AutoDM (Upload-Post)

Flujo exacto, ya validado, para publicar en el perfil **subastamotor** (IG **@subasta.motor**)
y activar el funnel de comentarios → DM.

## Por qué este flujo

El MCP de Upload-Post es remoto y **no puede leer ficheros locales**. Por eso cada slide se sube
a un staging temporal (R2) en 3 pasos: crear → PUT bytes → completar (devuelve `media_url`
presignado descargable). Ese `media_url` es lo que acepta `upload_photos`.

## Pasos

### 1. Verificar perfil
`list_users` → confirma que existe el perfil destino y que su Instagram NO tiene
`reauth_required: true`. (subastamotor → instagram @subasta.motor.)

### 2. Subir cada slide al staging (por cada slide_N.png)
1. `create_media_upload({filename, contentType:"image/png", contentLength:<bytes>, mediaType:"image", source:"mcp_claude"})`
   → devuelve `upload_id` y `upload_url` (presignado PUT, caduca en ~15 min).
2. PUT de los bytes (el modelo no sube ficheros locales al MCP, pero si hace el PUT):
   ```bash
   python3 scripts/stage_put.py <carrusel>/slide_N.png "<upload_url>"
   ```
   (o `curl -X PUT -H "Content-Type: image/png" --data-binary @slide_N.png "<upload_url>"`)
3. `complete_media_upload({uploadId:<upload_id>})` → devuelve `media_url` (presignado GET, ~6 h).

Guarda los 6 `media_url` en orden (slide_1..slide_6).

### 3. Publicar el carrusel
`upload_photos({`
- `user: "subastamotor"`,
- `platforms: ["instagram"]`,
- `photosPathsOrUrls: [media_url_1, ..., media_url_6]`  (en orden),
- `title: "<titulo corto>"`,
- `description: "<caption completo, ver caption.md>"`,
- `asyncUpload: true`
`})` → devuelve `request_id`.

### 4. Esperar y obtener la URL del post
Espera ~30-60 s y `get_status({requestId})` hasta `status:"completed"`.
Coge `post_url` (ej. `https://www.instagram.com/p/XXXX/`). La necesitas para el AutoDM.

### 5. Activar AutoDM (comentario → DM)
`manage_autodms({`
- `action: "start"`,
- `profile_username: "subastamotor"`,
- `post_url: "<post_url del paso 4>"`,
- `trigger_keywords: "subasta"`,
- `reply_message: "<DM con el enlace PUBLICO del BOE>"`,
- `monitoring_interval: 15`   (minimo permitido)
`})` → devuelve `monitor_id`. Guardalo (para pausar/parar luego).

## Datos importantes

- **Enlace del BOE para el DM**: usa el PUBLICO (sin login), no el `/reg/`:
  `https://subastas.boe.es/detalleSubasta.php?idSub=<idSub>`
- **El AutoDM sondea cada 15 min**: los DMs no son instantaneos.
- **Parar/pausar**: `manage_autodms({action:"stop"|"pause", monitor_id:<id>})`.
- **Ver estado/logs**: `manage_autodms({action:"status", include_inactive:true})` o `action:"logs"`.
- El staging se borra a las 24 h; da igual, el post ya queda en IG. Conserva el carrusel local.

## Historial

El `manage_autodms start` devuelve un `monitor_id` con el formato
`<email_de_la_cuenta>_<perfil>_<id>`. Guárdalo en un sitio privado (no en este repo)
para poder pausar/parar el funnel después.
