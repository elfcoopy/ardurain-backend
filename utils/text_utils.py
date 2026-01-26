from typing import List

def clean_text(s: str) -> str:
    if not s:
        return s
    return (
        s.replace("===Description===", "")
         .replace("===", "")
         .replace("==", "")
         .replace("\r", "")
         .strip()
    )

def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))

def dedup_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out
