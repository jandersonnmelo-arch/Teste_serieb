import streamlit as st

ID_KEYS = ("partida_id", "id_partida", "match_id", "fixture_id", "id")
HOME_KEYS = ("time_mandante", "mandante", "home_team", "home", "time_casa")
AWAY_KEYS = ("time_visitante", "visitante", "away_team", "away", "time_fora")
DATE_KEYS = ("data_realizacao", "data", "date", "data_hora", "horario", "datetime")
ROUND_KEYS = ("rodada", "round", "numero_rodada", "rodada_numero")
STATUS_KEYS = ("status", "situacao", "estado")

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
    return (
        any(k in keys for k in ID_KEYS)
        and any(k in keys for k in HOME_KEYS)
        and any(k in keys for k in AWAY_KEYS)
    )


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
                scan(child, child_path, depth + 1)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scan(child, f"{path}[{i}]", depth + 1)

    scan(data)
    return results


def render_fase_diagnostic(data):
    st.subheader("5. Diagnóstico das partidas da fase")
    st.caption("Leitura exclusiva do JSON já recebido — nenhuma requisição adicional à API.")
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
            st.write("Nenhuma coleção típica de partidas foi localizada.")

    if not matches:
        st.warning("Ainda não foi localizada uma partida no retorno da fase.")
        return

    rows = []
    for match in matches:
        rows.append({
            "ID": extract_id(match) or "—",
            "Rodada": first_value(match, ROUND_KEYS) or "—",
            "Data": first_value(match, DATE_KEYS) or "—",
            "Mandante": display_name(first_value(match, HOME_KEYS)) or "—",
            "Visitante": display_name(first_value(match, AWAY_KEYS)) or "—",
            "Status": first_value(match, STATUS_KEYS) or "—",
            "Caminho": match.get("__path", "—"),
        })

    st.success(f"✅ {len(rows)} partidas identificadas no JSON da fase.")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    finished_tokens = {"finalizado", "finalizada", "encerrado", "encerrada", "finished", "completed", "terminado", "terminada"}
    finished = [row for row in rows if str(row["Status"]).strip().lower() in finished_tokens]
    if finished:
        st.success(f"🏁 Partidas finalizadas identificadas: {len(finished)}")
        st.code("\n".join(str(row["ID"]) for row in finished[:30]))


def _team_text(value):
    if isinstance(value, dict):
        name = display_name(value) or "—"
        tid = value.get("time_id") or value.get("id")
        sigla = value.get("sigla")
        extra = []
        if tid is not None:
            extra.append(f"ID {tid}")
        if sigla:
            extra.append(str(sigla))
        return f"{name} — " + " — ".join(extra) if extra else str(name)
    return str(value) if value is not None else "—"


def _score_text(partida):
    h = partida.get("placar_mandante")
    a = partida.get("placar_visitante")
    if h is None and a is None:
        placar = partida.get("placar")
        if isinstance(placar, dict):
            h = placar.get("mandante") or placar.get("home")
            a = placar.get("visitante") or placar.get("away")
        elif placar not in (None, ""):
            return str(placar)
    if h is None and a is None:
        return "—"
    return f"{h if h is not None else 0} x {a if a is not None else 0}"


def _side_values(value):
    """Normaliza blocos da API que usam mandante/visitante, casa/fora ou home/away."""
    if not isinstance(value, dict):
        return {"Casa": value, "Fora": None}

    home = None
    away = None
    for key in ("mandante", "casa", "home", "time_mandante", "home_team"):
        if key in value:
            home = value[key]
            break
    for key in ("visitante", "fora", "away", "time_visitante", "away_team"):
        if key in value:
            away = value[key]
            break

    if home is None and away is None:
        # Alguns blocos podem estar indexados por 0/1 ou por IDs.
        numeric = [(k, v) for k, v in value.items() if str(k).isdigit()]
        if len(numeric) >= 2:
            home, away = numeric[0][1], numeric[1][1]

    return {"Casa": home, "Fora": away}


def _record_count(value):
    if value is None:
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        sides = _side_values(value)
        if sides["Casa"] is not None or sides["Fora"] is not None:
            return sum(_record_count(v) for v in sides.values())
        return len(value)
    return 1


def _describe(value):
    if value is None:
        return "não informado"
    if isinstance(value, list):
        return f"{len(value)} registro(s)"
    if isinstance(value, dict):
        return f"{len(value)} chave(s)"
    return "valor"


def _leaf_paths(value, prefix="", limit=120):
    found = []

    def rec(v, p):
        if len(found) >= limit:
            return
        if isinstance(v, dict):
            for k, child in v.items():
                path = f"{p}.{k}" if p else str(k)
                if isinstance(child, (dict, list)):
                    rec(child, path)
                else:
                    found.append(path)
                    if len(found) >= limit:
                        return
        elif isinstance(v, list):
            for idx, child in enumerate(v[:2]):
                rec(child, f"{p}[{idx}]")

    rec(value, prefix)
    return found


