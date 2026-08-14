
import base64
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import streamlit as st


# ============================================================
# LABORATÓRIO API FUTEBOL — SÉRIE B
# ============================================================
# Projeto INDEPENDENTE do Premium Football Analytics.
#
# Estrutura esperada no repositório:
#
#   api_futebol_lab.py
#   dados_app/
#       cache.json
#
# Objetivo desta fase:
#   1. Descobrir campeonatos automaticamente
#   2. Localizar Campeonato Brasileiro Série B
#   3. Descobrir edição/temporada atual
#   4. Descobrir fase atual
#   5. Descobrir rodada atual
#   6. Obter partidas pela fase
#   7. Salvar tudo no cache
#   8. Na segunda consulta, reutilizar o cache sem chamar a API
#   9. Só depois avançar para o detalhe/enriquecimento das partidas
#
# API:
#   https://api.api-futebol.com.br/v1
#
# Secrets aceitos:
#
# [api_futebol]
# token = "SUA_CHAVE"
#
# Opcional para persistência REAL no GitHub:
#
# GITHUB_TOKEN = "..."
# GITHUB_REPO = "usuario/repositorio"
# GITHUB_BRANCH = "main"
#
# O GitHub é opcional: sem esses secrets, o cache funciona localmente
# durante a execução do app. Com eles, o cache pode ser gravado em
# dados_app/cache.json no próprio repositório.
# ============================================================


BASE_URL = "https://api.api-futebol.com.br/v1"
CACHE_PATH = Path("dados_app") / "cache.json"
CACHE_VERSION = 4


st.set_page_config(
    page_title="Laboratório API Futebol — Série B",
    page_icon="🧪",
    layout="wide",
)

st.title("🧪 Laboratório API Futebol — Série B")
st.caption(
    "Ambiente independente para validar a API antes da integração ao Premium Football Analytics."
)


# ============================================================
# CONFIGURAÇÃO / TOKEN
# ============================================================

def get_secret(name, default=None):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return default


def get_token():
    # Streamlit Secrets pode retornar uma seção em um tipo próprio
    # (não necessariamente dict). Por isso, não usamos isinstance(..., dict).
    try:
        section = st.secrets.get("api_futebol")
        if section is not None:
            try:
                token = section.get("token")
            except AttributeError:
                token = section["token"] if "token" in section else None
            if token:
                return str(token).strip()
    except Exception:
        pass

    # Formatos alternativos aceitos para manter compatibilidade.
    for name in (
        "API_FUTEBOL_TOKEN",
        "API_FUTEBOL_KEY",
        "CHAVE_API_FUTEBOL",
    ):
        value = get_secret(name)
        if value:
            return str(value).strip()

    return None


TOKEN = get_token()


# ============================================================
# CACHE LOCAL
# ============================================================

def default_cache():
    return {
        "version": CACHE_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "updated_at": None,

        # Descoberta
        "campeonatos": None,
        "serie_b": None,
        "edicao_serie_b": None,
        "fase_serie_b": None,
        "rodada_serie_b": None,

        # Dados da competição
        "fase_detail": None,
        "partidas": [],

        # Detalhes individuais — etapa seguinte do laboratório
        "detalhes_partidas": {},
        "partidas_enriquecidas": {},
        "historico_times": {},

        # Controle
        "api_calls": 0,
        "api_call_history": [],
        "last_api_call": None,

        # Diagnóstico
        "last_error": None,
    }


def load_local_cache():
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not CACHE_PATH.exists():
        cache = default_cache()
        save_local_cache(cache)
        return cache

    try:
        raw = CACHE_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)

        if not isinstance(data, dict):
            raise ValueError("cache.json não contém um objeto JSON.")

        base = default_cache()
        base.update(data)

        # Compatibilidade: se uma versão anterior já possuir histórico,
        # ele é preservado; se não possuir, começa vazio.
        if not isinstance(base.get("partidas_enriquecidas"), dict):
            base["partidas_enriquecidas"] = {}
        if not isinstance(base.get("historico_times"), dict):
            base["historico_times"] = {}
        if not isinstance(base.get("historico_jogadores"), dict):
            base["historico_jogadores"] = {}

        return base

    except Exception as exc:
        st.warning(
            f"⚠️ O cache local estava inválido e foi recriado: {exc}"
        )
        cache = default_cache()
        save_local_cache(cache)
        return cache


def save_local_cache(cache):
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

    cache["updated_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    tmp = CACHE_PATH.with_suffix(".tmp")

    tmp.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tmp.replace(CACHE_PATH)


# ============================================================
# PERSISTÊNCIA OPCIONAL NO GITHUB
# ============================================================

def github_config():
    token = get_secret("GITHUB_TOKEN")
    repo = get_secret("GITHUB_REPO")
    branch = get_secret("GITHUB_BRANCH", "main")

    if token and repo:
        return token, repo, branch

    return None, None, branch


def github_get_cache():
    token, repo, branch = github_config()

    if not token or not repo:
        return None, "GitHub não configurado."

    url = f"https://api.github.com/repos/{repo}/contents/{CACHE_PATH.as_posix()}"

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            params={"ref": branch},
            timeout=20,
        )

        if response.status_code == 404:
            return None, None

        if not response.ok:
            return None, f"GitHub HTTP {response.status_code}: {response.text[:500]}"

        payload = response.json()
        encoded = payload.get("content", "").replace("\n", "")

        if not encoded:
            return None, None

        decoded = base64.b64decode(encoded).decode("utf-8")
        data = json.loads(decoded)

        if not isinstance(data, dict):
            return None, "O cache remoto não é um objeto JSON."

        data["_github_sha"] = payload.get("sha")
        return data, None

    except Exception as exc:
        return None, str(exc)


def merge_cache(remote, local):
    if not isinstance(remote, dict):
        return dict(local)

    merged = dict(remote)

    for key, value in local.items():
        if key == "_github_sha":
            continue

        # Para estruturas simples, o estado local da operação atual vence.
        if value is not None:
            merged[key] = value

    return merged


