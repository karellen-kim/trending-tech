"""글의 핵심 구조를 다이어그램으로 그린다.

LLM에게 SVG 좌표를 직접 그리게 하면 정렬이 어긋나고 관계가 흐릿해진다.
그래서 LLM은 노드/엣지만 JSON으로 뽑고, 배치와 렌더링은 이 파일이 격자로 계산한다.
(Paper2SysArch, arXiv:2511.18036 의 structure-constrained 접근)
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor

from summarizer import _run_claude, _parse_json

DIAGRAM_PROMPT = """아래 글의 핵심을 보여주는 다이어그램 명세를 JSON으로 만들어줘.
글을 안 읽은 사람이 그림만 보고 핵심을 알 수 있어야 한다.

[제목]: {title}
[내용]: {content}

type 은 글의 핵심에 맞춰 하나 고른다.
- flow    : 무엇이 어떤 경로로 흘러가는가 (처리 순서, 요청 경로, 파이프라인)
- compare : 무엇이 어떻게 달라졌는가 (전후 비교, 기존 방식 vs 새 방식)
- layers  : 무엇 위에 무엇이 얹혀 있는가 (계층, 스택)

JSON만 출력해. 마크다운 펜스나 설명 없이.
{{"type":"flow","title":"제목 18자 이내","caption":"이 그림이 보여주는 것 45자 이내",
 "nodes":[{{"id":"a","label":"이름 22자 이내","note":"수치나 조건 16자 이내"}}],
 "edges":[{{"from":"a","to":"b","label":"무슨 일이 일어나는지 16자 이내"}}],
 "groups":[{{"label":"그룹명","nodes":["a"]}}]}}

규칙:
- label 은 [내용]에 나온 구체적인 이름을 쓴다. "시스템", "데이터", "처리" 같은 뭉뚱그린 말은 금지.
- edge 의 label 은 반드시 채운다. 동사로 쓴다. "연결", "관련"은 금지. 12자를 넘기지 않는다.
- [내용]에 수치가 있으면 note 나 edge label 에 넣는다. 없는 수치를 지어내지 않는다.
- node 는 3~4개. 좁은 화면에서 읽혀야 하므로 5개를 넘기지 않는다.
- compare 일 때만 groups 를 정확히 2개 만들고, 각 그룹에 노드를 2개 이상 담는다.
  두 그룹이 같은 축으로 대응돼야 한다. 수치가 있으면 양쪽 note 에 넣어 차이가 보이게 한다.
  나머지 type 은 groups 를 생략한다.

빼는 것이 먼저다:
- 항상 붙어 다니는 두 노드는 하나로 합친다.
- 배치만 봐도 관계가 뻔하면 edge 를 넣지 않는다. edge 는 정보를 나를 때만 그린다.
- note 는 수치나 조건이 있을 때만 넣는다. 없으면 빈 문자열로 둔다.
- 지울 것이 없을 때가 완성이다. 채울 것이 없을 때가 아니다.

