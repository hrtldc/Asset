# -*- coding: utf-8 -*-
import json
import os
import time
from pathlib import Path
from pxr import Usd

output_dir = Path("G:/Simreay/output")
t0 = time.time()
print("Scanning USD files for authored physical properties...")

results = {}
for batch_dir in sorted(output_dir.iterdir()):
    if not batch_dir.is_dir():
        continue
    for item_dir in sorted(batch_dir.iterdir()):
        if not item_dir.is_dir():
            continue
        usd_file = item_dir / (item_dir.name + ".usd")
        if not usd_file.exists():
            usds = list(item_dir.glob("*.usd"))
            usd_file = usds[0] if usds else None

        info = {
            "mass_kg": None,
            "static_friction": 0.50,
            "dynamic_friction": 0.35,
            "restitution": 0.05,
            "semantic_class": None,
            "wikidata_qcode": None
        }

        if usd_file and usd_file.exists():
            try:
                stage = Usd.Stage.Open(str(usd_file))
                if stage:
                    root_mass = None
                    max_mass = None
                    for prim in stage.Traverse():
                        for prop in prim.GetAuthoredProperties():
                            pname = prop.GetName()
                            if pname == "physics:mass":
                                val = prop.Get()
                                if val is not None and val > 0:
                                    val_f = round(float(val), 3)
                                    if max_mass is None or val_f > max_mass:
                                        max_mass = val_f
                                    segs = [s for s in str(prim.GetPath()).split("/") if s]
                                    if len(segs) <= 2:
                                        root_mass = val_f
                            elif pname == "physics:staticFriction":
                                val = prop.Get()
                                if val is not None:
                                    info["static_friction"] = round(float(val), 2)
                            elif pname == "physics:dynamicFriction":
                                val = prop.Get()
                                if val is not None:
                                    info["dynamic_friction"] = round(float(val), 2)
                            elif pname == "physics:restitution":
                                val = prop.Get()
                                if val is not None:
                                    info["restitution"] = round(float(val), 2)
                            elif pname in ("semantics:class:params:semanticData", "semantics:labels:class"):
                                val = prop.Get()
                                if val and not info["semantic_class"]:
                                    cval = val[0] if isinstance(val, (list, tuple)) else str(val)
                                    cval = str(cval).replace("[", "").replace("]", "").strip()
                                    if cval and cval != "GenericProp":
                                        info["semantic_class"] = cval
                            elif pname in ("semantics:wikidata:params:semanticData", "semantics:labels:wikidata"):
                                val = prop.Get()
                                if val and not info["wikidata_qcode"]:
                                    cq = val[0] if isinstance(val, (list, tuple)) else str(val)
                                    cq = str(cq).replace("[", "").replace("]", "").strip()
                                    if cq and cq != "Q223557":
                                        info["wikidata_qcode"] = cq
                    info["mass_kg"] = root_mass if root_mass is not None else max_mass
            except Exception as e:
                pass

        results[batch_dir.name + "/" + item_dir.name] = info

out_path = Path("G:/JSUDS/Asset/static/data/usd_physics_cache.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("Extracted physics for", len(results), "assets in", round(time.time() - t0, 2), "seconds")
sample = results.get("qzs_10/SM_YuShiGui01-B")
print("qzs_10/SM_YuShiGui01-B ->", sample)

