# Web de Así Fue la Historia

Sitio estático generado con Python (`build.py`) y publicado en GitHub Pages.

- `site.yaml` — dominio, enlaces de WhatsApp/YouTube, tracking ID de Amazon, enlace de Payhip y precio del libro.
- `content/dictadores-*.yaml` — expedientes (un bloque por dictador).
- `content/episodios.yaml` — episodios de la serie "Así murieron los dictadores". `youtube_id` se completa a mano o se detecta solo.
- `content/biblioteca.yaml` — libros recomendados (Amazon).
- `scripts/sync_youtube.py` — trae todos los videos del canal (secreto `YOUTUBE_API_KEY`).
- `.github/workflows/publicar.yml` — publica en cada cambio y cada día a las 10:17 UTC.

Local: `pip install jinja2 markdown pyyaml && python build.py` → `dist/`.
