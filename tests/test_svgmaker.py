import re
import xml.etree.ElementTree as ET

import svgmaker

FLOW = {
    "type": "flow",
    "title": "요청 처리 경로",
    "caption": "요청이 캐시를 거쳐 DB에 닿는 경로",
    "nodes": [
        {"id": "c", "label": "클라이언트"},
        {"id": "k", "label": "Redis 캐시", "note": "TTL 60초"},
        {"id": "d", "label": "PostgreSQL"},
    ],
    "edges": [
        {"from": "c", "to": "k", "label": "조회"},
        {"from": "k", "to": "d", "label": "미스 시 위임"},
    ],
}

COMPARE = {
    "type": "compare",
    "title": "리밸런싱 방식 비교",
    "caption": "eager 방식과 cooperative 방식의 차이",
    "nodes": [
        {"id": "a1", "label": "전체 컨슈머 정지"},
        {"id": "a2", "label": "45초 소요"},
        {"id": "b1", "label": "해당 파티션만 이동"},
        {"id": "b2", "label": "3초 소요"},
    ],
    "groups": [
        {"label": "기존 eager", "nodes": ["a1", "a2"]},
        {"label": "cooperative", "nodes": ["b1", "b2"]},
    ],
    "edges": [],
}

LAYERS = {
    "type": "layers",
    "title": "관측 스택",
    "caption": "ADOT이 지표를 상위로 올린다",
    "nodes": [
        {"id": "a", "label": "에이전트"},
        {"id": "b", "label": "ADOT"},
        {"id": "c", "label": "AgentCore"},
    ],
    "edges": [{"from": "a", "to": "b", "label": "추적 전송"},
              {"from": "b", "to": "c", "label": "집계"}],
}


def _svg_of(html: str) -> str:
    m = re.search(r"<svg.*?</svg>", html, re.S)
    assert m, "svg 없음"
    return m.group(0)


def test_flow_renders_valid_xml():
    out = svgmaker.render_spec(FLOW)
    ET.fromstring(_svg_of(out))       # 파싱 실패하면 예외


def test_all_types_render_valid_xml():
    for spec in (FLOW, COMPARE, LAYERS):
        ET.fromstring(_svg_of(svgmaker.render_spec(spec)))


def test_every_node_label_appears():
    out = svgmaker.render_spec(FLOW)
    for n in FLOW["nodes"]:
        assert n["label"] in out, n


def test_edge_labels_are_drawn():
    """라벨 없는 화살표는 '관련 있음'일 뿐이라 반드시 그려야 한다"""
    out = svgmaker.render_spec(FLOW)
    assert "조회" in out
    assert "미스 시 위임" in out


def test_has_arrow_marker():
    out = svgmaker.render_spec(FLOW)
    assert "marker-end" in out and 'id="ar"' in out


def test_uses_currentcolor_for_theme():
    out = svgmaker.render_spec(FLOW)
    assert "currentColor" in out


def test_has_figure_and_accessible_label():
    out = svgmaker.render_spec(FLOW)
    assert out.startswith("<figure")
    assert "<figcaption>" in out
    assert 'role="img"' in out
    assert 'aria-label="요청이 캐시를 거쳐 DB에 닿는 경로"' in out


def test_viewbox_present_without_fixed_size():
    svg = _svg_of(svgmaker.render_spec(FLOW))
    assert "viewBox=" in svg
    assert not re.search(r'<svg[^>]*\swidth=', svg), "고정 width 가 있으면 반응형이 깨진다"


def test_compare_shows_both_group_labels():
    out = svgmaker.render_spec(COMPARE)
    assert "기존 eager" in out and "cooperative" in out


def test_compare_falls_back_when_groups_broken():
    broken = dict(COMPARE, groups=[{"label": "하나뿐", "nodes": ["a1"]}])
    out = svgmaker.render_spec(broken)
    assert out.startswith("<figure")     # flow 로 폴백해서라도 그린다


def test_rejects_type_none():
    assert svgmaker.render_spec({"type": "none"}) == ""


def test_rejects_unknown_type():
    assert svgmaker.render_spec(dict(FLOW, type="pie")) == ""


def test_rejects_too_few_nodes():
    assert svgmaker.render_spec(dict(FLOW, nodes=[{"id": "a", "label": "혼자"}])) == ""


def test_rejects_non_dict():
    assert svgmaker.render_spec(None) == ""
    assert svgmaker.render_spec("문자열") == ""


def test_drops_malformed_nodes():
    spec = dict(FLOW, nodes=FLOW["nodes"] + [{"label": "id 없음"}, "이상한값"])
    out = svgmaker.render_spec(spec)
    assert out.startswith("<figure")
    assert "id 없음" not in out


