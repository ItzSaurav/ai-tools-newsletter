"""
build_draft.py — Build the premium HTML newsletter email and send review draft.

Design goals:
  - Responsive, mobile-friendly inline CSS
  - Works correctly in Gmail (no external stylesheets, no floats)
  - Dark header with gradient, category section headers
  - Per-article cards: title, summary, "why builders care",
    Read Article button, source badge, difficulty badge, tags, reading time
  - Footer with repo link and generation timestamp
"""

from __future__ import annotations

import datetime
import html as html_module
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from dotenv import load_dotenv

from config import (
    CURATED_ITEMS_FILE,
    DRAFTS_DIR,
    ensure_dirs,
    get_logger,
)

load_dotenv()

log = get_logger(
    "build_draft",
    log_file=f"logs/build_{datetime.date.today().isoformat()}.log",
)

TODAY_UTC = datetime.datetime.now(datetime.timezone.utc)
TODAY_STR = TODAY_UTC.date().isoformat()
TODAY_PRETTY = TODAY_UTC.strftime("%B %d, %Y")

# ─────────────────────────────────────────────
# COLOUR PALETTE (per category)
# ─────────────────────────────────────────────
CATEGORY_COLORS = {
    "AI Models":      {"header": "#4F46E5", "badge": "#EEF2FF", "badge_text": "#4F46E5"},
    "AI Tools":       {"header": "#0891B2", "badge": "#E0F2FE", "badge_text": "#0891B2"},
    "Coding":         {"header": "#059669", "badge": "#ECFDF5", "badge_text": "#059669"},
    "Research":       {"header": "#7C3AED", "badge": "#F5F3FF", "badge_text": "#7C3AED"},
    "Agents":         {"header": "#D97706", "badge": "#FFFBEB", "badge_text": "#B45309"},
    "Infrastructure": {"header": "#DC2626", "badge": "#FEF2F2", "badge_text": "#DC2626"},
    "Open Source":    {"header": "#16A34A", "badge": "#F0FDF4", "badge_text": "#16A34A"},
    "Tutorials":      {"header": "#EA580C", "badge": "#FFF7ED", "badge_text": "#EA580C"},
    "Benchmarks":     {"header": "#BE185D", "badge": "#FDF2F8", "badge_text": "#BE185D"},
    "Industry News":  {"header": "#475569", "badge": "#F8FAFC", "badge_text": "#475569"},
}
_DEFAULT_COLORS = {"header": "#1E293B", "badge": "#F1F5F9", "badge_text": "#1E293B"}

DIFFICULTY_COLORS = {
    "Beginner":     {"bg": "#DCFCE7", "text": "#166534"},
    "Intermediate": {"bg": "#FEF9C3", "text": "#713F12"},
    "Advanced":     {"bg": "#FEE2E2", "text": "#991B1B"},
}
_DEFAULT_DIFF = {"bg": "#F1F5F9", "text": "#1E293B"}


def _esc(s: str) -> str:
    return html_module.escape(str(s))


def _esc_url(s: str) -> str:
    """Escape a URL for use in an HTML attribute (quotes escaped)."""
    return html_module.escape(str(s), quote=True)


def _category_colors(cat: str) -> dict:
    return CATEGORY_COLORS.get(cat, _DEFAULT_COLORS)


def _diff_colors(diff: str) -> dict:
    return DIFFICULTY_COLORS.get(diff, _DEFAULT_DIFF)


# ─────────────────────────────────────────────
# COMPONENT RENDERERS
# ─────────────────────────────────────────────

def _render_tag(tag: str) -> str:
    return (
        f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;'
        f'background:#F1F5F9;color:#334155;border-radius:12px;'
        f'font-size:11px;font-family:monospace;">'
        f'#{_esc(tag)}</span>'
    )


