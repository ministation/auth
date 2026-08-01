# Copyright (c) 2024–2026 Мини-станция (Mini-Station). All rights reserved.
# See LICENSE for terms.

"""Browser-facing auth pages styled like ministation.ru."""

from __future__ import annotations

import html
import json

from fastapi.responses import HTMLResponse

_HTML_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; "
        "style-src 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "script-src 'unsafe-inline'; "
        "img-src https: data:; "
        "connect-src 'none'; "
        "base-uri 'none'; "
        "frame-ancestors 'none'"
    ),
}


def error_page(title: str, message: str, *, site_url: str, status_code: int = 400) -> HTMLResponse:
    return _page(
        title=title,
        eyebrow="Авторизация Discord",
        message=html.escape(str(message)),
        site_url=site_url,
        status_code=status_code,
        tone="error",
        cta_href=site_url,
        cta_label="На сайт",
    )


def success_page(*, site_url: str, redirect_url: str, username: str) -> HTMLResponse:
    safe_user = html.escape(username)
    return _page(
        title="Готово!",
        eyebrow="Авторизация Discord",
        message=(
            f"Аккаунт <strong>{safe_user}</strong> привязан к игре.<br>"
            "Сейчас откроется Мини-станция…"
        ),
        site_url=site_url,
        status_code=200,
        tone="success",
        redirect_url=redirect_url,
        cta_href=redirect_url,
        cta_label="Перейти сейчас",
        redirect_delay_ms=1400,
    )


