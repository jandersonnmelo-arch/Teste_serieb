import streamlit as st

MATCH_ID_KEYS = ("partida_id", "id_partida", "id", "match_id", "fixture_id")
HOME_KEYS = ("time_mandante", "mandante", "home_team", "home", "time_casa")
AWAY_KEYS = ("time_visitante", "visitante", "away_team", "away", "time_fora")
ROUND_KEYS = ("rodada", "round", "numero_rodada", "rodada_numero")
DATE_KEYS = ("data", "date", "data_hora", "horario", "datetime")
STATUS_KEYS = ("status", "situacao", "estado")
SCORE_KEYS = ("placar", "resultado", "score")


def _get_first(d, keys):
    if not isinstance(d, dict):
        return None
    for key in keys:
        value = d.get(key)
        if value not in (None, ""):
            return value
    return None


def _name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("nome", "name", "nome_popular", "short_name", "apelido"):
            if value.get(key):
                return value[key]
    return value


def _match_id(value):
    raw = _get_first(value, MATCH_ID_KEYS)
    if isinstance(raw, dict):
        raw = raw.get("id") or raw.get("partida_id")
    return raw


def _looks_like_match(value):
    if not isinstance(value, dict):
        return False
    keys = {str(k).lower() for k in value.keys()}
    has_id = any(k in keys for k in MATCH_ID_KEYS)
    has_home = any(k in keys for k in HOME_KEYS)
    has_away = any(k in keys for k in AWAY_KEYS)
    has_score = any(k in keys for k in SCORE_KEYS)
    has_date = any(k in keys for k in DATE_KEYS)
    # Aceita também ID + apenas um sinal de partida, pois a API pode
    # colocar rodada/data/placar em objetos filhos.
    return has_id and (has_home or has_away or has_score or has_date)


def _walk_matches(value, path="$", out=None, seen_ids=None):
    if out is None:
        out = []
    if seen_ids is None:
        seen_ids = set()

    if isinstance(value, dict):
        if _looks_like_match(value):
            pid = _match_id(value)
            key = str(pid) if pid is not None else path
            if key not in seen_ids:
                seen_ids.add(key)
                item = dict(value)
                item["__path"] = path
                out.append(item)
        for key, child in value.items():
            _walk_matches(child, f"{path}.{key}", out, seen_ids)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk_matches(child, f"{path}[{i}]", out, seen_ids)
    return out


def _find_matches(value):
    return _walk_matches(value)


def _structure_map(value, path="$", rows=None, limit=500):
    """Cria um mapa compacto do JSON sem exibir o conteúdo inteiro."""
    if rows is None:
        rows = []
    if len(rows) >= limit:
        return rows

    if isinstance(value, dict):
        keys = list(value.keys())
        rows.append({
            "Caminho": path,
            "Tipo": "objeto",
            "Qtd. chaves": len(keys),
            "Chaves": ", ".join(str(k) for k in keys[:30]),
        })
        for key, child in value.items():
            _structure_map(child, f"{path}.{key}", rows, limit)
            if len(rows) >= limit:
                break
    elif isinstance(value, list):
        rows.append({
            "Caminho": path,
            "Tipo": "lista",
            "Qtd. chaves": len(value),
            "Chaves": "[lista]",
        })
        # Só percorre uma amostra de até 10 itens por lista.
        for i, child in enumerate(value[:10]):
            _structure_map(child, f"{path}[{i}]", rows, limit)
            if len(rows) >= limit:
                break
    return rows


def _find_named_collections(value, path="$", rows=None):
    if rows is None:
        rows = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {
                "partidas", "partida", "jogos", "jogo", "matches", "fixtures", "eventos"
            }:
                rows.append({
                    "Caminho": f"{path}.{key}",
                    "Tipo": type(child).__name__,
                    "Quantidade": len(child) if isinstance(child, (list, dict)) else "—",
                })
            _find_named_collections(child, f"{path}.{key}", rows)
    elif isinstance(value, list):
        for i, child in enumerate(value[:30]):
            _find_named_collections(child, f"{path}[{i}]", rows)
    return rows


def _value_text(value):
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def render_fase_diagnostic(data):
    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption("Análise do JSON já recebido — esta seção não faz nenhuma requisição à API.")

    if not data:
        st.info("Nenhum detalhe de fase carregado ainda.")
        return

    partidas = _find_matches(data)
    st.metric("Partidas encontradas", len(partidas))

    if partidas:
        rows = []
        for p in partidas:
            rows.append({
                "ID": _value_text(_match_id(p)),
                "Rodada": _value_text(_get_first(p, ROUND_KEYS)),
                "Data": _value_text(_get_first(p, DATE_KEYS)),
                "Mandante": _value_text(_name(_get_first(p, HOME_KEYS))),
                "Visitante": _value_text(_name(_get_first(p, AWAY_KEYS))),
                "Placar": _value_text(_get_first(p, SCORE_KEYS)),
                "Status": _value_text(_get_first(p, STATUS_KEYS)),
                "Caminho no JSON": p.get("__path", "—"),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)

        rodada_counts = {}
        for row in rows:
            rodada_counts[row["Rodada"]] = rodada_counts.get(row["Rodada"], 0) + 1
        st.subheader("📅 Partidas por rodada")
        st.dataframe(
            [{"Rodada": k, "Partidas": v} for k, v in rodada_counts.items()],
            use_container_width=True,
            hide_index=True,
        )

        finished_tokens = {"finalizado", "finalizada", "encerrado", "encerrada", "finished", "completed"}
        finished = sum(str(row["Status"]).strip().lower() in finished_tokens for row in rows)
        if finished:
            st.success(f"🏁 Partidas finalizadas identificadas: {finished}")
        return

    st.warning("Não foi localizada uma partida no retorno da fase.")

    named = _find_named_collections(data)
    if named:
        st.subheader("🔎 Coleções relevantes encontradas no JSON")
        st.dataframe(named, use_container_width=True, hide_index=True)

    with st.expander("🧭 Mapa estrutural do JSON — não faz nova requisição"):
        st.dataframe(
            _structure_map(data),
            use_container_width=True,
            hide_index=True,
        )

    st.info(
        "O retorno recebido não está no formato de partida que o extrator esperava. "
        "O mapa acima mostra exatamente onde estão as estruturas; com ele ajustaremos "
        "o extrator ao formato real da API, sem gastar outra requisição."
    )
