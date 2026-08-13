# monitor-ads

Auto-pausa de anuncios de testeo (knitting) cada 3 horas, corriendo en GitHub Actions (24/7, sin depender de la PC).

- **Decisión:** 100% Utmify (dashboard TELAS, ventas front reconciliadas).
- **Ejecución:** pausa en Meta por Graph API.
- **Regla:** breakeven sobre el precio front por mercado. Un ad de testeo se apaga cuando su gasto lifetime cruza el umbral para su cantidad de ventas de front (0v→0.7×front, 1v→1×, 2v→2×, 3v→3×, +0.5× por venta desde la 4ª). La fórmula deja vivos a los que rinden.
- **Blindaje:** si Utmify devuelve un pull incompleto, reintenta hasta 5× y no pausa nada si no consigue el universo completo.

## Secrets requeridos
- `UTMIFY_URL` — la URL MCP de Utmify con el token.
- `META_TOKEN` — el user access token de Meta (Graph API). **Caduca ~cada 60 días; renovar.**

Correr a mano: pestaña **Actions → auto-pausa-ads → Run workflow**.