def _page(
    *,
    title: str,
    eyebrow: str,
    message: str,
    site_url: str,
    status_code: int,
    tone: str,
    cta_href: str,
    cta_label: str,
    redirect_url: str | None = None,
    redirect_delay_ms: int = 1400,
) -> HTMLResponse:
    safe_title = html.escape(title)
    safe_eyebrow = html.escape(eyebrow)
    safe_site = html.escape(site_url, quote=True)
    safe_cta_href = html.escape(cta_href, quote=True)
    safe_cta_label = html.escape(cta_label)

    if tone == "success":
        icon = "✓"
        status_class = "status--ok"
    else:
        icon = "!"
        status_class = "status--err"

    refresh = ""
    script = ""
    if redirect_url:
        safe_refresh = html.escape(redirect_url, quote=True)
        refresh = f'<meta http-equiv="refresh" content="{max(1, redirect_delay_ms // 1000)};url={safe_refresh}">'
        script = (
            "<script>"
            f"setTimeout(function(){{location.replace({json.dumps(redirect_url)});}}, {int(redirect_delay_ms)});"
            "</script>"
        )

    page = f"""<!doctype html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex,nofollow">
  {refresh}
  <title>{safe_title} · Мини-станция</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=Exo+2:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --font-pixel: 'Press Start 2P', 'Courier New', monospace;
      --font-body: 'Exo 2', 'Segoe UI', system-ui, sans-serif;
      --bg: #0a0f1e;
      --panel: #141c33;
      --panel-2: #0f1628;
      --border: #283355;
      --ink: #e9eef9;
      --muted: #9aa8c6;
      --accent: #ffb020;
      --accent-deep: #e68900;
      --discord: #5865F2;
      --success: #38c273;
      --danger: #ef6a5e;
      --grad-accent: linear-gradient(135deg, #ffd54f 0%, #ff9800 48%, #ff6d00 100%);
      --shadow-hard: 0 4px 0 rgba(0, 0, 0, 0.35), 0 12px 28px rgba(0, 0, 0, 0.35);
      --shadow-btn: 0 3px 0 rgba(0, 0, 0, 0.45);
      --radius: 10px;
    }}
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px 16px;
      font-family: var(--font-body);
      color: var(--ink);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }}
    body::before {{
      content: '';
      position: fixed;
      inset: 0;
      z-index: -2;
      pointer-events: none;
      background:
        radial-gradient(860px 500px at 10% -10%, rgba(255, 176, 32, 0.14), transparent 70%),
        radial-gradient(700px 440px at 94% 6%, rgba(255, 140, 40, 0.12), transparent 68%),
        radial-gradient(600px 380px at 48% 108%, rgba(80, 120, 200, 0.06), transparent 62%),
        linear-gradient(180deg, #0a1020 0%, transparent 40%, rgba(8, 12, 24, 0.4) 100%);
    }}
    .glow {{
      position: fixed;
      border-radius: 50%;
      filter: blur(64px);
      pointer-events: none;
      z-index: -1;
      opacity: .7;
    }}
    .glow-1 {{
      width: 320px; height: 320px; top: 8%; left: 6%;
      background: rgba(255, 200, 46, 0.22);
    }}
    .glow-2 {{
      width: 280px; height: 280px; right: 8%; bottom: 12%;
      background: rgba(255, 140, 40, 0.16);
    }}
    .shell {{
      width: min(100%, 440px);
      display: grid;
      gap: 18px;
    }}
    .brand {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      text-decoration: none;
      color: var(--ink);
    }}
    .brand-mark {{
      width: 42px;
      height: 42px;
      border-radius: 10px;
      display: grid;
      place-items: center;
      background: var(--grad-accent);
      box-shadow: var(--shadow-btn);
      font-family: var(--font-pixel);
      font-size: 0.72rem;
      color: #1a1205;
      font-weight: 700;
    }}
    .brand h1 {{
      font-family: var(--font-pixel);
      font-size: 0.78rem;
      line-height: 1.4;
      letter-spacing: 0.02em;
    }}
    .brand h1 span {{ color: var(--accent); }}
    .card {{
      background: var(--panel);
      border: 2px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow-hard);
      padding: 28px 24px 24px;
      text-align: center;
    }}
    .status {{
      width: 64px;
      height: 64px;
      margin: 0 auto 18px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-family: var(--font-pixel);
      font-size: 1.2rem;
      border: 3px solid transparent;
    }}
    .status--ok {{
      color: #0d2a18;
      background: linear-gradient(145deg, #6ee7a4, var(--success));
      box-shadow: 0 0 0 6px rgba(56, 194, 115, 0.15), var(--shadow-btn);
    }}
    .status--err {{
      color: #2a0d0b;
      background: linear-gradient(145deg, #ff9a90, var(--danger));
      box-shadow: 0 0 0 6px rgba(239, 106, 94, 0.15), var(--shadow-btn);
    }}
    .eyebrow {{
      font-family: var(--font-pixel);
      font-size: 0.52rem;
      color: var(--accent);
      letter-spacing: 0.04em;
      margin-bottom: 12px;
      text-transform: uppercase;
    }}
    .card h2 {{
      font-family: var(--font-pixel);
      font-size: 0.95rem;
      line-height: 1.45;
      margin-bottom: 14px;
    }}
    .card p {{
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.55;
      margin-bottom: 22px;
    }}
    .card p strong {{ color: var(--ink); font-weight: 700; }}
    .cta {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      min-height: 44px;
      padding: 0 18px;
      border-radius: 8px;
      border: 2px solid var(--accent-deep);
      background: var(--grad-accent);
      color: #1a1205;
      text-decoration: none;
      font-family: var(--font-pixel);
      font-size: 0.58rem;
      line-height: 1.3;
      box-shadow: var(--shadow-btn);
      transition: transform .15s ease, filter .15s ease;
    }}
    .cta:hover {{ transform: translateY(-1px); filter: brightness(1.05); }}
    .cta:active {{ transform: translateY(1px); box-shadow: none; }}
    .meta {{
      text-align: center;
      color: var(--muted);
      font-size: 0.88rem;
    }}
    .meta a {{
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }}
    .meta a:hover {{ text-decoration: underline; }}
    .discord-chip {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: 16px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(88, 101, 242, 0.16);
      border: 1px solid rgba(88, 101, 242, 0.35);
      color: #c7cdff;
      font-size: 0.85rem;
    }}
    .discord-chip i {{
      width: 14px;
      height: 14px;
      border-radius: 4px;
      background: var(--discord);
      display: inline-block;
    }}
  </style>
</head>
<body>
  <div class="glow glow-1" aria-hidden="true"></div>
  <div class="glow glow-2" aria-hidden="true"></div>
  <div class="shell">
    <a class="brand" href="{safe_site}">
      <div class="brand-mark">MS</div>
      <h1>Мини<span>-</span>станция</h1>
    </a>
    <main class="card">
      <div class="status {status_class}" aria-hidden="true">{icon}</div>
      <div class="eyebrow">{safe_eyebrow}</div>
      <h2>{safe_title}</h2>
      <p>{message}</p>
      <a class="cta" href="{safe_cta_href}">{safe_cta_label}</a>
      <div class="discord-chip"><i></i> Discord · SS14</div>
    </main>
    <p class="meta"><a href="{safe_site}">ministation.ru</a></p>
  </div>
  {script}
</body>
</html>"""
    return HTMLResponse(page, status_code=status_code, headers=_HTML_HEADERS)
