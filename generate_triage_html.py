"""Generate ultra-premium triage_viewer.html using the tare.tools SIGNAL Design System and full 14-Theme Engine."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Load data
data_path = ROOT / "output" / "validation_triage_data.json"
triage_data = json.loads(data_path.read_text(encoding="utf-8"))


def slugify(text: str) -> str:
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug or "section"


def parse_markdown_with_toc(md_text: str, prefix: str = "doc") -> tuple[str, list[dict]]:
    lines = md_text.splitlines()
    html_lines = []
    toc = []
    
    in_code_block = False
    code_lang = ""
    code_content = []
    in_table = False
    table_lines = []
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        res = []
        if in_ul:
            res.append("</ul>")
            in_ul = False
        if in_ol:
            res.append("</ol>")
            in_ol = False
        return res

    def close_table():
        nonlocal in_table, table_lines
        if not in_table or not table_lines:
            in_table = False
            table_lines = []
            return []
        
        headers = [c.strip() for c in table_lines[0].strip("|").split("|")]
        rows = table_lines[2:] if len(table_lines) > 2 else []
        
        t_html = ['<div class="table-wrapper"><table class="wiki-table"><thead><tr>']
        for h in headers:
            t_html.append(f'<th>{inline_format(h)}</th>')
        t_html.append('</tr></thead><tbody>')
        for r in rows:
            cols = [c.strip() for c in r.strip("|").split("|")]
            t_html.append('<tr>')
            for c in cols:
                t_html.append(f'<td>{inline_format(c)}</td>')
            t_html.append('</tr>')
        t_html.append('</tbody></table></div>')
        in_table = False
        table_lines = []
        return t_html

    def inline_format(text: str) -> str:
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        return text

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append(
                    f'<div class="code-block-wrapper">'
                    f'<div class="code-block-header"><span>{code_lang or "code"}</span><button class="btn-copy-code" onclick="copyCode(this)">Copiar / Copy</button></div>'
                    f'<pre class="wiki-code"><code class="language-{code_lang}">{chr(10).join(code_content)}</code></pre>'
                    f'</div>'
                )
                in_code_block = False
                code_content = []
                code_lang = ""
            else:
                html_lines.extend(close_lists())
                html_lines.extend(close_table())
                in_code_block = True
                code_lang = stripped[3:].strip()
            continue

        if in_code_block:
            code_content.append(stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            html_lines.extend(close_lists())
            if not in_table:
                in_table = True
                table_lines = [stripped]
            else:
                table_lines.append(stripped)
            continue
        elif in_table:
            html_lines.extend(close_table())

        if not stripped:
            html_lines.extend(close_lists())
            continue

        if stripped.startswith("# "):
            html_lines.extend(close_lists())
            title = stripped[2:].strip()
            slug = f"{prefix}-{slugify(title)}"
            html_lines.append(f'<h1 id="{slug}" class="wiki-h1">{inline_format(title)}</h1>')
            toc.append({"level": 1, "title": title, "slug": slug})
            continue
        if stripped.startswith("## "):
            html_lines.extend(close_lists())
            title = stripped[3:].strip()
            slug = f"{prefix}-{slugify(title)}"
            html_lines.append(f'<h2 id="{slug}" class="wiki-h2"><a href="#{slug}" class="anchor-link">#</a> {inline_format(title)}</h2>')
            toc.append({"level": 2, "title": title, "slug": slug})
            continue
        if stripped.startswith("### "):
            html_lines.extend(close_lists())
            title = stripped[4:].strip()
            slug = f"{prefix}-{slugify(title)}"
            
            callout_class = ""
            if "🐞" in title or "bug" in title.lower():
                callout_class = " callout-bug-title"
            elif "🛡️" in title or "falso positivo" in title.lower() or "false positive" in title.lower():
                callout_class = " callout-fp-title"
            elif "📦" in title or "débito" in title.lower() or "debt" in title.lower():
                callout_class = " callout-debt-title"
                
            html_lines.append(f'<h3 id="{slug}" class="wiki-h3{callout_class}"><a href="#{slug}" class="anchor-link">#</a> {inline_format(title)}</h3>')
            toc.append({"level": 3, "title": title, "slug": slug})
            continue
        if stripped.startswith("#### "):
            html_lines.extend(close_lists())
            title = stripped[5:].strip()
            slug = f"{prefix}-{slugify(title)}"
            html_lines.append(f'<h4 id="{slug}" class="wiki-h4">{inline_format(title)}</h4>')
            continue

        if stripped.startswith("> "):
            html_lines.extend(close_lists())
            quote_text = stripped[2:].strip()
            alert_type = "note"
            if quote_text.startswith("[!WARNING]") or quote_text.startswith("⚠️"):
                alert_type = "warning"
                quote_text = quote_text.replace("[!WARNING]", "").strip()
            elif quote_text.startswith("[!TIP]") or quote_text.startswith("💡"):
                alert_type = "tip"
                quote_text = quote_text.replace("[!TIP]", "").strip()
            elif quote_text.startswith("[!IMPORTANT]"):
                alert_type = "important"
                quote_text = quote_text.replace("[!IMPORTANT]", "").strip()
            html_lines.append(f'<div class="wiki-callout wiki-callout-{alert_type}">{inline_format(quote_text)}</div>')
            continue

        if stripped in ("---", "***", "___"):
            html_lines.extend(close_lists())
            html_lines.append('<hr class="wiki-hr">')
            continue

        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                html_lines.extend(close_lists())
                html_lines.append('<ul class="wiki-ul">')
                in_ul = True
            html_lines.append(f'<li>{inline_format(stripped[2:])}</li>')
            continue

        m_ol = re.match(r'^\d+\.\s+(.+)$', stripped)
        if m_ol:
            if not in_ol:
                html_lines.extend(close_lists())
                html_lines.append('<ol class="wiki-ol">')
                in_ol = True
            html_lines.append(f'<li>{inline_format(m_ol.group(1))}</li>')
            continue

        html_lines.extend(close_lists())
        html_lines.append(f'<p class="wiki-p">{inline_format(stripped)}</p>')

    html_lines.extend(close_lists())
    html_lines.extend(close_table())
    return "\n".join(html_lines), toc


# Compile PT-BR docs
pt_triage = (ROOT / "docs" / "operations" / "TRIAGE_AND_DOGFOODING_GUIDE.md").read_text(encoding="utf-8")
pt_readme = (ROOT / "README.md").read_text(encoding="utf-8") + "\n\n---\n\n" + (ROOT / "docs" / "operations" / "LARGE_EXPORT_PLAYBOOK.md").read_text(encoding="utf-8")
pt_rules = (ROOT / "rules" / "ibm_watson_dialog.md").read_text(encoding="utf-8")
pt_arch = (ROOT / "docs" / "architecture" / "VALIDATION_AUDIT_CALIBRATION.md").read_text(encoding="utf-8")

html_pt_triage, toc_pt_triage = parse_markdown_with_toc(pt_triage, "pt-triage")
html_pt_manual, toc_pt_manual = parse_markdown_with_toc(pt_readme, "pt-manual")
html_pt_rules, toc_pt_rules = parse_markdown_with_toc(pt_rules, "pt-rules")
html_pt_arch, toc_pt_arch = parse_markdown_with_toc(pt_arch, "pt-arch")

# Compile EN-US docs
en_triage = (ROOT / "docs" / "operations" / "TRIAGE_AND_DOGFOODING_GUIDE.en.md").read_text(encoding="utf-8")
en_readme = (ROOT / "README.en.md").read_text(encoding="utf-8") + "\n\n---\n\n" + (ROOT / "docs" / "operations" / "LARGE_EXPORT_PLAYBOOK.en.md").read_text(encoding="utf-8")
en_rules = (ROOT / "rules" / "ibm_watson_dialog.en.md").read_text(encoding="utf-8")
en_arch = (ROOT / "docs" / "architecture" / "VALIDATION_AUDIT_CALIBRATION.en.md").read_text(encoding="utf-8")

html_en_triage, toc_en_triage = parse_markdown_with_toc(en_triage, "en-triage")
html_en_manual, toc_en_manual = parse_markdown_with_toc(en_readme, "en-manual")
html_en_rules, toc_en_rules = parse_markdown_with_toc(en_rules, "en-rules")
html_en_arch, toc_en_arch = parse_markdown_with_toc(en_arch, "en-arch")

def render_toc_sidebar(toc: list[dict], section_title: str) -> str:
    links = []
    for item in toc:
        indent = "padding-left: 12px;" if item["level"] == 2 else ("padding-left: 22px; font-size: 11px;" if item["level"] == 3 else "font-weight: 600;")
        links.append(f'<a href="#{item["slug"]}" class="toc-link" style="{indent}">{item["title"]}</a>')
    return f"""
      <aside class="wiki-toc-sidebar">
        <div class="wiki-toc-header">{section_title}</div>
        <nav class="wiki-toc-nav">
          {''.join(links)}
        </nav>
      </aside>
    """


html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="design-system" content="tare.tools/SIGNAL/v1">
  <title>tare.tools — Watson Assistant Dialog Triage & Mission Control</title>
  <style>
    /* ==========================================================================
       SIGNAL Design Tokens - Canonical UI Law (warm-black + lime-phosphor)
       ========================================================================== */
    :root {{
      color-scheme: dark;
      
      --bg-base: #0A0B08;
      --bg-void: #0A0B08;
      --atmo-glow: #12160C;
      --surface-1: #0F1109;
      --surface-2: #14170E;
      --surface-3: #1B1F14;
      --surface-hover: #1B1F14;
      
      --border-subtle: #1E2216;
      --border: #2B3020;
      --border-strong: #3A4029;
      
      --text-primary: #EDEEE1;
      --text-secondary: #A6AA90;
      --text-muted: #8B9173;
      --text-disabled: #4A4E39;
      
      --accent: #CBF23F; /* Dominant lime-phosphor */
      --accent-bg: rgba(203, 242, 63, 0.12);
      --accent-border: rgba(203, 242, 63, 0.40);
      
      --stream: #45E0C4; /* Live teal / oscilloscope */
      --stream-bg: rgba(69, 224, 196, 0.12);
      --stream-border: rgba(69, 224, 196, 0.34);
      
      --success: #7CCB6A;
      --success-bg: rgba(124, 203, 106, 0.12);
      --success-border: rgba(124, 203, 106, 0.32);
      
      --warning: #E8A93B;
      --warning-bg: rgba(232, 169, 59, 0.12);
      --warning-border: rgba(232, 169, 59, 0.32);
      
      --danger: #F2685C;
      --danger-bg: rgba(242, 104, 92, 0.12);
      --danger-border: rgba(242, 104, 92, 0.34);
      
      --font-ui: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --font-prose: "IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      
      --text-xs: 11px;
      --text-sm: 12px;
      --text-md: 13px;
      --text-lg: 15px;
      --text-xl: 18px;
      
      --h-topbar: 52px;
      --radius-sm: 8px;
      --radius-xs: 6px;
      --space-1: 4px;
      --space-2: 8px;
      --space-3: 12px;
      --space-4: 16px;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: var(--font-ui);
      background-color: var(--bg-base);
      background-image: radial-gradient(circle at 50% 0%, var(--atmo-glow) 0%, var(--bg-base) 75%);
      color: var(--text-primary);
      line-height: 1.55;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }}

    /* Header */
    header.app-header {{
      background: var(--surface-1);
      border-bottom: 1px solid var(--border);
      padding: 0 var(--space-4);
      height: var(--h-topbar);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
      z-index: 50;
    }}

    .brand {{ display: flex; align-items: center; gap: 10px; }}
    
    .brand-logo {{
      font-family: var(--font-mono);
      font-size: var(--text-md);
      font-weight: 700;
      letter-spacing: -0.3px;
      color: var(--text-primary);
      display: flex;
      align-items: center;
      gap: var(--space-2);
    }}
    .brand-logo::before {{
      content: "";
      display: inline-block;
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
    }}

    .brand-pill {{
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      font-weight: 600;
      background: var(--accent-bg);
      color: var(--accent);
      border: 1px solid var(--accent-border);
      padding: 2px 8px;
      border-radius: var(--radius-xs);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    /* Theme Selector Dropdown */
    .theme-select {{
      background: var(--surface-2);
      color: var(--text-secondary);
      border: 1px solid var(--border);
      border-radius: var(--radius-xs);
      padding: 4px 8px;
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      outline: none;
      transition: all 0.15s;
    }}
    .theme-select:focus, .theme-select:hover {{
      border-color: var(--accent);
      color: var(--text-primary);
      box-shadow: 0 0 0 1px var(--accent-border);
    }}
    .theme-select optgroup {{
      background: var(--surface-1);
      color: var(--text-muted);
      font-weight: 700;
    }}
    .theme-select option {{
      background: var(--surface-2);
      color: var(--text-primary);
      font-weight: 500;
    }}

    .nav-tabs {{
      display: flex;
      gap: 2px;
      background: var(--bg-base);
      padding: 2px;
      border-radius: var(--radius-xs);
      border: 1px solid var(--border-subtle);
    }}

    .nav-tab-btn {{
      padding: 5px 12px;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: var(--text-sm);
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      border-radius: var(--radius-xs);
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }}
    .nav-tab-btn:hover {{ color: var(--text-primary); }}
    .nav-tab-btn.active {{
      background: var(--surface-2);
      color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent-border);
    }}

    .header-actions {{ display: flex; align-items: center; gap: var(--space-2); }}

    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 5px 12px;
      border-radius: var(--radius-xs);
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      border: 1px solid var(--border);
      background: var(--surface-1);
      color: var(--text-secondary);
      transition: all 0.15s ease;
    }}
    .btn:hover {{ background: var(--surface-2); color: var(--text-primary); border-color: var(--border-strong); }}
    .btn-primary {{ background: var(--accent-bg); border-color: var(--accent-border); color: var(--accent); }}
    .btn-primary:hover {{ background: rgba(203, 242, 63, 0.22); color: #fff; }}
    .btn-danger {{ background: var(--danger-bg); border-color: var(--danger-border); color: var(--danger); }}
    .btn-danger:hover {{ background: rgba(242, 104, 92, 0.25); }}
    .btn-inspect {{ background: var(--stream-bg); border-color: var(--stream-border); color: var(--stream); }}
    .btn-inspect:hover {{ background: rgba(69, 224, 196, 0.25); }}
    .btn-sm {{ padding: 3px 8px; font-size: var(--text-xs); }}

    .segmented-control {{
      display: flex;
      background: var(--bg-base);
      border-radius: var(--radius-xs);
      padding: 2px;
      border: 1px solid var(--border-subtle);
    }}
    .segmented-control button {{
      padding: 3px 8px;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      border-radius: var(--radius-xs);
      transition: all 0.15s;
    }}
    .segmented-control button.active {{
      background: var(--surface-2);
      color: var(--text-primary);
      box-shadow: 0 0 0 1px var(--border);
    }}

    .lang-switcher {{
      display: flex;
      background: var(--bg-base);
      border-radius: var(--radius-xs);
      padding: 2px;
      border: 1px solid var(--border-subtle);
    }}
    .lang-switcher button {{
      padding: 3px 6px;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      font-weight: 600;
      cursor: pointer;
      border-radius: var(--radius-xs);
      transition: all 0.15s;
    }}
    .lang-switcher button.active {{
      background: var(--accent-bg);
      color: var(--accent);
      box-shadow: 0 0 0 1px var(--accent-border);
    }}

    /* Main Tab Views */
    .view-tab {{
      display: none;
      flex: 1;
      height: calc(100vh - var(--h-topbar));
      overflow: hidden;
    }}
    .view-tab.active {{ display: flex; }}

    /* Triage Tab */
    .triage-sidebar {{
      width: 320px;
      background: var(--surface-1);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }}
    .sidebar-section {{ padding: var(--space-3) var(--space-4); border-bottom: 1px solid var(--border-subtle); }}
    .sidebar-title {{
      font-size: var(--text-xs);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--text-muted);
      margin-bottom: var(--space-2);
    }}

    .search-box {{
      width: 100%;
      padding: 6px 10px;
      background: var(--bg-base);
      border: 1px solid var(--border);
      border-radius: var(--radius-xs);
      color: var(--text-primary);
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      outline: none;
    }}
    .search-box:focus {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-border); }}

    .filter-list {{ list-style: none; display: flex; flex-direction: column; gap: 2px; }}
    .filter-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 5px 8px;
      border-radius: var(--radius-xs);
      font-size: var(--text-xs);
      cursor: pointer;
      color: var(--text-secondary);
      transition: background 0.15s;
    }}
    .filter-item:hover {{ background: var(--surface-hover); color: var(--text-primary); }}
    .filter-item.active {{
      background: var(--surface-2);
      color: var(--accent);
      font-weight: 600;
      box-shadow: inset 2px 0 0 var(--accent);
    }}
    .filter-count {{ font-size: 10px; padding: 1px 6px; border-radius: 10px; background: var(--bg-base); color: var(--text-muted); }}

    .progress-bar-bg {{
      height: 4px;
      background: var(--bg-base);
      border-radius: 2px;
      overflow: hidden;
      display: flex;
      margin-top: 6px;
    }}
    .progress-bar-fill {{ height: 100%; transition: width 0.3s; }}
    .progress-labels {{
      display: flex;
      justify-content: space-between;
      font-size: var(--text-xs);
      color: var(--text-muted);
      margin-top: 4px;
    }}

    .triage-content-area {{
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: var(--bg-base);
    }}

    .content-header {{
      padding: 10px var(--space-4);
      background: var(--surface-1);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}

    .issue-list {{
      flex: 1;
      overflow-y: auto;
      padding: var(--space-4);
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
    }}

    .issue-card {{
      background: var(--surface-1);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 14px 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: border-color 0.15s, box-shadow 0.15s;
    }}
    .issue-card:hover {{ border-color: var(--border-strong); box-shadow: 0 2px 10px rgba(0, 0, 0, 0.4); }}
    .issue-card.triage-bug {{ border-left: 3px solid var(--danger); }}
    .issue-card.triage-false_positive {{ border-left: 3px solid var(--success); }}
    .issue-card.triage-debt {{ border-left: 3px solid var(--warning); }}

    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }}
    .card-tags {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}

    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 6px;
      border-radius: var(--radius-xs);
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .badge-red {{ background: var(--danger-bg); color: var(--danger); border: 1px solid var(--danger-border); }}
    .badge-yellow {{ background: var(--warning-bg); color: var(--warning); border: 1px solid var(--warning-border); }}
    .badge-blue {{ background: var(--stream-bg); color: var(--stream); border: 1px solid var(--stream-border); }}
    .badge-green {{ background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); }}
    .badge-muted {{ background: var(--surface-2); color: var(--text-muted); border: 1px solid var(--border-subtle); }}

    .code-title {{ font-family: var(--font-mono); font-size: var(--text-sm); font-weight: 600; color: var(--text-primary); }}
    .node-pill {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: var(--bg-base);
      border: 1px solid var(--border);
      padding: 1px 6px;
      border-radius: var(--radius-xs);
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      color: var(--text-secondary);
      cursor: pointer;
    }}
    .node-pill:hover {{ color: var(--accent); border-color: var(--accent-border); }}

    .message-box {{
      font-size: var(--text-sm);
      color: var(--text-primary);
      background: var(--surface-2);
      padding: 8px 12px;
      border-radius: var(--radius-xs);
      border-left: 2px solid var(--border-strong);
    }}

    .condition-box {{
      font-family: var(--font-mono);
      font-size: var(--text-xs);
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-xs);
      padding: 8px 12px;
      color: var(--stream);
      word-break: break-all;
      white-space: pre-wrap;
    }}

    .card-bottom {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 8px;
      border-top: 1px solid var(--border-subtle);
    }}

    .triage-buttons {{ display: flex; gap: 6px; }}
    .btn-triage {{
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      padding: 4px 10px;
      border-radius: var(--radius-xs);
      border: 1px solid var(--border);
      background: var(--surface-1);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s;
    }}
    .btn-triage:hover {{ color: var(--text-primary); background: var(--surface-2); }}
    .btn-triage.active-bug {{ background: var(--danger-bg); color: var(--danger); border-color: var(--danger-border); font-weight: 700; }}
    .btn-triage.active-false_positive {{ background: var(--success-bg); color: var(--success); border-color: var(--success-border); font-weight: 700; }}
    .btn-triage.active-debt {{ background: var(--warning-bg); color: var(--warning); border-color: var(--warning-border); font-weight: 700; }}

    .notes-input {{
      width: 100%;
      background: var(--bg-base);
      border: 1px solid var(--border);
      border-radius: var(--radius-xs);
      padding: 6px 10px;
      font-size: var(--text-xs);
      font-family: var(--font-ui);
      color: var(--text-primary);
      margin-top: 6px;
      outline: none;
      resize: vertical;
      min-height: 28px;
      max-height: 100px;
    }}
    .notes-input:focus {{ border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent-border); }}

    /* Dedicated Wiki Portal Layout */
    .wiki-portal-container {{ display: flex; flex: 1; height: 100%; overflow: hidden; }}
    .wiki-toc-sidebar {{
      width: 280px;
      background: var(--surface-1);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      padding: var(--space-4);
      flex-shrink: 0;
    }}
    .wiki-toc-header {{
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.8px;
      color: var(--accent);
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-subtle);
    }}
    .wiki-toc-nav {{ display: flex; flex-direction: column; gap: 2px; }}
    .toc-link {{
      color: var(--text-secondary);
      text-decoration: none;
      font-size: var(--text-xs);
      padding: 3px 6px;
      border-radius: var(--radius-xs);
      transition: all 0.15s;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .toc-link:hover {{ color: var(--accent); background: var(--accent-bg); }}

    .wiki-content-pane {{ flex: 1; overflow-y: auto; padding: 36px 54px; background: var(--bg-base); }}
    .wiki-content-inner {{ max-width: 860px; margin: 0 auto; }}

    .wiki-h1 {{
      font-size: 22px;
      font-weight: 700;
      color: var(--text-primary);
      margin-bottom: 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      letter-spacing: -0.3px;
    }}

    .wiki-h2 {{
      font-size: 16px;
      font-weight: 700;
      color: var(--text-primary);
      margin-top: 32px;
      margin-bottom: 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .anchor-link {{ color: var(--border-strong); text-decoration: none; font-weight: 400; font-size: 14px; }}
    .wiki-h2:hover .anchor-link, .wiki-h3:hover .anchor-link {{ color: var(--accent); }}

    .wiki-h3 {{
      font-size: 14px;
      font-weight: 600;
      color: var(--accent);
      margin-top: 20px;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .callout-bug-title {{ color: var(--danger); }}
    .callout-fp-title {{ color: var(--success); }}
    .callout-debt-title {{ color: var(--warning); }}

    .wiki-h4 {{ font-size: 11px; font-weight: 700; color: var(--text-muted); margin-top: 14px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .wiki-p {{ margin-bottom: 12px; font-size: var(--text-md); line-height: 1.65; color: var(--text-secondary); }}
    .wiki-hr {{ border: 0; border-top: 1px solid var(--border-subtle); margin: 28px 0; }}
    .wiki-ul, .wiki-ol {{ margin-bottom: 14px; padding-left: 20px; font-size: var(--text-md); line-height: 1.65; color: var(--text-secondary); }}
    .wiki-ul li, .wiki-ol li {{ margin-bottom: 4px; }}

    .wiki-callout {{
      border-left: 3px solid var(--accent);
      padding: 10px 14px;
      margin: 16px 0;
      background: var(--surface-2);
      border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
      font-size: var(--text-sm);
      color: var(--text-primary);
      line-height: 1.55;
    }}
    .wiki-callout-warning {{ border-left-color: var(--warning); background: var(--warning-bg); color: var(--warning); }}
    .wiki-callout-tip {{ border-left-color: var(--success); background: var(--success-bg); color: var(--success); }}
    .wiki-callout-important {{ border-left-color: var(--danger); background: var(--danger-bg); color: var(--danger); }}

    .table-wrapper {{ overflow-x: auto; margin: 16px 0; border: 1px solid var(--border); border-radius: var(--radius-xs); }}
    .wiki-table {{ width: 100%; border-collapse: collapse; font-size: var(--text-xs); text-align: left; }}
    .wiki-table th, .wiki-table td {{ padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); }}
    .wiki-table th {{ background: var(--surface-1); color: var(--text-primary); font-weight: 700; }}
    .wiki-table tr:last-child td {{ border-bottom: none; }}
    .wiki-table tr:hover td {{ background: var(--surface-hover); }}

    .code-block-wrapper {{ margin: 14px 0; border-radius: var(--radius-xs); border: 1px solid var(--border); background: var(--surface-2); overflow: hidden; }}
    .code-block-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 10px;
      background: var(--surface-1);
      border-bottom: 1px solid var(--border-subtle);
      font-size: 10px;
      font-family: var(--font-mono);
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    .btn-copy-code {{
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text-muted);
      border-radius: var(--radius-xs);
      padding: 1px 6px;
      font-size: 10px;
      font-family: var(--font-ui);
      cursor: pointer;
      transition: all 0.15s;
    }}
    .btn-copy-code:hover {{ color: var(--accent); border-color: var(--accent-border); }}

    .wiki-code {{ padding: 12px 14px; overflow-x: auto; font-family: var(--font-mono); font-size: var(--text-xs); color: var(--stream); line-height: 1.5; }}

    /* Drawer */
    .drawer-overlay {{
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(2px);
      z-index: 100;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.25s ease;
    }}
    .drawer-overlay.open {{ opacity: 1; pointer-events: auto; }}

    .drawer {{
      position: fixed;
      top: 0; right: 0;
      width: 680px;
      max-width: 90vw;
      height: 100vh;
      background: var(--surface-1);
      border-left: 1px solid var(--border);
      box-shadow: -8px 0 32px rgba(0, 0, 0, 0.7);
      z-index: 101;
      display: flex;
      flex-direction: column;
      transform: translateX(100%);
      transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    .drawer.open {{ transform: translateX(0); }}

    .drawer-header {{
      padding: 14px 20px;
      background: var(--surface-2);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
    }}
    .drawer-title {{ font-size: var(--text-md); font-weight: 700; color: var(--text-primary); }}
    .drawer-body {{ flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 16px; }}
    .drawer-section {{ display: flex; flex-direction: column; gap: 6px; }}
    .drawer-section-title {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: var(--accent); display: flex; align-items: center; gap: 6px; }}

    .breadcrumbs {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 4px;
      font-size: var(--text-xs);
      background: var(--bg-base);
      padding: 6px 10px;
      border-radius: var(--radius-xs);
      border: 1px solid var(--border-subtle);
    }}
    .crumb-item {{ color: var(--stream); cursor: pointer; font-family: var(--font-mono); }}
    .crumb-item:hover {{ color: var(--accent); text-decoration: underline; }}
    .crumb-sep {{ color: var(--text-muted); }}

    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; }}
    .meta-card {{ background: var(--bg-base); border: 1px solid var(--border); border-radius: var(--radius-xs); padding: 6px 10px; display: flex; flex-direction: column; gap: 2px; }}
    .meta-label {{ font-size: 9px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
    .meta-val {{ font-size: var(--text-xs); font-weight: 600; color: var(--text-primary); font-family: var(--font-mono); word-break: break-all; }}

    .slot-item, .child-item, .resp-item {{ background: var(--bg-base); border: 1px solid var(--border); border-radius: var(--radius-xs); padding: 8px 12px; display: flex; flex-direction: column; gap: 4px; }}
    .raw-json-box {{ font-family: var(--font-mono); font-size: var(--text-xs); background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-xs); padding: 10px; color: var(--stream); max-height: 220px; overflow-y: auto; white-space: pre; }}

    .toast {{
      position: fixed;
      bottom: 20px; right: 20px;
      background: var(--surface-3);
      color: var(--text-primary);
      padding: 8px 14px;
      border-radius: var(--radius-xs);
      border: 1px solid var(--accent-border);
      box-shadow: 0 4px 16px rgba(0,0,0,0.6);
      font-size: var(--text-xs);
      display: flex;
      align-items: center;
      gap: 6px;
      z-index: 1000;
      opacity: 0;
      transform: translateY(10px);
      transition: all 0.2s ease;
      pointer-events: none;
    }}
    .toast.show {{ opacity: 1; transform: translateY(0); }}

    .empty-state {{ text-align: center; padding: 48px 20px; color: var(--text-muted); }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: var(--border); border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: var(--text-muted); }}
  </style>
</head>
<body>

  <!-- Top Global Header with Tab Navigation, Theme Selector, and Language Switcher -->
  <header class="app-header">
    <div class="brand">
      <div class="brand-logo">
        <span data-i18n="app_title">tare.tools</span>
      </div>
      <span class="brand-pill">SIGNAL v1.0</span>

      <!-- Theme Selector Dropdown -->
      <select id="themeSelector" class="theme-select" onchange="applyTheme(this.value)" title="Seletor de Tema / Theme Selector">
        <optgroup label="Dark Themes (SIGNAL)">
          <option value="signal" selected>Signal (Default)</option>
          <option value="dracula">Dracula</option>
          <option value="tokyo_night">Tokyo Night</option>
          <option value="nord">Nord Frost</option>
          <option value="catppuccin">Catppuccin Mocha</option>
          <option value="monokai">Monokai Pro</option>
          <option value="gruvbox_dark">Gruvbox Dark</option>
          <option value="solarized_dark">Solarized Dark</option>
        </optgroup>
        <optgroup label="Light Themes">
          <option value="github_light">GitHub Light</option>
          <option value="light">Solar Paper (Light)</option>
          <option value="solarized_light">Solarized Light</option>
          <option value="nord_light">Nord Snow Storm</option>
          <option value="catppuccin_latte">Catppuccin Latte</option>
          <option value="gruvbox_light">Gruvbox Light</option>
        </optgroup>
      </select>

      <nav class="nav-tabs" id="global-tabs">
        <button class="nav-tab-btn active" data-tab="view-triage" id="tab-btn-triage" data-i18n="tab_triage">🔬 Painel de Triagem</button>
        <button class="nav-tab-btn" data-tab="view-triage-guide" id="tab-btn-guide" data-i18n="tab_guide">🎯 Guia de Triagem</button>
        <button class="nav-tab-btn" data-tab="view-manual" id="tab-btn-manual" data-i18n="tab_manual">📖 Manual CLI</button>
        <button class="nav-tab-btn" data-tab="view-ibm-rules" id="tab-btn-rules" data-i18n="tab_rules">📚 Regras IBM</button>
        <button class="nav-tab-btn" data-tab="view-arch" id="tab-btn-arch" data-i18n="tab_arch">📐 Arquitetura</button>
      </nav>
    </div>

    <div class="header-actions">
      <!-- Language Switcher -->
      <div class="lang-switcher" id="lang-selector">
        <button class="active" data-lang="pt-BR" id="btn-lang-pt">PT</button>
        <button data-lang="en-US" id="btn-lang-en">EN</button>
      </div>

      <div class="segmented-control" id="dataset-selector">
        <button class="active" data-corpus="current" id="btn-corpus-current">CURRENT</button>
        <button data-corpus="candidate" id="btn-corpus-candidate">CANDIDATE</button>
      </div>
      <button class="btn btn-sm" id="btn-import" title="Importar JSON / Import JSON" data-i18n="btn_import">📥 Importar</button>
      <input type="file" id="file-importer" accept=".json" style="display: none;">
      <button class="btn btn-sm btn-primary" id="btn-export-json" title="Exportar JSON / Export JSON" data-i18n="btn_export_json">📤 Exportar JSON</button>
      <button class="btn btn-sm" id="btn-export-md" title="Exportar MD / Export MD" data-i18n="btn_export_md">📄 Exportar MD</button>
    </div>
  </header>

  <!-- TAB 1: TRIAGE WORKSPACE -->
  <div id="view-triage" class="view-tab active">
    <aside class="triage-sidebar">
      <div class="sidebar-section">
        <input type="text" id="search-input" class="search-box" placeholder="Buscar por UUID, condição, texto..." data-i18n-placeholder="search_placeholder">
      </div>

      <div class="sidebar-section">
        <div class="sidebar-title" data-i18n="triage_progress_title">Progresso da Triagem</div>
        <div class="progress-wrapper">
          <div class="progress-bar-bg">
            <div id="prog-bug" class="progress-bar-fill" style="background: var(--danger); width: 0%;"></div>
            <div id="prog-fp" class="progress-bar-fill" style="background: var(--success); width: 0%;"></div>
            <div id="prog-debt" class="progress-bar-fill" style="background: var(--warning); width: 0%;"></div>
          </div>
          <div class="progress-labels">
            <span id="triaged-count">0 triados</span>
            <span id="total-actionable-count">0 total</span>
          </div>
        </div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-title" data-i18n="triage_status_title">Status da Triagem</div>
        <ul class="filter-list" id="status-filters">
          <li class="filter-item active" data-status="all" id="filter-status-all">
            <span data-i18n="filter_status_all">Todos os Itens</span>
            <span class="filter-count" id="count-status-all">0</span>
          </li>
          <li class="filter-item" data-status="pending" id="filter-status-pending">
            <span data-i18n="filter_status_pending">⏳ Pendentes</span>
            <span class="filter-count" id="count-status-pending">0</span>
          </li>
          <li class="filter-item" data-status="bug" id="filter-status-bug">
            <span data-i18n="filter_status_bug">🔴 Bugs Confirmados</span>
            <span class="filter-count" id="count-status-bug">0</span>
          </li>
          <li class="filter-item" data-status="false_positive" id="filter-status-fp">
            <span data-i18n="filter_status_fp">🟢 Falsos Positivos</span>
            <span class="filter-count" id="count-status-fp">0</span>
          </li>
          <li class="filter-item" data-status="debt" id="filter-status-debt">
            <span data-i18n="filter_status_debt">🟡 Débito / Backlog</span>
            <span class="filter-count" id="count-status-debt">0</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-title" data-i18n="severity_title">Severidade</div>
        <ul class="filter-list" id="severity-filters">
          <li class="filter-item active" data-severity="all" id="filter-sev-all">
            <span data-i18n="filter_sev_all">Todas as Severidades</span>
            <span class="filter-count" id="count-sev-all">0</span>
          </li>
          <li class="filter-item" data-severity="error" id="filter-sev-error">
            <span data-i18n="filter_sev_error">🔴 Erros (P0)</span>
            <span class="filter-count" id="count-sev-error">0</span>
          </li>
          <li class="filter-item" data-severity="warning" id="filter-sev-warning">
            <span data-i18n="filter_sev_warning">🟡 Avisos (P0 / P1 / Smells)</span>
            <span class="filter-count" id="count-sev-warning">0</span>
          </li>
          <li class="filter-item" data-severity="info" id="filter-sev-info">
            <span data-i18n="filter_sev_info">🔵 Infos (Amostra / Proveniência)</span>
            <span class="filter-count" id="count-sev-info">0</span>
          </li>
        </ul>
      </div>

      <div class="sidebar-section" style="flex: 1; overflow-y: auto;">
        <div class="sidebar-title" data-i18n="issue_code_title">Tipos de Problema (Código)</div>
        <ul class="filter-list" id="code-filters"></ul>
      </div>
    </aside>

    <main class="triage-content-area">
      <div class="content-header">
        <span class="issue-count-label" id="rendered-count-label">Exibindo 0 ocorrência(s)</span>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-sm btn-danger" id="btn-reset-triage" data-i18n="btn_reset">Resetar Triagem</button>
        </div>
      </div>

      <div class="issue-list" id="issues-container"></div>
    </main>

    <!-- Inspection Drawer Overlay & Panel -->
    <div id="drawer-overlay" class="drawer-overlay" onclick="closeDrawer()"></div>
    <div id="drawer" class="drawer">
      <div class="drawer-header">
        <div>
          <div class="drawer-title" id="drawer-node-name">🔍 Inspecionando Nó</div>
          <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
            <code id="drawer-node-uuid" style="color: var(--accent); font-size: 11px; font-family: var(--font-mono); cursor: pointer;" onclick="copyToClipboard(this.textContent)">UUID</code>
            <span id="drawer-node-kind" class="badge badge-muted">tipo</span>
            <span id="drawer-node-status" class="badge badge-green">STATUS</span>
          </div>
        </div>
        <button class="btn btn-sm" onclick="closeDrawer()" id="btn-close-drawer" data-i18n="btn_close">✕ Fechar</button>
      </div>

      <div class="drawer-body" id="drawer-content"></div>
    </div>
  </div>

  <!-- TAB 2: TRIAGE & DOGFOODING GUIDE (PORTAL LAYOUT) -->
  <div id="view-triage-guide" class="view-tab">
    <div class="wiki-portal-container lang-content lang-pt">
      {render_toc_sidebar(toc_pt_triage, "Guia de Triagem")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_pt_triage}</div>
      </main>
    </div>
    <div class="wiki-portal-container lang-content lang-en" style="display: none;">
      {render_toc_sidebar(toc_en_triage, "Triage Guide")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_en_triage}</div>
      </main>
    </div>
  </div>

  <!-- TAB 3: USER MANUAL (CLI) (PORTAL LAYOUT) -->
  <div id="view-manual" class="view-tab">
    <div class="wiki-portal-container lang-content lang-pt">
      {render_toc_sidebar(toc_pt_manual, "Manual CLI & Comandos")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_pt_manual}</div>
      </main>
    </div>
    <div class="wiki-portal-container lang-content lang-en" style="display: none;">
      {render_toc_sidebar(toc_en_manual, "CLI Manual & Reference")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_en_manual}</div>
      </main>
    </div>
  </div>

  <!-- TAB 4: IBM RULES (PORTAL LAYOUT) -->
  <div id="view-ibm-rules" class="view-tab">
    <div class="wiki-portal-container lang-content lang-pt">
      {render_toc_sidebar(toc_pt_rules, "Regras Oficiais IBM")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_pt_rules}</div>
      </main>
    </div>
    <div class="wiki-portal-container lang-content lang-en" style="display: none;">
      {render_toc_sidebar(toc_en_rules, "Official IBM Rules")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_en_rules}</div>
      </main>
    </div>
  </div>

  <!-- TAB 5: ARCHITECTURE & CALIBRATION (PORTAL LAYOUT) -->
  <div id="view-arch" class="view-tab">
    <div class="wiki-portal-container lang-content lang-pt">
      {render_toc_sidebar(toc_pt_arch, "Arquitetura & Calibração")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_pt_arch}</div>
      </main>
    </div>
    <div class="wiki-portal-container lang-content lang-en" style="display: none;">
      {render_toc_sidebar(toc_en_arch, "Architecture & Calibration")}
      <main class="wiki-content-pane">
        <div class="wiki-content-inner">{html_en_arch}</div>
      </main>
    </div>
  </div>

  <div id="toast" class="toast">Notificação</div>

  <script id="triage-data" type="application/json">
{json.dumps(triage_data, ensure_ascii=False)}
  </script>

  <script>
    /* ==========================================================================
       SIGNAL Themes & Palettes (14 High-Fidelity Design Themes)
       ========================================================================== */
    const THEMES = {{
      signal: {{
        name: 'Signal (Default)',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#0A0B08',
          '--bg-void': '#0A0B08',
          '--atmo-glow': '#12160C',
          '--surface-1': '#0F1109',
          '--surface-2': '#14170E',
          '--surface-3': '#1B1F14',
          '--surface-hover': '#1B1F14',
          '--border-subtle': '#1E2216',
          '--border': '#2B3020',
          '--border-strong': '#3A4029',
          '--text-primary': '#EDEEE1',
          '--text-secondary': '#A6AA90',
          '--text-muted': '#8B9173',
          '--text-disabled': '#4A4E39',
          '--accent': '#CBF23F',
          '--accent-bg': 'rgba(203, 242, 63, 0.12)',
          '--accent-border': 'rgba(203, 242, 63, 0.40)',
          '--stream': '#45E0C4',
          '--stream-bg': 'rgba(69, 224, 196, 0.12)',
          '--stream-border': 'rgba(69, 224, 196, 0.34)',
          '--success': '#7CCB6A',
          '--success-bg': 'rgba(124, 203, 106, 0.12)',
          '--success-border': 'rgba(124, 203, 106, 0.32)',
          '--warning': '#E8A93B',
          '--warning-bg': 'rgba(232, 169, 59, 0.12)',
          '--warning-border': 'rgba(232, 169, 59, 0.32)',
          '--danger': '#F2685C',
          '--danger-bg': 'rgba(242, 104, 92, 0.12)',
          '--danger-border': 'rgba(242, 104, 92, 0.34)'
        }}
      }},
      dracula: {{
        name: 'Dracula',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#282a36',
          '--bg-void': '#21222c',
          '--atmo-glow': '#21222c',
          '--surface-1': '#21222c',
          '--surface-2': '#343746',
          '--surface-3': '#44475a',
          '--surface-hover': '#6272a4',
          '--border-subtle': '#343746',
          '--border': '#44475a',
          '--border-strong': '#6272a4',
          '--text-primary': '#f8f8f2',
          '--text-secondary': '#d6acff',
          '--text-muted': '#6272a4',
          '--text-disabled': '#44475a',
          '--accent': '#bd93f9',
          '--accent-bg': 'rgba(189, 147, 249, 0.15)',
          '--accent-border': 'rgba(189, 147, 249, 0.45)',
          '--stream': '#8be9fd',
          '--stream-bg': 'rgba(139, 233, 253, 0.15)',
          '--stream-border': 'rgba(139, 233, 253, 0.40)',
          '--success': '#50fa7b',
          '--success-bg': 'rgba(80, 250, 123, 0.15)',
          '--success-border': 'rgba(80, 250, 123, 0.35)',
          '--warning': '#ffb86c',
          '--warning-bg': 'rgba(255, 184, 108, 0.15)',
          '--warning-border': 'rgba(255, 184, 108, 0.35)',
          '--danger': '#ff5555',
          '--danger-bg': 'rgba(255, 85, 85, 0.15)',
          '--danger-border': 'rgba(255, 85, 85, 0.35)'
        }}
      }},
      tokyo_night: {{
        name: 'Tokyo Night',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#1a1b26',
          '--bg-void': '#16161e',
          '--atmo-glow': '#16161e',
          '--surface-1': '#1f2335',
          '--surface-2': '#24283b',
          '--surface-3': '#292e42',
          '--surface-hover': '#2f354d',
          '--border-subtle': '#292e42',
          '--border': '#3b4261',
          '--border-strong': '#565f89',
          '--text-primary': '#c0caf5',
          '--text-secondary': '#9aa5ce',
          '--text-muted': '#565f89',
          '--text-disabled': '#3b4261',
          '--accent': '#7aa2f7',
          '--accent-bg': 'rgba(122, 162, 247, 0.15)',
          '--accent-border': 'rgba(122, 162, 247, 0.45)',
          '--stream': '#7dcfff',
          '--stream-bg': 'rgba(125, 207, 255, 0.15)',
          '--stream-border': 'rgba(125, 207, 255, 0.40)',
          '--success': '#9ece6a',
          '--success-bg': 'rgba(158, 206, 106, 0.15)',
          '--success-border': 'rgba(158, 206, 106, 0.35)',
          '--warning': '#ff9e64',
          '--warning-bg': 'rgba(255, 158, 100, 0.15)',
          '--warning-border': 'rgba(255, 158, 100, 0.35)',
          '--danger': '#f7768e',
          '--danger-bg': 'rgba(247, 118, 142, 0.15)',
          '--danger-border': 'rgba(247, 118, 142, 0.35)'
        }}
      }},
      nord: {{
        name: 'Nord Frost',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#242933',
          '--bg-void': '#1e222a',
          '--atmo-glow': '#1e222a',
          '--surface-1': '#2e3440',
          '--surface-2': '#3b4252',
          '--surface-3': '#434c5e',
          '--surface-hover': '#4c566a',
          '--border-subtle': '#3b4252',
          '--border': '#434c5e',
          '--border-strong': '#4c566a',
          '--text-primary': '#eceff4',
          '--text-secondary': '#d8dee9',
          '--text-muted': '#768299',
          '--text-disabled': '#434c5e',
          '--accent': '#88c0d0',
          '--accent-bg': 'rgba(136, 192, 208, 0.15)',
          '--accent-border': 'rgba(136, 192, 208, 0.45)',
          '--stream': '#81a1c1',
          '--stream-bg': 'rgba(129, 161, 193, 0.15)',
          '--stream-border': 'rgba(129, 161, 193, 0.40)',
          '--success': '#a3be8c',
          '--success-bg': 'rgba(163, 190, 140, 0.15)',
          '--success-border': 'rgba(163, 190, 140, 0.35)',
          '--warning': '#ebcb8b',
          '--warning-bg': 'rgba(235, 203, 139, 0.15)',
          '--warning-border': 'rgba(235, 203, 139, 0.35)',
          '--danger': '#bf616a',
          '--danger-bg': 'rgba(191, 97, 106, 0.15)',
          '--danger-border': 'rgba(191, 97, 106, 0.35)'
        }}
      }},
      catppuccin: {{
        name: 'Catppuccin Mocha',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#1e1e2e',
          '--bg-void': '#181825',
          '--atmo-glow': '#181825',
          '--surface-1': '#181825',
          '--surface-2': '#313244',
          '--surface-3': '#45475a',
          '--surface-hover': '#585b70',
          '--border-subtle': '#313244',
          '--border': '#45475a',
          '--border-strong': '#6c7086',
          '--text-primary': '#cdd6f4',
          '--text-secondary': '#cba6f7',
          '--text-muted': '#6c7086',
          '--text-disabled': '#45475a',
          '--accent': '#a6e3a1',
          '--accent-bg': 'rgba(166, 227, 161, 0.15)',
          '--accent-border': 'rgba(166, 227, 161, 0.45)',
          '--stream': '#89dceb',
          '--stream-bg': 'rgba(137, 220, 235, 0.15)',
          '--stream-border': 'rgba(137, 220, 235, 0.40)',
          '--success': '#a6e3a1',
          '--success-bg': 'rgba(166, 227, 161, 0.15)',
          '--success-border': 'rgba(166, 227, 161, 0.35)',
          '--warning': '#fab387',
          '--warning-bg': 'rgba(250, 179, 135, 0.15)',
          '--warning-border': 'rgba(250, 179, 135, 0.35)',
          '--danger': '#f38ba8',
          '--danger-bg': 'rgba(243, 139, 168, 0.15)',
          '--danger-border': 'rgba(243, 139, 168, 0.35)'
        }}
      }},
      monokai: {{
        name: 'Monokai Pro',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#272822',
          '--bg-void': '#1e1f1c',
          '--atmo-glow': '#1e1f1c',
          '--surface-1': '#2e2e28',
          '--surface-2': '#383830',
          '--surface-3': '#49483e',
          '--surface-hover': '#49483e',
          '--border-subtle': '#3e3d32',
          '--border': '#49483e',
          '--border-strong': '#75715e',
          '--text-primary': '#f8f8f2',
          '--text-secondary': '#e6db74',
          '--text-muted': '#75715e',
          '--text-disabled': '#49483e',
          '--accent': '#a6e22e',
          '--accent-bg': 'rgba(166, 226, 46, 0.15)',
          '--accent-border': 'rgba(166, 226, 46, 0.45)',
          '--stream': '#66d9ef',
          '--stream-bg': 'rgba(102, 217, 239, 0.15)',
          '--stream-border': 'rgba(102, 217, 239, 0.40)',
          '--success': '#a6e22e',
          '--success-bg': 'rgba(166, 226, 46, 0.15)',
          '--success-border': 'rgba(166, 226, 46, 0.35)',
          '--warning': '#fd971f',
          '--warning-bg': 'rgba(253, 151, 31, 0.15)',
          '--warning-border': 'rgba(253, 151, 31, 0.35)',
          '--danger': '#f92672',
          '--danger-bg': 'rgba(249, 38, 114, 0.15)',
          '--danger-border': 'rgba(249, 38, 114, 0.35)'
        }}
      }},
      gruvbox_dark: {{
        name: 'Gruvbox Dark',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#282828',
          '--bg-void': '#1d2021',
          '--atmo-glow': '#1d2021',
          '--surface-1': '#1d2021',
          '--surface-2': '#3c3836',
          '--surface-3': '#504945',
          '--surface-hover': '#665c54',
          '--border-subtle': '#3c3836',
          '--border': '#504945',
          '--border-strong': '#7c6f64',
          '--text-primary': '#ebdbb2',
          '--text-secondary': '#fabd2f',
          '--text-muted': '#928374',
          '--text-disabled': '#504945',
          '--accent': '#b8bb26',
          '--accent-bg': 'rgba(184, 187, 38, 0.15)',
          '--accent-border': 'rgba(184, 187, 38, 0.45)',
          '--stream': '#8ec07c',
          '--stream-bg': 'rgba(142, 192, 124, 0.15)',
          '--stream-border': 'rgba(142, 192, 124, 0.40)',
          '--success': '#b8bb26',
          '--success-bg': 'rgba(184, 187, 38, 0.15)',
          '--success-border': 'rgba(184, 187, 38, 0.35)',
          '--warning': '#fe8019',
          '--warning-bg': 'rgba(254, 128, 25, 0.15)',
          '--warning-border': 'rgba(254, 128, 25, 0.35)',
          '--danger': '#fb4934',
          '--danger-bg': 'rgba(251, 73, 52, 0.15)',
          '--danger-border': 'rgba(251, 73, 52, 0.35)'
        }}
      }},
      solarized_dark: {{
        name: 'Solarized Dark',
        scheme: 'dark',
        vars: {{
          '--bg-base': '#002b36',
          '--bg-void': '#073642',
          '--atmo-glow': '#073642',
          '--surface-1': '#073642',
          '--surface-2': '#0b414f',
          '--surface-3': '#586e75',
          '--surface-hover': '#657b83',
          '--border-subtle': '#0b414f',
          '--border': '#586e75',
          '--border-strong': '#657b83',
          '--text-primary': '#fdf6e3',
          '--text-secondary': '#93a1a1',
          '--text-muted': '#657b83',
          '--text-disabled': '#586e75',
          '--accent': '#268bd2',
          '--accent-bg': 'rgba(38, 139, 210, 0.15)',
          '--accent-border': 'rgba(38, 139, 210, 0.45)',
          '--stream': '#2aa198',
          '--stream-bg': 'rgba(42, 161, 152, 0.15)',
          '--stream-border': 'rgba(42, 161, 152, 0.40)',
          '--success': '#859900',
          '--success-bg': 'rgba(133, 153, 0, 0.15)',
          '--success-border': 'rgba(133, 153, 0, 0.35)',
          '--warning': '#b58900',
          '--warning-bg': 'rgba(181, 137, 0, 0.15)',
          '--warning-border': 'rgba(181, 137, 0, 0.35)',
          '--danger': '#dc322f',
          '--danger-bg': 'rgba(220, 50, 47, 0.15)',
          '--danger-border': 'rgba(220, 50, 47, 0.35)'
        }}
      }},
      github_light: {{
        name: 'GitHub Light',
        scheme: 'light',
        vars: {{
          '--bg-base': '#ffffff',
          '--bg-void': '#f6f8fa',
          '--atmo-glow': '#eaeef2',
          '--surface-1': '#f6f8fa',
          '--surface-2': '#eaeff4',
          '--surface-3': '#e1e4e8',
          '--surface-hover': '#e1e4e8',
          '--border-subtle': '#eaecef',
          '--border': '#d0d7de',
          '--border-strong': '#8c959f',
          '--text-primary': '#1f2328',
          '--text-secondary': '#59636e',
          '--text-muted': '#8c959f',
          '--text-disabled': '#d0d7de',
          '--accent': '#0969da',
          '--accent-bg': 'rgba(9, 105, 218, 0.10)',
          '--accent-border': 'rgba(9, 105, 218, 0.35)',
          '--stream': '#0550ae',
          '--stream-bg': 'rgba(5, 80, 174, 0.10)',
          '--stream-border': 'rgba(5, 80, 174, 0.35)',
          '--success': '#1a7f37',
          '--success-bg': 'rgba(26, 127, 55, 0.10)',
          '--success-border': 'rgba(26, 127, 55, 0.30)',
          '--warning': '#9a6700',
          '--warning-bg': 'rgba(154, 103, 0, 0.10)',
          '--warning-border': 'rgba(154, 103, 0, 0.30)',
          '--danger': '#cf222e',
          '--danger-bg': 'rgba(207, 34, 46, 0.10)',
          '--danger-border': 'rgba(207, 34, 46, 0.30)'
        }}
      }},
      light: {{
        name: 'Solar Paper (Light)',
        scheme: 'light',
        vars: {{
          '--bg-base': '#f8fafc',
          '--bg-void': '#f1f5f9',
          '--atmo-glow': '#e2e8f0',
          '--surface-1': '#ffffff',
          '--surface-2': '#f1f5f9',
          '--surface-3': '#e2e8f0',
          '--surface-hover': '#e2e8f0',
          '--border-subtle': '#e2e8f0',
          '--border': '#cbd5e1',
          '--border-strong': '#94a3b8',
          '--text-primary': '#0f172a',
          '--text-secondary': '#334155',
          '--text-muted': '#64748b',
          '--text-disabled': '#94a3b8',
          '--accent': '#0284c7',
          '--accent-bg': 'rgba(2, 132, 199, 0.10)',
          '--accent-border': 'rgba(2, 132, 199, 0.35)',
          '--stream': '#0d9488',
          '--stream-bg': 'rgba(13, 148, 136, 0.10)',
          '--stream-border': 'rgba(13, 148, 136, 0.35)',
          '--success': '#16a34a',
          '--success-bg': 'rgba(22, 163, 74, 0.10)',
          '--success-border': 'rgba(22, 163, 74, 0.30)',
          '--warning': '#d97706',
          '--warning-bg': 'rgba(217, 119, 6, 0.10)',
          '--warning-border': 'rgba(217, 119, 6, 0.30)',
          '--danger': '#dc2626',
          '--danger-bg': 'rgba(220, 38, 38, 0.10)',
          '--danger-border': 'rgba(220, 38, 38, 0.30)'
        }}
      }},
      solarized_light: {{
        name: 'Solarized Light',
        scheme: 'light',
        vars: {{
          '--bg-base': '#fdf6e3',
          '--bg-void': '#eee8d5',
          '--atmo-glow': '#e0d9c5',
          '--surface-1': '#ffffff',
          '--surface-2': '#eee8d5',
          '--surface-3': '#e0d9c5',
          '--surface-hover': '#d6ceb8',
          '--border-subtle': '#e0d9c5',
          '--border': '#cbcdbe',
          '--border-strong': '#657b83',
          '--text-primary': '#073642',
          '--text-secondary': '#586e75',
          '--text-muted': '#93a1a1',
          '--text-disabled': '#b58900',
          '--accent': '#268bd2',
          '--accent-bg': 'rgba(38, 139, 210, 0.12)',
          '--accent-border': 'rgba(38, 139, 210, 0.40)',
          '--stream': '#2aa198',
          '--stream-bg': 'rgba(42, 161, 152, 0.12)',
          '--stream-border': 'rgba(42, 161, 152, 0.40)',
          '--success': '#859900',
          '--success-bg': 'rgba(133, 153, 0, 0.12)',
          '--success-border': 'rgba(133, 153, 0, 0.32)',
          '--warning': '#b58900',
          '--warning-bg': 'rgba(181, 137, 0, 0.12)',
          '--warning-border': 'rgba(181, 137, 0, 0.32)',
          '--danger': '#dc322f',
          '--danger-bg': 'rgba(220, 50, 47, 0.12)',
          '--danger-border': 'rgba(220, 50, 47, 0.32)'
        }}
      }},
      nord_light: {{
        name: 'Nord Snow Storm',
        scheme: 'light',
        vars: {{
          '--bg-base': '#eceff4',
          '--bg-void': '#e5e9f0',
          '--atmo-glow': '#d8dee9',
          '--surface-1': '#ffffff',
          '--surface-2': '#e5e9f0',
          '--surface-3': '#d8dee9',
          '--surface-hover': '#cbd3e0',
          '--border-subtle': '#d8dee9',
          '--border': '#c2cad8',
          '--border-strong': '#4c566a',
          '--text-primary': '#2e3440',
          '--text-secondary': '#4c566a',
          '--text-muted': '#7b88a1',
          '--text-disabled': '#c2cad8',
          '--accent': '#5e81ac',
          '--accent-bg': 'rgba(94, 129, 172, 0.12)',
          '--accent-border': 'rgba(94, 129, 172, 0.40)',
          '--stream': '#88c0d0',
          '--stream-bg': 'rgba(136, 192, 208, 0.15)',
          '--stream-border': 'rgba(136, 192, 208, 0.45)',
          '--success': '#a3be8c',
          '--success-bg': 'rgba(163, 190, 140, 0.12)',
          '--success-border': 'rgba(163, 190, 140, 0.32)',
          '--warning': '#ebcb8b',
          '--warning-bg': 'rgba(235, 203, 139, 0.12)',
          '--warning-border': 'rgba(235, 203, 139, 0.32)',
          '--danger': '#bf616a',
          '--danger-bg': 'rgba(191, 97, 106, 0.12)',
          '--danger-border': 'rgba(191, 97, 106, 0.32)'
        }}
      }},
      catppuccin_latte: {{
        name: 'Catppuccin Latte',
        scheme: 'light',
        vars: {{
          '--bg-base': '#eff1f5',
          '--bg-void': '#e6e9ef',
          '--atmo-glow': '#dce0e8',
          '--surface-1': '#ffffff',
          '--surface-2': '#e6e9ef',
          '--surface-3': '#dce0e8',
          '--surface-hover': '#ccd0da',
          '--border-subtle': '#dce0e8',
          '--border': '#bcc0cc',
          '--border-strong': '#6c6f85',
          '--text-primary': '#4c4f69',
          '--text-secondary': '#6c6f85',
          '--text-muted': '#8c8fa1',
          '--text-disabled': '#bcc0cc',
          '--accent': '#1e66f5',
          '--accent-bg': 'rgba(30, 102, 245, 0.12)',
          '--accent-border': 'rgba(30, 102, 245, 0.40)',
          '--stream': '#04a5e5',
          '--stream-bg': 'rgba(4, 165, 229, 0.12)',
          '--stream-border': 'rgba(4, 165, 229, 0.40)',
          '--success': '#40a02b',
          '--success-bg': 'rgba(64, 160, 43, 0.12)',
          '--success-border': 'rgba(64, 160, 43, 0.32)',
          '--warning': '#df8e1d',
          '--warning-bg': 'rgba(223, 142, 29, 0.12)',
          '--warning-border': 'rgba(223, 142, 29, 0.32)',
          '--danger': '#d20f39',
          '--danger-bg': 'rgba(210, 15, 57, 0.12)',
          '--danger-border': 'rgba(210, 15, 57, 0.32)'
        }}
      }},
      gruvbox_light: {{
        name: 'Gruvbox Light',
        scheme: 'light',
        vars: {{
          '--bg-base': '#fbf1c7',
          '--bg-void': '#ebdbb2',
          '--atmo-glow': '#d5c4a1',
          '--surface-1': '#ffffff',
          '--surface-2': '#ebdbb2',
          '--surface-3': '#d5c4a1',
          '--surface-hover': '#bdae93',
          '--border-subtle': '#d5c4a1',
          '--border': '#bdae93',
          '--border-strong': '#504945',
          '--text-primary': '#282828',
          '--text-secondary': '#504945',
          '--text-muted': '#7c6f64',
          '--text-disabled': '#bdae93',
          '--accent': '#af3a03',
          '--accent-bg': 'rgba(175, 58, 3, 0.12)',
          '--accent-border': 'rgba(175, 58, 3, 0.40)',
          '--stream': '#076678',
          '--stream-bg': 'rgba(7, 102, 120, 0.12)',
          '--stream-border': 'rgba(7, 102, 120, 0.40)',
          '--success': '#79740e',
          '--success-bg': 'rgba(121, 116, 14, 0.12)',
          '--success-border': 'rgba(121, 116, 14, 0.32)',
          '--warning': '#b57614',
          '--warning-bg': 'rgba(181, 118, 20, 0.12)',
          '--warning-border': 'rgba(181, 118, 20, 0.32)',
          '--danger': '#9d0006',
          '--danger-bg': 'rgba(157, 0, 6, 0.12)',
          '--danger-border': 'rgba(157, 0, 6, 0.32)'
        }}
      }}
    }};

    const STORAGE_KEY_THEME = 'SIGNAL_GRAPH_THEME';
    let currentTheme = 'signal';
    try {{
      const savedTheme = localStorage.getItem(STORAGE_KEY_THEME);
      if (savedTheme && THEMES[savedTheme]) currentTheme = savedTheme;
    }} catch (e) {{}}

    function applyTheme(themeId) {{
      if (!THEMES[themeId]) themeId = 'signal';
      currentTheme = themeId;
      const theme = THEMES[themeId];
      const root = document.documentElement;
      
      Object.keys(theme.vars).forEach(varName => {{
        root.style.setProperty(varName, theme.vars[varName]);
      }});

      if (theme.scheme === 'light') {{
        root.style.colorScheme = 'light';
      }} else {{
        root.style.colorScheme = 'dark';
      }}

      try {{
        localStorage.setItem(STORAGE_KEY_THEME, themeId);
      }} catch (e) {{}}

      const selector = document.getElementById('themeSelector');
      if (selector && selector.value !== themeId) {{
        selector.value = themeId;
      }}
    }}

    const I18N = {{
      'pt-BR': {{
        app_title: "tare.tools",
        tab_triage: "🔬 Painel de Triagem",
        tab_guide: "🎯 Guia de Triagem",
        tab_manual: "📖 Manual CLI",
        tab_rules: "📚 Regras IBM",
        tab_arch: "📐 Arquitetura",
        search_placeholder: "Buscar por UUID, condição, texto...",
        triage_progress_title: "Progresso da Triagem",
        triage_status_title: "Status da Triagem",
        filter_status_all: "Todos os Itens",
        filter_status_pending: "⏳ Pendentes",
        filter_status_bug: "🔴 Bugs Confirmados",
        filter_status_fp: "🟢 Falsos Positivos",
        filter_status_debt: "🟡 Débito / Backlog",
        severity_title: "Severidade",
        filter_sev_all: "Todas as Severidades",
        filter_sev_error: "🔴 Erros (P0)",
        filter_sev_warning: "🟡 Avisos (P0 / P1 / Smells)",
        filter_sev_info: "🔵 Infos (Amostra / Proveniência)",
        issue_code_title: "Tipos de Problema (Código)",
        btn_import: "📥 Importar",
        btn_export_json: "📤 Exportar JSON",
        btn_export_md: "📄 Exportar MD",
        btn_reset: "Resetar Triagem",
        btn_inspect: "🔍 Inspecionar Nó",
        btn_close: "✕ Fechar",
        btn_bug: "🐞 Bug Confirmado",
        btn_fp: "🛡️ Falso Positivo",
        btn_debt: "📦 Débito / Backlog",
        notes_placeholder: "Adicionar nota de rationale / contexto para calibração...",
        empty_issues: "Nenhuma issue encontrada",
        empty_issues_sub: "Tente ajustar os filtros de busca, severidade ou status da triagem.",
        showing_issues: (count) => `Exibindo ${{count}} ocorrência(s)`,
        triaged_label: (triaged, pct) => `${{triaged}} triados (${{pct}}%)`,
        total_label: (total) => `${{total}} total`,
        copied_toast: (text) => `Copiado: ${{text}}`,
        export_success: "Decisões de triagem exportadas com sucesso!",
        import_success: (count) => `Triagem importada: ${{count}} decisões carregadas.`,
        reset_confirm: "Tem certeza que deseja resetar todas as decisões de triagem salvas localmente?",
        reset_success: "Triagem resetada."
      }},
      'en-US': {{
        app_title: "tare.tools",
        tab_triage: "🔬 Triage Workspace",
        tab_guide: "🎯 Triage Guide",
        tab_manual: "📖 CLI Manual",
        tab_rules: "📚 IBM Rules",
        tab_arch: "📐 Architecture",
        search_placeholder: "Search by UUID, condition, text...",
        triage_progress_title: "Triage Progress",
        triage_status_title: "Triage Status",
        filter_status_all: "All Items",
        filter_status_pending: "⏳ Pending",
        filter_status_bug: "🔴 Confirmed Bugs",
        filter_status_fp: "🟢 False Positives",
        filter_status_debt: "🟡 Technical Debt",
        severity_title: "Severity",
        filter_sev_all: "All Severities",
        filter_sev_error: "🔴 Errors (P0)",
        filter_sev_warning: "🟡 Warnings (P0 / P1 / Smells)",
        filter_sev_info: "🔵 Infos (Sample / Provenance)",
        issue_code_title: "Issue Types (Code)",
        btn_import: "📥 Import",
        btn_export_json: "📤 Export JSON",
        btn_export_md: "📄 Export MD",
        btn_reset: "Reset Triage",
        btn_inspect: "🔍 Inspect Node",
        btn_close: "✕ Close",
        btn_bug: "🐞 Confirmed Bug",
        btn_fp: "🛡️ False Positive",
        btn_debt: "📦 Tech Debt",
        notes_placeholder: "Add reviewer rationale / calibration notes...",
        empty_issues: "No issues found",
        empty_issues_sub: "Try adjusting search filters, severity, or triage status.",
        showing_issues: (count) => `Showing ${{count}} finding(s)`,
        triaged_label: (triaged, pct) => `${{triaged}} triaged (${{pct}}%)`,
        total_label: (total) => `${{total}} total`,
        copied_toast: (text) => `Copied: ${{text}}`,
        export_success: "Triage decisions exported successfully!",
        import_success: (count) => `Triage imported: ${{count}} decisions loaded.`,
        reset_confirm: "Are you sure you want to reset all locally saved triage decisions?",
        reset_success: "Triage reset."
      }}
    }};

    const MSG_I18N_EN = {{
      "sys_number_zero_handler_unreachable": "Slot capture uses @sys-number which rejects 0, but has descendant handler for == 0, <= 0 or < 1; zero handling is unreachable.",
      "sys_number_zero_valid_but_not_captured": "Prompt includes 0 in domain and defines @sys-number:0 branch, but slot capture condition rejects zero.",
      "slot_capture_type_mismatch_document": "Slot captures @sys-number, but descendant logic expects $inputType:document; capture condition does not match processed input type.",
      "unsatisfiable_slot_enable_condition": "Condition requires variable to be simultaneously truthy and false ($x && $x == false); slot cannot be enabled.",
      "shadowed_by_always_true": "Prior sibling with condition 'true' prevents evaluation in normal flow with no observed incoming Jump.",
      "unknown_entity": "Entity not declared in catalog: @",
      "unknown_intent": "Intent not defined in catalog: #",
      "unknown_variable": "Context variable not declared in registry: $",
      "invalid_spel_entity_call": "Entities are not functions; syntax @entity(...) is invalid.",
      "invalid_spel_entity_shorthand_member": "Shorthand @entity:(val) already returns boolean and cannot access property like .literal.",
      "digression_blocked_by_transition": "Watson prevents digression out when active node forces jump or Skip user input.",
      "digression_blocked_by_forcing_child": "Watson prevents digression out when node has active child with condition true/anything_else.",
      "duplicate_sibling_condition": "Condition is identical to prior sibling with no incoming Jump in interval.",
      "disabled_condition_false": "Condition contains explicit 'false' deliberately disabling branch in normal flow.",
      "legacy_order_ambiguous": "Legacy sequence value is shared across siblings; relative execution order cannot be proven.",
      "missing_root_anything_else": "No root node found with condition 'anything_else'."
    }};

    const RAW_DATA = JSON.parse(document.getElementById('triage-data').textContent);
    let currentCorpus = 'current';
    let currentLang = localStorage.getItem('watson_dialog_lang') || 'pt-BR';
    let triageDecisions = JSON.parse(localStorage.getItem('watson_dialog_triage_decisions') || '{{}}');
    
    let activeFilters = {{
      search: '',
      status: 'all',
      severity: 'all',
      code: 'all'
    }};

    const issuesContainer = document.getElementById('issues-container');
    const searchInput = document.getElementById('search-input');
    const toast = document.getElementById('toast');
    const drawer = document.getElementById('drawer');
    const drawerOverlay = document.getElementById('drawer-overlay');

    function t(key, ...args) {{
      const dict = I18N[currentLang] || I18N['pt-BR'];
      const val = dict[key] || I18N['pt-BR'][key] || key;
      return typeof val === 'function' ? val(...args) : val;
    }}

    function showToast(msg) {{
      toast.textContent = msg;
      toast.classList.add('show');
      setTimeout(() => toast.classList.remove('show'), 2500);
    }}

    function copyCode(btn) {{
      const code = btn.closest('.code-block-wrapper').querySelector('code').innerText;
      navigator.clipboard.writeText(code);
      btn.textContent = currentLang === 'en-US' ? "Copied!" : "Copiado!";
      setTimeout(() => btn.textContent = currentLang === 'en-US' ? "Copy" : "Copiar", 2000);
    }}

    function applyLanguage(lang) {{
      currentLang = lang;
      localStorage.setItem('watson_dialog_lang', lang);
      document.querySelectorAll('#lang-selector button').forEach(b => {{
        b.classList.toggle('active', b.dataset.lang === lang);
      }});

      document.querySelectorAll('[data-i18n]').forEach(el => {{
        const key = el.dataset.i18n;
        el.innerHTML = t(key);
      }});

      document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {{
        const key = el.dataset.i18nPlaceholder;
        el.placeholder = t(key);
      }});

      document.querySelectorAll('.lang-content').forEach(el => {{
        if (lang === 'en-US') {{
          el.style.display = el.classList.contains('lang-en') ? 'flex' : 'none';
        }} else {{
          el.style.display = el.classList.contains('lang-pt') ? 'flex' : 'none';
        }}
      }});

      updateSidebarCounts();
      renderIssues();
    }}

    document.querySelectorAll('#global-tabs .nav-tab-btn').forEach(btn => {{
      btn.onclick = () => {{
        document.querySelectorAll('#global-tabs .nav-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.view-tab').forEach(v => v.classList.remove('active'));
        btn.classList.add('active');
        const tabId = btn.dataset.tab;
        document.getElementById(tabId).classList.add('active');
      }};
    }});

    function getIssueKey(issue) {{
      return `${{currentCorpus}}:${{issue.node}}:${{issue.code}}:${{issue.field}}`;
    }}

    function getCurrentDataset() {{
      const corpusData = RAW_DATA[currentCorpus];
      return [...corpusData.actionable_issues, ...(corpusData.sample_info_issues || [])];
    }}

    function getNodeData(nodeId) {{
      const corpusData = RAW_DATA[currentCorpus];
      const nodes = corpusData.nodes || {{}};
      return nodes[nodeId] || nodes[nodeId.replace(/^slot:/, '')] || null;
    }}

    function saveDecisions() {{
      localStorage.setItem('watson_dialog_triage_decisions', JSON.stringify(triageDecisions));
      updateSidebarCounts();
      renderIssues();
    }}

    function setDecision(issueKey, status) {{
      if (!triageDecisions[issueKey]) {{
        triageDecisions[issueKey] = {{ status: null, notes: '', timestamp: new Date().toISOString() }};
      }}
      triageDecisions[issueKey].status = triageDecisions[issueKey].status === status ? null : status;
      triageDecisions[issueKey].timestamp = new Date().toISOString();
      saveDecisions();
    }}

    function setNotes(issueKey, text) {{
      if (!triageDecisions[issueKey]) {{
        triageDecisions[issueKey] = {{ status: null, notes: '', timestamp: new Date().toISOString() }};
      }}
      triageDecisions[issueKey].notes = text;
      localStorage.setItem('watson_dialog_triage_decisions', JSON.stringify(triageDecisions));
    }}

    function inspectNode(nodeId) {{
      const node = getNodeData(nodeId);
      const drawerContent = document.getElementById('drawer-content');
      
      document.getElementById('drawer-node-uuid').textContent = nodeId;
      document.getElementById('drawer-node-name').textContent = node && node.name ? `🔍 ${{node.name}}` : `🔍 ${{nodeId}}`;
      document.getElementById('drawer-node-kind').textContent = node ? node.kind : 'node';
      document.getElementById('drawer-node-status').textContent = node && node.status ? node.status : 'ATIVO';
      document.getElementById('drawer-node-status').className = `badge ${{node && (node.status === 'INATIVO' || node.status === 'REVISAO') ? 'badge-muted' : 'badge-green'}}`;

      if (!node) {{
        drawerContent.innerHTML = `
          <div class="empty-state">
            <p>${{currentLang === 'en-US' ? 'Node structural details not found in summary.' : 'Detalhes estruturais do nó não disponíveis no sumário.'}}</p>
            <p style="font-family: var(--font-mono); font-size: 12px; margin-top: 8px;">UUID: ${{nodeId}}</p>
          </div>
        `;
        openDrawer();
        return;
      }}

      let breadcrumbsHtml = '';
      if (node.path && node.path.length > 0) {{
        breadcrumbsHtml = `
          <div class="drawer-section">
            <div class="drawer-section-title">${{currentLang === 'en-US' ? '📍 Structural Breadcrumbs' : '📍 Linhagem / Caminho Estrutural'}}</div>
            <div class="breadcrumbs">
              ${{node.path.map((p, idx) => `
                <span class="crumb-item" onclick="inspectNode('${{p.uuid}}')">${{p.name || p.uuid}}</span>
                ${{idx < node.path.length - 1 ? '<span class="crumb-sep">/</span>' : ''}}
              `).join('')}}
            </div>
          </div>
        `;
      }}

      let slotsHtml = '';
      if (node.slots && node.slots.length > 0) {{
        slotsHtml = `
          <div class="drawer-section">
            <div class="drawer-section-title">${{currentLang === 'en-US' ? '📥 Context Slots' : '📥 Slots de Contexto'}} (${{node.slots.length}})</div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              ${{node.slots.map(s => `
                <div class="slot-item">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="color: var(--text-primary); font-size: var(--text-xs);">${{s.identifier || s.uuid}}</strong>
                    <span class="badge ${{s.required ? 'badge-red' : 'badge-muted'}}">${{s.required ? (currentLang === 'en-US' ? 'Mandatory' : 'Obrigatório') : (currentLang === 'en-US' ? 'Optional' : 'Opcional')}}</span>
                  </div>
                  <div style="font-size: var(--text-xs); color: var(--text-muted);">
                    ${{currentLang === 'en-US' ? 'Variable' : 'Variável'}}: <code style="color: var(--accent);">${{s.variable_name ? '$' + s.variable_name : s.variable_uuid || '(none)'}}</code>
                  </div>
                  <div class="condition-box">${{escapeHtml(s.condition || 'true')}}</div>
                  ${{s.enable_condition ? `<div style="font-size: 10px; color: var(--text-muted);">${{currentLang === 'en-US' ? 'Enable Condition' : 'Habilitação'}}: <code>${{escapeHtml(s.enable_condition)}}</code></div>` : ''}}
                </div>
              `).join('')}}
            </div>
          </div>
        `;
      }}

      let responsesHtml = '';
      if (node.responses && node.responses.length > 0) {{
        responsesHtml = `
          <div class="drawer-section">
            <div class="drawer-section-title">${{currentLang === 'en-US' ? '💬 Configured Responses' : '💬 Respostas Configuradas'}} (${{node.responses.length}})</div>
            <div style="display: flex; flex-direction: column; gap: 8px;">
              ${{node.responses.map(r => `
                <div class="resp-item">
                  <div style="font-size: var(--text-xs); color: var(--text-primary);">${{r.text ? escapeHtml(r.text) : `<span style="color: var(--text-muted);">${{currentLang === 'en-US' ? '(no raw text / structured payload)' : '(sem texto direto / componente estruturado)'}}</span>`}}</div>
                  ${{r.condition ? `<div class="condition-box" style="font-size: 10px;">${{escapeHtml(r.condition)}}</div>` : ''}}
                </div>
              `).join('')}}
            </div>
          </div>
        `;
      }}

      let childrenHtml = '';
      if (node.children && node.children.length > 0) {{
        childrenHtml = `
          <div class="drawer-section">
            <div class="drawer-section-title">${{currentLang === 'en-US' ? '🌿 Sub-nodes / Children' : '🌿 Sub-nós / Filhos'}} (${{node.children.length}})</div>
            <div style="display: flex; flex-direction: column; gap: 6px;">
              ${{node.children.slice(0, 10).map(c => `
                <div class="child-item" onclick="inspectNode('${{c.uuid}}')" style="cursor: pointer;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-size: var(--text-xs); font-weight: 600; color: var(--accent);">${{c.name || c.uuid}}</span>
                    <span class="badge badge-muted">${{c.status || 'ATIVO'}}</span>
                  </div>
                  <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-muted);">${{escapeHtml(c.condition || 'true')}}</div>
                </div>
              `).join('')}}
              ${{node.children.length > 10 ? `<div style="font-size: 10px; color: var(--text-muted); text-align: center;">+ ${{node.children.length - 10}} ${{currentLang === 'en-US' ? 'other children...' : 'outros filhos...'}}</div>` : ''}}
            </div>
          </div>
        `;
      }}

      drawerContent.innerHTML = `
        ${{breadcrumbsHtml}}

        <div class="drawer-section">
          <div class="drawer-section-title">${{currentLang === 'en-US' ? '⚙️ Execution Metadata' : '⚙️ Metadados de Execução'}}</div>
          <div class="meta-grid">
            <div class="meta-card">
              <span class="meta-label">${{currentLang === 'en-US' ? 'Sequence' : 'Sequência'}}</span>
              <span class="meta-val">${{node.sequence !== null && node.sequence !== undefined ? node.sequence : 'null'}}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">${{currentLang === 'en-US' ? 'Jump / Transition' : 'Transição / Jump'}}</span>
              <span class="meta-val">${{node.jump_target ? `👉 ${{node.jump_target}}` : (currentLang === 'en-US' ? '(wait input)' : '(espera input)')}}</span>
            </div>
            <div class="meta-card">
              <span class="meta-label">${{currentLang === 'en-US' ? 'Digression In / Out' : 'Digressão Entrada / Saída'}}</span>
              <span class="meta-val">${{node.in_digression_in ? 'In: YES' : 'In: NO'}} | ${{node.in_digression_out ? 'Out: YES' : 'Out: NO'}}</span>
            </div>
          </div>
        </div>

        <div class="drawer-section">
          <div class="drawer-section-title">${{currentLang === 'en-US' ? '⚡ SpEL Activation Condition' : '⚡ Condição de Ativação SpEL'}}</div>
          <div class="condition-box">${{escapeHtml(node.condition || 'true')}}</div>
        </div>

        ${{slotsHtml}}
        ${{responsesHtml}}
        ${{childrenHtml}}

        <div class="drawer-section">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div class="drawer-section-title">${{currentLang === 'en-US' ? '📄 Node Raw JSON' : '📄 Raw JSON do Nó'}}</div>
            <button class="btn btn-sm" onclick="copyToClipboard(JSON.stringify(getNodeData('${{nodeId}}').raw_json, null, 2))">📋 ${{currentLang === 'en-US' ? 'Copy JSON' : 'Copiar JSON'}}</button>
          </div>
          <pre class="raw-json-box">${{escapeHtml(JSON.stringify(node.raw_json || {{}}, null, 2))}}</pre>
        </div>
      `;

      openDrawer();
    }}

    function openDrawer() {{
      drawer.classList.add('open');
      drawerOverlay.classList.add('open');
    }}

    function closeDrawer() {{
      drawer.classList.remove('open');
      drawerOverlay.classList.remove('open');
    }}

    function getFilteredIssues() {{
      const items = getCurrentDataset();
      return items.filter(issue => {{
        const key = getIssueKey(issue);
        const decision = triageDecisions[key] || {{ status: null, notes: '' }};

        if (activeFilters.search) {{
          const q = activeFilters.search.toLowerCase();
          const matchNode = (issue.node || '').toLowerCase().includes(q);
          const matchCode = (issue.code || '').toLowerCase().includes(q);
          const matchMsg = (issue.message || '').toLowerCase().includes(q);
          const matchVal = JSON.stringify(issue.value || '').toLowerCase().includes(q);
          const matchNotes = (decision.notes || '').toLowerCase().includes(q);
          if (!matchNode && !matchCode && !matchMsg && !matchVal && !matchNotes) return false;
        }}

        if (activeFilters.status !== 'all') {{
          if (activeFilters.status === 'pending' && decision.status !== null) return false;
          if (activeFilters.status !== 'pending' && decision.status !== activeFilters.status) return false;
        }}

        if (activeFilters.severity !== 'all' && issue.severity !== activeFilters.severity) return false;
        if (activeFilters.code !== 'all' && issue.code !== activeFilters.code) return false;

        return true;
      }});
    }}

    function updateSidebarCounts() {{
      const allItems = getCurrentDataset();
      let bugCount = 0, fpCount = 0, debtCount = 0, pendingCount = 0;
      let errCount = 0, warnCount = 0, infoCount = 0;
      const codeCounts = {{}};

      allItems.forEach(item => {{
        const key = getIssueKey(item);
        const dec = triageDecisions[key] || {{ status: null }};
        if (dec.status === 'bug') bugCount++;
        else if (dec.status === 'false_positive') fpCount++;
        else if (dec.status === 'debt') debtCount++;
        else pendingCount++;

        if (item.severity === 'error') errCount++;
        if (item.severity === 'warning') warnCount++;
        if (item.severity === 'info') infoCount++;

        codeCounts[item.code] = (codeCounts[item.code] || 0) + 1;
      }});

      document.getElementById('count-status-all').textContent = allItems.length;
      document.getElementById('count-status-pending').textContent = pendingCount;
      document.getElementById('count-status-bug').textContent = bugCount;
      document.getElementById('count-status-fp').textContent = fpCount;
      document.getElementById('count-status-debt').textContent = debtCount;

      document.getElementById('count-sev-all').textContent = allItems.length;
      document.getElementById('count-sev-error').textContent = errCount;
      document.getElementById('count-sev-warning').textContent = warnCount;
      document.getElementById('count-sev-info').textContent = infoCount;

      const triagedTotal = bugCount + fpCount + debtCount;
      document.getElementById('triaged-count').textContent = t('triaged_label', triagedTotal, Math.round((triagedTotal / Math.max(1, allItems.length)) * 100));
      document.getElementById('total-actionable-count').textContent = t('total_label', allItems.length);

      const total = allItems.length || 1;
      document.getElementById('prog-bug').style.width = `${{(bugCount / total) * 100}}%`;
      document.getElementById('prog-fp').style.width = `${{(fpCount / total) * 100}}%`;
      document.getElementById('prog-debt').style.width = `${{(debtCount / total) * 100}}%`;

      const codeList = document.getElementById('code-filters');
      codeList.innerHTML = '';
      
      const allLi = document.createElement('li');
      allLi.className = `filter-item ${{activeFilters.code === 'all' ? 'active' : ''}}`;
      allLi.innerHTML = `<span>${{currentLang === 'en-US' ? 'All Issue Types' : 'Todos os Tipos'}}</span><span class="filter-count">${{allItems.length}}</span>`;
      allLi.onclick = () => {{ activeFilters.code = 'all'; updateSidebarCounts(); renderIssues(); }};
      codeList.appendChild(allLi);

      Object.entries(codeCounts).sort((a, b) => b[1] - a[1]).forEach(([code, count]) => {{
        const li = document.createElement('li');
        li.className = `filter-item ${{activeFilters.code === code ? 'active' : ''}}`;
        li.innerHTML = `<span style="font-family: var(--font-mono); font-size: 10px;">${{code}}</span><span class="filter-count">${{count}}</span>`;
        li.onclick = () => {{ activeFilters.code = code; updateSidebarCounts(); renderIssues(); }};
        codeList.appendChild(li);
      }});
    }}

    function getMessageTranslated(issue) {{
      if (currentLang === 'en-US' && MSG_I18N_EN[issue.code]) {{
        return MSG_I18N_EN[issue.code];
      }}
      return issue.message;
    }}

    function renderIssues() {{
      const filtered = getFilteredIssues();
      document.getElementById('rendered-count-label').textContent = t('showing_issues', filtered.length);

      if (filtered.length === 0) {{
        issuesContainer.innerHTML = `
          <div class="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--accent); opacity: 0.6;">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="8" y1="12" x2="16" y2="12"></line>
            </svg>
            <h3>${{t('empty_issues')}}</h3>
            <p>${{t('empty_issues_sub')}}</p>
          </div>
        `;
        return;
      }}

      issuesContainer.innerHTML = filtered.map(issue => {{
        const key = getIssueKey(issue);
        const decision = triageDecisions[key] || {{ status: null, notes: '' }};
        const status = decision.status;

        const sevLabel = issue.severity === 'error' 
          ? (currentLang === 'en-US' ? '🔴 ERROR P0' : '🔴 ERRO P0')
          : (issue.severity === 'warning' 
              ? (currentLang === 'en-US' ? '🟡 WARNING' : '🟡 AVISO')
              : '🔵 INFO');

        const sevBadge = issue.severity === 'error' 
          ? `<span class="badge badge-red">${{sevLabel}}</span>` 
          : (issue.severity === 'warning' 
              ? `<span class="badge badge-yellow">${{sevLabel}}</span>` 
              : `<span class="badge badge-blue">${{sevLabel}}</span>`);

        const catBadge = `<span class="badge badge-muted">${{issue.category}}</span>`;

        let cardClass = 'issue-card';
        if (status === 'bug') cardClass += ' triage-bug';
        if (status === 'false_positive') cardClass += ' triage-false_positive';
        if (status === 'debt') cardClass += ' triage-debt';

        const conditionHtml = issue.value !== null && issue.value !== undefined
          ? `<div class="condition-box">${{typeof issue.value === 'object' ? JSON.stringify(issue.value, null, 2) : escapeHtml(String(issue.value))}}</div>`
          : '';

        return `
          <div class="${{cardClass}}" data-key="${{key}}">
            <div class="card-top">
              <div class="card-tags">
                ${{sevBadge}}
                ${{catBadge}}
                <span class="code-title">${{issue.code}}</span>
                <span class="node-pill" title="${{currentLang === 'en-US' ? 'Click to copy UUID' : 'Clique para copiar UUID'}}" onclick="copyToClipboard('${{issue.node}}')">
                  📍 ${{issue.node}}
                </span>
                <span style="font-size: 11px; color: var(--text-muted);">${{currentLang === 'en-US' ? 'field' : 'campo'}}: <code>${{issue.field}}</code></span>
              </div>
              <button class="btn btn-sm btn-inspect" onclick="inspectNode('${{issue.node}}')">
                ${{t('btn_inspect')}}
              </button>
            </div>

            <div class="message-box">
              ${{escapeHtml(getMessageTranslated(issue))}}
            </div>

            ${{conditionHtml}}

            <div class="card-bottom">
              <div class="triage-buttons">
                <button class="btn-triage ${{status === 'bug' ? 'active-bug' : ''}}" onclick="setDecision('${{key}}', 'bug')">
                  ${{t('btn_bug')}}
                </button>
                <button class="btn-triage ${{status === 'false_positive' ? 'active-false_positive' : ''}}" onclick="setDecision('${{key}}', 'false_positive')">
                  ${{t('btn_fp')}}
                </button>
                <button class="btn-triage ${{status === 'debt' ? 'active-debt' : ''}}" onclick="setDecision('${{key}}', 'debt')">
                  ${{t('btn_debt')}}
                </button>
              </div>
            </div>

            <textarea 
              class="notes-input" 
              placeholder="${{t('notes_placeholder')}}" 
              oninput="setNotes('${{key}}', this.value)"
            >${{decision.notes || ''}}</textarea>
          </div>
        `;
      }}).join('');
    }}

    function escapeHtml(text) {{
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }}

    function copyToClipboard(text) {{
      navigator.clipboard.writeText(text);
      showToast(t('copied_toast', text));
    }}

    document.getElementById('btn-export-json').onclick = () => {{
      const exportPayload = {{
        version: "1.0",
        protocol: "tare.tools/SIGNAL/v1",
        exported_at: new Date().toISOString(),
        corpus: currentCorpus,
        language: currentLang,
        theme: currentTheme,
        summary: {{
          total_items: getCurrentDataset().length,
          decisions_count: Object.keys(triageDecisions).length,
        }},
        decisions: triageDecisions
      }};
      const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `watson_triage_decisions_${{currentCorpus}}_${{new Date().toISOString().slice(0, 10)}}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(t('export_success'));
    }};

    document.getElementById('btn-export-md').onclick = () => {{
      const allItems = getCurrentDataset();
      let md = `# tare.tools — Watson Dialog Triage Report (${{currentCorpus.toUpperCase()}})\\n\\n`;
      md += `*Protocol:* tare.tools/SIGNAL/v1\\n`;
      md += `*Date:* ${{new Date().toLocaleString()}}\\n\\n`;
      md += `## Decisions\\n\\n`;

      allItems.forEach(item => {{
        const key = getIssueKey(item);
        const dec = triageDecisions[key];
        if (dec && dec.status) {{
          md += `### [${{dec.status.toUpperCase()}}] ${{item.code}} (${{item.node}})\\n`;
          md += `- **Severity:** ${{item.severity}}\\n`;
          md += `- **Field:** \`${{item.field}}\`\\n`;
          md += `- **Message:** ${{getMessageTranslated(item)}}\\n`;
          if (item.value) md += `- **Value:** \`${{JSON.stringify(item.value)}}\`\\n`;
          if (dec.notes) md += `- **Reviewer Notes:** ${{dec.notes}}\\n`;
          md += `\\n`;
        }}
      }});

      const blob = new Blob([md], {{ type: 'text/markdown' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `watson_triage_report_${{currentCorpus}}_${{new Date().toISOString().slice(0, 10)}}.md`;
      a.click();
      URL.revokeObjectURL(url);
      showToast(t('export_success'));
    }};

    const fileImporter = document.getElementById('file-importer');
    document.getElementById('btn-import').onclick = () => fileImporter.click();
    fileImporter.onchange = (e) => {{
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (event) => {{
        try {{
          const parsed = JSON.parse(event.target.result);
          if (parsed.decisions) {{
            triageDecisions = {{ ...triageDecisions, ...parsed.decisions }};
            saveDecisions();
            showToast(t('import_success', Object.keys(parsed.decisions).length));
          }} else {{
            showToast(currentLang === 'en-US' ? "Invalid file format." : "Formato de arquivo inválido.");
          }}
        }} catch (err) {{
          showToast(currentLang === 'en-US' ? "Error reading JSON." : "Erro ao processar JSON.");
        }}
      }};
      reader.readAsText(file);
    }};

    document.getElementById('btn-reset-triage').onclick = () => {{
      if (confirm(t('reset_confirm'))) {{
        triageDecisions = {{}};
        saveDecisions();
        showToast(t('reset_success'));
      }}
    }};

    document.querySelectorAll('#lang-selector button').forEach(btn => {{
      btn.onclick = () => applyLanguage(btn.dataset.lang);
    }});

    document.querySelectorAll('#dataset-selector button').forEach(btn => {{
      btn.onclick = () => {{
        document.querySelectorAll('#dataset-selector button').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentCorpus = btn.dataset.corpus;
        updateSidebarCounts();
        renderIssues();
        showToast(currentLang === 'en-US' ? `Loaded dataset: ${{currentCorpus.toUpperCase()}}` : `Carregado dataset: ${{currentCorpus.toUpperCase()}}`);
      }};
    }});

    document.querySelectorAll('#status-filters .filter-item').forEach(item => {{
      item.onclick = () => {{
        document.querySelectorAll('#status-filters .filter-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        activeFilters.status = item.dataset.status;
        renderIssues();
      }};
    }});

    document.querySelectorAll('#severity-filters .filter-item').forEach(item => {{
      item.onclick = () => {{
        document.querySelectorAll('#severity-filters .filter-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
        activeFilters.severity = item.dataset.severity;
        renderIssues();
      }};
    }});

    searchInput.oninput = (e) => {{
      activeFilters.search = e.target.value;
      renderIssues();
    }};

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') closeDrawer();
    }});

    // Initialize Theme & Language
    applyTheme(currentTheme);
    applyLanguage(currentLang);
  </script>
</body>
</html>
"""

out_html = ROOT / "triage_viewer.html"
out_html.write_text(html_content, encoding="utf-8")
print(f"Generated tare.tools SIGNAL design system & theme engine console ({out_html.stat().st_size:,} bytes)")
