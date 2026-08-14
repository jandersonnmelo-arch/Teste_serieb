
import requests
import streamlit as st

# ============================================================
# LABORATÓRIO API FUTEBOL — SÉRIE B
# ============================================================
# Independente do Main.py.
# Não altera o cache do Premium e não consulta API-Sports.
#
# Configure no Streamlit Secrets:
#
# [api_futebol]
# token = "SUA_CHAVE"
#
# Base documentada:
# https://api.api-futebol.com.br/v1
# Autenticação:
# Authorization: Bearer TOKEN
# ============================================================

BASE_URL = "https://api.api-futebol.com.br/v1"

st.set_page_config(
    page_title="Laboratório API Futebol",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Laboratório API Futebol")
st.caption("Série B — teste independente antes da integração ao Premium")

def get_token():
    try:
        if "api_futebol" in st.secrets:
            return st.secrets["api_futebol"].get("token")
    except Exception:
        pass

    try:
        return st.secrets.get("API_FUTEBOL_TOKEN")
    except Exception:
        return None

TOKEN = get_token()

def api_get(path, params=None):
    if not TOKEN:
        return None, "API_FUTEBOL_TOKEN não configurado nos Secrets."

    try:
        r = requests.get(
            BASE_URL + path,
            params=params or {},
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
            },
            timeout=20,
        )

        if r.status_code == 401:
            return None, "HTTP 401 — token inválido ou não autorizado."
        if r.status_code == 403:
            return None, "HTTP 403 — acesso negado/plano não liberou este recurso."
        if r.status_code == 429:
            return None, "HTTP 429 — limite de requisições atingido."
        if not r.ok:
            return None, f"HTTP {r.status_code}: {r.text[:800]}"

        try:
            return r.json(), None
        except Exception:
            return None, "Resposta não-JSON."

    except Exception as e:
        return None, str(e)

def first_list(data, keys):
    """Extrai listas de respostas em formatos diferentes da API."""
    if not isinstance(data, dict):
        return []

    # Formatos tradicionais: {"data": [...]} / {"results": [...]} etc.
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value

    # A API Futebol pode devolver coleções indexadas por chave numérica:
    # {
    #   "0": {...},
    #   "1": {...},
    #   "9": {
    #       "campeonato_id": 14,
    #       "nome": "Campeonato Brasileiro Série B",
    #       ...
    #   }
    # }
    numeric_items = []
    for key, value in data.items():
        try:
            int(str(key))
        except (TypeError, ValueError):
            continue

        if isinstance(value, dict):
            numeric_items.append((int(str(key)), value))

    if numeric_items:
        numeric_items.sort(key=lambda item: item[0])
        return [value for _, value in numeric_items]

    # Alguns retornos podem ser um único objeto de campeonato/fase.
    if any(
        k in data
        for k in (
            "campeonato_id",
            "edicao_id",
            "fase_id",
            "partida_id",
        )
    ):
        return [data]

    return []

def show_raw(label, data):
    with st.expander(label):
        st.json(data if data is not None else {})


def walk_json(value, path="$", rows=None):
    """Percorre recursivamente o JSON e registra todos os caminhos."""
    if rows is None:
        rows = []

    if isinstance(value, dict):
        if not value:
            rows.append({
                "Caminho": path,
                "Tipo": "objeto vazio",
                "Valor/Quantidade": "0 campos",
            })
        else:
            rows.append({
                "Caminho": path,
                "Tipo": "objeto",
                "Valor/Quantidade": f"{len(value)} campos",
            })
            for key, child in value.items():
                walk_json(child, f"{path}.{key}", rows)

    elif isinstance(value, list):
        rows.append({
            "Caminho": path,
            "Tipo": "lista",
            "Valor/Quantidade": f"{len(value)} item(ns)",
        })
        # Mostra a estrutura do primeiro item sem gerar uma tabela gigantesca.
        if value:
            walk_json(value[0], f"{path}[0]", rows)

    else:
        preview = str(value)
        if len(preview) > 160:
            preview = preview[:157] + "..."
        rows.append({
            "Caminho": path,
            "Tipo": type(value).__name__,
            "Valor/Quantidade": preview,
        })

    return rows


