import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote
import re
import os
import unicodedata
from collections import defaultdict

OC = os.getenv("OC", "chetera")
BASE = "http://www.law.go.kr"

def highlight(text, query):
    if not query or not text:
        return text
    escaped_query = re.escape(query)
    pattern = re.compile(f'({escaped_query})', re.IGNORECASE)
    return pattern.sub(r'<mark>\1</mark>', text)

def get_law_list_from_api(query):
    exact_query = f'"{query}"'
    encoded_query = quote(exact_query)
    page = 1
    laws = []
    while True:
        url = f"{BASE}/DRF/lawSearch.do?OC={OC}&target=law&type=XML&display=100&page={page}&search=2&knd=A0002&query={encoded_query}"
        try:
            res = requests.get(url, timeout=10)
            res.encoding = 'utf-8'
            if res.status_code != 200:
                break
            root = ET.fromstring(res.content)
            for law in root.findall("law"):
                laws.append({
                    "법령명": law.findtext("법령명한글", "").strip(),
                    "MST": law.findtext("법령일련번호", "")
                })
            if len(root.findall("law")) < 100:
                break
            page += 1
        except Exception as e:
            print(f"법률 검색 중 오류 발생: {e}")
            break
    print(f"검색된 법률 수: {len(laws)}")
    for idx, law in enumerate(laws):
        print(f"{idx+1}. {law['법령명']}")
    return laws

def get_law_text_by_mst(mst):
    url = f"{BASE}/DRF/lawService.do?OC={OC}&target=law&MST={mst}&type=XML"
    try:
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        if res.status_code == 200:
            return res.content
        else:
            print(f"법령 XML 가져오기 실패: 상태 코드 {res.status_code}")
            return None
    except Exception as e:
        print(f"법령 XML 가져오기 중 오류 발생: {e}")
        return None

def clean(text):
    return re.sub(r"\s+", "", text or "")

def normalize_number(text):
    try:
        return str(int(unicodedata.numeric(text)))
    except:
        return text

def make_article_number(조문번호, 조문가지번호):
    return f"제{조문번호}조의{조문가지번호}" if 조문가지번호 and 조문가지번호 != "0" else f"제{조문번호}조"

def has_batchim(word):
    if not word:
        return False
    last_char = word[-1]
    if '가' <= last_char <= '힣':
        char_code = ord(last_char)
        jongseong = (char_code - 0xAC00) % 28
        return jongseong != 0
    return False

def has_rieul_batchim(word):
    if not word:
        return False
    last_char = word[-1]
    if '가' <= last_char <= '힣':
        char_code = ord(last_char)
        jongseong = (char_code - 0xAC00) % 28
        return jongseong == 8
    return False

def extract_article_num(loc):
    article_match = re.search(r'제(\d+)조(?:의(\d+))?', loc)
    if not article_match:
        return (0, 0)
    article_num = int(article_match.group(1))
    article_sub = int(article_match.group(2)) if article_match.group(2) else 0
    return (article_num, article_sub)

def extract_chunk_and_josa(token, searchword):
    suffix_exclude = ["의", "에", "에서", "에게", "등", "등의", "등인", "등만", "등에", "만", "만을", "만이", "만은", "만에", "만으로"]
    josa_list = ["을", "를", "과", "와", "이", "가", "이나", "나", "으로", "로", "은", "는", 
                 "란", "이란", "라", "이라", "로서", "으로서", "로써", "으로써", 
                 "\"란", "\"이란", "\"라", "\"이라"]

    if token == searchword:
        return token, None, None
    if searchword not in token:
        return token, None, None
    if not token.startswith(searchword):
        return token, None, None

    for s in sorted(suffix_exclude, key=len, reverse=True):
        if token == searchword + s:
            return searchword, None, s

    for j in sorted(josa_list, key=len, reverse=True):
        if token == searchword + j:
            if j.startswith("\""):
                return searchword, j[1:], None
            return searchword, j, None

    if token.startswith(searchword) and len(token) > len(searchword):
        return token, None, None

    return token, None, None
