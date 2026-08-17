import streamlit as st


ID_KEYS = ("partida_id", "id_partida", "match_id", "fixture_id", "id")
HOME_KEYS = ("time_mandante", "mandante", "home_team", "home", "time_casa")
AWAY_KEYS = ("time_visitante", "visitante", "away_team", "away", "time_fora")
DATE_KEYS = ("data_realizacao", "data", "date", "data_hora", "horario", "datetime")
ROUND_KEYS = ("rodada", "round", "numero_rodada", "rodada_numero")
STATUS_KEYS = ("status", "situacao", "estado")
SCORE_KEYS = ("placar", "resultado", "score")


def first_value(obj, keys):
    if not isinstance(obj, dict):
        return None
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def display_name(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("nome", "name", "nome_popular", "short_name", "apelido"):
            if value.get(key):
                return value[key]
    return value


def extract_id(obj):
    value = first_value(obj, ID_KEYS)
    if isinstance(value, dict):
        return value.get("id") or value.get("partida_id")
    return value


def is_match(obj):
    if not isinstance(obj, dict):
        return False
    if obj.get("partida_id") is not None:
        return True
    keys = {str(k).lower() for k in obj.keys()}
    has_id = any(k in keys for k in ID_KEYS)
    has_home = any(k in keys for k in HOME_KEYS)
    has_away = any(k in keys for k in AWAY_KEYS)
    return has_id and has_home and has_away


def walk(value, path="$", found=None):
    if found is None:
        found = []
    if isinstance(value, dict):
        if is_match(value):
            item = dict(value)
            item["__path"] = path
            found.append(item)
        for key, child in value.items():
            walk(child, f"{path}.{key}", found)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{path}[{index}]", found)
    return found


def extract_matches(data):
    raw = walk(data)
    unique = {}
    without_id = []
    for item in raw:
        pid = extract_id(item)
        if pid is None:
            without_id.append(item)
        else:
            unique.setdefault(str(pid), item)
    return list(unique.values()) + without_id


def json_structure_summary(data):
    results = []

    def scan(value, path="$", depth=0):
        if depth > 12:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                k = str(key).lower()
                if k in {"partidas", "partida", "jogos", "jogo", "matches", "fixtures", "eventos", "rodadas"}:
                    if isinstance(child, list):
                        results.append((child_path, "lista", len(child)))
                    elif isinstance(child, dict):
                        numeric = [v for kk, v in child.items() if str(kk).isdigit()]
                        results.append((child_path, "objeto", len(child), f"itens_numéricos={len(numeric)}"))
                    else:
                        results.append((child_path, type(child).__name__, 1))
                scan(child, child_path, depth + 1)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scan(child, f"{path}[{i}]", depth + 1)

    scan(data)
    return results


def render_fase_diagnostic(data):
    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption("Análise do JSON já recebido — esta seção não faz nenhuma requisição à API.")
    if not data:
        st.info("Nenhum detalhe de fase carregado ainda.")
        return

    matches = extract_matches(data)
    st.metric("Partidas encontradas", len(matches))

    structure = json_structure_summary(data)
    with st.expander("🧭 Estrutura encontrada no JSON", expanded=not bool(matches)):
        if structure:
            for row in structure:
                st.write(" • ".join(str(x) for x in row))
        else:
            st.write("Nenhuma coleção com nome típico de partidas foi localizada.")

    if not matches:
        st.warning("Ainda não foi localizada uma partida no retorno da fase.")
        return

    rows = []
    for match in matches:
        rows.append({
            "ID": extract_id(match) if extract_id(match) is not None else "—",
            "Rodada": first_value(match, ROUND_KEYS) or "—",
            "Data": first_value(match, DATE_KEYS) or "—",
            "Mandante": display_name(first_value(match, HOME_KEYS)) or "—",
            "Visitante": display_name(first_value(match, AWAY_KEYS)) or "—",
            "Placar": first_value(match, SCORE_KEYS) or "—",
            "Status": first_value(match, STATUS_KEYS) or "—",
            "Caminho no JSON": match.get("__path", "—"),
        })

    st.success(f"✅ {len(rows)} partidas identificadas no JSON da fase.")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    finished_tokens = {"finalizado", "finalizada", "encerrado", "encerrada", "finished", "completed", "terminado", "terminada"}
    finished = [row for row in rows if str(row["Status"]).strip().lower() in finished_tokens]
    if finished:
        st.success(f"🏁 Partidas finalizadas identificadas: {len(finished)}")
        st.code("\n".join(str(row["ID"]) for row in finished[:30]))


# ============================================================
# RAIO-X RESUMIDO DE UMA PARTIDA
# ============================================================
RICH_BLOCKS = {
    "gols": "⚽ Gols",
    "cartoes": "🟨 Cartões",
    "estatisticas": "📊 Estatísticas",
    "escalacoes": "👥 Escalações",
    "substituicoes": "🔄 Substituições",
    "arbitros": "🧑‍⚖️ Árbitros",
    "estadio": "🏟️ Estádio",
    "clima": "🌦️ Clima",
    "cronometro": "⏱️ Cronômetro",
    "transmissao": "📺 Transmissão",
    "disputa_penalti": "🥅 Disputa de pênaltis",
}


def _count_records(value):
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        numeric = [k for k in value.keys() if str(k).isdigit()]
        if numeric:
            return len(numeric)
        return len(value)
    if value is None:
        return 0
    return 1


def _flatten_leaf_keys(value, prefix="", limit=80):
    found = []

    def walk_keys(v, p):
        if len(found) >= limit:
            return
        if isinstance(v, dict):
            for k, child in v.items():
                path = f"{p}.{k}" if p else str(k)
                if isinstance(child, (dict, list)):
                    walk_keys(child, path)
                else:
                    found.append(path)
                    if len(found) >= limit:
                        return
        elif isinstance(v, list) and v:
            walk_keys(v[0], f"{p}[]")

    walk_keys(value, prefix)
    return found


def _format_team(value):
    if isinstance(value, dict):
        name = display_name(value)
        team_id = value.get("time_id") or value.get("id")
        sigla = value.get("sigla")
        bits = [str(x) for x in (name, f"ID {team_id}" if team_id is not None else None, sigla) if x]
        return " — ".join(bits) if bits else str(value)
    return str(value) if value is not None else "—"


def render_partida_raiox(data):
    """Resume blocos ricos de uma partida usando somente o JSON já recebido."""
    if not data:
        return

    partida = data.get("partida", data) if isinstance(data, dict) else data
    if not isinstance(partida, dict):
        st.warning("O retorno da partida não está em formato de objeto.")
        return

    st.header("6. Raio-X resumido da partida")
    st.caption("Resumo automático do JSON já recebido. Esta seção não faz novas requisições à API-Futebol.")

    home = partida.get("time_mandante")
    away = partida.get("time_visitante")
    score_home = partida.get("placar_mandante")
    score_away = partida.get("placar_visitante")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Partida", str(partida.get("partida_id", "—")))
    with c2:
        st.metric("Status", str(partida.get("status", "—")))
    with c3:
        score = "—"
        if score_home is not None or score_away is not None:
            score = f"{score_home if score_home is not None else 0} x {score_away if score_away is not None else 0}"
        st.metric("Placar", score)

    st.write(f"**Casa:** {_format_team(home)}")
    st.write(f"**Fora:** {_format_team(away)}")

    st.subheader("📦 Blocos disponíveis")
    block_rows = []
    for key, label in RICH_BLOCKS.items():
        if key in partida:
            value = partida.get(key)
            block_rows.append({
                "Bloco": label,
                "Chave": key,
                "Registros/itens": _count_records(value),
                "Tipo": type(value).__name__,
            })
    if block_rows:
        st.dataframe(block_rows, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum bloco rico conhecido foi localizado.")

    for key, label in RICH_BLOCKS.items():
        if key not in partida:
            continue
        value = partida[key]
        count = _count_records(value)
        with st.expander(f"{label} — {count} item(ns)"):
            if isinstance(value, dict):
                st.write(f"**{len(value)} chave(s) no bloco.**")
            elif isinstance(value, list):
                st.write(f"**{len(value)} registro(s).**")
            else:
                st.write(f"**Valor:** {value}")

            leafs = _flatten_leaf_keys(value)
            if leafs:
                st.write("**Campos encontrados:**")
                st.code("\n".join(leafs))

            # Exibe apenas uma amostra pequena, evitando despejar centenas de linhas.
            if isinstance(value, list) and value:
                st.write("**Primeiro registro:**")
                st.json(value[0])
            elif isinstance(value, dict):
                st.write("**Estrutura resumida:**")
                preview = {}
                for k, v in list(value.items())[:30]:
                    if isinstance(v, list):
                        preview[k] = f"[{len(v)} itens]"
                    elif isinstance(v, dict):
                        preview[k] = f"{{{len(v)} chaves}}"
                    else:
                        preview[k] = v
                st.json(preview)
