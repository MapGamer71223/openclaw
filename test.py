"""
Run this from your backend's venv on the same machine, to see the REAL
exception each PicImageSearch engine throws instead of having it silently
swallowed by source_search.py's `except Exception: return []`.

Usage:
  python test_picimagesearch.py "C:\\path\\to\\some\\test\\image.jpg"
"""
import sys

image_path = sys.argv[1] if len(sys.argv) > 1 else None
if not image_path:
    print("Pass an image path as an argument.")
    sys.exit(1)

from PicImageSearch.sync import Google, Tineye, Yandex

for name, cls in [("google", Google), ("yandex", Yandex), ("tineye", Tineye)]:
    print(f"\n=== {name} ===")
    try:
        engine = cls()
        resp = engine.search(file=image_path)
        raw = getattr(resp, "raw", [])
        print(f"OK - {len(raw)} raw result(s)")
        if raw:
            first = raw[0]
            print("  first url:", getattr(first, "url", None))
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")