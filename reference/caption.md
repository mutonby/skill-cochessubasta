# Plantilla de caption (Instagram)

Rellena con los datos de `data.json`. Tono: gancho directo + ficha + CTA de comentario + disclaimer.

```
🔥 {MARCA} {MODELO} por {PRECIO} en subasta pública (BOE)

{1-2 frases de gancho: por qué es interesante este coche en concreto}

📋 Ficha
· Precio salida: {PRECIO} · Puja mínima: {PUJA} · Depósito: {DEPOSITO}
· Año {AÑO} · {KM} km · {COMBUSTIBLE}
· {Sin cargas ✅ / Cargas: X €}
· 📍 {PROVINCIA} · ⏰ Termina el {FECHA_FIN}

💬 Comenta SUBASTA y te enviamos el enlace oficial del BOE por mensaje privado 📩

Es una subasta pública de {ORGANISMO}. No vendemos el coche; te damos la info para que pujes tú.
Verifica siempre las condiciones en el BOE antes de pujar.

#subastas #coches #{marca} #cochessegundamano #chollos #subastasboe #{provincia} #cochesdeocasion
```

## Reglas
- La palabra clave del CTA ("SUBASTA") debe coincidir con `trigger_keywords` del AutoDM.
- Mantén SIEMPRE el disclaimer legal (fuente pública + "no vendemos" + "verifica condiciones").
- No pongas datos de terceros (matrículas ajenas) — eso ya se difumina en las imágenes.
- Sin web por ahora (el perfil aún no enlaza a buscosubastas.es).

## DM del AutoDM (reply_message)
```
¡Gracias por tu interés! 🔥 Aquí tienes la subasta del {MARCA} {MODELO} en el BOE 👉
https://subastas.boe.es/detalleSubasta.php?idSub={IDSUB}

⚠️ Es una subasta pública de {ORGANISMO}. Verifica las condiciones en el BOE antes de pujar. ¡Suerte! 🍀
```
