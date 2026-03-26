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
    """Remove section headers and truncate at reference/footer sections."""
    # Common markers for the end of the main article content in Korean Wikipedia
    end_markers = [
        "== 주석 ==",
        "== 참고 문헌 ==",
        "== 참고문헌 ==",
        "== 외부 링크 ==",
        "== 외부링크 ==",
        "== 같이 보기 ==",
        "== 같이보기 ==",
        "== 기각된 분류 =="
    ]
    
    # Find the earliest occurrence of any end marker
    first_marker_pos = len(text)
    for marker in end_markers:
        pos = text.find(marker)
        if pos != -1 and pos < first_marker_pos:
            first_marker_pos = pos
            
    # Truncate text before the first footer section
    text = text[:first_marker_pos]

    # Remove remaining == Section == headers
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
    Tokenize a paragraph using a character-centric approach to avoid duplication
    and support multiple morphemes per syllable (Korean patchim overlaps).
    """
    tokens = kiwi.tokenize(para)
    
    # Initialize character-based storage
    # Each entry: { 'char': str, 'lemmas': set, 'redactable': bool, 'is_gap': bool }
    chars = []
    for c in para:
        chars.append({
            'surface': c,
            'lemmas': set(),
            'redactable': False,
            'is_gap': True # Default to gap, tokens will flip this
        })

    for tok in tokens:
        tag_base = tok.tag.split('-')[0]
        is_redactable = tag_base in REDACTABLE_TAGS
        
        # --- Handle Numbers Special Case ---
        if tag_base in ('SN', 'W_SERIAL'):
            surface = para[tok.start:tok.start + tok.len]
            # Remove commas (1,000 -> 1000)
            # Since we are character-centric, we'll mark characters that should be skipped (commas)
            # and split on dots.
            
            dot_positions = []
            for i in range(tok.start, tok.start + tok.len):
                if i < len(chars):
                    c = chars[i]['surface']
                    if c == ',':
                        # Mark comma for removal (keep as gap, but it will be filtered out or ignored)
                        chars[i]['is_gap'] = True
                        chars[i]['surface'] = "" # effectively remove
                    elif c == '.':
                        # Keep dot as a visible gap
                        chars[i]['is_gap'] = True
                        chars[i]['redactable'] = False
                    else:
                        chars[i]['is_gap'] = False
                        chars[i]['lemmas'].add(c) # Use the digit itself as the lemma for numbers
                        if is_redactable:
                            chars[i]['redactable'] = True
            continue
        # -----------------------------------
        
        # Mark all characters covered by this token
        for i in range(tok.start, tok.start + tok.len):
            if i < len(chars):
                chars[i]['is_gap'] = False
                chars[i]['lemmas'].add(tok.form.lower())
                if is_redactable:
                    chars[i]['redactable'] = True

    # Group characters into segments to keep data size reasonable
    # Grouping rule: adjacent characters with the same redactable status and same lemma set
    segments = []
    if not chars:
        return []

    current_seg = {
        'surface': chars[0]['surface'],
        'lemmas': sorted(list(chars[0]['lemmas'])),
        'tag': 'GAP' if chars[0]['is_gap'] else 'TOKEN',
        'redactable': chars[0]['redactable']
    }

    for i in range(1, len(chars)):
        c_info = chars[i]
        if c_info['surface'] == "": continue
        
        c_lemmas = sorted(list(c_info['lemmas']))
        c_tag = 'GAP' if c_info['is_gap'] else 'TOKEN'
        
        # If properties match current segment, append to it
        if (c_lemmas == current_seg['lemmas'] and 
            c_tag == current_seg['tag'] and 
            c_info['redactable'] == current_seg['redactable']):
            current_seg['surface'] += c_info['surface']
        else:
            segments.append(current_seg)
            current_seg = {
                'surface': c_info['surface'],
                'lemmas': c_lemmas,
                'tag': c_tag,
                'redactable': c_info['redactable']
            }
    
    segments.append(current_seg)
    return segments

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
