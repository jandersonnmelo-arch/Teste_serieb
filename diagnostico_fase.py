import re
import streamlit as st


MATCH_ID_KEYS = (
    "partida_id", "id_partida", "id", "match_id", "fixture_id"
)

HOME_KEYS = (
    "time_mandante", "mandante", "home_team", "home", "time_casa"
)

AWAY_KEYS = (
    "time_visitante", "visitante", "away_team", "away", "time_fora"
)

ROUND_KEYS = (
    "rodada", "round", "numero_rodada", "rodada_numero"
)

DATE_KEYS = (
    "data", "date", "data_hora", "horario", "datetime"
)

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


def _looks_like_match(value):
    """Reconhece uma partida mesmo quando ela está dentro de um dict indexado."""
    if not isinstance(value, dict):
        return False

    keys = {str(k).lower() for k in value.keys()}

    has_id = any(k in keys for k in MATCH_ID_KEYS)
    has_home = any(k in keys for k in HOME_KEYS)
    has_away = any(k in keys for k in AWAY_KEYS)
    has_score = any(k in keys for k in SCORE_KEYS)
    has_date = any(k in keys for k in DATE_KEYS)

    # A API pode variar os campos. Dois sinais fortes já bastam.
    strong = int(has_home) + int(has_away) + int(has_score) + int(has_date)
    return has_id and strong >= 2


def _match_id(value):
    raw = _get_first(value, MATCH_ID_KEYS)
    if isinstance(raw, dict):
        raw = raw.get("id") or raw.get("partida_id")
    return raw


def _walk_matches(value, path="$", out=None, seen_paths=None):
    """Percorre listas e dicionários, inclusive coleções indexadas por '0','1',..."""
    if out is None:
        out = []
    if seen_paths is None:
        seen_paths = set()

    if isinstance(value, dict):
        if _looks_like_match(value):
            pid = _match_id(value)
            fingerprint = (str(pid), path) if pid is not None else (None, path)
            if fingerprint not in seen_paths:
                seen_paths.add(fingerprint)
                item = dict(value)
                item["__path"] = path
                out.append(item)
            # Ainda percorremos os filhos para encontrar estruturas adicionais.

        for key, child in value.items():
            child_path = f"{path}.{key}"
            _walk_matches(child, child_path, out, seen_paths)

    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk_matches(child, f"{path}[{i}]", out, seen_paths)

    return out


def _find_matches(value):
    matches = _walk_matches(value)

    # Deduplicação final por ID, mantendo a primeira ocorrência.
    unique = {}
    anonymous = []
    for item in matches:
        pid = _match_id(item)
        if pid is None:
            anonymous.append(item)
        else:
            unique.setdefault(str(pid), item)
    return list(unique.values()) + anonymous


def _value_text(value):
    if value is None:
        return "—"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)


def render_fase_diagnostic(data):
    if not data:
        st.info("Nenhum detalhe de fase carregado ainda.")
        return

    partidas = _find_matches(data)

    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption(
        "Análise do JSON já recebido — esta seção não faz nenhuma requisição à API."
    )
    st.metric("Partidas encontradas", len(partidas))

    if not partidas:
        st.warning("Não foi localizada uma partida no retorno da fase.")
        st.info(
            "O extrator agora também percorre objetos indexados numericamente. "
            "Se continuar em 0, será necessário inspecionar o formato exato do JSON recebido."
        )
        return

    rows = []
    for p in partidas:
        home = _name(_get_first(p, HOME_KEYS))
        away = _name(_get_first(p, AWAY_KEYS))
        score = _get_first(p, SCORE_KEYS)
        rodada = _get_first(p, ROUND_KEYS)
        data_jogo = _get_first(p, DATE_KEYS)
        status = _get_first(p, STATUS_KEYS)
        pid = _match_id(p)

        rows.append({
            "ID": _value_text(pid),
            "Rodada": _value_text(rodada),
            "Data": _value_text(data_jogo),
            "Mandante": _value_text(home),
            "Visitante": _value_text(away),
            "Placar": _value_text(score),
            "Status": _value_text(status),
            "Caminho no JSON": p.get("__path", "—"),
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)

    rodada_counts = {}
    for row in rows:
        key = row["Rodada"]
        rodada_counts[key] = rodada_counts.get(key, 0) + 1

    st.subheader("📅 Partidas por rodada")
    st.dataframe(
        [
            {"Rodada": rodada, "Partidas": quantidade}
            for rodada, quantidade in sorted(
                rodada_counts.items(),
                key=lambda item: str(item[0]),
            )
        ],
        use_container_width=True,
        hide_index=True,
    )

    finished_tokens = {
        "finalizado", "finalizada", "encerrado", "encerrada", "finished", "completed"
    }
    finished = sum(
        str(row["Status"]).strip().lower() in finished_tokens
        for row in rows
    )
    if finished:
        st.success(f"🏁 Partidas finalizadas identificadas: {finished}")
