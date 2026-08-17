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
    """Formato observado no retorno da API-Futebol: objeto com partida_id e times."""
    if not isinstance(obj, dict):
        return False

    # A API-Futebol da fase 1112 entrega as partidas como objetos indexados
    # dentro de `partidas`, cada uma contendo partida_id, time_mandante e
    # time_visitante. O ID sozinho já é suficiente para reconhecer a partida.
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
    """Extrai partidas do JSON completo, inclusive partidas indexadas por 0,1,2..."""
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
    """Mostra somente coleções relevantes para depuração, sem nova chamada à API."""
    results = []

    def scan(value, path="$", depth=0):
        if depth > 12:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}"
                k = str(key).lower()
                if k in {
                    "partidas", "partida", "jogos", "jogo", "matches",
                    "fixtures", "eventos", "rodadas"
                }:
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
        st.info(
            "O diagnóstico percorreu o JSON inteiro. Se a resposta exibida acima "
            "contiver `partidas` com itens, o próximo ajuste será feito diretamente nessa estrutura."
        )
        return

    rows = []
    for match in matches:
        pid = extract_id(match)
        home = display_name(first_value(match, HOME_KEYS))
        away = display_name(first_value(match, AWAY_KEYS))
        date = first_value(match, DATE_KEYS)
        round_value = first_value(match, ROUND_KEYS)
        status = first_value(match, STATUS_KEYS)
        score = first_value(match, SCORE_KEYS)

        rows.append({
            "ID": pid if pid is not None else "—",
            "Rodada": round_value if round_value is not None else "—",
            "Data": date if date is not None else "—",
            "Mandante": home if home is not None else "—",
            "Visitante": away if away is not None else "—",
            "Placar": score if score is not None else "—",
            "Status": status if status is not None else "—",
            "Caminho no JSON": match.get("__path", "—"),
        })

    st.success(f"✅ {len(rows)} partidas identificadas no JSON da fase.")
    st.dataframe(rows, use_container_width=True, hide_index=True)

    finished_tokens = {
        "finalizado", "finalizada", "encerrado", "encerrada",
        "finished", "completed", "terminado", "terminada"
    }
    finished = [
        row for row in rows
        if str(row["Status"]).strip().lower() in finished_tokens
    ]

    if finished:
        st.success(f"🏁 Partidas finalizadas identificadas: {len(finished)}")
        st.caption("IDs finalizados encontrados:")
        st.code("\n".join(str(row["ID"]) for row in finished[:30]))