def find_keys_deep(value, wanted=None, path="$", found=None):
    """Procura campos relevantes em qualquer nível do JSON."""
    if wanted is None:
        wanted = {
            "jogador", "jogadores", "atleta", "atletas", "player", "players",
            "escalacao", "escalacoes", "titular", "titulares", "reserva", "reservas",
            "evento", "eventos", "gol", "gols", "cartao", "cartoes",
            "substituicao", "substituicoes", "estatistica", "estatisticas",
            "finalizacao", "finalizacoes", "chutes", "shots",
            "passes", "desarmes", "posse", "escanteios", "corners",
            "impedimentos", "faltas", "goleiro", "defesas", "saves",
            "xg", "expected_goals", "placar", "resultado",
        }

    if found is None:
        found = []

    if isinstance(value, dict):
        for key, child in value.items():
            key_norm = str(key).strip().lower()
            if key_norm in wanted:
                found.append({
                    "Campo": str(key),
                    "Caminho": path,
                    "Tipo": type(child).__name__,
                    "Quantidade": len(child) if isinstance(child, (list, dict)) else "—",
                })
            find_keys_deep(child, wanted, f"{path}.{key}", found)

    elif isinstance(value, list):
        for i, child in enumerate(value[:5]):
            find_keys_deep(child, wanted, f"{path}[{i}]", found)

    return found


def extract_player_candidates(value, path="$", rows=None):
    """Localiza objetos que parecem representar jogadores/atletas."""
    if rows is None:
        rows = []

    if isinstance(value, dict):
        keys = {str(k).lower() for k in value.keys()}
        player_markers = {
            "jogador", "atleta", "player", "jogador_id",
            "atleta_id", "player_id", "nome_jogador", "nome_atleta"
        }

        if keys.intersection(player_markers) or (
            "nome" in keys and (
                "numero" in keys or "camisa" in keys or
                "posicao" in keys or "posição" in keys
            )
        ):
            rows.append({
                "Caminho": path,
                "Campos": ", ".join(map(str, value.keys())),
                "Nome possível": (
                    value.get("nome")
                    or value.get("nome_jogador")
                    or value.get("nome_atleta")
                    or value.get("player")
                    or value.get("jogador")
                    or value.get("atleta")
                    or "—"
                ),
            })

        for key, child in value.items():
            extract_player_candidates(child, f"{path}.{key}", rows)

    elif isinstance(value, list):
        for i, child in enumerate(value[:100]):
            extract_player_candidates(child, f"{path}[{i}]", rows)

    return rows


# ------------------------------------------------------------
# 0 — STATUS DO TOKEN
# ------------------------------------------------------------
st.header("0. Conexão")

if not TOKEN:
    st.error(
        "Configure a chave nos Secrets do Streamlit antes de testar. "
        "A chave não precisa ser colocada neste arquivo."
    )
else:
    st.success("🔐 Token encontrado nos Secrets.")

# ------------------------------------------------------------
# 1 — CAMPEONATOS
# ------------------------------------------------------------
st.header("1. Campeonatos liberados")

