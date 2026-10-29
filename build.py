#!/usr/bin/env python3
"""Generador de la web de Así Fue la Historia.

Uso:
  python3 build.py              # sitio de producción en dist/
  python3 build.py --preview    # enlaces relativos (vista previa sin servidor)
"""
import datetime as dt
import difflib
import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
PREVIEW = "--preview" in sys.argv

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

FINALES = {
    "asesinado": {"nombre": "Asesinados", "frase": "Emboscados, acribillados o linchados"},
    "ejecutado": {"nombre": "Ejecutados", "frase": "Juzgados y llevados a la horca o al paredón"},
    "preso": {"nombre": "Presos o procesados", "frase": "Murieron en una celda o en pleno juicio"},
    "exilio": {"nombre": "En el exilio", "frase": "Murieron lejos del país que gobernaron"},
    "accidente": {"nombre": "Accidentes", "frase": "Un avión y un auto que no llegaron a destino"},
    "cama": {"nombre": "En su cama", "frase": "Murieron sin condena, algunos con honores"},
}
ORDEN_FINALES = ["asesinado", "ejecutado", "preso", "exilio", "accidente", "cama"]


def load_yaml(p):
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fecha_larga(iso):
    if not iso:
        return ""
    parts = [int(x) for x in str(iso).split("-")]
    if len(parts) == 3:
        return f"{parts[2]} de {MESES[parts[1]-1]} de {parts[0]}"
    if len(parts) == 2:
        return f"{MESES[parts[1]-1]} de {parts[0]}"
    return str(parts[0])


def normalizar(s):
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def md(text):
    return markdown.markdown(text or "", extensions=["extra", "smarty"],
                             extension_configs={"smarty": {"substitutions": {
                                 "left-double-quote": "“", "right-double-quote": "”"}}})


