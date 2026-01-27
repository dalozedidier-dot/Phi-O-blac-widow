diff --git a/contract_probe.py b/contract_probe.py
index 0000000..1111111 100644
--- a/contract_probe.py
+++ b/contract_probe.py
@@ -1,200 +1,260 @@
@@
 def extract_zones_ast_only(instrument_path: Path) -> Dict[str, Any]:
-    """Extraction *honnête* des zones (AST uniquement)."""
-    try:
-        zones = extract_zone_thresholds_ast(str(instrument_path))
-        zones["attempted"] = True
-        zones["method"] = "ast"
-        # Normaliser un dict plat "zones" pour la conformité
-        # - constants: ZONE_* literals
-        # - if_chain: list[tuple[op, threshold, zone_label]]
-        flat: Dict[str, Any] = {}
-        for k, v in (zones.get("constants") or {}).items():
-            flat[k] = v
-        zones["zones"] = flat
-        return zones
-    except Exception as e:
-        return {"zones": {}, "attempted": True, "method": "ast_failed", "error": str(e)}
+    """
+    Extraction *honnête* des zones (AST uniquement).
+
+    Objectif contractuel:
+    - ne jamais crasher (shape stable)
+    - capturer uniquement ce qui est réellement extractible depuis l'AST
+    - supporter plusieurs formats possibles renvoyés par tests/contracts.py
+    """
+    normalized: Dict[str, Any] = {
+        "zones": {},
+        "constants": {},
+        "if_chain": [],
+        "attempted": True,
+        "method": "ast",
+    }
+
+    try:
+        raw = extract_zone_thresholds_ast(str(instrument_path))
+
+        # Guard 1: None
+        if raw is None:
+            normalized["method"] = "ast_failed"
+            normalized["error"] = "extract_zone_thresholds_ast returned None"
+            return normalized
+
+        # Guard 2: type inattendu
+        if not isinstance(raw, dict):
+            normalized["method"] = "ast_failed"
+            normalized["error"] = f"extract_zone_thresholds_ast returned non-dict: {type(raw).__name__}"
+            return normalized
+
+        # Format A (contractuel): {"constants": {...}, "if_chain": [...]}
+        if isinstance(raw.get("constants"), dict) or isinstance(raw.get("if_chain"), list):
+            normalized["constants"] = raw.get("constants") if isinstance(raw.get("constants"), dict) else {}
+            normalized["if_chain"] = raw.get("if_chain") if isinstance(raw.get("if_chain"), list) else []
+
+        # Format B1 (heuristique): {"thresholds": [...], ...}
+        elif isinstance(raw.get("thresholds"), (list, tuple)):
+            ths = [
+                x for x in list(raw.get("thresholds"))
+                if isinstance(x, (int, float)) and not isinstance(x, bool)
+            ]
+            normalized["constants"] = {f"THRESH_{i}": float(v) for i, v in enumerate(ths)}
+            normalized["pattern"] = raw.get("pattern", "thresholds")
+
+        # Format B2 (heuristique): {"mapping": {...}, ...}
+        elif isinstance(raw.get("mapping"), dict):
+            mp = raw.get("mapping") if isinstance(raw.get("mapping"), dict) else {}
+            normalized["constants"] = {
+                str(k): v for k, v in mp.items()
+                if isinstance(v, (int, float, str)) and not isinstance(v, bool)
+            }
+            normalized["pattern"] = raw.get("pattern", "mapping")
+
+        else:
+            normalized["method"] = "ast_failed"
+            normalized["error"] = f"extract_zone_thresholds_ast returned dict without recognized keys: {sorted(raw.keys())}"
+            return normalized
+
+        # Flat "zones" = constants littéraux uniquement
+        flat: Dict[str, Any] = {}
+        for k, v in (normalized.get("constants") or {}).items():
+            if isinstance(v, (int, float, str)) and not isinstance(v, bool):
+                flat[k] = v
+        normalized["zones"] = flat
+
+        # Conserver le reste des champs non conflictuels (diagnostic)
+        for k, v in raw.items():
+            if k in ("zones", "constants", "if_chain", "attempted", "method", "error"):
+                continue
+            normalized[k] = v
+
+        return normalized
+
+    except Exception as e:
+        normalized["method"] = "ast_failed"
+        normalized["error"] = str(e)
+        return normalized