def _render_article_card(item: dict) -> str:
    cat = item.get("category", "Industry News")
    colors = _category_colors(cat)
    diff = item.get("difficulty", "Intermediate")
    diff_c = _diff_colors(diff)
    title = _esc(item.get("title", "Untitled"))
    url = _esc_url(item.get("url", "#"))
    source = _esc(item.get("source", ""))
    summary = _esc(item.get("summary", ""))
    why = _esc(item.get("why_builders_care", item.get("why_it_matters", "")))
    reading_time = item.get("reading_time_mins", 5)
    tags = item.get("tags", [])
    conf = item.get("confidence_score", "")

    tags_html = "".join(_render_tag(t) for t in tags) if tags else ""

    return f"""
<!-- Article Card -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:600px;margin:0 auto 24px auto;border-radius:12px;
              overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08);
              border:1px solid #E2E8F0;">
  <!-- Card accent bar -->
  <tr>
    <td style="height:4px;background:{colors['header']};"></td>
  </tr>
  <!-- Card body -->
  <tr>
    <td style="padding:20px 24px;background:#FFFFFF;">
      <!-- Meta row -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="margin-bottom:10px;">
        <tr>
          <td>
            <span style="display:inline-block;padding:2px 10px;background:{colors['badge']};
                         color:{colors['badge_text']};border-radius:20px;
                         font-size:11px;font-weight:600;text-transform:uppercase;
                         letter-spacing:0.5px;">{_esc(cat)}</span>
            &nbsp;
            <span style="display:inline-block;padding:2px 10px;background:{diff_c['bg']};
                         color:{diff_c['text']};border-radius:20px;font-size:11px;
                         font-weight:600;">{_esc(diff)}</span>
            &nbsp;
            <span style="font-size:11px;color:#94A3B8;">⏱ {reading_time} min read</span>
          </td>
          <td align="right">
            <span style="font-size:11px;color:#94A3B8;">{_esc(source)}</span>
          </td>
        </tr>
      </table>
      <!-- Title -->
      <h3 style="margin:0 0 10px 0;font-size:18px;font-weight:700;
                 color:#0F172A;line-height:1.35;">
        <a href="{url}" style="color:#0F172A;text-decoration:none;"
           target="_blank">{title}</a>
      </h3>
      <!-- Summary -->
      <p style="margin:0 0 12px 0;font-size:14px;color:#475569;line-height:1.65;">
        {summary}
      </p>
      <!-- Why builders care -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="margin-bottom:14px;border-radius:8px;
                    background:linear-gradient(135deg,#F0F9FF,#E0F2FE);">
        <tr>
          <td style="padding:10px 14px;">
            <p style="margin:0;font-size:13px;color:#0369A1;font-weight:500;">
              🔧 <strong>Why builders care:</strong> {why}
            </p>
          </td>
        </tr>
      </table>
      <!-- Tags and CTA -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:middle;">
            {tags_html}
          </td>
          <td align="right" style="vertical-align:middle;white-space:nowrap;">
            <a href="{url}" target="_blank"
               style="display:inline-block;padding:8px 18px;
                      background:{colors['header']};color:#FFFFFF;
                      border-radius:6px;text-decoration:none;
                      font-size:13px;font-weight:600;">
              Read →
            </a>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
"""


def _render_category_section(cat: str, items: List[dict]) -> str:
    colors = _category_colors(cat)
    cards = "".join(_render_article_card(item) for item in items)
    return f"""
<!-- Category Section: {cat} -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:600px;margin:0 auto 8px auto;">
  <tr>
    <td style="padding:28px 0 12px 0;">
      <table role="presentation" cellpadding="0" cellspacing="0">
        <tr>
          <td style="width:4px;background:{colors['header']};border-radius:2px;"></td>
          <td style="padding-left:12px;">
            <h2 style="margin:0;font-size:20px;font-weight:700;
                       color:{colors['header']};">{_esc(cat)}</h2>
          </td>
        </tr>
      </table>
    </td>
  </tr>
</table>
{cards}
"""


def build_html(curated_data: dict) -> str:
    items = curated_data.get("curated_items", [])
    intro = _esc(curated_data.get("intro", ""))
    n_articles = len(items)
    sources = list(dict.fromkeys(i.get("source", "") for i in items))

    # Group by category (preserve order)
    grouped: dict[str, List[dict]] = {}
    for item in items:
        cat = item.get("category", "Industry News")
        grouped.setdefault(cat, []).append(item)

    sections_html = "".join(
        _render_category_section(cat, cat_items)
        for cat, cat_items in grouped.items()
    )

    sources_text = " · ".join(sources[:8])
    repo_url = "https://github.com/ItzSaurav/ai-tools-newsletter"
    repo_url_esc = _esc_url(repo_url)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>The Builder's Brief — {TODAY_PRETTY}</title>
</head>
<body style="margin:0;padding:0;background:#F8FAFC;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

