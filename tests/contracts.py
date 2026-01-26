def extract_zone_thresholds_ast(instrument_path: str) -> Dict[str, Any]:
    """
    Extraction AST conservatrice des zones.

    CONTRAT: ne renvoie JAMAIS None.
    Retourne toujours un dict contenant au minimum:
      {
        "constants": dict[str, int|float|str],
        "if_chain": list[tuple[str, float, str]],
        "pattern": str,
      }
    """
    out: Dict[str, Any] = {"constants": {}, "if_chain": [], "pattern": "none"}

    p = Path(instrument_path)
    if not p.exists():
        out["pattern"] = "missing_file"
        out["error"] = f"instrument not found: {instrument_path}"
        return out

    src = p.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        out["pattern"] = "syntax_error"
        out["error"] = str(e)
        return out

    candidate_names = {"ZONE_THRESHOLDS", "ZONES", "ZONE_BOUNDS", "ZONE_LIMITS", "ZONE_CUTS", "THRESHOLDS"}

    # 1) Assigns explicites
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in candidate_names:
                    val = _literal_eval_safe(node.value)
                    if isinstance(val, (list, tuple)) and all(_is_number(x) for x in val):
                        ths = [float(x) for x in val]
                        out["pattern"] = "assign_thresholds"
                        out["name"] = t.id
                        for i, th in enumerate(ths):
                            out["constants"][f"ZONE_THRESHOLD_{i}"] = th
                        return out
                    if isinstance(val, dict):
                        out["pattern"] = "assign_mapping"
                        out["name"] = t.id
                        # flatten conservatif
                        for k, v in val.items():
                            if isinstance(v, (int, float, str)) and not isinstance(v, bool):
                                out["constants"][f"ZONE_MAP_{str(k)}"] = v
                        return out

    # 2) Chaînes if/elif sur T < seuil → zone="X"
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            chain = _collect_if_chain(node)
            if not chain:
                continue
            ths, zlabels = _parse_if_chain_for_T(chain)
            if ths and zlabels and len(ths) == len(zlabels):
                out["pattern"] = "if_chain"
                out["if_chain"] = [("Lt", float(ths[i]), str(zlabels[i])) for i in range(len(ths))]
                for i, th in enumerate(ths):
                    out["constants"][f"ZONE_IF_THRESHOLD_{i}"] = float(th)
                    out["constants"][f"ZONE_IF_LABEL_{i}"] = str(zlabels[i])
                return out

    # Aucun signal détecté: out reste vide mais valide
    return out
