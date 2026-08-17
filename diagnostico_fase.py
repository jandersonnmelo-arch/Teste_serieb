import streamlit as st


MATCH_KEYS = {
    "partidas", "partida", "jogos", "jogo", "matches", "match", "games", "game",
    "fixtures", "fixture", "confrontos", "confronto"
}


def _walk(value, path="$", rows=None):
    if rows is None:
        rows = []
    if isinstance(value, dict):
        for key, child in value.items():
            p = f"{path}.{key}"
            rows.append({
                "Caminho": p,
                "Tipo": type(child).__name__,
                "Quantidade": len(child) if isinstance(child, (dict, list)) else "—",
            })
            _walk(child, p, rows)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk(child, f"{path}[{i}]", rows)
    return rows


def _looks_like_match(obj):
    """Detecta uma partida sem depender do nome exato do campo da API."""
    if not isinstance(obj, dict):
        return False

    keys = {str(k).lower() for k in obj.keys()}

    explicit_id = keys & {
        "partida_id", "id_partida", "match_id", "fixture_id", "jogo_id", "confronto_id"
    }

    home = keys & {
        "mandante", "time_mandante", "equipe_mandante", "home", "home_team",
        "time_casa", "equipe_casa"
    }
    away = keys & {
        "visitante", "time_visitante", "equipe_visitante", "away", "away_team",
        "time_fora", "equipe_fora"
    }

    date_or_status = keys & {
        "data", "data_hora", "datetime", "date", "status", "situacao",
        "inicio", "horario"
    }

    return bool(explicit_id or (home and away) or ((home or away) and date_or_status))


def _find_matches(value, path="$", out=None):
    """Localiza partidas em listas, dicionários indexados e estruturas aninhadas."""
    if out is None:
        out = []

    if isinstance(value, dict):
        # O próprio objeto pode ser uma partida.
        if _looks_like_match(value):
            out.append((path, value))

        for key, child in value.items():
            key_lower = str(key).lower()
            child_path = f"{path}.{key}"

            # A API pode devolver partidas como lista, objeto indexado por IDs,
            # ou diretamente como um objeto único.
            if key_lower in MATCH_KEYS:
                if isinstance(child, list):
                    for i, item in enumerate(child):
                        _find_matches(item, f"{child_path}[{i}]", out)
                elif isinstance(child, dict):
                    _find_matches(child, child_path, out)
                continue

            _find_matches(child, child_path, out)

    elif isinstance(value, list):
        for i, child in enumerate(value):
            _find_matches(child, f"{path}[{i}]", out)

    return out


def _value(obj, *names):
    for name in names:
        if name in obj and obj[name] not in (None, "", []):
            return obj[name]
    return None


def _team_name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _value(value, "nome", "name", "nome_popular", "short_name") or str(value)
    return value


def _extract_row(path, p):
    pid = _value(
        p,
        "partida_id", "id_partida", "match_id", "fixture_id", "jogo_id", "confronto_id", "id"
    )

    home = _value(
        p, "mandante", "time_mandante", "equipe_mandante", "home_team", "home",
        "time_casa", "equipe_casa"
    )
    away = _value(
        p, "visitante", "time_visitante", "equipe_visitante", "away_team", "away",
        "time_fora", "equipe_fora"
    )

    score = _value(p, "placar", "resultado", "score")
    if isinstance(score, dict):
        score = (
            f"{_value(score, 'mandante', 'home', 'casa', 'home_score') or '—'} x "
            f"{_value(score, 'visitante', 'away', 'fora', 'away_score') or '—'}"
        )

    return {
        "ID": pid if pid is not None else "—",
        "Rodada": _value(p, "rodada", "round", "numero_rodada", "round_number") or "—",
        "Data": _value(p, "data", "date", "data_hora", "datetime", "inicio", "horario") or "—",
        "Mandante": _team_name(home) if home is not None else "—",
        "Visitante": _team_name(away) if away is not None else "—",
        "Placar": score if score is not None else "—",
        "Status": _value(p, "status", "situacao", "estado") or "—",
        "Caminho no JSON": path,
    }


def render_fase_diagnostic(data):
    if not data:
        st.info("Nenhum detalhe de fase carregado ainda.")
        return

    found = _find_matches(data)

    # Deduplicação. Quando não há ID, o caminho no JSON mantém a partida única.
    unique = {}
    for path, p in found:
        pid = _value(
            p, "partida_id", "id_partida", "match_id", "fixture_id", "jogo_id", "confronto_id", "id"
        )
        key = f"id:{pid}" if pid is not None else f"path:{path}"
        unique[key] = (path, p)

    found = list(unique.values())

    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption("Análise do JSON já recebido — esta seção não faz nenhuma requisição à API.")
    st.metric("Partidas encontradas", len(found))

    if not found:
        st.warning("Não foi localizada uma estrutura de partida no retorno da fase.")
        st.write("**Estrutura recebida — caminhos relevantes encontrados:**")
        paths = _walk(data)
        relevant = [
            row for row in paths
            if any(term in row["Caminho"].lower() for term in MATCH_KEYS)
        ]
        if relevant:
            st.dataframe(relevant[:200], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma chave com nome típico de partidas foi encontrada. O formato da resposta precisa ser mapeado antes do próximo teste.")
        return

    rows = [_extract_row(path, p) for path, p in found]
    st.dataframe(rows, use_container_width=True, hide_index=True)

    rodada_counts = {}
    for row in rows:
        rodada = str(row["Rodada"])
        rodada_counts[rodada] = rodada_counts.get(rodada, 0) + 1

    st.subheader("📅 Partidas por rodada")
    st.dataframe(
        [{"Rodada": k, "Partidas": v} for k, v in sorted(rodada_counts.items(), key=lambda x: x[0])],
        use_container_width=True,
        hide_index=True,
    )

    st.caption("O caminho do JSON é exibido para podermos confirmar exatamente onde a API-Futebol está entregando cada partida.")