if st.button("🏆 Listar campeonatos", type="primary"):
    data, error = api_get("/campeonatos")

    if error:
        st.error(error)
    else:
        st.session_state["campeonatos"] = data
        comps = first_list(data, ["campeonatos", "data", "results"])

        st.success(f"Resposta recebida. {len(comps)} campeonato(s) listado(s).")

        if comps:
            rows = []
            for c in comps:
                rows.append({
                    "ID": c.get("id"),
                    "Nome": c.get("nome") or c.get("name"),
                    "Temporada": c.get("temporada") or c.get("season"),
                    "País": c.get("pais") or c.get("country"),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

        show_raw("🔍 JSON — campeonatos", data)

# ------------------------------------------------------------
# 2 — ID DA SÉRIE B
# ------------------------------------------------------------
st.header("2. Identificar Série B")

st.caption(
    "A API retornou os campeonatos como objetos indexados por chaves numéricas; "
    "o laboratório agora reconhece esse formato automaticamente."
)

campeonatos = st.session_state.get("campeonatos")
comps = first_list(campeonatos, ["campeonatos", "data", "results"])

serie_b_ids = []
if comps:
    for c in comps:
        text = " ".join(
            str(c.get(k) or "")
            for k in ["nome", "name", "slug", "descricao", "description"]
        ).lower()
        if "série b" in text or "serie b" in text:
            campeonato_id = (
                c.get("campeonato_id")
                or c.get("id")
            )

            edicao_atual = c.get("edicao_atual") or {}
            edicao_id = (
                edicao_atual.get("edicao_id")
                if isinstance(edicao_atual, dict)
                else None
            )

            serie_b_ids.append(
                (
                    str(campeonato_id) if campeonato_id is not None else "",
                    c.get("nome") or c.get("name"),
                    str(edicao_id) if edicao_id is not None else "",
                )
            )

if serie_b_ids:
    st.success("Série B encontrada na lista.")

    serie_b_rows = []
    for cid, nome, eid in serie_b_ids:
        serie_b_rows.append({
            "Campeonato ID": cid,
            "Nome": nome,
            "Edição 2026 ID": eid or "—",
        })

    st.dataframe(
        serie_b_rows,
        use_container_width=True,
        hide_index=True,
    )

manual_championship_id = st.text_input(
    "ID do campeonato Série B (se necessário)",
    value=serie_b_ids[0][0] if serie_b_ids else "",
)

# ------------------------------------------------------------
# 3 — FASES
# ------------------------------------------------------------
st.header("3. Fases da Série B")

if st.button("📚 Carregar fases"):
    cid = manual_championship_id.strip()

    if not cid:
        st.warning("Informe o ID da Série B.")
    else:
        data, error = api_get(f"/campeonatos/{cid}/fases")

        if error:
            st.error(error)
        else:
            st.session_state["fases"] = data
            phases = first_list(data, ["fases", "data", "results"])

            st.success(f"Resposta recebida. {len(phases)} fase(s).")

            if phases:
                rows = []
                for p in phases:
                    rows.append({
                        "ID": p.get("id"),
                        "Nome": p.get("nome") or p.get("name"),
                        "Status": p.get("status"),
                    })
                st.dataframe(rows, use_container_width=True, hide_index=True)

            show_raw("🔍 JSON — fases", data)

# ------------------------------------------------------------
# 4 — DETALHE DE UMA FASE
# ------------------------------------------------------------
st.header("4. Detalhe da fase")

fases_data = st.session_state.get("fases")
phases = first_list(fases_data, ["fases", "data", "results"])

phase_id = st.text_input(
    "ID da fase",
    value=str(phases[0].get("id")) if phases and phases[0].get("id") else "",
)

if st.button("📋 Consultar fase"):
    cid = manual_championship_id.strip()

    if not cid or not phase_id.strip():
        st.warning("Informe campeonato_id e fase_id.")
    else:
        data, error = api_get(
            f"/campeonatos/{cid}/fases/{phase_id.strip()}"
        )

        if error:
            st.error(error)
        else:
            st.session_state["fase_detail"] = data
            st.success("✅ Fase carregada.")
            show_raw("🔍 JSON — detalhe da fase", data)

# ------------------------------------------------------------
# 5 — PARTIDA
# ------------------------------------------------------------
st.header("5. Enriquecimento de uma partida")

st.write(
    "Cole o ID de uma partida FINALIZADA da Série B. "
    "O endpoint de partida é o recurso mais rico da API."
)

fixture_id = st.text_input(
    "ID da partida",
    value="",
    placeholder="Ex.: 23447",
)

if st.button("🔬 Testar partida"):
    fid = fixture_id.strip()

    if not fid:
        st.warning("Informe o ID da partida.")
        st.stop()

    data, error = api_get(f"/partidas/{fid}")

    if error:
        st.error(error)
    else:
        st.session_state["partida"] = data

        # Tentativa de localizar o objeto principal.
        partida = data.get("partida", data)

        st.success("✅ Detalhes da partida recebidos.")

        # -------------------------
        # Resumo
        # -------------------------
        st.subheader("⚽ Resumo")

        home = (
            partida.get("time_mandante")
            or partida.get("mandante")
            or partida.get("home_team")
            or partida.get("home")
        )
        away = (
            partida.get("time_visitante")
            or partida.get("visitante")
            or partida.get("away_team")
            or partida.get("away")
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.write("**Casa**")
            st.write(home if isinstance(home, str) else str(home or "—"))
        with c2:
            st.write("**Fora**")
            st.write(away if isinstance(away, str) else str(away or "—"))
        with c3:
            st.write("**ID**")
            st.write(fid)

        # -------------------------
        # Descoberta automática
        # -------------------------
        st.subheader("🧩 Estrutura encontrada")

        if isinstance(partida, dict):
            keys = sorted(partida.keys())
            st.write(
                f"**{len(keys)} campos no objeto principal da partida:**"
            )
            st.code("\n".join(keys))

        # -------------------------
        # Cobertura
        # -------------------------
        st.subheader("📊 Mapa de cobertura")

        aliases = {
            "Placar": ["placar", "resultado", "score"],
            "Estatísticas": ["estatisticas", "statistics", "stats"],
            "Escalações": ["escalacoes", "escalações", "lineups"],
            "Titulares": ["titulares", "starters"],
            "Reservas": ["reservas", "substitutes"],
            "Eventos": ["eventos", "events", "gols", "cartoes", "substituicoes"],
            "Gols": ["gols", "goals"],
            "Cartões": ["cartoes", "cartões", "cards"],
            "Substituições": ["substituicoes", "substituições", "substitutions"],
            "Jogadores": ["jogadores", "players", "atletas"],
            "Finalizações": ["finalizacoes", "finalizações", "shots"],
            "Passes": ["passes"],
            "Desarmes": ["desarmes", "tackles"],
            "Posse": ["posse", "possession"],
            "Escanteios": ["escanteios", "corners"],
            "Impedimentos": ["impedimentos", "offsides"],
            "Faltas": ["faltas", "fouls"],
            "Goleiros": ["goleiros", "goalkeepers", "defesas", "saves"],
            "xG": ["xg", "expected_goals", "gols_esperados"],
        }

        rows = []
        lower_keys = {
            str(k).lower(): k
            for k in (partida.keys() if isinstance(partida, dict) else [])
        }

        for label, possible in aliases.items():
            found = []
            for p in possible:
                if p.lower() in lower_keys:
                    found.append(lower_keys[p.lower()])

            rows.append({
                "Dado": label,
                "Encontrado": "✅" if found else "❌",
                "Campo(s)": ", ".join(map(str, found)) if found else "—",
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)

        # -------------------------
        # JSON completo
        # -------------------------
        show_raw("🔍 JSON bruto — partida", data)

        # -------------------------
        # RAIO-X RECURSIVO — sem nova chamada à API
        # -------------------------
        st.subheader("🧬 Raio-X completo do retorno")

        st.caption(
            "Esta seção analisa o mesmo JSON já recebido. "
            "Ela não faz nenhuma chamada adicional à API."
        )

        deep_rows = walk_json(data)
        st.metric("Nós/caminhos inspecionados", len(deep_rows))

        with st.expander("📂 Todos os caminhos encontrados"):
            st.dataframe(
                deep_rows,
                use_container_width=True,
                hide_index=True,
            )

        st.subheader("🎯 Campos relevantes encontrados em qualquer nível")

        relevant_rows = find_keys_deep(data)

        if relevant_rows:
            # Remove duplicidades exatas para deixar o diagnóstico legível.
            seen = set()
            unique_rows = []
            for row in relevant_rows:
                key = (
                    row["Campo"],
                    row["Caminho"],
                    row["Tipo"],
                    str(row["Quantidade"]),
                )
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(row)

            st.success(
                f"Encontrados {len(unique_rows)} campo(s)/estrutura(s) "
                "potencialmente úteis."
            )
            st.dataframe(
                unique_rows,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "Nenhum dos campos relevantes foi encontrado pelo diagnóstico "
                "automático."
            )

        st.subheader("👤 Candidatos a jogadores/atletas")

        player_rows = extract_player_candidates(data)

        if player_rows:
            # Deduplicação por caminho.
            seen_paths = set()
            unique_players = []
            for row in player_rows:
                if row["Caminho"] not in seen_paths:
                    seen_paths.add(row["Caminho"])
                    unique_players.append(row)

            st.success(
                f"{len(unique_players)} estrutura(s) parecem representar "
                "jogadores/atletas."
            )
            st.dataframe(
                unique_players,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning(
                "Nenhuma estrutura claramente identificável como jogador/atleta "
                "foi encontrada neste retorno."
            )

        st.info(
            "Importante: este teste mede o que a API devolveu nesta partida "
            "específica. Um campo ausente aqui não significa necessariamente "
            "que a API nunca forneça esse campo em outras partidas."
        )

# ------------------------------------------------------------
# 6 — CHECKLIST FINAL
# ------------------------------------------------------------
st.divider()
st.header("6. Checklist para integração")

st.write(
    """
Depois do teste, vamos decidir objetivamente:

1. Qual é o ID da Série B 2026.
2. Qual é o ID da fase.
3. Como listar as partidas.
4. Qual é o ID único de cada partida.
5. Quais campos de estatística existem.
6. Se escalações e jogadores estão completos.
7. Se eventos estão completos.
8. Quais métricas podem alimentar o histórico dos times.
9. Quais métricas podem alimentar o histórico dos jogadores.
10. Quais campos podem ser usados para validação cruzada com outras fontes.
"""
)

st.info(
    "Não coloque sua API Key neste arquivo nem no chat. "
    "Use o Secrets do Streamlit."
)