def _sample(value):
    if isinstance(value, list):
        return value[:2]
    if isinstance(value, dict):
        preview = {}
        for key, child in list(value.items())[:40]:
            if isinstance(child, list):
                preview[key] = f"[{len(child)} itens]"
            elif isinstance(child, dict):
                preview[key] = f"{{{len(child)} chaves}}"
            else:
                preview[key] = child
        return preview
    return value


def render_partida_raiox(data):
    """Normaliza e diagnostica uma partida usando somente o JSON já recebido."""
    if not data:
        return

    partida = data.get("partida", data) if isinstance(data, dict) else data
    if not isinstance(partida, dict):
        st.warning("O retorno da partida não está em formato de objeto.")
        return

    st.header("6. Raio-X técnico da partida")
    st.caption("JSON já recebido. Nenhuma chamada adicional à API-Futebol é realizada nesta etapa.")

    # Cabeçalho único: evita a duplicação Casa/Fora que havia no laboratório.
    home = partida.get("time_mandante") or partida.get("mandante")
    away = partida.get("time_visitante") or partida.get("visitante")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Partida", str(partida.get("partida_id", "—")))
    c2.metric("Status", str(partida.get("status", "—")))
    c3.metric("Placar", _score_text(partida))
    c4.metric("Rodada", str(partida.get("rodada", "—")))
    st.write(f"**Casa:** {_team_text(home)}")
    st.write(f"**Fora:** {_team_text(away)}")

    # Catálogo dos blocos reais recebidos.
    st.subheader("📦 Catálogo de dados recebidos")
    catalog = []
    for key, label in RICH_BLOCKS.items():
        if key in partida:
            value = partida[key]
            sides = _side_values(value)
            catalog.append({
                "Bloco": label,
                "Chave": key,
                "Casa": _describe(sides["Casa"]),
                "Fora": _describe(sides["Fora"]),
                "Total": _record_count(value),
            })
    if catalog:
        st.dataframe(catalog, use_container_width=True, hide_index=True)

    # Estatísticas: mostra explicitamente Casa/Fora e os campos internos.
    if "estatisticas" in partida:
        st.subheader("📊 Estatísticas normalizadas")
        sides = _side_values(partida["estatisticas"])
        stat_rows = []
        for side, value in sides.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        stat = item.get("estatistica") or item.get("nome") or item.get("name") or item.get("tipo") or item.get("campo")
                        val = item.get("valor", item.get("value", item.get("resultado")))
                        stat_rows.append({"Lado": side, "Métrica": stat or "—", "Valor": val if val is not None else item})
            elif isinstance(value, dict):
                for key, val in value.items():
                    stat_rows.append({"Lado": side, "Métrica": key, "Valor": val})
        if stat_rows:
            st.dataframe(stat_rows, use_container_width=True, hide_index=True)
        else:
            st.info("O bloco de estatísticas existe, mas a estrutura interna ainda precisa de um mapeamento específico.")

    # Gols, cartões e substituições: contagem por lado, sem assumir que o bloco seja uma lista.
    for key, label in (("gols", "⚽ Gols"), ("cartoes", "🟨 Cartões"), ("substituicoes", "🔄 Substituições"), ("escalacoes", "👥 Escalações")):
        if key not in partida:
            continue
        st.subheader(label)
        sides = _side_values(partida[key])
        left, right = st.columns(2)
        left.metric("Casa", _record_count(sides["Casa"]))
        right.metric("Fora", _record_count(sides["Fora"]))
        with st.expander(f"🔎 Estrutura de {key}"):
            st.write("**Campos encontrados:**")
            paths = _leaf_paths(partida[key])
            st.code("\n".join(paths) if paths else "Nenhum campo folha identificado.")
            st.write("**Amostra:**")
            st.json(_sample(partida[key]))

    # Outros blocos são preservados para futura integração, sem despejar o JSON inteiro.
    others = [k for k in RICH_BLOCKS if k in partida and k not in {"estatisticas", "gols", "cartoes", "substituicoes", "escalacoes"}]
    if others:
        st.subheader("🧩 Outros dados disponíveis")
        for key in others:
            label = RICH_BLOCKS[key]
            value = partida[key]
            with st.expander(f"{label} — {_describe(value)}"):
                st.write("**Campos encontrados:**")
                paths = _leaf_paths(value)
                st.code("\n".join(paths) if paths else "Nenhum campo folha identificado.")
                st.json(_sample(value))

    with st.expander("🧾 Campos do objeto principal"):
        st.code("\n".join(sorted(partida.keys())))