def test_escapes_html_in_labels():
    """라벨은 이스케이프 없이 SVG에 들어가므로 반드시 막아야 한다"""
    spec = dict(FLOW, nodes=[{"id": "a", "label": "<script>x</script>"},
                             {"id": "b", "label": "정상"}], edges=[])
    out = svgmaker.render_spec(spec)
    assert "<script>" not in out
    assert "&lt;script&gt;" in out
    ET.fromstring(_svg_of(out))


def test_edge_with_unknown_id_is_ignored():
    spec = dict(FLOW, edges=[{"from": "c", "to": "없는id", "label": "x"}])
    out = svgmaker.render_spec(spec)
    assert out.startswith("<figure")
    ET.fromstring(_svg_of(out))


def test_long_label_is_truncated():
    spec = dict(FLOW, nodes=[{"id": "a", "label": "가" * 200}, {"id": "b", "label": "정상"}], edges=[])
    out = svgmaker.render_spec(spec)
    assert "…" in out


def test_generate_returns_empty_on_none_type(monkeypatch):
    monkeypatch.setattr(svgmaker, "_run_claude", lambda p, **kw: '{"type": "none"}')
    assert svgmaker.generate_concept_svg("T", "본문" * 200) == ""


def test_generate_returns_empty_on_garbage(monkeypatch):
    monkeypatch.setattr(svgmaker, "_run_claude", lambda p, **kw: "모델이 딴소리를 함")
    assert svgmaker.generate_concept_svg("T", "본문" * 200) == ""


def test_generate_handles_code_fence(monkeypatch):
    import json
    monkeypatch.setattr(svgmaker, "_run_claude",
                        lambda p, **kw: "```json\n" + json.dumps(FLOW) + "\n```")
    src = "클라이언트가 Redis 캐시를 조회하고 미스면 PostgreSQL 로 위임한다. " * 6
    out = svgmaker.generate_concept_svg("요청 처리 경로", src)
    assert "Redis 캐시" in out


# ── 원문 근거 검사 (프롬프트 예시 베끼기 방어) ──

SOURCE = ("Kafka 파티션 리밸런싱 성능 개선. eager 방식은 전체 컨슈머가 멈췄지만 "
          "cooperative 방식은 영향받는 파티션만 이동한다. 45초에서 3초로 단축됐다.")


def test_grounded_accepts_labels_from_source():
    spec = {"nodes": [{"label": "eager 방식"}, {"label": "cooperative 방식"},
                      {"label": "파티션 이동"}]}
    assert svgmaker._grounded(spec, SOURCE) is True


def test_grounded_rejects_copied_prompt_examples():
    """다른 글 내용을 그대로 베낀 명세는 버려야 한다"""
    spec = {"nodes": [{"label": "ADOT 콜렉터"}, {"label": "CloudWatch 집계"},
                      {"label": "IAM 자격증명"}]}
    assert svgmaker._grounded(spec, SOURCE) is False


def test_grounded_allows_partial_mismatch():
    """3분의 2 이상이 원문에 있으면 통과 (약간의 의역은 허용)"""
    spec = {"nodes": [{"label": "eager 방식"}, {"label": "cooperative 방식"},
                      {"label": "지어낸것"}]}
    assert svgmaker._grounded(spec, SOURCE) is True


def test_grounded_rejects_empty_source():
    assert svgmaker._grounded({"nodes": [{"label": "x"}]}, "") is False


def test_generate_drops_ungrounded_spec(monkeypatch):
    import json
    fake = {"type": "flow", "title": "t", "caption": "c",
            "nodes": [{"id": "a", "label": "ADOT 콜렉터"}, {"id": "b", "label": "CloudWatch"}],
            "edges": [{"from": "a", "to": "b", "label": "전송"}]}
    monkeypatch.setattr(svgmaker, "_run_claude", lambda p, **kw: json.dumps(fake))
    assert svgmaker.generate_concept_svg("Kafka 리밸런싱", SOURCE * 2) == ""


def test_add_svgs_respects_max(monkeypatch):
    calls = []
    monkeypatch.setattr(svgmaker, "generate_concept_svg",
                        lambda t, c: calls.append(t) or "<figure/>")
    items = [{"title": str(i), "summary": "가" * 300} for i in range(10)]
    svgmaker.add_svgs(items, max_items=3)
    assert len(calls) == 3


def test_add_svgs_skips_items_without_content(monkeypatch):
    monkeypatch.setattr(svgmaker, "generate_concept_svg", lambda t, c: "<figure/>")
    items = [{"title": "빈 요약", "summary": ""}]
    svgmaker.add_svgs(items, max_items=5)
    assert items[0].get("svg", "") == ""
