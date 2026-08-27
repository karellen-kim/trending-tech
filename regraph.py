#!/usr/bin/env python3
"""이미 그려진 다이어그램을 지금 레이아웃으로 다시 그린다.

수집 원본이 남아 있지 않으므로 SVG 자체에서 명세를 되읽는다.
svgmaker 가 만든 그림이라 구조가 규칙적이다 — 노드는 rect + font-size 13 텍스트,
note 는 font-size 11, 엣지 라벨은 마스크 rect 뒤의 opacity 0.8 텍스트다.

    python regraph.py --check   # 되읽기만 하고 손실을 보고한다
    python regraph.py           # 다시 그려 파일에 쓴다
"""
import re
import sys

from config import DOCS_DIR
import svgmaker

# render_spec 은 figure + figcaption 까지 만든다. svg 만 갈아끼우면 figure 가 중첩된다.
_FIG = re.compile(r'<figure class="diagram">.*?</figure>', re.S)
_ARIA = re.compile(r'aria-label="([^"]*)"')
_RECT = re.compile(r'<rect x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)" rx="4" '
                   r'fill="([^"]*)" stroke="([^"]*)" stroke-width="1.5"/>')
_TEXT = re.compile(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*?font-size="(\d+)"[^>]*?>(.*?)</text>')
_TEXT_ANY = re.compile(r'<text\b[^>]*>(?:.*?)</text>', re.S)
_UNESC = [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"')]


def _unesc(s: str) -> str:
    for a, b in _UNESC:
        s = s.replace(a, b)
    return s


def _texts(svg: str) -> list[dict]:
    """모든 텍스트를 좌표·크기와 함께 뽑는다."""
    out = []
    for m in re.finditer(r'<text ([^>]*)>(.*?)</text>', svg, re.S):
        attrs, body = m.group(1), m.group(2)
        def g(name, cast=str):
            mm = re.search(rf'\b{name}="([^"]*)"', attrs)
            return cast(mm.group(1)) if mm else None
        out.append({
            "x": float(g("x") or 0), "y": float(g("y") or 0),
            "size": int(g("font-size") or 0),
            "weight": g("font-weight") or "",
            "fill": g("fill") or "",
            "opacity": g("opacity") or "",
            "text": _unesc(re.sub(r"<[^>]+>", "", body)).strip(),
        })
    return out


def parse_svg(svg: str) -> dict | None:
    """SVG 를 svgmaker.render_spec 이 받는 명세로 되돌린다. 못 읽으면 None."""
    w = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))
    caption = _unesc(_ARIA.search(svg).group(1)) if _ARIA.search(svg) else ""
    txts = _texts(svg)

    title = ""
    for t in txts:
        if t["size"] == 13 and t["weight"] == "700" and t["y"] <= 30:
            title = t["text"]
            break

    rects = [{"x": int(m.group(1)), "y": int(m.group(2)),
              "w": int(m.group(3)), "h": int(m.group(4)),
              "accent": "accent-wash" in m.group(5)} for m in _RECT.finditer(svg)]
    if not rects:
        return None

    # 각 상자 안에 들어가는 텍스트를 모아 label 과 note 를 만든다
    nodes = []
    for i, r in enumerate(rects):
        inner = [t for t in txts
                 if r["x"] <= t["x"] <= r["x"] + r["w"] and r["y"] <= t["y"] <= r["y"] + r["h"]]
        label = " ".join(t["text"] for t in sorted(inner, key=lambda t: t["y"])
                         if t["size"] == 13 and t["weight"] == "600")
        note = next((t["text"] for t in inner if t["size"] == 11 and "accent" in t["fill"]), "")
        if not label:
            continue
        nodes.append({"id": f"n{i}", "label": label, "note": note,
                      "_x": r["x"], "_y": r["y"], "_accent": r["accent"]})
    if len(nodes) < 2:
        return None

    # 엣지 라벨: 마스크 rect 뒤에 오는 opacity 0.8 텍스트
    edge_labels = [t["text"] for t in txts if t["size"] == 11 and t["opacity"] == "0.8"]

    # 타입 판별 — 폭과 구성으로 갈린다
    group_labels = [t for t in txts if t["size"] == 12 and t["weight"] == "700"]
    if len(group_labels) == 2 and 'stroke-dasharray="3 4"' in svg:
        kind = "compare"
    elif len({n["_x"] for n in nodes}) == 1 and len(nodes) >= 2:
        kind = "layers"
    else:
        kind = "flow"

    spec = {"type": kind, "title": title, "caption": caption,
            "nodes": [{"id": n["id"], "label": n["label"], "note": n["note"]} for n in nodes]}

    if kind == "compare":
        mid = sorted({n["_x"] for n in nodes})
        split = mid[len(mid) // 2] if len(mid) > 1 else 0
        left = [n["id"] for n in nodes if n["_x"] < split]
        right = [n["id"] for n in nodes if n["_x"] >= split]
        if not left or not right:
            return None
        spec["groups"] = [{"label": group_labels[0]["text"], "nodes": left},
                          {"label": group_labels[1]["text"], "nodes": right}]
        spec["edges"] = []
    else:
        # 읽기 순서(위→아래, 왼→오른쪽)대로 이어 붙인다. 원래 그림도 그 순서로 그려졌다.
        ordered = sorted(nodes, key=lambda n: (n["_y"], n["_x"]))
        spec["edges"] = [
            {"from": ordered[i]["id"], "to": ordered[i + 1]["id"],
             "label": edge_labels[i] if i < len(edge_labels) else ""}
            for i in range(len(ordered) - 1)]
    return spec


def _plain(svg: str) -> list[str]:
    """비교용 — 그림 안 글자만 뽑아 정렬한다."""
    return sorted(t["text"] for t in _texts(svg) if t["text"])


def main(check: bool, force: bool = False) -> None:
    files = sorted(DOCS_DIR.glob("????-??-??.html"))
    total = redrawn = failed = 0
    lost = []
    for f in files:
        h = f.read_text(encoding="utf-8")
        out, pos, changed = [], 0, False
        for m in _FIG.finditer(h):
            total += 1
            old = m.group(0)
            spec = parse_svg(old)
            if not spec:
                failed += 1
                continue
            try:
                new = svgmaker.render_spec(spec)
            except Exception as e:
                failed += 1
                lost.append(f"{f.stem}: 렌더 실패 {type(e).__name__}")
                continue
            if not new or "<svg" not in new:
                failed += 1
                continue
            # 글자가 빠지지 않았는지 — 되읽기의 유일한 위험은 라벨 손실이다.
            # 한 글자라도 잃으면 다시 그리지 않고 원본을 그대로 둔다.
            before, after = set(_plain(old)), set(_plain(new))
            missing = before - after
            if missing:
                lost.append(f"{f.stem}: {sorted(missing)[:3]}")
                if not force:
                    continue
            redrawn += 1
            changed = True
            out.append(h[pos:m.start()]); out.append(new); pos = m.end()
        if changed and not check:
            out.append(h[pos:])
            f.write_text("".join(out), encoding="utf-8")

    print(f"SVG {total}개 / 다시 그림 {redrawn} / 되읽기 실패 {failed}")
    if lost:
        head = "손실을 감수하고 다시 그린 것" if force else "손실이 나서 원본을 둔 것"
        print(f"{head} {len(lost)}건:")
        for l in lost[:12]:
            print("  ", l)
    else:
        print("글자 손실 없음")
    if check:
        print("(--check 모드 — 파일은 쓰지 않았다)")


if __name__ == "__main__":
    main(check="--check" in sys.argv, force="--force" in sys.argv)