def main():
    cfg = load_yaml(ROOT / "site.yaml")
    cfg["anio"] = dt.date.today().year
    base_url = f"https://{cfg['dominio']}" if cfg.get("dominio") else ""

    dictadores = []
    for p in sorted((ROOT / "content").glob("dictadores-*.yaml")):
        dictadores += load_yaml(p)
    por_slug = {d["slug"]: d for d in dictadores}
    for d in dictadores:
        d["html"] = md(d["cuerpo"])
        d["eps"] = []
        d["muerte_larga"] = fecha_larga(d["muerte"])
        d["anio_muerte"] = int(str(d["muerte"])[:4])
        d["final_info"] = FINALES[d["final"]]

    episodios = load_yaml(ROOT / "content" / "episodios.yaml")
    biblioteca = load_yaml(ROOT / "content" / "biblioteca.yaml")

    # Videos sincronizados desde YouTube (scripts/sync_youtube.py)
    vpath = ROOT / "data" / "videos.json"
    videos = json.loads(vpath.read_text(encoding="utf-8")) if vpath.exists() else []
    videos.sort(key=lambda v: v.get("publicado", ""), reverse=True)
    por_vid = {v["id"]: v for v in videos}

    # Enlazar episodios con su video: id manual o el título más parecido.
    for e in episodios:
        if not e.get("youtube_id") and videos:
            titulos = {normalizar(v["titulo"]): v["id"] for v in videos}
            match = difflib.get_close_matches(normalizar(e["titulo"]), titulos.keys(), n=1, cutoff=0.72)
            if match:
                e["youtube_id"] = titulos[match[0]]
        e["video"] = por_vid.get(e.get("youtube_id"))
        e["fecha_larga"] = fecha_larga(e["fecha"])
        e["lista"] = [por_slug[s] for s in e["dictadores"]]
        for d in e["lista"]:
            d["eps"].append(e)
    episodios.sort(key=lambda e: e["numero"], reverse=True)

    for b in biblioteca:
        q = f"{b['titulo']} {b['autor']}".replace(" ", "+")
        tag = f"&tag={cfg['amazon_tag']}" if cfg.get("amazon_tag") else ""
        b["url"] = (f"https://www.amazon.com/dp/{b['asin']}" + (f"?tag={cfg['amazon_tag']}" if tag else "")
                    if b.get("asin") else f"https://www.amazon.com/s?k={q}{tag}")
        b["afiliado"] = bool(tag)
        tag_es = cfg.get("amazon_tag_es") or ""
        b["url_es"] = (f"https://www.amazon.es/dp/{b['asin_es']}" if b.get("asin_es")
                       else f"https://www.amazon.es/s?k={q}") + (("&" if "?" in (f"/s?k={q}" if not b.get("asin_es") else "") else "?") + f"tag={tag_es}" if tag_es else "")
        b["afiliado_es"] = bool(tag_es)

    # Videos del canal relacionados con cada expediente (por apellido)
    claves = {"saddam-hussein": "saddam", "fidel-castro": "fidel", "porfirio-diaz": "porfirio",
              "tiburcio-carias-andino": "carias", "leon-febres-cordero": "febres",
              "anastasio-somoza-debayle": "somoza", "muamar-el-gadafi": "gadafi",
              "hector-bienvenido-trujillo": "trujillo", "ramfis-trujillo": "ramfis"}
    ids_serie = {e.get("youtube_id") for e in episodios}
    for d in dictadores:
        clave = claves.get(d["slug"], normalizar(d["nombre"]).split()[-1])
        d["videos_rel"] = [v for v in videos if clave in normalizar(v["titulo"]).split()
                           and v["id"] not in ids_serie][:4]

    cronologia = sorted(dictadores, key=lambda d: str(d["muerte"]))
    grupos = [{"clave": k, **FINALES[k], "lista": [d for d in cronologia if d["final"] == k]}
              for k in ORDEN_FINALES]

    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html", "xml"]))
    env.filters["fecha"] = fecha_larga

    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST / "static")

    # Libros recomendados por video según el tema de su título (content/libro-temas-videos.yaml)
    temas_path = ROOT / "content" / "libro-temas-videos.yaml"
    temas = load_yaml(temas_path) if temas_path.exists() else []
    tag, tag_es = cfg.get("amazon_tag") or "", cfg.get("amazon_tag_es") or ""

    def libro_links(lb):
        q = f"{lb['titulo']} {lb['autor']}".replace(" ", "+")
        com = (f"https://www.amazon.com/dp/{lb['asin']}" + (f"?tag={tag}" if tag else "")) if lb.get("asin") \
            else f"https://www.amazon.com/s?k={q}" + (f"&tag={tag}" if tag else "")
        return dict(lb, url=com,
                    url_es=f"https://www.amazon.es/s?k={q}" + (f"&tag={tag_es}" if tag_es else ""))

    def tiene(texto, palabra):
        return f" {normalizar(str(palabra))} " in texto

    for v in videos:
        t = " " + re.sub(r"\s+", " ", normalizar(v["titulo"])) + " "
        elegidos, vistos, temas_v = [], set(), []
        for tm in temas:
            if tm.get("general"):
                continue
            if any(tiene(t, w) for w in tm["palabras"]):
                temas_v.append(tm["tema"])
                for lb in tm["libros"]:
                    if lb["titulo"] not in vistos:
                        vistos.add(lb["titulo"]); elegidos.append(lb)
        if not elegidos:
            for tm in temas:
                if tm.get("general") and any(tiene(t, w) for w in tm["palabras"]):
                    temas_v.append(tm["tema"]); elegidos = list(tm["libros"])
        v["libros"] = [libro_links(lb) for lb in elegidos[:4]]
        v["temas"] = temas_v

    # Blog: artículos en Markdown con cabecera YAML (content/articulos/*.md o articulo-*.md en la raíz)
    articulos = []
    for p in sorted((ROOT / "content" / "articulos").glob("*.md")) + sorted(ROOT.glob("articulo-*.md")):
        raw = p.read_text(encoding="utf-8")
        _, cab, cuerpo = raw.split("---", 2)
        a = yaml.safe_load(cab)
        if a.get("borrador") and not PREVIEW:
            continue
        a["html"] = md(cuerpo)
        a["respuesta_html"] = md(a.get("respuesta", ""))
        a["fecha_larga"] = fecha_larga(str(a["fecha"]))
        a["minutos"] = max(1, round(len(cuerpo.split()) / 220))
        t = " " + " ".join(normalizar(w) for w in a.get("palabras", [])) + " " + normalizar(a["titulo"]) + " "
        libs, vistos = [], set()
        for tm in temas:
            if not tm.get("general") and any(tiene(t, w) for w in tm["palabras"]):
                for lb in tm["libros"]:
                    if lb["titulo"] not in vistos:
                        vistos.add(lb["titulo"]); libs.append(lb)
        a["libros"] = [libro_links(lb) for lb in libs[:4]]
        articulos.append(a)
    articulos.sort(key=lambda a: str(a["fecha"]), reverse=True)

    # Efemérides: efemerides-MM.yaml (raíz o content/), 2-3 por día
    efemerides = {}
    for p in sorted((ROOT / "content").glob("efemerides-*.yaml")) + sorted(ROOT.glob("efemerides-*.yaml")):
        dat = load_yaml(p) or {}
        mes = int(dat["mes"])
        for e in dat.get("entradas", []):
            e["mes"] = mes
            e["mes_nombre"] = MESES[mes - 1]
            e["slug_dia"] = f"{int(e['dia'])}-{MESES[mes - 1]}"
            efemerides.setdefault((mes, int(e["dia"])), []).append(e)
    for k, lst in efemerides.items():
        lst.sort(key=lambda e: (not e.get("destacada"), e["anio"]))
    efe_dias = [{"mes": m, "dia": d, "slug": f"{d}-{MESES[m-1]}", "nombre": f"{d} de {MESES[m-1]}",
                 "lista": efemerides[(m, d)]} for (m, d) in sorted(efemerides)]
    efe_meses = []
    for m in sorted({m for (m, _) in efemerides}):
        efe_meses.append({"mes": m, "nombre": MESES[m - 1], "dias": [x for x in efe_dias if x["mes"] == m]})

    paginas = []

    def render(tpl, out, **ctx):
        depth = out.count("/")
        prefix = "../" * depth

        def url(path=""):
            path = path.strip("/")
            if PREVIEW:
                if not path:
                    return prefix + "index.html"
                if path.startswith("static/") or "." in path.split("/")[-1]:
                    return prefix + path
                return prefix + path + "/index.html"
            return "/" + (path + "/" if path and "." not in path.split("/")[-1] else path)

        canon = base_url + ("/" + out[:-len("index.html")] if out.endswith("index.html") else "/" + out)
        html = env.get_template(tpl).render(cfg=cfg, url=url, canon=canon, base_url=base_url,
                                            preview=PREVIEW, ruta=out, **ctx)
        dest = DIST / out
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        if out.endswith("index.html"):
            paginas.append(canon)

    comun = dict(episodios=episodios, dictadores=dictadores, grupos=grupos,
                 cronologia=cronologia, biblioteca=biblioteca, videos=videos, finales=FINALES)

    render("home.html", "index.html", **comun)
    render("serie.html", "series/asi-murieron-los-dictadores/index.html", **comun)
    for e in episodios:
        render("episodio.html", f"videos/{e['slug']}/index.html", e=e, **comun)
    for d in dictadores:
        rel = [x for x in cronologia if x["final"] == d["final"] and x is not d][:3]
        libros = [b for b in biblioteca if d["slug"] in b["dictadores"]]
        render("dictador.html", f"dictadores/{d['slug']}/index.html", d=d, relacionados=rel,
               libros=libros, **comun)
    render("dictadores.html", "dictadores/index.html", **comun)
    render("videos.html", "videos/index.html", **comun)
    render("libros.html", "libros/index.html", **comun)
    render("biblioteca.html", "biblioteca/index.html", **comun)
    render("galeria.html", "galeria/index.html", **comun)
    render("comunidad.html", "comunidad/index.html", **comun)
    render("sobre.html", "sobre/index.html", **comun)
    render("legal.html", "privacidad/index.html", tipo="privacidad", **comun)
    render("legal.html", "aviso-de-afiliados/index.html", tipo="afiliados", **comun)
    render("404.html", "404.html", **comun)
    render("gracias.html", "gracias/index.html", **comun)
    render("apoya.html", "apoya/index.html", **comun)
    render("enlaces.html", "enlaces/index.html", articulos=articulos, **comun)
    if articulos:
        render("blog.html", "blog/index.html", articulos=articulos, **comun)
        for a in articulos:
            otros = [o for o in articulos if o is not a][:5]
            render("articulo.html", f"blog/{a['slug']}/index.html", a=a, otros=otros, **comun)
    if efe_dias:
        render("efemerides.html", "efemerides/index.html", efe_meses=efe_meses, **comun)
        for i, x in enumerate(efe_dias):
            render("efemeride-dia.html", f"efemerides/{x['slug']}/index.html", x=x,
                   ant=efe_dias[i - 1] if i > 0 else None,
                   sig=efe_dias[i + 1] if i + 1 < len(efe_dias) else None, **comun)
        (DIST / "efemerides.json").write_text(json.dumps(
            {f"{x['mes']}-{x['dia']}": [{"anio": e["anio"], "titulo": e["titulo"], "pais": e.get("pais", ""),
                                          "texto": e.get("texto", ""), "imagen": e.get("imagen", ""),
                                          "video": e.get("video", ""), "articulo": e.get("articulo", ""),
                                          "destacada": bool(e.get("destacada")), "slug": x["slug"]}
                                         for e in x["lista"]] for x in efe_dias}, ensure_ascii=False),
            encoding="utf-8")
        print(f"Efemérides: {sum(len(x['lista']) for x in efe_dias)} en {len(efe_dias)} días")
    for v in videos:
        if v.get("libros"):
            render("libros-video.html", f"v/{v['id']}/index.html", v=v, **comun)
    con_libros = [v for v in videos if v.get("libros")]
    (DIST / "libros-por-video.txt").write_text(
        "\n".join(f"{v['id']}\t{base_url}/v/{v['id']}/\t{v['titulo']}" for v in con_libros) + "\n",
        encoding="utf-8")
    (DIST / "libros-por-video.json").write_text(json.dumps(
        [{"id": v["id"], "titulo": v["titulo"], "libros": [{"titulo": b["titulo"], "autor": b["autor"], "url": b["url"]}
                                                           for b in v["libros"]]} for v in con_libros],
        ensure_ascii=False), encoding="utf-8")
    print(f"Libros por video: {len(con_libros)} de {len(videos)} videos")

    if not PREVIEW:
        hoy = dt.date.today().isoformat()
        sm = ['<?xml version="1.0" encoding="UTF-8"?>',
              '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sm += [f"<url><loc>{p}</loc><lastmod>{hoy}</lastmod></url>" for p in paginas]
        sm.append("</urlset>")
        (DIST / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
        (DIST / "robots.txt").write_text(
            f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n", encoding="utf-8")
        if cfg.get("dominio"):
            (DIST / "CNAME").write_text(cfg["dominio"] + "\n", encoding="utf-8")
        (DIST / ".nojekyll").write_text("", encoding="utf-8")
        if cfg.get("adsense_client"):
            pub = cfg["adsense_client"].replace("ca-", "")
            (DIST / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")

    print(f"OK: {len(paginas)} páginas en {DIST}")


if __name__ == "__main__":
    main()
