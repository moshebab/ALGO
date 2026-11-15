#!/usr/bin/env python3
"""
Regenerate ALGO_Slides/lectures and ALGO_Slides/index.html strictly for published lectures.

Usage:
  python3 publish_lectures.py              # rebuild current published lectures
  python3 publish_lectures.py 07 08 09     # set published lectures to 07, 08, 09
  python3 publish_lectures.py --add 09     # add lecture 09 to published list
"""
import json
import os
import re
import shutil
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
SOURCE_REPO = Path("/Users/moshebabaioff/Downloads/Antigravity/algorithms-course")
CONFIG_PATH = REPO_DIR / "published_lectures.json"

FORBIDDEN_SUBSTRINGS = ["משה קול"]


def load_published_nums() -> list[str]:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return [f"{int(x):02d}" for x in data.get("published_lectures", [])]
    return ["07", "08"]


def save_published_nums(nums: list[str]) -> None:
    clean = sorted({f"{int(x):02d}" for x in nums})
    CONFIG_PATH.write_text(
        json.dumps({"course_name": "ALGO", "published_lectures": clean}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def extract_style_and_cards(source_index_html: str):
    style_match = re.search(r"<style>.*?</style>", source_index_html, flags=re.DOTALL)
    if not style_match:
        raise RuntimeError("Could not find <style> block in source index.html")
    style_block = style_match.group(0)

    card_pattern = re.compile(
        r'(<article\s+class="lecture-card"\s+data-num="(\d+)"[^>]*>.*?</article>)',
        flags=re.DOTALL,
    )
    cards_by_num = {}
    for full_card, num in card_pattern.findall(source_index_html):
        cards_by_num[f"{int(num):02d}"] = full_card
    return style_block, cards_by_num


def is_safe_public_file(filename: str) -> bool:
    low = filename.lower()
    if low.startswith("notes") or low.endswith(".md") or low.startswith("."):
        return False
    if low.startswith("slides") and low.endswith(".html"):
        return True
    if "animation" in low and low.endswith(".html"):
        return True
    return False




def inject_noindex_into_html(html_path: Path) -> None:
    txt = html_path.read_text(encoding="utf-8")
    if 'name="robots"' in txt.lower():
        return
    meta = (
        '<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">'
        '<meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet">'
    )
    updated, count = re.subn(r"(<head[^>]*>)", r"\1\n  " + meta, txt, count=1, flags=re.IGNORECASE)
    if count == 0:
        updated = meta + "\n" + txt
    html_path.write_text(updated, encoding="utf-8")


def sync_lectures_and_build_index(published_nums: list[str]) -> None:
    source_index_path = SOURCE_REPO / "index.html"
    if not source_index_path.exists():
        raise FileNotFoundError(f"Source index not found: {source_index_path}")

    source_html = source_index_path.read_text(encoding="utf-8")
    style_block, cards_by_num = extract_style_and_cards(source_html)

    missing = [n for n in published_nums if n not in cards_by_num]
    if missing:
        raise ValueError(f"Lecture card(s) not found in source index.html: {missing}")

    lectures_out = REPO_DIR / "lectures"
    if lectures_out.exists():
        shutil.rmtree(lectures_out)
    lectures_out.mkdir(parents=True, exist_ok=True)

    selected_cards = []
    tags_seen = []
    lecturers_seen = []

    for num in sorted(published_nums):
        card_html = cards_by_num[num]
        selected_cards.append(card_html)

        tag_m = re.search(r'data-tag="([^"]+)"', card_html)
        if tag_m and tag_m.group(1) not in tags_seen:
            tags_seen.append(tag_m.group(1))

        lec_m = re.search(r'data-lecturer="([^"]+)"', card_html)
        if lec_m and lec_m.group(1) not in lecturers_seen:
            lecturers_seen.append(lec_m.group(1))

        # Find matching source lecture folder
        matches = sorted((SOURCE_REPO / "lectures").glob(f"{num}-*"))
        if not matches:
            raise FileNotFoundError(f"No lecture folder matching {num}-* in {SOURCE_REPO / 'lectures'}")
        src_dir = matches[0]
        dst_dir = lectures_out / src_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)

        # Copy all public slide/animation HTML files in that lecture folder
        for item in sorted(src_dir.iterdir()):
            if item.is_file() and is_safe_public_file(item.name):
                shutil.copy2(item, dst_dir / item.name)

        # Also copy any file explicitly linked from the published card in index.html
        hrefs = re.findall(r'href="([^"]+)"', card_html)
        for href in hrefs:
            if href.startswith(("http://", "https://", "mailto:", "#", "data:")):
                continue
            src_target = SOURCE_REPO / href
            dst_target = REPO_DIR / href
            if "notes" in dst_target.name.lower() or dst_target.suffix.lower() == ".md":
                raise RuntimeError(f"Refusing to publish internal file linked in card: {href}")
            if src_target.exists() and src_target.is_file():
                dst_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_target, dst_target)

        # Check relative refs inside copied HTML files and copy any needed local assets
        for html_file in list(dst_dir.glob("*.html")):
            content = html_file.read_text(encoding="utf-8")
            for sub in FORBIDDEN_SUBSTRINGS:
                if sub in content:
                    raise RuntimeError(f"Forbidden internal reference found in {html_file.name}")
            refs = re.findall(r'(?:href|src)="([^"]+)"', content)
            for ref in refs:
                if ref.startswith(("http://", "https://", "mailto:", "#", "data:", "javascript:")):
                    continue
                ref_clean = ref.split("#")[0].split("?")[0]
                if not ref_clean:
                    continue
                src_asset = (src_dir / ref_clean).resolve()
                dst_asset = (dst_dir / ref_clean).resolve()
                if src_asset.exists() and src_asset.is_file() and not dst_asset.exists():
                    if "notes" in src_asset.name.lower() or src_asset.suffix.lower() == ".md":
                        raise RuntimeError(f"Refusing to copy internal asset {ref_clean}")
                    dst_asset.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_asset, dst_asset)

    # Build filter buttons strictly from published lectures
    filter_buttons_html = ['<button class="filter-btn active" onclick="setFilter(\'all\', this)">הכל</button>']
    if len(tags_seen) > 1:
        for t in tags_seen:
            filter_buttons_html.append(
                f'<button class="filter-btn" onclick="setFilter(\'{t}\', this)">{t}</button>'
            )
    if len(lecturers_seen) > 1:
        for lec in lecturers_seen:
            short = "בביוף" if "בביוף" in lec else ("בר סיני" if "בר סיני" in lec else lec)
            filter_buttons_html.append(
                f'<button class="filter-btn" onclick="setFilter(\'{short}\', this)">{lec}</button>'
            )

    count = len(selected_cards)
    count_label = "הרצאה מפורסמת אחת" if count == 1 else f"<strong>{count}</strong> הרצאות מפורסמות"

    cards_joined = "\n\n      ".join(selected_cards)
    filters_joined = "\n        ".join(filter_buttons_html)

    index_html = f"""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="noindex, nofollow, noarchive, nosnippet">
  <meta name="googlebot" content="noindex, nofollow, noarchive, nosnippet">
  <title>ALGO — אלגוריתמים (67504) | שקפי הרצאות</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;500;600;700;800&family=Rubik:wght@400;500;600;700&display=swap" rel="stylesheet">
  {style_block}
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="univ-tag">האוניברסיטה העברית בירושלים · בית הספר להנדסה ולמדעי המחשב</div>
      <h1>ALGO — אלגוריתמים (67504)</h1>
      <p class="header-desc">שקפי הרצאות וסימולציות אינטראקטיביות</p>
      <div class="stats-bar">
        <span class="stat-pill">{count_label}</span>
        <span class="stat-pill">סמסטר א׳ · תשפ״ז</span>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="controls">
      <div class="search-box">
        <input type="text" id="searchInput" placeholder="חיפוש הרצאה או נושא..." oninput="filterCards()">
        <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
      </div>
      <div class="filter-tags">
        {filters_joined}
      </div>
    </div>

    <section class="cards-grid" id="cardsGrid">
      {cards_joined}
    </section>

    <footer>
      ALGO · קורס אלגוריתמים (67504) · האוניברסיטה העברית בירושלים
    </footer>
  </main>

  <script>
    let activeTag = 'all';

    function setFilter(tag, btn) {{
      activeTag = tag;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      filterCards();
    }}

    function filterCards() {{
      const query = document.getElementById('searchInput').value.trim().toLowerCase();
      const cards = document.querySelectorAll('.lecture-card');

      cards.forEach(card => {{
        const text = card.textContent.toLowerCase();
        const cardTag = card.getAttribute('data-tag') || '';
        const cardLecturer = card.getAttribute('data-lecturer') || '';

        const matchesQuery = !query || text.includes(query);
        let matchesTag = true;

        if (activeTag !== 'all') {{
          if (activeTag === 'בביוף') {{
            matchesTag = cardLecturer.includes('בביוף');
          }} else if (activeTag === 'בר סיני') {{
            matchesTag = cardLecturer.includes('בר סיני');
          }} else {{
            matchesTag = cardTag === activeTag;
          }}
        }}

        card.style.display = (matchesQuery && matchesTag) ? 'flex' : 'none';
      }});
    }}
  </script>
</body>
</html>
"""
    (REPO_DIR / "index.html").write_text(index_html, encoding="utf-8")
    (REPO_DIR / ".nojekyll").write_text("", encoding="utf-8")
    for html_file in (REPO_DIR / "lectures").rglob("*.html"):
        inject_noindex_into_html(html_file)
    (REPO_DIR / "robots.txt").write_text(
        """# Allow Googlebot/Bingbot to read <meta name="robots" content="noindex"> so URLs never appear in search
User-agent: Googlebot
Disallow: /*.json$
Disallow: /*.pdf$

User-agent: Bingbot
Disallow: /*.json$
Disallow: /*.pdf$

User-agent: *
Disallow: /
""",
        encoding="utf-8",
    )

    print(f"Built index.html and synced lectures for published lectures: {', '.join(sorted(published_nums))}")


def main():
    args = sys.argv[1:]
    current = load_published_nums()
    if not args:
        nums = current
    elif args[0] == "--add":
        nums = sorted(set(current) | {f"{int(x):02d}" for x in args[1:]})
        save_published_nums(nums)
    else:
        nums = sorted({f"{int(x):02d}" for x in args})
        save_published_nums(nums)
    sync_lectures_and_build_index(nums)


if __name__ == "__main__":
    main()
