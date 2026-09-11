# -*- coding: utf-8 -*-
"""
Export asset metadata into static JSON for Cloudflare Pages / Static Hosting
"""
import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(APP_DIR))

import server

def export():
    print("Scanning and exporting asset metadata to static/data/assets.json ...")
    assets = server.scan_assets(force_reload=True)
    
    from collections import Counter
    cat_counter = Counter(a["category"] for a in assets)
    sorted_categories = [cat for cat, _ in cat_counter.most_common()]
    
    batch_counter = Counter(a["batch"] for a in assets)
    sorted_batches = sorted(list(batch_counter.keys()))

    total_videos = sum(1 for a in assets if a["has_video"])
    total_usds = sum(1 for a in assets if a["has_usd"])
    total_size_gb = round(sum(a["total_size_bytes"] for a in assets) / (1024**3), 2)

    data = {
        "assets": assets,
        "total": len(assets),
        "batches": sorted_batches,
        "categories": sorted_categories,
        "category_counts": dict(cat_counter),
        "batch_counts": dict(batch_counter),
        "stats": {
            "total_assets": len(assets),
            "total_videos": total_videos,
            "total_usds": total_usds,
            "total_batches": len(sorted_batches),
            "total_categories": len(sorted_categories),
            "total_size_gb": total_size_gb
        }
    }

    out_dir = APP_DIR / "static" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "assets.json"
    
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully exported {len(assets)} assets to {out_file} ({out_file.stat().st_size / 1024:.1f} KB)")

if __name__ == "__main__":
    export()