그리지 않아야 할 때 — 아래에 하나라도 해당하면 {{"type":"none"}} 만 출력한다:
- 잘 쓴 문단 하나가 같은 일을 하는 경우.
- 항목을 늘어놓기만 하는 글(릴리스 목록, 링크 모음, 단순 공지, 인용).
- 노드가 2개 이하로만 나오는 경우.
- [내용]에 근거가 없어 이름을 지어내야 하는 경우.
"""

MIN_CONTENT = 150
_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}

# ── 레이아웃 상수 (그리드 정렬용) ──
NODE_W = 176
GAP_X, GAP_Y = 48, 32   # 좁은 화면을 생각해 가로 간격을 좁게 잡는다
PAD_X, PAD_Y = 16, 50
CHAR_W = 7.0          # 13px 한글 기준 대략 폭
LABEL_MAX = 13        # 노드 라벨 한 줄 최대 글자 (한글 13자 ≈ 168px)
LABEL_LINES = 2
LINE_H = 17
NODE_PAD = 20         # 박스 위아래 여백
MAX_ROWS = 4          # 세로로 쌓을 수 있는 최대 단수 (그림이 길어지는 것을 막는다)
MAX_COL_NODES = 3     # compare 한 열의 최대 노드 수


def _chars_for(width: int) -> int:
    """박스 폭에 들어가는 대략적인 글자 수 (13px 한글 기준)."""
    return max(6, int((width - 20) / 12.4))


def _node_height(label: str, note: str = "", width: int = NODE_W) -> int:
    """박스 높이를 내용에 맞춰 계산한다. 고정 높이를 쓰면 라벨이 박스를 넘친다."""
    lines = len(_wrap(label, _chars_for(width)))
    if note and str(note).strip():
        lines += 1
    return lines * LINE_H + NODE_PAD


def _e(s) -> str:
    return "".join(_ESC.get(c, c) for c in str(s or ""))


def _wrap(text: str, width: int = LABEL_MAX, max_lines: int = LABEL_LINES) -> list[str]:
    text = " ".join(str(text or "").split())
    if not text:
        return [""]
    # 공백 없는 긴 토큰(한글 문장 등)은 단어 단위로 안 잘리므로 폭 단위로 먼저 쪼갠다
    words = []
    for w in text.split(" "):
        while len(w) > width:
            words.append(w[:width])
            w = w[width:]
        if w:
            words.append(w)

    lines, cur = [], ""
    for word in words:
        cand = f"{cur} {word}".strip()
        if len(cand) <= width or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        lines[-1] = lines[-1][:width - 1] + "…"
    return lines[:max_lines]


def _node_svg(x: int, y: int, label: str, note: str = "", accent: bool = False,
              height: int | None = None, width: int = NODE_W) -> str:
    h = height or _node_height(label, note, width)
    cx = x + width // 2
    fill = "var(--accent-wash, #f5f2ee)" if accent else "transparent"
    stroke = "var(--accent, #e05c1a)" if accent else "currentColor"
    lines = _wrap(label, _chars_for(width))
    has_note = bool(note and str(note).strip())
    total = len(lines) + (1 if has_note else 0)
    start_y = y + h / 2 - (total - 1) * LINE_H / 2 + 4.5
    texts = ""
    for i, ln in enumerate(lines):
        texts += (f'<text x="{cx}" y="{start_y + i * LINE_H:.0f}" text-anchor="middle" '
                  f'font-size="13" font-weight="600" fill="currentColor">{_e(ln)}</text>')
    if has_note:
        texts += (f'<text x="{cx}" y="{start_y + len(lines) * LINE_H:.0f}" '
                  f'text-anchor="middle" font-size="11" fill="var(--accent, #e05c1a)">'
                  f'{_e(_wrap(note, _chars_for(width), 1)[0])}</text>')
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{h}" rx="4" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>{texts}')


def _edge_label(x: float, y: float, text: str) -> str:
    if not text:
        return ""
    t = _wrap(text, 16, 1)[0]
    w = max(len(t) * CHAR_W + 8, 20)
    return (f'<rect x="{x - w / 2:.0f}" y="{y - 16:.0f}" width="{w:.0f}" height="15" rx="2" '
            f'fill="var(--paper, #fff)" stroke="none"/>'
            f'<text x="{x:.0f}" y="{y - 5:.0f}" text-anchor="middle" font-size="11" '
            f'fill="currentColor" opacity="0.8">{_e(t)}</text>')


_ARROW_DEF = ('<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" '
              'markerHeight="6" orient="auto-start-reverse">'
              '<path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor"/></marker></defs>')


def _svg_open(w: int, h: int, caption: str) -> str:
    # style 로 실제 크기를 고정한다. 이게 없으면 max-width:100% 가 그림을 본문 폭까지
    # 확대해서 13px 글자가 본문보다 커 보인다. 화면이 좁을 때만 축소된다.
    return (f'<svg viewBox="0 0 {w} {h}" style="width:{w}px;max-width:100%" '
            f'role="img" aria-label="{_e(caption)}" font-family="inherit" '
            f'xmlns="http://www.w3.org/2000/svg" fill="none">{_ARROW_DEF}')


def _title_text(w: int, title: str) -> str:
    return (f'<text x="{w // 2}" y="26" text-anchor="middle" font-size="13" font-weight="700" '
            f'fill="currentColor">{_e(_wrap(title, 40, 1)[0])}</text>')


def _render_flow(spec: dict) -> str:
    """좌→우 파이프라인. 한 줄에 3개까지만 두어 가로 폭을 억제한다.
    노드 4개를 한 줄에 놓으면 982px 가 되어 모바일에서 1/3 로 압착됐다."""
    nodes = spec["nodes"]
    per_row = 3 if len(nodes) > 3 else len(nodes)
    rows = [nodes[i:i + per_row] for i in range(0, len(nodes), per_row)]
    row_h = [max(_node_height(n.get("label", ""), n.get("note", "")) for n in row) for row in rows]
    w = PAD_X * 2 + per_row * NODE_W + (per_row - 1) * GAP_X
    h = PAD_Y + sum(row_h) + GAP_Y * (len(rows) - 1) + 14

    pos, body, y = {}, "", PAD_Y
    for r, row in enumerate(rows):
        for c, n in enumerate(row):
            x = PAD_X + c * (NODE_W + GAP_X)
            pos[n["id"]] = (x, y, row_h[r])
            body += _node_svg(x, y, n.get("label", ""), n.get("note", ""), height=row_h[r])
        y += row_h[r] + GAP_Y

    for e in spec.get("edges", []):
        a, b = pos.get(e.get("from")), pos.get(e.get("to"))
        if not a or not b:
            continue
        if a[1] == b[1] and b[0] > a[0]:                      # 같은 줄, 오른쪽으로
            x1, x2 = a[0] + NODE_W, b[0]
            cy = a[1] + a[2] / 2
            body += (f'<line x1="{x1}" y1="{cy:.0f}" x2="{x2 - 3}" y2="{cy:.0f}" '
                     f'stroke="currentColor" stroke-width="1.5" marker-end="url(#ar)"/>')
            body += _edge_label((x1 + x2) / 2, cy, e.get("label", ""))
        else:                                                  # 줄바꿈·역방향은 세로 경유
            x1, y1 = a[0] + NODE_W / 2, a[1] + a[2]
            x2, y2 = b[0] + NODE_W / 2, b[1]
            mid = (y1 + y2) / 2
            body += (f'<path d="M {x1:.0f} {y1:.0f} L {x1:.0f} {mid:.0f} L {x2:.0f} {mid:.0f} '
                     f'L {x2:.0f} {y2 - 3:.0f}" stroke="currentColor" stroke-width="1.5" '
                     f'marker-end="url(#ar)"/>')
            body += _edge_label((x1 + x2) / 2, mid, e.get("label", ""))
    return _svg_open(w, h, spec.get("caption", "")) + _title_text(w, spec.get("title", "")) + body + "</svg>"


def _render_layers(spec: dict) -> str:
    """위→아래 계층. 단수가 많으면 세로로 한없이 길어지므로 MAX_ROWS 로 자른다.
    계층은 세로가 본질이라 높이를 못 줄이는 대신, 박스를 넓게 잡아 세로로만 긴 그림이 되는 것을 막는다."""
    nodes = spec["nodes"][:MAX_ROWS]
    node_w = 260
    heights = [_node_height(n.get("label", ""), n.get("note", ""), node_w) for n in nodes]
    w = PAD_X * 2 + node_w + 160          # 엣지 라벨이 옆에 놓일 자리를 둔다
    h = PAD_Y + sum(heights) + GAP_Y * (len(nodes) - 1) + 14
    x = (w - node_w) // 2

    pos, body, y = {}, "", PAD_Y
    for n, nh in zip(nodes, heights):
        pos[n["id"]] = (y, nh)
        body += _node_svg(x, y, n.get("label", ""), n.get("note", ""), height=nh, width=node_w)
        y += nh + GAP_Y

    for e in spec.get("edges", []):
        a, b = pos.get(e.get("from")), pos.get(e.get("to"))
        if not a or not b or a[0] == b[0]:
            continue
        down = b[0] > a[0]
        top = a[0] + a[1] if down else a[0]
        bot = b[0] if down else b[0] + b[1]
        cx = w / 2
        body += (f'<line x1="{cx:.0f}" y1="{top:.0f}" x2="{cx:.0f}" '
                 f'y2="{bot + (-3 if down else 3):.0f}" stroke="currentColor" '
                 f'stroke-width="1.5" marker-end="url(#ar)"/>')
        body += _edge_label(cx + 2, (top + bot) / 2 + 8, e.get("label", ""))
    return _svg_open(w, h, spec.get("caption", "")) + _title_text(w, spec.get("title", "")) + body + "</svg>"


def _render_compare(spec: dict) -> str:
    """두 방식을 좌우로 놓고 차이를 보여준다. 오른쪽(새 방식)을 강조색으로."""
    groups = spec.get("groups", [])[:2]
    by_id = {n["id"]: n for n in spec["nodes"]}
    cols = []
    for g in groups:
        cols.append([by_id[i] for i in g.get("nodes", []) if i in by_id])
    if len(cols) != 2 or not all(cols):
        return _render_flow(spec)

    cols = [c[:MAX_COL_NODES] for c in cols]   # 열이 길어지면 그림이 세로로 늘어난다
    rows = max(len(c) for c in cols)
    # 두 열의 같은 행은 높이를 맞춰야 좌우 비교가 된다
    row_h = []
    for ri in range(rows):
        cands = [_node_height(c[ri].get("label", ""), c[ri].get("note", ""))
                 for c in cols if ri < len(c)]
        row_h.append(max(cands))
    col_w = NODE_W + 24
    w = PAD_X * 2 + col_w * 2 + GAP_X
    h = PAD_Y + 26 + sum(row_h) + GAP_Y * (rows - 1) + 14
    body = ""
    for ci, col in enumerate(cols):
        cx = PAD_X + ci * (col_w + GAP_X) + 12
        body += (f'<text x="{cx + NODE_W // 2}" y="{PAD_Y + 10}" text-anchor="middle" '
                 f'font-size="12" font-weight="700" fill="currentColor" opacity="0.75">'
                 f'{_e(_wrap(groups[ci].get("label", ""), 18, 1)[0])}</text>')
        y = PAD_Y + 26
        for ri, n in enumerate(col):
            body += _node_svg(cx, y, n.get("label", ""), n.get("note", ""),
                              accent=(ci == 1), height=row_h[ri])
            if ri + 1 < len(col):
                mx = cx + NODE_W / 2
                body += (f'<line x1="{mx:.0f}" y1="{y + row_h[ri]}" x2="{mx:.0f}" '
                         f'y2="{y + row_h[ri] + GAP_Y - 3}" stroke="currentColor" '
                         f'stroke-width="1.5" marker-end="url(#ar)"/>')
            y += row_h[ri] + GAP_Y
    # 두 열 사이 구분선
    sx = PAD_X + col_w + GAP_X / 2
    body += (f'<line x1="{sx:.0f}" y1="{PAD_Y}" x2="{sx:.0f}" y2="{h - 8}" '
             f'stroke="currentColor" stroke-width="1" stroke-dasharray="3 4" opacity="0.35"/>')
    return _svg_open(w, h, spec.get("caption", "")) + _title_text(w, spec.get("title", "")) + body + "</svg>"


_RENDERERS = {"flow": _render_flow, "compare": _render_compare, "layers": _render_layers}


def render_spec(spec) -> str:
    """LLM이 준 명세를 SVG figure 로 렌더링한다. 명세가 부실하면 빈 문자열."""
    if not isinstance(spec, dict):
        return ""
    dtype = str(spec.get("type", "")).lower()
    if dtype not in _RENDERERS:
        return ""
    nodes = spec.get("nodes")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 8:
        return ""
    clean = [n for n in nodes if isinstance(n, dict) and n.get("id") and n.get("label")]
    if len(clean) < 2:
        return ""
    spec = dict(spec, nodes=clean)
    spec["edges"] = [e for e in (spec.get("edges") or []) if isinstance(e, dict)]
    # caption 이 비면 claim 을, 그것도 없으면 title 을 쓴다 (aria-label 로도 쓰인다)
    spec["caption"] = spec.get("caption") or spec.get("claim") or spec.get("title") or ""
    try:
        svg = _RENDERERS[dtype](spec)
    except Exception:
        return ""
    return f'<figure class="diagram">{svg}<figcaption>{_e(spec["caption"])}</figcaption></figure>'


_WORD = re.compile(r"[0-9A-Za-z가-힣]+")


def _grounded(spec: dict, source: str) -> bool:
    """라벨이 원문에 근거하는지 확인한다.
    모델이 다른 글 내용을 베끼거나 없는 컴포넌트를 지어내는 것을 걸러낸다.
    의역은 허용해야 하므로 과반만 맞으면 통과시킨다."""
    src_words = set(w.lower() for w in _WORD.findall(source))
    src_text = source.lower()
    if not src_words:
        return False
    checked = hit = 0
    for n in spec.get("nodes", []):
        label = str(n.get("label", ""))
        words = [w.lower() for w in _WORD.findall(label) if len(w) > 1]
        if not words:
            continue
        checked += 1
        if any(w in src_words or w in src_text for w in words):
            hit += 1
    return checked > 0 and hit * 2 >= checked


def generate_concept_svg(title: str, content: str) -> str:
    if not content or len(content.strip()) < MIN_CONTENT:
        return ""
    source = f"{title}\n{content}"
    raw = _run_claude(DIAGRAM_PROMPT.format(title=title, content=content[:2000]), timeout=180)
    spec = _parse_json(raw)
    if not isinstance(spec, dict):
        print(f"[다이어그램] 명세 파싱 실패: {title[:40]}")
        return ""
    if str(spec.get("type", "")).lower() == "none":
        return ""
    if not _grounded(spec, source):
        labels = [n.get("label") for n in spec.get("nodes", []) if isinstance(n, dict)]
        print(f"[다이어그램] 원문 근거 부족으로 버림: {title[:34]} / {labels}")
        return ""
    out = render_spec(spec)
    if not out:
        print(f"[다이어그램] 명세 불충분: {title[:34]} / type={spec.get('type')} "
              f"nodes={len(spec.get('nodes') or [])}")
    return out


def add_svgs(items: list[dict], max_items: int) -> list[dict]:
    targets = [i for i in items if len((i.get("summary") or "").strip()) >= MIN_CONTENT][:max_items]
    if not targets:
        return items

    def one(item):
        item["svg"] = generate_concept_svg(item.get("title", ""), item.get("summary", ""))

    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(one, targets))
    return items