def apply_josa_rule(orig, replaced, josa):
    if orig == replaced:
        return f'"{orig}"를 "{replaced}"로 한다.'

    orig_has_batchim = has_batchim(orig)
    replaced_has_batchim = has_batchim(replaced)
    replaced_has_rieul = has_rieul_batchim(replaced)

    if josa is None:
        if not orig_has_batchim:
            if not replaced_has_batchim or replaced_has_rieul:
                return f'"{orig}"를 "{replaced}"로 한다.'
            else:
                return f'"{orig}"를 "{replaced}"으로 한다.'
        else:
            if not replaced_has_batchim or replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'

    clean_josa = josa[1:] if josa.startswith('"') else josa

    if clean_josa == "을":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}을"을 "{replaced}를"로 한다.'

    elif clean_josa == "를":
        if replaced_has_batchim:
            return f'"{orig}를"을 "{replaced}을"로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "과":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}과"를 "{replaced}와"로 한다.'

    elif clean_josa == "와":
        if replaced_has_batchim:
            return f'"{orig}와"를 "{replaced}과"로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "이":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}이"를 "{replaced}가"로 한다.'

    elif clean_josa == "가":
        if replaced_has_batchim:
            return f'"{orig}가"를 "{replaced}이"로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "이나":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}이나"를 "{replaced}나"로 한다.'

    elif clean_josa == "나":
        if replaced_has_batchim:
            return f'"{orig}나"를 "{replaced}이나"로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "으로":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}으로"를 "{replaced}로"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}으로"를 "{replaced}로"로 한다.'

    elif clean_josa == "로":
        if orig_has_batchim:
            if replaced_has_batchim:
                if replaced_has_rieul:
                    return f'"{orig}"을 "{replaced}"로 한다.'
                else:
                    return f'"{orig}로"를 "{replaced}으로"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"로 한다.'
        else:
            if replaced_has_batchim:
                if replaced_has_rieul:
                    return f'"{orig}"를 "{replaced}"로 한다.'
                else:
                    return f'"{orig}로"를 "{replaced}으로"로 한다.'
            else:
                return f'"{orig}"를 "{replaced}"로 한다.'
    elif clean_josa == "는":
        if replaced_has_batchim:
            return f'"{orig}는"을 "{replaced}은"으로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "은":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}은"을 "{replaced}는"으로 한다.'

    elif clean_josa == "란":
        if replaced_has_batchim:
            quote_prefix = '"' if josa.startswith('"') else ""
            return f'"{orig}{josa}"을 "{replaced}이{quote_prefix}란"으로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "이란":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            quote_prefix = '"' if josa.startswith('"') else ""
            return f'"{orig}{josa}"을 "{replaced}{quote_prefix}란"으로 한다.'

    elif clean_josa == "로서" or clean_josa == "로써":
        if orig_has_batchim:
            if replaced_has_batchim:
                if replaced_has_rieul:
                    return f'"{orig}"을 "{replaced}"로 한다.'
                else:
                    return f'"{orig}{josa}"를 "{replaced}으{clean_josa}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"로 한다.'
        else:
            if replaced_has_batchim:
                if replaced_has_rieul:
                    return f'"{orig}"를 "{replaced}"로 한다.'
                else:
                    return f'"{orig}{josa}"를 "{replaced}으{clean_josa}"로 한다.'
            else:
                return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "으로서" or clean_josa == "으로써":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}{josa}"를 "{replaced}로{clean_josa[2:]}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            return f'"{orig}{josa}"를 "{replaced}로{clean_josa[2:]}"로 한다.'

    elif clean_josa == "라":
        if replaced_has_batchim:
            quote_prefix = '"' if josa.startswith('"') else ""
            return f'"{orig}{josa}"를 "{replaced}이{quote_prefix}라"로 한다.'
        else:
            return f'"{orig}"를 "{replaced}"로 한다.'

    elif clean_josa == "이라":
        if replaced_has_batchim:
            if replaced_has_rieul:
                return f'"{orig}"을 "{replaced}"로 한다.'
            else:
                return f'"{orig}"을 "{replaced}"으로 한다.'
        else:
            quote_prefix = '"' if josa.startswith('"') else ""
            return f'"{orig}{josa}"를 "{replaced}{quote_prefix}라"로 한다.'

    if orig_has_batchim:
        return f'"{orig}"을 "{replaced}"로 한다.'
    else:
        return f'"{orig}"를 "{replaced}"로 한다.'
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("사용법: python law_processor.py <명령> <검색어> [바꿀단어]")
        print("  명령: search, amend")
        print("  예시1: python law_processor.py search 지방법원")
        print("  예시2: python law_processor.py amend 지방법원 지역법원")
        sys.exit(1)

    command = sys.argv[1]
    search_word = sys.argv[2]

    if command == "search":
        results = run_search_logic(search_word)
        for law_name, snippets in results.items():
            print(f"## {law_name}")
            for snippet in snippets:
                print(snippet)
                print("---")

    elif command == "amend":
        if len(sys.argv) < 4:
            print("바꿀단어를 입력하세요.")
            sys.exit(1)
        replace_word = sys.argv[3]
        results = run_amendment_logic(search_word, replace_word)
        for result in results:
            print(result)
            print("\n")

    else:
        print(f"알 수 없는 명령: {command}")
        sys.exit(1)
