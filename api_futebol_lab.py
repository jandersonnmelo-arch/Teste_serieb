import requests
import streamlit as st

from diagnostico_fase import render_fase_diagnostic, render_partida_raiox

BASE_URL = "https://api.api-futebol.com.br/v1"

st.set_page_config(page_title="Laboratório API Futebol", page_icon="🧪", layout="wide")
st.title("🧪 Laboratório API Futebol")
st.caption("Série B — teste independente antes da integração ao Premium")


def get_token_candidates():
    """Lê os formatos de Secret sem transformar um bloco TOML em string."""
    candidates = []

    try:
        if "api_futebol" in st.secrets:
            value = st.secrets["api_futebol"]

            # st.secrets pode devolver um objeto de mapeamento que não é
            # exatamente um dict Python. O teste correto é possuir `.get`.
            if hasattr(value, "get"):
                token = value.get("token")
                if token:
                    candidates.append((str(token), "api_futebol.token"))
            elif value:
                candidates.append((str(value), "api_futebol"))
    except Exception:
        pass

    try:
        token = st.secrets.get("API_FUTEBOL_TOKEN")
        if token:
            candidates.append((str(token), "API_FUTEBOL_TOKEN"))
    except Exception:
        pass

    # Remove duplicatas sem alterar o conteúdo do token.
    unique = []
    seen = set()
    for token, source in candidates:
        if token not in seen:
            unique.append((token, source))
            seen.add(token)
    return unique


TOKEN_CANDIDATES = get_token_candidates()
TOKEN = TOKEN_CANDIDATES[0][0] if TOKEN_CANDIDATES else None
TOKEN_SOURCE = TOKEN_CANDIDATES[0][1] if TOKEN_CANDIDATES else None


def masked_token(token):
    """Exibe apenas os últimos 4 caracteres para diagnóstico seguro."""
    if not token:
        return "não configurado"
    text = str(token)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * max(8, len(text) - 4) + text[-4:]


def api_get(path, params=None):
    if not TOKEN_CANDIDATES:
        return None, "API-Futebol: token não configurado nos Secrets."

    last_401 = None

    for token, source in TOKEN_CANDIDATES:
        try:
            response = requests.get(
                BASE_URL + path,
                params=params or {},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                timeout=20,
            )

            if response.status_code == 401:
                last_401 = source
                # Se houver dois formatos de Secret configurados, tenta o
                # próximo sem alterar nenhum deles.
                continue

            if response.status_code == 403:
                return None, "HTTP 403 — acesso negado/plano não liberou este recurso."
            if response.status_code == 429:
                return None, "HTTP 429 — limite de requisições atingido."
            if not response.ok:
                return None, f"HTTP {response.status_code}: {response.text[:800]}"

            try:
                return response.json(), None
            except Exception:
                return None, "Resposta não-JSON."

        except Exception as exc:
            return None, str(exc)

    return None, (
        "HTTP 401 — a API recusou o(s) token(s) configurado(s). "
        f"Última origem testada: {last_401 or 'desconhecida'}. "
        "A aplicação preservou o token exatamente como está nos Secrets."
    )


def first_list(data, keys):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        numeric_values = [
            value
            for key, value in data.items()
            if str(key).isdigit() and isinstance(value, dict)
        ]
        if numeric_values:
            return numeric_values
    return []


def show_raw(title, data):
    with st.expander(title):
        st.json(data)


st.header("0. Conexão")
if not TOKEN_CANDIDATES:
    st.error("Configure a chave nos Secrets do Streamlit antes de testar. A chave não precisa ser colocada neste arquivo.")
else:
    st.success(f"🔐 Token encontrado nos Secrets ({TOKEN_SOURCE}).")
    st.caption(f"Diagnóstico: {len(TOKEN_CANDIDATES)} token(s) encontrado(s); valor oculto: {masked_token(TOKEN)}")


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
                    "ID": c.get("id") or c.get("campeonato_id"),
                    "Nome": c.get("nome") or c.get("name"),
                    "Temporada": c.get("temporada") or c.get("season"),
                    "País": c.get("pais") or c.get("country"),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        show_raw("🔍 JSON — campeonatos", data)


st.header("2. Identificar Série B")
st.caption("A API pode retornar campeonatos como objetos indexados por chaves numéricas; o laboratório reconhece esse formato automaticamente.")

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
            campeonato_id = c.get("campeonato_id") or c.get("id")
            edicao_atual = c.get("edicao_atual") or {}
            edicao_id = edicao_atual.get("edicao_id") if isinstance(edicao_atual, dict) else None
            serie_b_ids.append((
                str(campeonato_id) if campeonato_id is not None else "",
                c.get("nome") or c.get("name"),
                str(edicao_id) if edicao_id is not None else "",
            ))

if serie_b_ids:
    st.success("Série B encontrada na lista.")
    st.dataframe([
        {"Campeonato ID": cid, "Nome": nome, "Edição 2026 ID": eid or "—"}
        for cid, nome, eid in serie_b_ids
    ], use_container_width=True, hide_index=True)

manual_championship_id = st.text_input(
    "ID do campeonato Série B (se necessário)",
    value=serie_b_ids[0][0] if serie_b_ids else "",
)


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
                st.dataframe([
                    {
                        "ID": p.get("id") or p.get("fase_id"),
                        "Nome": p.get("nome") or p.get("name"),
                        "Status": p.get("status"),
                    }
                    for p in phases
                ], use_container_width=True, hide_index=True)
            show_raw("🔍 JSON — fases", data)


st.header("4. Detalhe da fase")
fases_data = st.session_state.get("fases")
phases = first_list(fases_data, ["fases", "data", "results"])
phase_id = st.text_input(
    "ID da fase",
    value=str(phases[0].get("fase_id") or phases[0].get("id")) if phases else "",
)

if st.button("📋 Consultar fase"):
    cid = manual_championship_id.strip()
    pid = phase_id.strip()
    if not cid or not pid:
        st.warning("Informe campeonato_id e fase_id.")
    else:
        data, error = api_get(f"/campeonatos/{cid}/fases/{pid}")
        if error:
            st.error(error)
        else:
            st.session_state["fase_detail"] = data
            st.success("✅ Fase carregada.")
            show_raw("🔍 JSON — detalhe da fase", data)


st.header("4B. Diagnóstico das partidas da fase")
st.caption("Usa somente o JSON da fase já carregado. Esta seção não faz nenhuma requisição adicional à API-Futebol.")
fase_detail = st.session_state.get("fase_detail")
if fase_detail is None:
    st.info("Primeiro consulte a fase acima. Depois o diagnóstico aparecerá automaticamente aqui.")
else:
    render_fase_diagnostic(fase_detail)


st.header("5. Enriquecimento de uma partida")
st.write("Cole o ID de uma partida FINALIZADA da Série B. O endpoint de partida é o recurso mais rico da API.")
fixture_id = st.text_input("ID da partida", value="", placeholder="Ex.: 30141")

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
        st.success("✅ Detalhes da partida recebidos.")
        st.info("A partida foi armazenada na sessão. O raio-X abaixo não fará novas chamadas à API.")
        show_raw("🔍 JSON bruto — detalhe completo da partida", data)


partida_existente = st.session_state.get("partida")
if partida_existente:
    render_partida_raiox(partida_existente)
