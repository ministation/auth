# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Small HTML pages for browser-facing auth flows."""

from __future__ import annotations

import html
import json

from fastapi.responses import HTMLResponse


def error_page(title: str, message: str, *, site_url: str, status_code: int = 400) -> HTMLResponse:
    return _page(
        title=title,
        message=html.escape(str(message)),
        site_url=site_url,
        status_code=status_code,
        accent="#6cb6ff",
        cta_href=site_url,
        cta_label="Перейти на сайт",
    )


def success_page(*, site_url: str, redirect_url: str, username: str) -> HTMLResponse:
    return _page(
        title="Готово",
        message=f"Аккаунт <b>{html.escape(username)}</b> привязан. Сейчас откроется сайт…",
        site_url=site_url,
        status_code=200,
        accent="#3dd68c",
        redirect_url=redirect_url,
        cta_href=redirect_url,
        cta_label="Перейти сейчас",
    )


def _page(
    *,
    title: str,
    message: str,
    site_url: str,
    status_code: int,
    accent: str,
    cta_href: str,
    cta_label: str,
    redirect_url: str | None = None,
) -> HTMLResponse:
    safe_title = html.escape(title)
    safe_cta_href = html.escape(cta_href, quote=True)
    safe_cta_label = html.escape(cta_label)
    refresh = ""
    script = ""
    if redirect_url:
        safe_refresh = html.escape(redirect_url, quote=True)
        refresh = f'<meta http-equiv="refresh" content="1;url={safe_refresh}">'
        script = (
            "<script>"
            f"setTimeout(function(){{location.replace({json.dumps(redirect_url)});}}, 700);"
            "</script>"
        )

    page = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  {refresh}
  <title>{safe_title}</title>
  <style>
    :root {{
      --bg: #0f1419;
      --card: #161c24;
      --line: #2a3441;
      --text: #e7ecf3;
      --muted: #9aa7b5;
      --accent: {accent};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        radial-gradient(1200px 500px at 20% -10%, #1d2a3a 0%, transparent 60%),
        var(--bg);
      color: var(--text);
      padding: 1.5rem;
    }}
    main {{
      width: min(100%, 28rem);
      padding: 2rem;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: color-mix(in srgb, var(--card) 92%, black);
      box-shadow: 0 20px 50px rgba(0,0,0,.35);
    }}
    h1 {{ margin: 0 0 .75rem; font-size: 1.35rem; }}
    p {{ margin: 0 0 1rem; color: var(--muted); line-height: 1.5; }}
    a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{message}</p>
    <p><a href="{safe_cta_href}">{safe_cta_label}</a></p>
  </main>
  {script}
</body>
</html>"""
    return HTMLResponse(
        page,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
        },
    )
