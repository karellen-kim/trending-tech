#!/usr/bin/env python3
"""특정 날짜 HTML 재생성 (수집 → 요약 → HTML 저장)"""
import sys
from main import collect, summarize, save_html

def rerender(date_str: str):
    print(f"[rerender] {date_str} 재생성 시작")
    data = collect(date_str)
    data = summarize(data)
    save_html(data)
    print(f"[rerender] 완료: docs/{date_str}.html")

if __name__ == "__main__":
    date_str = sys.argv[1] if len(sys.argv) > 1 else "2026-05-31"
    rerender(date_str)
