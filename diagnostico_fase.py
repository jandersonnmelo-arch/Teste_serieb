import streamlit as st


def _walk(value, path="$", rows=None):
    if rows is None:
        rows = []
    if isinstance(value, dict):
        for key, child in value.items():
            p = f"{path}.{key}"
            rows.append({"Caminho": p, "Tipo": type(child).__name__, "Quantidade": len(child) if isinstance(child, (dict, list)) else "—"})
            _walk(child, p, rows)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk(child, f"{path}[{i}]", rows)
    return rows


def _find_matches(value, path="$", out=None):
    if out is None:
        out = []
    if isinstance(value, dict):
        for key, child in value.items():
            k = str(key).lower()
            if k in {"partidas", "partida", "jogos", "matches", "games"} and isinstance(child, list):
                for item in child:
                    if isinstance(item, dict):
                        out.append(item)
            _find_matches(child, f"{path}.{key}", out)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _find_matches(child, f"{path}[{i}]", out)
    return out


def render_fase_diagnostic(data):
    if not data:
        st.info("Nenhum detalhe de fase carregado ainda.")
        return
    partidas = _find_matches(data)
    unique = {}
    for p in partidas:
        pid = p.get("partida_id") or p.get("id") or p.get("match_id")
        if pid is not None:
            unique[str(pid)] = p
    partidas = list(unique.values())
    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption("Análise do JSON já recebido — esta seção não faz nenhuma requisição à API.")
    st.metric("Partidas encontradas", len(partidas))
    if not partidas:
        st.warning("Não foi localizada uma lista de partidas no retorno da fase.")
        return
    rows = []
    for p in partidas:
        rodada = p.get("rodada") or p.get("round") or p.get("numero_rodada") or "—"
        mandante = p.get("mandante") or p.get("time_mandante") or p.get("home_team") or p.get("home") or "—"
        visitante = p.get("visitante") or p.get("time_visitante") or p.get("away_team") or p.get("away") or "—"
        placar = p.get("placar") or p.get("resultado") or p.get("score") or "—"
        rows.append({"ID": p.get("partida_id") or p.get("id") or p.get("match_id") or "—", "Rodada": rodada, "Data": p.get("data") or p.get("date") or p.get("data_hora") or "—", "Mandante": mandante, "Visitante": visitante, "Placar": placar, "Status": p.get("status") or "—"})
    st.dataframe(rows, use_container_width=True, hide_index=True)
    rodada_counts = {}
    for r in rows:
        rodada_counts[str(r["Rodada"])] = rodada_counts.get(str(r["Rodada"]), 0) + 1
    st.subheader("📅 Partidas por rodada")
    st.dataframe([{"Rodada": k, "Partidas": v} for k, v in sorted(rodada_counts.items(), key=lambda x: x[0])], use_container_width=True, hide_index=True)
