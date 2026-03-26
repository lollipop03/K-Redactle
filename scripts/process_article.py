"""
K-Redactle Article Preprocessor
Fetches Korean Wikipedia articles and tokenizes them with kiwipiepy.
Outputs JavaScript data to be embedded directly in game.js.

Usage:
    python scripts/process_article.py 세종대왕 한국어
"""

import sys
import json
import re
import requests
from kiwipiepy import Kiwi

# POS tags that are "content words" and should be redacted
REDACTABLE_TAGS = {
    'NNG',   # 일반 명사
    'NNP',   # 고유 명사
    'NNB',   # 의존 명사
    'VV',    # 동사
    'VA',    # 형용사
    'XR',    # 어근
    'SL',    # 외국어
    'SH',    # 한자
    'SN',    # 숫자
    'W_SERIAL', # 시리얼 번호/날짜 등
}

def fetch_wiki_article(title: str) -> tuple[str, str]:
    """Fetch Korean Wikipedia article plaintext. Returns (resolved_title, text)."""
    url = 'https://ko.wikipedia.org/w/api.php'
    headers = {
        'User-Agent': 'K-Redactle-Bot/1.0 (https://github.com/your-username/K-Redactle)'
    }
    params = {
        'action': 'query',
        'titles': title,
        'prop': 'extracts',
        'explaintext': True,
        'redirects': True,
        'format': 'json',
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    
    if resp.status_code != 200:
        print(f'  ! Error: Wikipedia API returned status {resp.status_code}')
        return title, ""

    try:
        data = resp.json()
    except Exception as e:
        print(f'  ! Error decoding JSON: {e}')
        print(f'  ! Response preview: {resp.text[:100]}')
        return title, ""

    pages = data['query']['pages']
    page = next(iter(pages.values()))
    resolved_title = page.get('title', title)
    text = page.get('extract', '')
    return resolved_title, text

def clean_text(text: str) -> str:
    """Remove section headers and trim blank lines."""
    # Remove == Section == headers
    text = re.sub(r'=+[^=]+=+', '', text)
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def split_paragraphs(text: str, max_para: int = 8) -> list[str]:
    """Split into paragraphs, limit for demo."""
    paras = [p.strip() for p in text.split('\n\n') if p.strip()]
    # Filter out very short paragraphs (section names etc)
    paras = [p for p in paras if len(p) > 30]
    return paras[:max_para]

def process_paragraph(kiwi: Kiwi, para: str) -> list[dict]:
    """
    Tokenize a paragraph and return a list of segment dicts.
    Segments preserve the original text structure (eojeol + spaces).
    
    Each segment: { surface, lemma, tag, redactable }
    Non-morpheme gaps (spaces, punctuation between tokens) are included as
    non-redactable segments.
    """
    tokens = kiwi.tokenize(para)
    segments = []
    cursor = 0

    for tok in tokens:
        start = tok.start
        end = tok.start + tok.len

        # Gap before this token (spaces, punctuation not captured by kiwi)
        if cursor < start:
            gap = para[cursor:start]
            if gap:
                segments.append({
                    'surface': gap,
                    'lemma': gap,
                    'tag': 'GAP',
                    'redactable': False,
                })

        surface = para[start:end]
        tag_base = tok.tag.split('-')[0]  # strip -R / -I suffixes
        
        # --- Handle Numbers Special Case ---
        if tag_base in ('SN', 'W_SERIAL'):
            # 1. Remove commas (1,000 -> 1000)
            surface_clean = surface.replace(',', '')
            # 2. Split by dots (3.14 -> 3, ., 14)
            # We use a capturing group in re.split to keep the delimiter (.)
            parts = re.split(r'(\.)', surface_clean)
            for part in parts:
                if not part: continue
                if part == '.':
                    segments.append({
                        'surface': '.',
                        'lemma': '.',
                        'tag': 'GAP',
                        'redactable': False,
                    })
                else:
                    # Treat the numeric part as a redactable SN token
                    segments.append({
                        'surface': part,
                        'lemma': part,
                        'tag': 'SN',
                        'redactable': True,
                    })
            cursor = end
            continue
        # -----------------------------------

        redactable = tag_base in REDACTABLE_TAGS

        segments.append({
            'surface': surface,
            'lemma': tok.form,
            'tag': tag_base,
            'redactable': redactable,
        })
        cursor = end

    # Trailing gap
    if cursor < len(para):
        gap = para[cursor:]
        if gap:
            segments.append({
                'surface': gap,
                'lemma': gap,
                'tag': 'GAP',
                'redactable': False,
            })

    return segments

def get_title_lemmas(kiwi: Kiwi, title: str) -> list[str]:
    """Return the lemmas of content words in the title."""
    tokens = kiwi.tokenize(title)
    lemmas = []
    for tok in tokens:
        tag_base = tok.tag.split('-')[0]
        if tag_base in REDACTABLE_TAGS:
            lemmas.append(tok.form)
    # Fallback: treat whole title as the lemma
    if not lemmas:
        lemmas = [title]
    return lemmas

def process_article(title: str) -> dict:
    print(f'Fetching: {title}')
    resolved_title, raw_text = fetch_wiki_article(title)
    
    if not raw_text:
        print(f'  ! Warning: No content found for {title}. Skipping.')
        return None

    print(f'  → resolved: {resolved_title} ({len(raw_text)} chars)')

    text = clean_text(raw_text)
    paras = split_paragraphs(text)
    print(f'  → {len(paras)} paragraphs')

    print('  Loading Kiwi...')
    kiwi = Kiwi()

    title_lemmas = get_title_lemmas(kiwi, resolved_title)
    print(f'  → title lemmas: {title_lemmas}')

    paragraphs_data = []
    for i, para in enumerate(paras):
        segs = process_paragraph(kiwi, para)
        paragraphs_data.append(segs)
        print(f'  paragraph {i+1}: {len(segs)} segments')

    return {
        'title': resolved_title,
        'titleLemmas': title_lemmas,
        'sourceUrl': f'https://ko.wikipedia.org/wiki/{resolved_title.replace(" ", "_")}',
        'paragraphs': paragraphs_data
    }

if __name__ == '__main__':
    titles = []
    if len(sys.argv) > 1:
        if sys.argv[1] == '--file' and len(sys.argv) > 2:
            try:
                with open(sys.argv[2], 'r', encoding='utf-8') as f:
                    titles = [line.strip() for line in f if line.strip()]
                print(f'Read {len(titles)} titles from {sys.argv[2]}')
            except Exception as e:
                print(f'Error reading file: {e}')
                sys.exit(1)
        else:
            titles = sys.argv[1:]
    else:
        # Default fallback
        titles = ['세종대왕', '한국어', '이순신', '서울', '방탄소년단']

    articles = []
    for t in titles:
        art = process_article(t)
        if art:
            articles.append(art)

    if not articles:
        print("No articles processed. Exiting.")
        sys.exit(1)

    # Output as a JS const for direct embedding
    js_data = json.dumps(articles, ensure_ascii=False, indent=2)
    out = f'// Auto-generated by scripts/process_article.py\nexport const ARTICLES = {js_data};\n'
    
    import os
    OUTPUT_FILE = 'data/articles.js'
    os.makedirs('data', exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'Done! Written to {OUTPUT_FILE}')
    print(f'  Total articles: {len(articles)}')