def github_save_cache(cache, commit_message):
    token, repo, branch = github_config()

    if not token or not repo:
        return False, "GitHub não configurado."

    remote, remote_error = github_get_cache()

    if remote_error:
        return False, remote_error

    sha = remote.get("_github_sha") if isinstance(remote, dict) else None

    if remote:
        merged = merge_cache(remote, cache)
    else:
        merged = dict(cache)

    merged.pop("_github_sha", None)

    merged["updated_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

    content = json.dumps(
        merged,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")

    encoded = base64.b64encode(content).decode("ascii")

    url = f"https://api.github.com/repos/{repo}/contents/{CACHE_PATH.as_posix()}"

    body = {
        "message": commit_message,
        "content": encoded,
        "branch": branch,
    }

    if sha:
        body["sha"] = sha

    try:
        response = requests.put(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json=body,
            timeout=30,
        )

        if not response.ok:
            return False, f"GitHub HTTP {response.status_code}: {response.text[:800]}"

        return True, None

    except Exception as exc:
        return False, str(exc)


def persist_cache(cache, commit_message):
    # Sempre mantém o arquivo local atualizado.
    save_local_cache(cache)

    # Se GitHub estiver configurado, tenta persistir também.
    token, repo, _ = github_config()

    if token and repo:
        ok, error = github_save_cache(cache, commit_message)

        if not ok:
            return False, error

    return True, None


# ============================================================
# UTILITÁRIOS DE RESPOSTA
# ============================================================

def first_list(data, keys):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            return value

    # Alguns retornos podem conter a lista dentro de response.
    response = data.get("response")

    if isinstance(response, list):
        return response

    if isinstance(response, dict):
        for key in keys:
            value = response.get(key)
            if isinstance(value, list):
                return value

    return []


def unwrap_response(data):
    if isinstance(data, dict) and isinstance(data.get("response"), dict):
        return data["response"]

    return data


def show_raw(label, data):
    with st.expander(label):
        st.json(data if data is not None else {})


def text_of(obj, *keys):
    if not isinstance(obj, dict):
        return None

    for key in keys:
        value = obj.get(key)

        if value is not None and value != "":
            return value

    return None


# ============================================================
# API HTTP
# ============================================================

def api_get(path, cache):
    """Consulta a API Futebol e retorna sempre (payload, chamada, erro)."""
    if not TOKEN:
        return None, False, "API_FUTEBOL_TOKEN não configurado nos Secrets."

    path = str(path).strip()
    if not path.startswith("/"):
        path = "/" + path

    try:
        response = requests.get(
            BASE_URL + path,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Accept": "application/json",
            },
            timeout=30,
        )

        # Toda resposta HTTP recebida conta como chamada da API Futebol.
        cache["api_calls"] = int(cache.get("api_calls", 0)) + 1

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cache["last_api_call"] = now
        cache.setdefault("api_call_history", []).append(now)
        cache["api_call_history"] = cache["api_call_history"][-500:]

        if response.status_code == 401:
            error = "HTTP 401 — token inválido ou não autorizado."
            cache["last_error"] = error
            return None, True, error

        if response.status_code == 403:
            error = "HTTP 403 — acesso negado ou recurso não liberado pelo plano."
            cache["last_error"] = error
            return None, True, error

        if response.status_code == 429:
            error = "HTTP 429 — limite de requisições atingido."
            cache["last_error"] = error
            return None, True, error

        try:
            payload = response.json()
        except Exception:
            payload = None

        if not response.ok:
            error = f"HTTP {response.status_code}: {response.text[:800]}"
            cache["last_error"] = error
            return None, True, error

        if payload is None:
            error = "A API respondeu, mas o corpo não é JSON."
            cache["last_error"] = error
            return None, True, error

        cache["last_error"] = None
        return payload, True, None

    except requests.RequestException as exc:
        error = f"Erro de rede: {exc}"
        cache["last_error"] = error
        return None, False, error


# ============================================================
# DESCOBERTA AUTOMÁTICA DA SÉRIE B
# ============================================================

def find_serie_b(campeonatos):
    comps = first_list(
        campeonatos,
        ["campeonatos", "data", "results"],
    )

    candidates = []

    for item in comps:
        if not isinstance(item, dict):
            continue

        text = " ".join(
            str(item.get(key) or "")
            for key in (
                "nome",
                "name",
                "nome_popular",
                "slug",
                "descricao",
                "description",
            )
        ).lower()

        if "série b" in text or "serie b" in text:
            candidates.append(item)

    # Prioriza o Campeonato Brasileiro Série B.
    for item in candidates:
        text = " ".join(
            str(item.get(key) or "")
            for key in (
                "nome",
                "name",
                "nome_popular",
                "slug",
            )
        ).lower()

        if "brasileiro" in text and "série b" in text:
            return item

        if "brasileiro" in text and "serie b" in text:
            return item

    return candidates[0] if candidates else None


def get_serie_b_from_cache(cache):
    value = cache.get("serie_b")

    if isinstance(value, dict) and value.get("campeonato_id") is not None:
        return value

    return None


def discover_serie_b(cache, force=False):
    if not force:
        cached = get_serie_b_from_cache(cache)

        if cached:
            return cached, False, None

    data, called, error = api_get("/campeonatos", cache)

    if error:
        persist_cache(cache, "Laboratório: erro na descoberta de campeonatos")
        return None, called, error

    cache["campeonatos"] = data

    target = find_serie_b(data)

    if not target:
        error = "A API respondeu, mas a Série B não foi encontrada."
        cache["last_error"] = error
        persist_cache(cache, "Laboratório: Série B não encontrada")
        return None, True, error

    campeonato_id = (
        target.get("campeonato_id")
        or target.get("id")
    )

    if campeonato_id is None:
        error = (
            "A Série B foi encontrada, mas não veio com ID de campeonato."
        )
        cache["last_error"] = error
        persist_cache(cache, "Laboratório: Série B sem ID")
        return None, True, error

    result = {
        "campeonato_id": campeonato_id,
        "nome": text_of(
            target,
            "nome",
            "name",
        ),
        "nome_popular": text_of(
            target,
            "nome_popular",
        ),
        "slug": text_of(
            target,
            "slug",
        ),
        "raw": target,
    }

    cache["serie_b"] = result

    ok, save_error = persist_cache(
        cache,
        "Laboratório: descobriu Campeonato Brasileiro Série B",
    )

    if not ok:
        return result, True, save_error

    return result, called, None


# ============================================================
# EDIÇÃO / FASE / RODADA
# ============================================================

def extract_structure_from_championship(payload):
    root = unwrap_response(payload)

    if not isinstance(root, dict):
        return None, None, None

    edition = (
        root.get("edicao_atual")
        or root.get("edicao")
    )

    phase = (
        root.get("fase_atual")
        or root.get("fase")
    )

    round_info = (
        root.get("rodada_atual")
        or root.get("rodada")
    )

    return edition, phase, round_info


def load_serie_b_structure(cache, force=False):
    serie_b, called, error = discover_serie_b(cache, force=force)

    if error:
        return None, called, error

    campeonato_id = str(serie_b["campeonato_id"])

    if (
        not force
        and cache.get("edicao_serie_b")
        and cache.get("fase_serie_b")
    ):
        return {
            "campeonato_id": serie_b["campeonato_id"],
            "edicao": cache["edicao_serie_b"],
            "fase": cache["fase_serie_b"],
            "rodada": cache.get("rodada_serie_b"),
            "raw": cache.get("campeonato_detail"),
        }, called, None

    payload, api_called, error = api_get(
        f"/campeonatos/{campeonato_id}",
        cache,
    )

    called = called or api_called

    if error:
        persist_cache(
            cache,
            "Laboratório: erro no detalhe da Série B",
        )
        return None, called, error

    cache["campeonato_detail"] = payload

    edition, phase, round_info = extract_structure_from_championship(
        payload
    )

    if edition is not None:
        cache["edicao_serie_b"] = edition

    if phase is not None:
        cache["fase_serie_b"] = phase

    if round_info is not None:
        cache["rodada_serie_b"] = round_info

    ok, save_error = persist_cache(
        cache,
        "Laboratório: salvou estrutura 2026 da Série B",
    )

    if not ok:
        return None, called, save_error

    return {
        "campeonato_id": serie_b["campeonato_id"],
        "edicao": edition,
        "fase": phase,
        "rodada": round_info,
        "raw": payload,
    }, called, None


def load_phase_detail(cache, force=False):
    phase = cache.get("fase_serie_b")
    serie_b = cache.get("serie_b")

    if not isinstance(phase, dict) or not isinstance(serie_b, dict):
        return None, False, "Estrutura da Série B ainda não foi descoberta."

    phase_id = phase.get("fase_id") or phase.get("id")
    campeonato_id = (
        serie_b.get("campeonato_id")
        or serie_b.get("id")
    )

    if phase_id is None or campeonato_id is None:
        return None, False, "Não foi possível identificar campeonato_id/fase_id."

    if not force and cache.get("fase_detail") is not None:
        return cache["fase_detail"], False, None

    payload, called, error = api_get(
        f"/campeonatos/{campeonato_id}/fases/{phase_id}",
        cache,
    )

    if error:
        persist_cache(
            cache,
            "Laboratório: erro no detalhe da fase",
        )
        return None, called, error

    cache["fase_detail"] = payload

    ok, save_error = persist_cache(
        cache,
        "Laboratório: salvou detalhe da fase da Série B",
    )

    if not ok:
        return payload, called, save_error

    return payload, called, None


# ============================================================
# EXTRAÇÃO ROBUSTA DAS PARTIDAS
# ============================================================

def normalize_match(obj):
    if not isinstance(obj, dict):
        return None

    match_id = (
        obj.get("partida_id")
        or obj.get("id")
    )

    if match_id is None:
        return None

    home = (
        obj.get("time_mandante")
        or obj.get("mandante")
        or obj.get("time_casa")
        or obj.get("home")
        or obj.get("home_team")
    )

    away = (
        obj.get("time_visitante")
        or obj.get("visitante")
        or obj.get("time_fora")
        or obj.get("away")
        or obj.get("away_team")
    )

    def team_name(value):
        if isinstance(value, dict):
            return (
                value.get("nome_popular")
                or value.get("nome")
                or value.get("name")
                or value.get("nome_time")
                or str(value.get("id") or "Time")
            )

        return str(value) if value is not None else "—"

    return {
        "id": match_id,
        "home": team_name(home),
        "away": team_name(away),
        "date": (
            obj.get("data_realizacao")
            or obj.get("data")
            or obj.get("horario")
            or obj.get("date")
        ),
        "status": (
            obj.get("status")
            or obj.get("situacao")
            or obj.get("status_partida")
        ),
        "round": (
            obj.get("rodada")
            or obj.get("round")
        ),
        "raw": obj,
    }


def walk_dicts(value):
    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from walk_dicts(child)

    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def extract_matches_from_phase(payload):
    found = []
    seen = set()

    # Primeiro, procura listas em chaves obviamente relacionadas a partidas.
    if isinstance(payload, dict):
        roots = [payload]

        response = payload.get("response")
        if isinstance(response, dict):
            roots.append(response)

        for root in roots:
            for key in (
                "partidas",
                "matches",
                "jogos",
                "games",
            ):
                value = root.get(key)

                if isinstance(value, list):
                    for item in value:
                        normalized = normalize_match(item)

                        if normalized and str(normalized["id"]) not in seen:
                            seen.add(str(normalized["id"]))
                            found.append(normalized)

    # Fallback: percorre todos os objetos para encontrar partidas.
    if not found:
        for obj in walk_dicts(payload):
            normalized = normalize_match(obj)

            if normalized and str(normalized["id"]) not in seen:
                seen.add(str(normalized["id"]))
                found.append(normalized)

    return found


def load_serie_b_matches(cache, force=False):
    if not force and cache.get("partidas"):
        return cache["partidas"], False, None

    payload, called, error = load_phase_detail(
        cache,
        force=force,
    )

    if error:
        return [], called, error

    matches = extract_matches_from_phase(payload)

    cache["partidas"] = matches

    ok, save_error = persist_cache(
        cache,
        "Laboratório: salvou partidas da Série B",
    )

    if not ok:
        return matches, called, save_error

    return matches, called, None


# ============================================================
# CONTROLES DA INTERFACE
# ============================================================

if "lab_cache" not in st.session_state:
    st.session_state["lab_cache"] = load_local_cache()

cache = st.session_state["lab_cache"]


with st.sidebar:
    st.markdown("## 🧪 Estado do laboratório")

    st.metric(
        "Chamadas API",
        cache.get("api_calls", 0),
    )

    st.metric(
        "Partidas no cache",
        len(cache.get("partidas") or []),
    )

    if cache.get("serie_b"):
        st.success(
            f"Série B: ID {cache['serie_b'].get('campeonato_id')}"
        )
    else:
        st.info("Série B ainda não descoberta.")

    github_token, github_repo, github_branch = github_config()

    if github_token and github_repo:
        st.success("💾 Persistência GitHub: ativa")
        st.caption(
            f"{github_repo} · branch {github_branch} · "
            f"{CACHE_PATH.as_posix()}"
        )
    else:
        st.warning(
            "💾 Persistência GitHub: não configurada. "
            "O cache local ainda funciona."
        )

    if st.button("🔄 Recarregar cache", use_container_width=True):
        st.session_state["lab_cache"] = load_local_cache()
        st.rerun()


# ============================================================
# 0 — CONEXÃO
# ============================================================

st.header("0. Conexão")

if TOKEN:
    st.success("🔐 Token da API Futebol encontrado nos Secrets.")
else:
    st.error(
        "Configure API_FUTEBOL_TOKEN ou [api_futebol].token "
        "nos Secrets do Streamlit."
    )


# ============================================================
# 1 — DESCOBERTA AUTOMÁTICA
# ============================================================

st.header("1. Descoberta automática da Série B")

st.write(
    "Esta etapa consulta a lista de campeonatos somente quando "
    "a Série B ainda não estiver no cache."
)

c1, c2 = st.columns(2)

with c1:
    if st.button(
        "🏆 Descobrir Série B",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Consultando campeonatos..."):
            result, called, error = discover_serie_b(
                cache,
                force=False,
            )

        if error:
            st.error(str(error))
        else:
            st.success(
                "Série B localizada. "
                + (
                    "Foi feita uma chamada à API."
                    if called
                    else "O resultado veio do cache."
                )
            )

        st.session_state["lab_cache"] = cache

with c2:
    if st.button(
        "♻️ Forçar nova descoberta",
        use_container_width=True,
    ):
        with st.spinner("Forçando nova consulta de campeonatos..."):
            result, called, error = discover_serie_b(
                cache,
                force=True,
            )

        if error:
            st.error(str(error))
        else:
            st.success("Nova descoberta concluída.")

        st.session_state["lab_cache"] = cache


serie_b = cache.get("serie_b")

if serie_b:
    st.subheader("🏆 Série B encontrada")

    st.dataframe(
        [
            {
                "Campo": "Campeonato ID",
                "Valor": serie_b.get("campeonato_id"),
            },
            {
                "Campo": "Nome",
                "Valor": serie_b.get("nome"),
            },
            {
                "Campo": "Nome popular",
                "Valor": serie_b.get("nome_popular"),
            },
            {
                "Campo": "Slug",
                "Valor": serie_b.get("slug"),
            },
        ],
        use_container_width=True,
        hide_index=True,
    )

    show_raw("🔍 JSON bruto — Série B", serie_b.get("raw"))


# ============================================================
# 2 — EDIÇÃO / FASE / RODADA
# ============================================================

st.header("2. Estrutura atual da Série B")

if st.button(
    "📚 Descobrir edição, fase e rodada",
    type="primary",
    use_container_width=True,
):
    with st.spinner("Consultando estrutura do campeonato..."):
        structure, called, error = load_serie_b_structure(
            cache,
            force=False,
        )

    if error:
        st.error(str(error))
    else:
        st.success(
            "Estrutura carregada. "
            + (
                "Consulta feita à API."
                if called
                else "Dados recuperados do cache."
            )
        )

    st.session_state["lab_cache"] = cache


edition = cache.get("edicao_serie_b")
phase = cache.get("fase_serie_b")
round_info = cache.get("rodada_serie_b")

if edition or phase or round_info:
    rows = [
        {
            "Objeto": "Edição atual",
            "ID": (
                edition.get("edicao_id") or edition.get("id")
                if isinstance(edition, dict)
                else None
            ),
            "Nome": (
                text_of(edition, "nome", "name")
                if isinstance(edition, dict)
                else edition
            ),
            "Temporada": (
                text_of(edition, "temporada", "season")
                if isinstance(edition, dict)
                else None
            ),
        },
        {
            "Objeto": "Fase atual",
            "ID": (
                phase.get("fase_id") or phase.get("id")
                if isinstance(phase, dict)
                else None
            ),
            "Nome": (
                text_of(phase, "nome", "name")
                if isinstance(phase, dict)
                else phase
            ),
            "Temporada": None,
        },
        {
            "Objeto": "Rodada atual",
            "ID": (
                round_info.get("rodada")
                or round_info.get("id")
                if isinstance(round_info, dict)
                else None
            ),
            "Nome": (
                text_of(round_info, "nome", "name")
                if isinstance(round_info, dict)
                else round_info
            ),
            "Temporada": None,
        },
    ]

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("🔍 JSON — edição"):
        st.json(edition if edition is not None else {})

    with st.expander("🔍 JSON — fase"):
        st.json(phase if phase is not None else {})

    with st.expander("🔍 JSON — rodada"):
        st.json(round_info if round_info is not None else {})


# ============================================================
# 3 — PARTIDAS
# ============================================================

st.header("3. Partidas da Série B")

if st.button(
    "⚽ Carregar partidas",
    type="primary",
    use_container_width=True,
):
    with st.spinner("Obtendo partidas pela fase atual..."):
        matches, called, error = load_serie_b_matches(
            cache,
            force=False,
        )

    if error:
        st.error(str(error))
    else:
        st.success(
            f"{len(matches)} partida(s) encontradas. "
            + (
                "Consulta feita à API."
                if called
                else "Resultado recuperado do cache."
            )
        )

    st.session_state["lab_cache"] = cache


matches = cache.get("partidas") or []

if matches:
    rows = []

    for match in matches:
        rows.append(
            {
                "ID": match.get("id"),
                "Casa": match.get("home"),
                "Fora": match.get("away"),
                "Data": match.get("date"),
                "Rodada": (
                    text_of(match.get("round"), "nome", "name")
                    if isinstance(match.get("round"), dict)
                    else match.get("round")
                ),
                "Status": match.get("status"),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )

    st.success(
        "🟢 As partidas estão persistidas no cache. "
        "Recarregar a página não deve exigir nova consulta."
    )

    show_raw(
        "🔍 JSON bruto — partidas normalizadas",
        matches,
    )
else:
    st.info(
        "Nenhuma partida está no cache ainda. "
        "Execute a etapa 2 e depois 'Carregar partidas'."
    )


# ============================================================
# 4 — TESTE DE CACHE
# ============================================================

st.header("4. Teste de persistência/cache")

st.write(
    "O objetivo desta etapa é comprovar que a segunda consulta "
    "não chama novamente a API quando os dados já estão no cache."
)

before_calls = int(cache.get("api_calls", 0))

if st.button(
    "🧪 Executar leitura pelo cache",
    use_container_width=True,
):
    # Releitura física do arquivo para simular um novo ciclo do app.
    disk_cache = load_local_cache()

    after_calls = int(disk_cache.get("api_calls", 0))

    cached_serie_b = disk_cache.get("serie_b")
    cached_phase = disk_cache.get("fase_serie_b")
    cached_matches = disk_cache.get("partidas") or []

    st.session_state["lab_cache"] = disk_cache
    cache = disk_cache

    if cached_serie_b:
        st.success(
            "✅ Série B recuperada do cache sem nova chamada nesta operação."
        )
    else:
        st.warning("Série B ainda não está no cache.")

    st.write(
        f"Chamadas registradas antes: **{before_calls}**"
    )
    st.write(
        f"Chamadas registradas após leitura: **{after_calls}**"
    )
    st.write(
        f"Partidas recuperadas do cache: **{len(cached_matches)}**"
    )

    if cached_phase:
        st.write("✅ Fase atual também está persistida.")
    else:
        st.write("⚠️ Fase ainda não está persistida.")


# ============================================================
# 5 — DETALHE DE UMA PARTIDA
# ============================================================

st.header("5. Detalhe da partida")

st.info("Primeiro recuperamos o detalhe da API e salvamos no cache. Depois o mesmo JSON é transformado em uma camada estável para os analistas.")

fixture_options = [
    str(item.get("id"))
    for item in matches
    if item.get("id") is not None
]

if fixture_options:
    selected_fixture = st.selectbox(
        "Partida para o próximo teste",
        fixture_options,
    )

    if st.button(
        "🔬 Testar detalhe desta partida",
        use_container_width=True,
    ):
        fixture_id = selected_fixture

        # O detalhe fica separado para não confundir a fase de descoberta.
        existing = cache.get("detalhes_partidas", {}).get(
            str(fixture_id)
        )

        if existing is not None:
            st.success(
                "🟢 Detalhe já está no cache. "
                "Nenhuma chamada será feita."
            )
            st.json(existing)
        else:
            with st.spinner(
                f"Consultando partida {fixture_id}..."
            ):
                data, called, error = api_get(
                    f"/partidas/{fixture_id}",
                    cache,
                )

            if error:
                st.error(str(error))
            else:
                cache.setdefault(
                    "detalhes_partidas",
                    {},
                )[str(fixture_id)] = data

                ok, save_error = persist_cache(
                    cache,
                    f"Laboratório: detalhe da partida {fixture_id}",
                )

                if not ok:
                    st.error(save_error)
                else:
                    st.success(
                        "✅ Detalhe recebido e salvo no cache. "
                        + ("Foi feita uma chamada à API." if called else "Veio do cache.")
                    )
                    st.json(data)

                st.session_state["lab_cache"] = cache
else:
    st.caption(
        "Quando as partidas forem carregadas, seus IDs aparecerão aqui."
    )


# ============================================================
# FUNÇÕES DE ENRIQUECIMENTO / BASE HISTÓRICA
# ============================================================

def first_value(obj, keys):
    if isinstance(obj, dict):
        for key in keys:
            if key in obj and obj[key] not in (None, "", []):
                return obj[key]
    return None


def find_objects_by_keys(value, key_sets):
    found = []
    if isinstance(value, dict):
        if any(all(k in value for k in ks) for ks in key_sets):
            found.append(value)
        for child in value.values():
            found.extend(find_objects_by_keys(child, key_sets))
    elif isinstance(value, list):
        for child in value:
            found.extend(find_objects_by_keys(child, key_sets))
    return found


def normalize_team_ref(value):
    if not isinstance(value, dict):
        return {"id": None, "nome": str(value) if value is not None else None}
    return {
        "id": first_value(value, ["time_id", "id", "team_id"]),
        "nome": first_value(value, ["nome_popular", "nome", "name", "nome_time"]),
    }


def extract_team_from_match(payload, side):
    keys = (
        ["time_mandante", "mandante", "time_casa", "home", "home_team"]
        if side == "home"
        else ["time_visitante", "visitante", "time_fora", "away", "away_team"]
    )
    if isinstance(payload, dict):
        value = first_value(payload, keys)
        if value is not None:
            return normalize_team_ref(value)
    return {"id": None, "nome": None}


def extract_score(payload):
    if not isinstance(payload, dict):
        return {}
    score = first_value(payload, ["placar", "score", "resultado"])
    if isinstance(score, dict):
        return {
            "casa": first_value(score, ["mandante", "casa", "home", "home_score", "gols_mandante"]),
            "fora": first_value(score, ["visitante", "fora", "away", "away_score", "gols_visitante"]),
        }
    return {
        "casa": first_value(payload, ["placar_mandante", "gols_mandante", "home_score", "home_goals"]),
        "fora": first_value(payload, ["placar_visitante", "gols_visitante", "away_score", "away_goals"]),
    }


def extract_named_list(payload, names):
    """Localiza listas/blocos mesmo quando a API os coloca dentro de response/data.

    A API Futebol já apresentou estruturas diferentes entre endpoints/temporadas.
    Por isso não dependemos mais de a chave estar exatamente no nível raiz.
    Nenhuma chamada HTTP é feita aqui.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    aliases = set(str(x).strip().lower() for x in names)
    aliases.update({
        "escalações", "escalacoes", "escalação", "escalacao",
        "jogadores", "players", "atletas",
        "estatísticas", "estatisticas", "statistics",
        "eventos", "events",
    })

    # Primeiro procura exatamente no nível atual.
    for key, value in payload.items():
        if str(key).strip().lower() in aliases:
            if isinstance(value, (list, dict)):
                return value

    # Depois procura dentro de wrappers comuns.
    for wrapper in ("response", "data", "resultado", "result", "partida", "match"):
        child = payload.get(wrapper)
        if isinstance(child, (dict, list)):
            found = extract_named_list(child, names)
            if found:
                return found

    # Último recurso: busca recursiva conservadora.
    for child in payload.values():
        if isinstance(child, dict):
            found = extract_named_list(child, names)
            if found:
                return found
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    found = extract_named_list(item, names)
                    if found:
                        return found

    return []


def _player_id_from_obj(value):
    if not isinstance(value, dict):
        return None
    return first_value(value, [
        "jogador_id", "player_id", "id_jogador", "id", "codigo_jogador",
    ])


def _player_name_from_obj(value):
    if isinstance(value, str):
        return value.strip() or None
    if not isinstance(value, dict):
        return None
    return first_value(value, [
        "nome", "name", "nome_jogador", "nome_popular", "player_name",
    ])


def _team_context(value):
    if not isinstance(value, dict):
        return {}
    team = first_value(value, [
        "team", "time", "equipe", "clube", "club",
        "time_mandante", "time_visitante", "mandante", "visitante",
        "home_team", "away_team", "home", "away",
    ])
    if isinstance(team, dict):
        return normalize_team_ref(team)
    if team is not None:
        return normalize_team_ref(team)
    return {}


def _valid_team_ref(team):
    """Retorna True quando a referência do time realmente identifica um clube."""
    if not isinstance(team, dict):
        return False
    return team.get("id") not in (None, "", 0) or bool(str(team.get("nome") or "").strip())


def _merge_team_ref(primary, fallback):
    """Usa a referência primária e completa campos ausentes com o fallback."""
    primary = primary if isinstance(primary, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    merged = {
        "id": primary.get("id") or fallback.get("id"),
        "nome": primary.get("nome") or fallback.get("nome"),
    }
    return merged if _valid_team_ref(merged) else {}


def _stats_from_player_obj(value):
    if not isinstance(value, dict):
        return {}
    stats = first_value(value, [
        "statistics", "estatisticas", "stats", "estatistica",
        "dados", "dados_jogador",
    ])
    if isinstance(stats, list):
        return stats[0] if stats and isinstance(stats[0], dict) else {}
    return stats if isinstance(stats, dict) else {}


def _stable_player_id(player, team=None):
    """Gera um identificador estável quando a fonte não fornece ID numérico."""
    pid = _player_id_from_obj(player)
    if pid is not None:
        return pid
    name = _player_name_from_obj(player)
    team = team or {}
    tid = team.get("id") if isinstance(team, dict) else None
    if name:
        base = " ".join(str(name).strip().lower().split())
        return f"nome:{tid or 'sem_time'}:{base}"
    return None


def _player_payload(value):
    """Converte formatos simples de escalação em um objeto de jogador."""
    if isinstance(value, dict):
        explicit = first_value(value, ["jogador", "player", "atleta"])
        if isinstance(explicit, dict):
            return explicit
        if isinstance(explicit, str) and explicit.strip():
            return {
                "nome": explicit.strip(),
                "id": first_value(value, ["jogador_id", "player_id", "id_jogador"]),
                "numero": first_value(value, ["numero", "camisa", "number"]),
                "posicao": first_value(value, ["posicao", "position", "pos"]),
            }
        return value
    if isinstance(value, str) and value.strip():
        return {"nome": value.strip()}
    return None


def _collect_player_entries(value, inherited_team=None, result=None, seen=None):
    """Extrai jogadores de escalações/estatísticas sem nova chamada à API.

    Aceita os formatos já usados pela API Futebol: player/jogador/atleta como
    objeto ou texto, listas diretas, grupos por mandante/visitante, titulares,
    reservas e wrappers aninhados. Também aceita jogadores que possuem
    `statistics` no próprio objeto — formato que o parser anterior descartava.
    """
    if result is None:
        result = []
    if seen is None:
        seen = set()

    if isinstance(value, list):
        for item in value:
            _collect_player_entries(item, inherited_team, result, seen)
        return result

    if isinstance(value, str):
        player = _player_payload(value)
        pid = _stable_player_id(player, inherited_team)
        if player and pid is not None and str(pid) not in seen:
            result.append({"player": player, "team": inherited_team or {}, "stats": {}})
            seen.add(str(pid))
        return result

    if not isinstance(value, dict):
        return result

    current_team = _merge_team_ref(_team_context(value), inherited_team)
    # Alguns formatos colocam o time dentro de statistics/dados_jogador.
    # Aproveitamos essa informação antes de aceitar `sem_time`.
    if not current_team:
        current_team = _team_context(_stats_from_player_obj(value))

    # Caso explícito: {player/jogador/atleta: {...}, statistics: ...}
    explicit_player = first_value(value, ["jogador", "player", "atleta"])
    if explicit_player is not None:
        player = _player_payload(value)
        if player:
            pid = _stable_player_id(player, current_team)
            if pid is not None and str(pid) not in seen:
                result.append({
                    "player": player,
                    "team": current_team,
                    "stats": _stats_from_player_obj(value) or _stats_from_player_obj(player),
                })
                seen.add(str(pid))

    # Caso direto: o próprio objeto é o jogador. Não descartamos mais objetos
    # que contenham `statistics`.
    direct_name = _player_name_from_obj(value)
    direct_id = _player_id_from_obj(value)
    has_player_shape = (
        direct_name is not None
        and (
            direct_id is not None
            or any(k in value for k in ("numero", "camisa", "number", "posicao", "position", "pos", "statistics", "estatisticas", "stats"))
        )
    )
    if has_player_shape and explicit_player is None:
        pid = _stable_player_id(value, current_team)
        if pid is not None and str(pid) not in seen:
            result.append({
                "player": value,
                "team": current_team,
                "stats": _stats_from_player_obj(value),
            })
            seen.add(str(pid))

    # Containers conhecidos, incluindo variantes com acento.
    known_containers = (
        "jogadores", "players", "atletas", "titulares", "starters",
        "reservas", "substitutes", "substitutos", "escalacao", "escalação",
        "lineup", "lineups", "mandante", "visitante", "casa", "fora",
        "home", "away", "home_team", "away_team", "elenco", "squad",
    )
    for key in known_containers:
        child = value.get(key)
        if child is not None:
            _collect_player_entries(child, current_team, result, seen)

    # Fallback recursivo. Não desce novamente em objetos de estatística para
    # evitar transformar campos numéricos em falsos jogadores.
    known = {
        "jogador", "player", "atleta", "team", "time", "equipe", "clube", "club",
        "statistics", "estatisticas", "stats", "estatistica", "dados", "dados_jogador",
    }
    for key, child in value.items():
        if key in known or key in known_containers:
            continue
        if isinstance(child, (dict, list)):
            _collect_player_entries(child, current_team, result, seen)

    return result


def _players_from_events(events, home=None, away=None, seen=None):
    """Cria registros mínimos para atletas citados em eventos quando a escalação
    não foi entregue. Isso nunca substitui a escalação; apenas evita perder
    jogadores que a própria partida já identificou."""
    if seen is None:
        seen = set()
    result = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        player = ev.get("player") or ev.get("jogador") or ev.get("atleta")
        if not isinstance(player, dict):
            continue
        team = ev.get("team") or ev.get("time") or {}
        if not isinstance(team, dict):
            team = {"nome": str(team)}
        team = normalize_team_ref(team)
        if not _valid_team_ref(team):
            # Eventos às vezes identificam o time por um campo lateral.
            team = normalize_team_ref(
                ev.get("team_id") or ev.get("time_id") or ev.get("equipe_id")
            )
        if not _valid_team_ref(team):
            # Se não houver time no evento, não inventamos a associação.
            team = {}
        pid = _stable_player_id(player, team)
        if pid is None or str(pid) in seen:
            continue
        result.append({"player": player, "team": normalize_team_ref(team), "stats": {}})
        seen.add(str(pid))
    return result


def _collect_players_with_match_teams(value, home, away, inherited_team=None, result=None, seen=None):
    """Percorre escalações atribuindo explicitamente mandante/visitante.

    Algumas respostas da API trazem `titulares`/`reservas` dentro de blocos
    `mandante` e `visitante`, mas os próprios jogadores não repetem o time.
    Nesse caso, o contexto da partida é a fonte correta para preencher o time.
    """
    if result is None:
        result = []
    if seen is None:
        seen = set()

    if isinstance(value, list):
        for item in value:
            _collect_players_with_match_teams(
                item, home, away, inherited_team, result, seen
            )
        return result

    if not isinstance(value, dict):
        return result

    current_team = _merge_team_ref(_team_context(value), inherited_team)

    home_keys = {
        "mandante", "casa", "home", "home_team", "time_mandante",
        "time_casa", "mandante_time", "home_team_players",
    }
    away_keys = {
        "visitante", "fora", "away", "away_team", "time_visitante",
        "time_fora", "visitante_time", "away_team_players",
    }

    for key, child in value.items():
        normalized_key = str(key).strip().lower()
        if normalized_key in home_keys:
            _collect_players_with_match_teams(
                child, home, away, home, result, seen
            )
        elif normalized_key in away_keys:
            _collect_players_with_match_teams(
                child, home, away, away, result, seen
            )
        elif isinstance(child, (dict, list)):
            _collect_players_with_match_teams(
                child, home, away, current_team, result, seen
            )

    # Também tenta interpretar o próprio objeto como jogador.
    direct_name = _player_name_from_obj(value)
    direct_id = _player_id_from_obj(value)
    if direct_name is not None and (
        direct_id is not None
        or any(k in value for k in (
            "numero", "camisa", "number", "posicao", "position", "pos",
            "statistics", "estatisticas", "stats",
        ))
    ):
        team = current_team or _team_context(_stats_from_player_obj(value))
        pid = _stable_player_id(value, team)
        if pid is not None and str(pid) not in seen:
            result.append({
                "player": value,
                "team": team,
                "stats": _stats_from_player_obj(value),
            })
            seen.add(str(pid))

    # Containers de escalação.
    for key in (
        "jogadores", "players", "atletas", "titulares", "starters",
        "reservas", "substitutes", "substitutos", "escalacao", "escalação",
        "lineup", "lineups", "elenco", "squad",
    ):
        child = value.get(key)
        if child is not None:
            _collect_players_with_match_teams(
                child, home, away, current_team, result, seen
            )

    return result


def extract_players_from_detail(detail, lineups=None, events=None):
    """Extrai jogadores do detalhe persistido, sem chamar a API.

    A associação ao time é resolvida nesta ordem: time explícito do jogador,
    time presente nas estatísticas, contexto mandante/visitante da escalação
    e, por último, eventos. Nenhuma etapa faz chamada HTTP.
    """
    home = extract_team_from_match(detail, "home")
    away = extract_team_from_match(detail, "away")

    direct = extract_named_list(detail, [
        "jogadores", "players", "atletas", "jogadores_partida",
        "estatisticas_jogadores", "player_statistics",
    ])
    records = []
    seen = set()

    if direct:
        records = _collect_player_entries(direct, result=[], seen=seen)

    if lineups:
        # Não exige que o bloco de escalações tenha uma forma específica.
        # Quando houver mandante/visitante, o contexto é propagado.
        records = _collect_players_with_match_teams(
            lineups, home, away, result=records, seen=seen
        )

    if events:
        records.extend(_players_from_events(events, home=home, away=away, seen=seen))

    return records


def enrich_match_detail(match_id, detail):
    """Converte o JSON bruto em uma camada estável para os analistas."""
    home = extract_team_from_match(detail, "home")
    away = extract_team_from_match(detail, "away")
    score = extract_score(detail)

    stats = extract_named_list(detail, ["estatisticas", "stats", "statistics"])
    events = extract_named_list(detail, ["eventos", "events"])
    lineups = extract_named_list(detail, ["escalacoes", "lineups", "lineup"])
    players = extract_players_from_detail(detail, lineups, events)

    # Algumas respostas colocam esses blocos dentro de outros objetos.
    if not stats:
        stats = find_objects_by_keys(detail, [["tipo", "valor"], ["estatistica", "valor"]])
    if not events:
        events = find_objects_by_keys(detail, [["minuto", "tipo"], ["minute", "type"]])

    return {
        "partida_id": match_id,
        "campeonato_id": 14,
        "temporada": 2026,
        "times": {"casa": home, "fora": away},
        "placar": score,
        "data": first_value(detail, ["data_realizacao", "data", "horario", "date"]),
        "status": first_value(detail, ["status", "situacao", "status_partida"]),
        "rodada": first_value(detail, ["rodada", "round"]),
        "estatisticas": stats,
        "eventos": events,
        "escalacoes": lineups,
        "jogadores": players,
        "raw": detail,
        "enriquecido_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _to_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace("%", "").replace(",", ".")
        try:
            return float(text)
        except Exception:
            return None
    return None


def _stat_name(stat):
    if not isinstance(stat, dict):
        return ""
    return str(
        stat.get("tipo")
        or stat.get("nome")
        or stat.get("name")
        or stat.get("estatistica")
        or stat.get("type")
        or ""
    ).strip().lower()


def _extract_side_stat(stats, side, aliases):
    aliases = [str(x).lower() for x in aliases]

    if isinstance(stats, dict):
        direct = stats.get(side)
        if isinstance(direct, list):
            stats = direct

    if not isinstance(stats, list):
        return None

    for stat in stats:
        if not isinstance(stat, dict):
            continue

        name = _stat_name(stat)
        if not any(alias in name or name in alias for alias in aliases):
            continue

        raw = (
            stat.get(side)
            if stat.get(side) is not None
            else stat.get("valor", stat.get("value"))
        )

        if isinstance(raw, dict):
            raw = (
                raw.get(side)
                or raw.get("home" if side == "casa" else "away")
            )

        value = _to_number(raw)
        if value is not None:
            return value

    return None


STAT_ALIASES = {
    "Escanteios": ["corner", "corners", "escanteio", "escanteios"],
    "Finalizações": ["shot", "shots", "finalização", "finalizacoes", "total shots"],
    "Finalizações no alvo": [
        "shots on goal", "shots on target",
        "finalizações no alvo", "finalizacao no alvo",
    ],
    "Posse": ["possession", "posse"],
    "Faltas": ["foul", "fouls", "faltas"],
    "Amarelos": ["yellow", "yellow cards", "cartão amarelo", "cartoes amarelos"],
    "Vermelhos": ["red", "red cards", "cartão vermelho", "cartoes vermelhos"],
    "Impedimentos": ["offside", "offsides", "impedimentos"],
    "Pênaltis": ["penalty", "penalties", "pênalti", "penaltis"],
}


def _team_history_record(enriched, side):
    teams = enriched.get("times") or {}
    own = teams.get(side) or {}
    opponent_side = "fora" if side == "casa" else "casa"
    opponent = teams.get(opponent_side) or {}

    score = enriched.get("placar") or {}
    gf = _to_number(
        score.get("casa") if side == "casa" else score.get("fora")
    )
    ga = _to_number(
        score.get("fora") if side == "casa" else score.get("casa")
    )

    stats = enriched.get("estatisticas") or []
    normalized_stats = {
        metric: _extract_side_stat(
            stats,
            side,
            aliases,
        )
        for metric, aliases in STAT_ALIASES.items()
    }

    return {
        "partida_id": str(enriched.get("partida_id")),
        "mandante": side == "casa",
        "time": own,
        "adversario": opponent,
        "gols_feitos": gf,
        "gols_sofridos": ga,
        "placar": score,
        "estatisticas": normalized_stats,
        "eventos": enriched.get("eventos") or [],
        "data": enriched.get("data"),
        "status": enriched.get("status"),
        "rodada": enriched.get("rodada"),
    }


def _extract_player_records(enriched):
    """Normaliza a camada estável de jogadores para o histórico."""
    players = enriched.get("jogadores") or []
    if isinstance(players, dict):
        players = [players]
    if not isinstance(players, list):
        return []

    result = []
    for group in players:
        if not isinstance(group, dict):
            continue

        group_team = group.get("team") or group.get("time") or group.get("equipe") or {}
        group_players = group.get("players") or group.get("jogadores") or group.get("atletas")

        if isinstance(group_players, list):
            for entry in group_players:
                if not isinstance(entry, dict):
                    continue
                player = entry.get("player") or entry.get("jogador") or entry.get("atleta") or entry
                stats = entry.get("statistics") or entry.get("estatisticas") or entry.get("stats") or {}
                if isinstance(stats, list):
                    stats = stats[0] if stats else {}
                result.append({
                    "player": player if isinstance(player, dict) else {"nome": str(player)},
                    "team": group_team,
                    "stats": stats if isinstance(stats, dict) else {},
                })
        else:
            player = group.get("player") or group.get("jogador") or group.get("atleta") or group
            stats = group.get("statistics") or group.get("estatisticas") or group.get("stats") or {}
            if isinstance(stats, list):
                stats = stats[0] if stats else {}
            result.append({
                "player": player if isinstance(player, dict) else {"nome": str(player)},
                "team": group_team,
                "stats": stats if isinstance(stats, dict) else {},
            })

    return result


def _player_name_key(value):
    name = _player_name_from_obj(value)
    if name is None and isinstance(value, dict):
        name = value.get("nome") or value.get("name")
    if not name:
        return None
    return " ".join(str(name).strip().lower().split())


def _player_has_real_team(player):
    team = player.get("time") if isinstance(player, dict) else None
    return _valid_team_ref(team)


def migrate_player_history_teams(cache):
    """Corrige registros históricos antigos gravados como `sem_time`.

    A migração usa somente `partidas_enriquecidas` já persistidas. Quando um
    jogador antigo pode ser relacionado a uma ocorrência que contém o time,
    o registro é reindexado com a chave estável correta. Registros sem evidência
    suficiente permanecem intactos; assim, não há risco de atribuir jogador ao
    clube errado e nenhuma chamada adicional à API é feita.
    """
    history = cache.get("historico_jogadores") or {}
    if not history:
        return {"alterados": 0, "sem_time": 0}

    # nome -> ocorrências conhecidas (id/nome do time + player_id).
    evidence = {}
    for enriched in (cache.get("partidas_enriquecidas") or {}).values():
        if not isinstance(enriched, dict):
            continue
        for record in _extract_player_records(enriched):
            player = record.get("player") or {}
            team = normalize_team_ref(record.get("team") or {})
            if not _valid_team_ref(team):
                continue
            name_key = _player_name_key(player)
            if not name_key:
                continue
            evidence.setdefault(name_key, []).append({
                "player_id": _player_id_from_obj(player),
                "team": team,
            })

    new_history = {}
    changed = 0

    for old_key, player in history.items():
        if not isinstance(player, dict):
            continue

        name_key = _player_name_key(player)
        candidates = evidence.get(name_key, []) if name_key else []
        current_team = normalize_team_ref(player.get("time") or {})

        if not _valid_team_ref(current_team) and candidates:
            # Prioriza a ocorrência que possui o mesmo ID numérico do jogador.
            player_id = _player_id_from_obj(player) or player.get("jogador_id")
            same_id = [
                c for c in candidates
                if player_id is not None and c.get("player_id") is not None
                and str(c.get("player_id")) == str(player_id)
            ]
            chosen = (same_id or candidates)[-1]
            player["time"] = chosen["team"]
            current_team = chosen["team"]

        if _valid_team_ref(current_team):
            stable_id = _stable_player_id(
                {"id": player.get("jogador_id"), "nome": player.get("nome")},
                current_team,
            )
            if stable_id is None:
                stable_id = old_key
            player["jogador_id"] = stable_id
            new_key = str(stable_id)
        else:
            new_key = str(old_key)

        # Consolida duplicatas sem perder jogos.
        if new_key in new_history and new_history[new_key] is not player:
            target = new_history[new_key]
            existing_games = target.setdefault("jogos", [])
            known_matches = {str(g.get("partida_id")) for g in existing_games}
            for game in player.get("jogos") or []:
                if str(game.get("partida_id")) not in known_matches:
                    existing_games.append(game)
            if not target.get("time") and player.get("time"):
                target["time"] = player["time"]
            changed += 1
            continue

        new_history[new_key] = player
        if new_key != str(old_key):
            changed += 1

    cache["historico_jogadores"] = new_history
    remaining = sum(
        1 for p in new_history.values()
        if not _player_has_real_team(p)
    )
    return {"alterados": changed, "sem_time": remaining}


def update_team_history(cache, enriched):
    """
    Alimenta a base histórica exclusivamente a partir da partida enriquecida.
    Não chama nenhuma API e não duplica uma partida já registrada.
    """
    history = cache.setdefault("historico_times", {})
    player_history = cache.setdefault("historico_jogadores", {})

    for side in ("casa", "fora"):
        team = enriched.get("times", {}).get(side) or {}
        team_id = team.get("id")
        name = team.get("nome")
        key = str(team_id or name or "").strip()

        if not key:
            continue

        bucket = history.setdefault(
            key,
            {
                "time_id": team_id,
                "nome": name,
                "jogos": [],
            },
        )

        record = _team_history_record(enriched, side)
        match_id = record["partida_id"]

        if not any(
            str(item.get("partida_id")) == match_id
            for item in bucket["jogos"]
        ):
            bucket["jogos"].append(record)

    # Histórico individual — somente o que já veio no enriquecimento.
    for player_record in _extract_player_records(enriched):
        player = player_record.get("player") or {}
        team = player_record.get("team") or {}
        stats = player_record.get("stats") or {}

        player_id = _stable_player_id(player, team)
        if player_id is None:
            continue

        pkey = str(player_id)

        pb = player_history.setdefault(
            pkey,
            {
                "jogador_id": player_id,
                "nome": player.get("nome") or player.get("name") or player.get("nome_jogador") or f"Jogador {player_id}",
                "foto": player.get("foto") or player.get("photo"),
                "numero": player.get("numero") or player.get("camisa") or player.get("number"),
                "posicao": player.get("posicao") or player.get("position") or player.get("pos"),
                "time": team,
                "jogos": [],
            },
        )

        match_id = str(enriched.get("partida_id"))
        if any(
            str(item.get("partida_id")) == match_id
            for item in pb["jogos"]
        ):
            continue

        pb["jogos"].append({
            "partida_id": match_id,
            "data": enriched.get("data"),
            "status": enriched.get("status"),
            "estatisticas": stats,
            "titular": (
                stats.get("games", {}).get("substitute") is not True
                if isinstance(stats.get("games"), dict)
                else None
            ),
            "minutos": (
                stats.get("games", {}).get("minutes")
                if isinstance(stats.get("games"), dict)
                else None
            ),
        })


def rebuild_historical_base(cache):
    """
    Reconstrói os índices históricos SOMENTE com as partidas que já estão
    em partidas_enriquecidas. Nenhuma chamada HTTP é realizada.
    """
    cache["historico_times"] = {}
    cache["historico_jogadores"] = {}

    for enriched in (cache.get("partidas_enriquecidas") or {}).values():
        if isinstance(enriched, dict):
            # Reprocessa o JSON bruto já persistido para corrigir registros
            # antigos que foram salvos como `sem_time`. Isso não faz HTTP.
            raw = enriched.get("raw")
            if isinstance(raw, dict):
                home = extract_team_from_match(raw, "home")
                away = extract_team_from_match(raw, "away")
                lineups = extract_named_list(raw, ["escalacoes", "lineups", "lineup"])
                events = extract_named_list(raw, ["eventos", "events"])
                enriched["jogadores"] = extract_players_from_detail(
                    raw, lineups=lineups, events=events
                )
                # Mantém os times normalizados caso o parser antigo tenha
                # deixado a camada `times` incompleta.
                enriched["times"] = {"casa": home, "fora": away}
            update_team_history(cache, enriched)

    migration = migrate_player_history_teams(cache)

    return {
        "partidas": len(cache.get("partidas_enriquecidas") or {}),
        "times": len(cache.get("historico_times") or {}),
        "jogadores": len(cache.get("historico_jogadores") or {}),
        "jogadores_corrigidos": migration["alterados"],
        "jogadores_sem_time": migration["sem_time"],
    }


def summarize_team_history(cache, team_key, limit=10, venue="todos"):
    history = cache.get("historico_times") or {}
    bucket = history.get(str(team_key))

    if bucket is None:
        target = str(team_key).strip().lower()
        for item in history.values():
            if str(item.get("nome") or "").strip().lower() == target:
                bucket = item
                break

    if not bucket:
        return None

    games = list(bucket.get("jogos") or [])

    if venue == "casa":
        games = [g for g in games if g.get("mandante") is True]
    elif venue == "fora":
        games = [g for g in games if g.get("mandante") is False]

    games = games[-max(1, int(limit)):]

    finished = [
        g for g in games
        if _to_number(g.get("gols_feitos")) is not None
        and _to_number(g.get("gols_sofridos")) is not None
    ]

    wins = draws = losses = 0
    goals_for = goals_against = 0.0

    for g in finished:
        gf = float(g["gols_feitos"])
        ga = float(g["gols_sofridos"])
        goals_for += gf
        goals_against += ga

        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1

    n = len(finished)
    points = wins * 3 + draws

    averages = {}
    for metric in STAT_ALIASES:
        values = [
            _to_number((g.get("estatisticas") or {}).get(metric))
            for g in games
        ]
        values = [v for v in values if v is not None]
        averages[metric] = (
            round(sum(values) / len(values), 2)
            if values else None
        )

    return {
        "nome": bucket.get("nome"),
        "time_id": bucket.get("time_id"),
        "jogos_analisados": len(games),
        "jogos_com_placar": n,
        "vitorias": wins,
        "empates": draws,
        "derrotas": losses,
        "pontos": points,
        "aproveitamento": (
            round(points / (n * 3) * 100, 2)
            if n else None
        ),
        "gols_feitos": goals_for,
        "gols_sofridos": goals_against,
        "media_gols_feitos": (
            round(goals_for / n, 2) if n else None
        ),
        "media_gols_sofridos": (
            round(goals_against / n, 2) if n else None
        ),
        "medias_estatisticas": averages,
        "ultimos_jogos": games,
    }


def enrich_selected_match(cache, fixture_id):
    key = str(fixture_id)
    detail = cache.get("detalhes_partidas", {}).get(key)
    if detail is None:
        return None, False, "O detalhe da partida ainda não está no cache. Execute primeiro o teste de detalhe."

    enriched = enrich_match_detail(fixture_id, detail)
    cache.setdefault("partidas_enriquecidas", {})[key] = enriched
    update_team_history(cache, enriched)

    ok, error = persist_cache(
        cache,
        f"Laboratório: enriquecimento da partida {fixture_id}",
    )
    if not ok:
        return enriched, False, error
    return enriched, False, None


# ============================================================
# 6 — ENRIQUECIMENTO / BASE HISTÓRICA
# ============================================================

st.header("6. Enriquecimento da partida")

if fixture_options:
    enrich_id = st.selectbox("Partida para enriquecer", fixture_options, key="enrich_fixture")
    enriched_existing = cache.get("partidas_enriquecidas", {}).get(str(enrich_id))

    if st.button("🧬 Enriquecer e salvar na base", type="primary", use_container_width=True):
        enriched, called, error = enrich_selected_match(cache, enrich_id)
        if error:
            st.error(str(error))
        else:
            st.success("✅ Enriquecimento concluído e persistido no cache. Nenhuma nova chamada à API foi necessária.")
            st.session_state["lab_cache"] = cache
            st.json(enriched)
    elif enriched_existing:
        st.success("🟢 Esta partida já está enriquecida e pode ser recuperada do cache sem nova chamada à API.")
        st.json(enriched_existing)

    st.metric("Partidas enriquecidas", len(cache.get("partidas_enriquecidas") or {}))
    st.metric("Times na base histórica", len(cache.get("historico_times") or {}))
    st.metric("Jogadores na base histórica", len(cache.get("historico_jogadores") or {}))
else:
    st.caption("Carregue as partidas primeiro.")


# ============================================================
# 7 — BASE HISTÓRICA — TESTE DOS ANALISTAS
# ============================================================

st.divider()
st.header("7. 📊 Base Histórica — Teste dos Analistas")

st.caption(
    "Esta etapa usa somente partidas que já foram enriquecidas e persistidas. "
    "Nenhuma chamada à API é feita para calcular o histórico."
)

if st.button(
    "🔄 Reconstruir base histórica",
    type="primary",
    use_container_width=True,
):
    before_calls = int(cache.get("api_calls", 0))
    result = rebuild_historical_base(cache)
    after_calls = int(cache.get("api_calls", 0))

    ok, save_error = persist_cache(
        cache,
        "Laboratório: reconstruiu base histórica dos analistas",
    )

    if not ok:
        st.error(save_error)
    else:
        st.session_state["lab_cache"] = cache
        st.success(
            "✅ Base histórica reconstruída e persistida. "
            f"Nenhuma chamada à API foi necessária "
            f"({before_calls} → {after_calls})."
        )
        st.write(
            f"**Partidas enriquecidas:** {result['partidas']} · "
            f"**Times:** {result['times']} · "
            f"**Jogadores:** {result['jogadores']} · "
            f"**Corrigidos:** {result.get('jogadores_corrigidos', 0)} · "
            f"**Ainda sem time:** {result.get('jogadores_sem_time', 0)}"
        )

historical_teams = cache.get("historico_times") or {}

if historical_teams:
    team_labels = []
    team_by_label = {}

    for key, team in historical_teams.items():
        label = f"{team.get('nome') or 'Time'} · ID {team.get('time_id') or key}"
        team_labels.append(label)
        team_by_label[label] = key

    selected_team_label = st.selectbox(
        "🏟️ Time para analisar",
        team_labels,
        key="historical_team_select",
    )

    selected_team_key = team_by_label[selected_team_label]

    h1, h2 = st.columns(2)

    with h1:
        history_window = st.selectbox(
            "Janela",
            [5, 10, 15, 20],
            index=1,
            key="historical_window",
        )

    with h2:
        venue_filter = st.selectbox(
            "Mandante/visitante",
            ["todos", "casa", "fora"],
            key="historical_venue",
        )

    summary = summarize_team_history(
        cache,
        selected_team_key,
        limit=history_window,
        venue=venue_filter,
    )

    if summary:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Jogos", summary["jogos_analisados"])
        m2.metric("Aproveitamento", f"{summary['aproveitamento'] or 0:.1f}%")
        m3.metric("Gols feitos/jogo", summary["media_gols_feitos"] or "—")
        m4.metric("Gols sofridos/jogo", summary["media_gols_sofridos"] or "—")

        m5, m6, m7 = st.columns(3)
        m5.metric("Vitórias", summary["vitorias"])
        m6.metric("Empates", summary["empates"])
        m7.metric("Derrotas", summary["derrotas"])

        st.markdown("#### 📈 Médias estatísticas")

        stats_rows = [
            {"Estatística": name, "Média": value if value is not None else "—"}
            for name, value in summary["medias_estatisticas"].items()
        ]

        st.dataframe(
            stats_rows,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### 🧾 Partidas que alimentaram o histórico")

        game_rows = []
        for game in summary["ultimos_jogos"]:
            gf = game.get("gols_feitos")
            ga = game.get("gols_sofridos")

            if gf is not None and ga is not None:
                result_label = (
                    "V" if gf > ga
                    else "E" if gf == ga
                    else "D"
                )
            else:
                result_label = "—"

            game_rows.append({
                "Data": game.get("data") or "—",
                "Adversário": (game.get("adversario") or {}).get("nome")
                    if isinstance(game.get("adversario"), dict)
                    else game.get("adversario"),
                "Casa": "Sim" if game.get("mandante") else "Não",
                "Placar": (
                    f"{gf:g} x {ga:g}"
                    if gf is not None and ga is not None
                    else "—"
                ),
                "Resultado": result_label,
                "Partida ID": game.get("partida_id"),
            })

        st.dataframe(
            game_rows,
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("#### 👤 Jogadores na base histórica")

    players_history = cache.get("historico_jogadores") or {}
    team_players = []

    selected_team_id = historical_teams[selected_team_key].get("time_id")

    selected_team = historical_teams[selected_team_key] or {}
    selected_team_name = str(selected_team.get("nome") or "").strip().lower()

    for player in players_history.values():
        player_team = player.get("time") or {}
        player_team_id = (
            player_team.get("id")
            if isinstance(player_team, dict)
            else None
        )
        player_team_name = (
            str(player_team.get("nome") or "").strip().lower()
            if isinstance(player_team, dict) else str(player_team).strip().lower()
        )

        same_id = (
            selected_team_id is not None
            and player_team_id is not None
            and str(player_team_id) == str(selected_team_id)
        )
        same_name = bool(selected_team_name and player_team_name == selected_team_name)

        if same_id or same_name:
            team_players.append(player)

    if team_players:
        player_rows = []
        for player in team_players:
            games = player.get("jogos") or []

            minutes = [
                _to_number(g.get("minutos"))
                for g in games
                if _to_number(g.get("minutos")) is not None
            ]

            player_rows.append({
                "Jogador": player.get("nome"),
                "Jogos": len(games),
                "Minutos": sum(minutes) if minutes else "—",
            })

        st.dataframe(
            player_rows,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info(
            "Nenhum jogador desse time foi encontrado no enriquecimento "
            "disponível. Isso não gera chamada adicional à API."
        )

    # Diagnóstico específico do enriquecimento individual.
    st.markdown("#### 🔎 Diagnóstico do enriquecimento dos jogadores")
    player_count = len(players_history)
    st.write(
        f"Jogadores persistidos: **{player_count}** · "
        f"Partidas enriquecidas: **{len(cache.get('partidas_enriquecidas') or {})}**"
    )
    if player_count:
        sample = []
        for player in list(players_history.values())[:20]:
            sample.append({
                "Jogador": player.get("nome"),
                "ID": player.get("jogador_id"),
                "Jogos": len(player.get("jogos") or []),
                "Time": (player.get("time") or {}).get("nome")
                    if isinstance(player.get("time"), dict) else player.get("time"),
            })
        st.dataframe(sample, use_container_width=True, hide_index=True)

else:
    st.info(
        "Ainda não há histórico de times. "
        "Enriqueça a Vila Nova x CRB e clique em "
        "'Reconstruir base histórica'."
    )


# ============================================================
# 8 — DIAGNÓSTICO
# ====================================================

st.divider()
st.header("8. Diagnóstico")

d1, d2, d3, d4 = st.columns(4)

with d1:
    st.metric(
        "Chamadas API",
        cache.get("api_calls", 0),
    )

with d2:
    st.metric(
        "Partidas",
        len(cache.get("partidas") or []),
    )

with d3:
    st.metric(
        "Detalhes",
        len(cache.get("detalhes_partidas") or {}),
    )

with d4:
    st.metric(
        "Cache versão",
        cache.get("version", CACHE_VERSION),
    )

st.write(
    f"**Arquivo local:** `{CACHE_PATH.as_posix()}`"
)

st.write(
    f"**Última chamada:** "
    f"{cache.get('last_api_call') or '—'}"
)

st.write(
    f"**Última atualização do cache:** "
    f"{cache.get('updated_at') or '—'}"
)

if cache.get("last_error"):
    st.error(
        f"Último erro: {cache.get('last_error')}"
    )

with st.expander("🔍 JSON completo do cache"):
    st.json(cache)

st.info(
    "Este laboratório não altera o Premium. "
    "A integração só será feita depois que a cobertura da API Futebol "
    "estiver validada."
)