<!-- Outer wrapper -->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:#F8FAFC;padding:24px 16px;">
  <tr>
    <td align="center">

      <!-- Max-width container -->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:640px;">

        <!-- ══════ HEADER ══════ -->
        <tr>
          <td style="border-radius:16px 16px 0 0;overflow:hidden;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:linear-gradient(135deg,#0F172A 0%,#1E3A5F 50%,#0F172A 100%);">
              <tr>
                <td style="padding:36px 32px 28px 32px;">
                  <!-- Logo row -->
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                    <tr>
                      <td>
                        <span style="display:inline-block;padding:4px 12px;
                                     background:rgba(99,102,241,0.3);
                                     border:1px solid rgba(99,102,241,0.5);
                                     border-radius:20px;font-size:12px;
                                     color:#A5B4FC;font-weight:600;
                                     letter-spacing:1px;text-transform:uppercase;">
                          AI Newsletter
                        </span>
                      </td>
                      <td align="right">
                        <span style="font-size:12px;color:#64748B;">{TODAY_PRETTY}</span>
                      </td>
                    </tr>
                  </table>
                  <!-- Title -->
                  <h1 style="margin:16px 0 8px 0;font-size:32px;font-weight:800;
                             color:#FFFFFF;letter-spacing:-0.5px;line-height:1.2;">
                    The Builder's Brief
                  </h1>
                  <p style="margin:0 0 20px 0;font-size:15px;color:#94A3B8;
                            font-weight:400;">
                    Hand-curated AI tools, research &amp; agents for builders
                  </p>
                  <!-- Stats row -->
                  <table role="presentation" cellpadding="0" cellspacing="0">
                    <tr>
                      <td style="padding:6px 14px;background:rgba(255,255,255,0.08);
                                 border-radius:8px;margin-right:8px;">
                        <span style="font-size:13px;color:#CBD5E1;">
                          📰 <strong style="color:#FFF;">{n_articles}</strong> articles
                        </span>
                      </td>
                      <td style="width:8px;"></td>
                      <td style="padding:6px 14px;background:rgba(255,255,255,0.08);
                                 border-radius:8px;">
                        <span style="font-size:13px;color:#CBD5E1;">
                          🤖 AI-curated
                        </span>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <!-- Intro -->
              {f'''<tr>
                <td style="padding:0 32px 28px 32px;">
                  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                         style="background:rgba(255,255,255,0.05);border-radius:8px;
                                border-left:3px solid #6366F1;">
                    <tr>
                      <td style="padding:14px 18px;">
                        <p style="margin:0;font-size:14px;color:#CBD5E1;line-height:1.6;">
                          {intro}
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>''' if intro else ''}
            </table>
          </td>
        </tr>

        <!-- ══════ CONTENT ══════ -->
        <tr>
          <td style="background:#F8FAFC;padding:24px 20px;">
            {sections_html}
          </td>
        </tr>

        <!-- ══════ FOOTER ══════ -->
        <tr>
          <td style="border-radius:0 0 16px 16px;overflow:hidden;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                   style="background:#0F172A;">
              <tr>
                <td style="padding:28px 32px;text-align:center;">
                  <p style="margin:0 0 8px 0;font-size:13px;color:#64748B;">
                    Sources: {_esc(sources_text)}
                  </p>
                  <p style="margin:0 0 8px 0;font-size:12px;color:#475569;">
                    Generated by
                    <a href="{repo_url_esc}" style="color:#6366F1;text-decoration:none;">
                      AI Tools Newsletter Pipeline
                    </a>
                    on {_esc(TODAY_PRETTY)} UTC
                  </p>
                  <p style="margin:0;font-size:11px;color:#334155;">
                    This is an automated review draft — approve with
                    <code style="background:#1E293B;color:#94A3B8;padding:1px 5px;
                                 border-radius:3px;">python approve_and_send.py</code>
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>

</body>
</html>"""


# ─────────────────────────────────────────────
# EMAIL SENDER
# ─────────────────────────────────────────────

def send_review_email(subject: str, html_content: str, recipient: str) -> bool:
    user = os.getenv("GMAIL_USER")
    password = os.getenv("GMAIL_APP_PASSWORD")

    if not user or not password:
        log.error("Gmail credentials not set. Cannot send review email.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"The Builder's Brief <{user}>"
    msg["To"] = recipient

    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        log.info(f"Connecting to Gmail SMTP to send draft to {recipient}…")
        t0 = datetime.datetime.now()
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=20)
        server.starttls()
        server.login(user, password)
        server.sendmail(user, recipient, msg.as_string())
        server.quit()
        elapsed = (datetime.datetime.now() - t0).total_seconds()
        log.info(f"Review draft sent successfully in {elapsed:.1f}s")
        return True
    except Exception as exc:
        log.error(f"Failed to send review email: {exc}")
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main() -> None:
    ensure_dirs()

    if not os.path.exists(CURATED_ITEMS_FILE):
        log.error(f"{CURATED_ITEMS_FILE} not found. Aborting.")
        return

    with open(CURATED_ITEMS_FILE, "r", encoding="utf-8") as f:
        curated_data = json.load(f)

    items = curated_data.get("curated_items", [])
    if not items:
        log.warning("No curated items to build draft from.")
        return

    log.info(f"Building HTML email for {len(items)} articles…")
    final_html = build_html(curated_data)

    # Save HTML draft
    draft_path = f"{DRAFTS_DIR}/{TODAY_STR}.html"
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(final_html)
    log.info(f"Draft saved → {draft_path}")

    # Save JSON snapshot for approve_and_send.py
    draft_json_path = f"{DRAFTS_DIR}/{TODAY_STR}.json"
    with open(draft_json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    # Send review email
    if os.getenv("DRY_RUN", "false").lower() != "true":
        recipient = os.getenv("GMAIL_USER", "")
        if recipient:
            send_review_email(
                subject=f"[REVIEW] The Builder's Brief — {TODAY_PRETTY}",
                html_content=final_html,
                recipient=recipient,
            )
        else:
            log.warning("GMAIL_USER not set. Skipping review email.")
    else:
        log.info("DRY_RUN=true — skipping email send.")


if __name__ == "__main__":
    main()
