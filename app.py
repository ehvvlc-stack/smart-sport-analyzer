import streamlit as st
import requests
import pandas as pd

from datetime import date, timedelta, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Smart Sports Analyzer",
    page_icon="⚽",
    layout="wide"
)


st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(180deg, #0b1020 0%, #111827 100%);
        color: #f3f4f6;
    }

    .block-container {
        max-width: 1450px;
        padding-top: 1.5rem;
        padding-bottom: 4rem;
    }

    h1, h2, h3 {
        color: #f8fafc !important;
        letter-spacing: -0.02em;
    }

    h1 {
        font-size: 3rem !important;
        font-weight: 800 !important;
    }

    p, label, span {
        color: #d1d5db;
    }

    [data-testid="stMetric"] {
        background: rgba(31, 41, 55, 0.86);
        border: 1px solid rgba(148, 163, 184, 0.16);
        border-radius: 18px;
        padding: 18px 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
    }

    [data-testid="stMetricLabel"] {
        color: #9ca3af;
    }

    [data-testid="stMetricValue"] {
        color: #ffffff;
        font-weight: 800;
    }

    button[data-baseweb="tab"] {
        border-radius: 12px 12px 0 0;
        padding: 12px 16px;
    }

    button[data-baseweb="tab"] p {
        font-weight: 650;
    }

    [data-testid="stAlert"] {
        border-radius: 16px;
    }

    [data-testid="stDataFrame"] {
        border-radius: 16px;
        overflow: hidden;
    }

    .stButton > button {
        border-radius: 12px;
        font-weight: 700;
        min-height: 44px;
    }

    hr {
        border-color: rgba(148, 163, 184, 0.15);
    }
    </style>
    """,
    unsafe_allow_html=True
)


TOKEN = st.secrets["SPORTMONKS_TOKEN"]

try:
    APIFOOTBALL_KEY = st.secrets["APIFOOTBALL_KEY"]
except Exception:
    APIFOOTBALL_KEY = ""
BASE_URL = "https://api.sportmonks.com/v3/football"
ARQUIVO_HISTORICO = Path("historico_partidas.csv")
ARQUIVO_ALERTAS = Path("historico_alertas.csv")
ARQUIVO_VALIDACAO = Path("validacao_alertas.csv")

LIGAS = {
    271: "Superliga",
    501: "Premiership",
    513: "Premiership Play-Offs",
    1659: "Superliga Play-offs"
}

FIXTURE_REPLAY = 19700205

if "historico_live" not in st.session_state:
    st.session_state.historico_live = {}

if "sim_historico" not in st.session_state:
    st.session_state.sim_historico = []

if "ultimo_nivel_alerta" not in st.session_state:
    st.session_state.ultimo_nivel_alerta = {}

if "ultimo_nivel_simulador" not in st.session_state:
    st.session_state.ultimo_nivel_simulador = None

if "demo_validacao_criada" not in st.session_state:
    st.session_state.demo_validacao_criada = False

st.title("⚽ Analisador Esportivo Inteligente")
st.caption(
    "Monitor automático de domínio geral, momento recente e alertas estatísticos"
)


def requisicao(url, params):
    try:
        resposta = requests.get(
            url,
            params=params,
            timeout=20
        )

        if resposta.status_code != 200:
            return None, resposta.status_code

        return resposta.json(), 200

    except requests.exceptions.RequestException:
        return None, -1


def buscar_fixture(
    fixture_id,
    incluir_eventos=False
):
    url = f"{BASE_URL}/fixtures/{fixture_id}"

    include = (
        "participants;"
        "scores;"
        "statistics.type;"
        "state"
    )

    if incluir_eventos:
        include += ";events.type"

    params = {
        "api_token": TOKEN,
        "include": include
    }

    dados, status = requisicao(
        url,
        params
    )

    if status != 200:
        return None

    return dados.get("data", {})


def identificar_times(jogo):
    casa = "Casa"
    visitante = "Visitante"

    ids = {
        "home": None,
        "away": None
    }

    nomes_por_id = {}

    for participante in jogo.get(
        "participants",
        []
    ):
        pid = participante.get("id")
        nome = participante.get("name", "Time")

        nomes_por_id[pid] = nome

        local = participante.get(
            "meta", {}
        ).get("location")

        if local == "home":
            casa = nome
            ids["home"] = pid

        elif local == "away":
            visitante = nome
            ids["away"] = pid

    return casa, visitante, ids, nomes_por_id


def placar_atual(jogo):
    gols_home = 0
    gols_away = 0

    for placar in jogo.get("scores", []):
        if placar.get("description") == "CURRENT":
            score = placar.get("score", {})
            lado = score.get("participant")

            if lado == "home":
                gols_home = score.get("goals", 0)

            elif lado == "away":
                gols_away = score.get("goals", 0)

    return gols_home, gols_away


def ler_estatisticas(jogo, ids):
    dados = {
        "home": {
            "possession": 0,
            "corners": 0,
            "dribbles": 0,
            "yellow": 0,
            "red": 0
        },
        "away": {
            "possession": 0,
            "corners": 0,
            "dribbles": 0,
            "yellow": 0,
            "red": 0
        }
    }

    for item in jogo.get("statistics", []):
        participant_id = item.get("participant_id")

        if participant_id == ids["home"]:
            lado = "home"

        elif participant_id == ids["away"]:
            lado = "away"

        else:
            continue

        tipo = str(
            item.get("type", {}).get("name", "")
        ).strip().lower()

        valor = item.get(
            "data", {}
        ).get("value", 0)

        try:
            valor = float(valor)
        except (TypeError, ValueError):
            valor = 0

        if "corner" in tipo or "escanteio" in tipo:
            dados[lado]["corners"] = valor

        elif "possession" in tipo or "posse" in tipo:
            dados[lado]["possession"] = valor

        elif "successful dribble" in tipo or "drible" in tipo:
            dados[lado]["dribbles"] = valor

        elif "yellowred" in tipo or "yellow-red" in tipo:
            dados[lado]["red"] += valor

        elif (
            "redcard" in tipo
            or "red card" in tipo
            or "cartão vermelho" in tipo
        ):
            dados[lado]["red"] += valor

        elif (
            "yellowcard" in tipo
            or "yellow card" in tipo
            or "cartão amarelo" in tipo
        ):
            dados[lado]["yellow"] = valor

    return dados


def participacao(a, b):
    total = a + b

    if total <= 0:
        return 50.0

    return (a / total) * 100


def calcular_indice(home, away):
    posse_h = participacao(
        home["possession"],
        away["possession"]
    )

    posse_a = 100 - posse_h

    corners_h = participacao(
        home["corners"],
        away["corners"]
    )

    corners_a = 100 - corners_h

    dribles_h = participacao(
        home["dribbles"],
        away["dribbles"]
    )

    dribles_a = 100 - dribles_h

    disciplina_h = max(
        0,
        100
        - home["yellow"] * 2
        - home["red"] * 12
    )

    disciplina_a = max(
        0,
        100
        - away["yellow"] * 2
        - away["red"] * 12
    )

    bruto_h = (
        posse_h * 0.35
        + corners_h * 0.35
        + dribles_h * 0.20
        + disciplina_h * 0.10
    )

    bruto_a = (
        posse_a * 0.35
        + corners_a * 0.35
        + dribles_a * 0.20
        + disciplina_a * 0.10
    )

    total = bruto_h + bruto_a

    if total <= 0:
        return 50.0, 50.0

    indice_h = (bruto_h / total) * 100
    indice_a = 100 - indice_h

    return round(indice_h, 1), round(indice_a, 1)


def preparar_eventos(
    jogo,
    nomes_por_id
):
    linhas = []

    for evento in jogo.get("events", []):
        minuto = (
            evento.get("minute", 0)
            or 0
        )

        extra = evento.get("extra_minute")

        participante_id = evento.get(
            "participant_id"
        )

        time = nomes_por_id.get(
            participante_id,
            "Sem time"
        )

        tipo = (
            evento.get("type", {}).get("name")
            if isinstance(
                evento.get("type"),
                dict
            )
            else None
        )

        if not tipo:
            tipo = evento.get(
                "addition",
                "Evento"
            )

        jogador = evento.get(
            "player_name",
            ""
        )

        resultado = evento.get(
            "result",
            ""
        )

        tempo = (
            f"{minuto}+{extra}'"
            if extra
            else f"{minuto}'"
        )

        linhas.append(
            {
                "minuto_num": minuto,
                "Tempo": tempo,
                "Time": time,
                "Evento": tipo,
                "Jogador": jogador,
                "Resultado": resultado
            }
        )

    linhas.sort(
        key=lambda x: x["minuto_num"]
    )

    return linhas


def pontuar_evento(evento):
    nome = str(
        evento["Evento"]
    ).lower()

    if "goal" in nome:
        return 8

    if "red" in nome:
        return -6

    if "yellow" in nome:
        return -2

    if "substitution" in nome:
        return 1

    return 1


def pressao_eventos(
    eventos,
    minuto_atual,
    casa,
    visitante,
    janela=10
):
    inicio_janela = max(
        0,
        minuto_atual - janela
    )

    recentes = [
        e
        for e in eventos
        if inicio_janela
        < e["minuto_num"]
        <= minuto_atual
    ]

    pontos_casa = 0
    pontos_visitante = 0

    for evento in recentes:
        pontos = pontuar_evento(
            evento
        )

        if evento["Time"] == casa:
            pontos_casa += pontos

        elif evento["Time"] == visitante:
            pontos_visitante += pontos

    positivos_casa = max(
        0,
        pontos_casa
    )

    positivos_visitante = max(
        0,
        pontos_visitante
    )

    soma = (
        positivos_casa
        + positivos_visitante
    )

    if soma == 0:
        indice_casa = 50
        indice_visitante = 50

    else:
        indice_casa = (
            positivos_casa / soma
        ) * 100

        indice_visitante = (
            100 - indice_casa
        )

    diferenca = (
        pontos_casa
        - pontos_visitante
    )

    if diferenca >= 6:
        leitura = (
            f"🔥 Momento recente forte: {casa}"
        )

    elif diferenca <= -6:
        leitura = (
            f"🔥 Momento recente forte: {visitante}"
        )

    elif diferenca >= 3:
        leitura = (
            f"📈 Momento recente favorável: {casa}"
        )

    elif diferenca <= -3:
        leitura = (
            f"📈 Momento recente favorável: {visitante}"
        )

    else:
        leitura = (
            "⚖️ Momento recente equilibrado"
        )

    return {
        "indice_casa": round(
            indice_casa,
            1
        ),
        "indice_visitante": round(
            indice_visitante,
            1
        ),
        "pontos_casa": pontos_casa,
        "pontos_visitante": pontos_visitante,
        "leitura": leitura,
        "recentes": recentes
    }


def minuto_estimado(jogo):
    estado = jogo.get(
        "state",
        {}
    )

    minuto = estado.get(
        "clock",
        None
    )

    if isinstance(minuto, dict):
        minuto = minuto.get(
            "minute"
        )

    if minuto is None:
        minuto = estado.get(
            "minute"
        )

    try:
        return int(minuto)
    except:
        return 90


def combinar_indices(
    dominio_h,
    dominio_a,
    momento_h,
    momento_a,
    home=None,
    away=None
):
    combinado_h = (
        dominio_h * 0.70
        + momento_h * 0.30
    )

    combinado_a = (
        dominio_a * 0.70
        + momento_a * 0.30
    )

    total = (
        combinado_h
        + combinado_a
    )

    if total <= 0:
        return 50.0, 50.0

    final_h = (
        combinado_h / total
    ) * 100

    final_a = (
        100 - final_h
    )

    return (
        round(final_h, 1),
        round(final_a, 1)
    )



def gerar_alerta_hibrido(
    casa,
    visitante,
    combinado_h,
    combinado_a,
    momento_h,
    momento_a,
    home,
    away
):
    """
    Alerta experimental de intensidade estatística.
    Não é previsão de gol nem recomendação de aposta.
    """

    if combinado_h >= combinado_a:
        time = casa
        indice = combinado_h
        momento = momento_h
        stats_time = home
        stats_adv = away
    else:
        time = visitante
        indice = combinado_a
        momento = momento_a
        stats_time = away
        stats_adv = home

    vantagem_corners = (
        stats_time["corners"] - stats_adv["corners"]
    )

    posse = stats_time["possession"]

    if (
        indice >= 62
        and momento >= 65
        and (
            posse >= 55
            or vantagem_corners >= 2
        )
    ):
        return {
            "nivel": "ALTA",
            "icone": "🔥",
            "texto": (
                f"Pressão estatística consistente de {time}: "
                f"índice geral {indice:.1f}% e momento recente {momento:.1f}%."
            )
        }

    if (
        indice >= 57
        and momento >= 60
    ):
        return {
            "nivel": "MÉDIA",
            "icone": "📈",
            "texto": (
                f"{time} apresenta vantagem estatística recente "
                f"({indice:.1f}% no índice geral)."
            )
        }

    return {
        "nivel": "BAIXA",
        "icone": "⚖️",
        "texto": (
            "Sem sinal estatístico forte neste momento."
        )
    }


def salvar_no_csv(
    fixture_id,
    casa,
    visitante,
    gols_h,
    gols_a,
    indice_h,
    indice_a,
    home,
    away
):
    linha = pd.DataFrame(
        [
            {
                "data_hora":
                    datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),

                "fixture_id":
                    fixture_id,

                "casa":
                    casa,

                "visitante":
                    visitante,

                "gols_casa":
                    gols_h,

                "gols_visitante":
                    gols_a,

                "indice_casa":
                    indice_h,

                "indice_visitante":
                    indice_a,

                "posse_casa":
                    home["possession"],

                "posse_visitante":
                    away["possession"],

                "escanteios_casa":
                    home["corners"],

                "escanteios_visitante":
                    away["corners"]
            }
        ]
    )

    if ARQUIVO_HISTORICO.exists():
        linha.to_csv(
            ARQUIVO_HISTORICO,
            mode="a",
            header=False,
            index=False
        )

    else:
        linha.to_csv(
            ARQUIVO_HISTORICO,
            index=False
        )


def registrar_live(
    fixture_id,
    casa,
    visitante,
    gols_h,
    gols_a,
    indice_h,
    indice_a,
    home,
    away
):
    if fixture_id not in st.session_state.historico_live:
        st.session_state.historico_live[
            fixture_id
        ] = []

    historico = st.session_state.historico_live[
        fixture_id
    ]

    snapshot = {
        "hora":
            datetime.now().strftime(
                "%H:%M:%S"
            ),
        "indice_home":
            indice_h,
        "indice_away":
            indice_a
    }

    if historico:
        ultimo = historico[-1]

        if (
            ultimo["indice_home"]
            == snapshot["indice_home"]
            and
            ultimo["indice_away"]
            == snapshot["indice_away"]
        ):
            return

    historico.append(snapshot)

    salvar_no_csv(
        fixture_id,
        casa,
        visitante,
        gols_h,
        gols_a,
        indice_h,
        indice_a,
        home,
        away
    )

    if len(historico) > 40:
        st.session_state.historico_live[
            fixture_id
        ] = historico[-40:]



def classificar_pressao_live(
    combinado_h,
    combinado_a,
    momento_h,
    momento_a,
    casa,
    visitante
):
    if combinado_h >= combinado_a:
        dominante = casa
        indice = combinado_h
        momento = momento_h
    else:
        dominante = visitante
        indice = combinado_a
        momento = momento_a

    diferenca = abs(combinado_h - combinado_a)

    if diferenca >= 25 and momento >= 65:
        return "ALTA", "🔥", dominante

    if diferenca >= 12 and momento >= 58:
        return "MODERADA", "📈", dominante

    return "BAIXA", "⚖️", dominante


def barra_pressao_html(
    casa,
    visitante,
    valor_casa,
    valor_visitante
):
    total = valor_casa + valor_visitante

    if total <= 0:
        pct_casa = 50
        pct_visitante = 50
    else:
        pct_casa = (valor_casa / total) * 100
        pct_visitante = 100 - pct_casa

    st.markdown(
        f"""
        <div style="
            display:flex;
            width:100%;
            height:18px;
            border-radius:999px;
            overflow:hidden;
            border:1px solid rgba(148,163,184,0.20);
            margin:8px 0 4px 0;
        ">
            <div style="
                width:{pct_casa:.1f}%;
                background:#ef4444;
            "></div>
            <div style="
                width:{pct_visitante:.1f}%;
                background:#3b82f6;
            "></div>
        </div>
        <div style="
            display:flex;
            justify-content:space-between;
            font-size:0.88rem;
            color:#94a3b8;
            margin-bottom:14px;
        ">
            <span>{casa} {pct_casa:.1f}%</span>
            <span>{pct_visitante:.1f}% {visitante}</span>
        </div>
        """,
        unsafe_allow_html=True
    )



def ler_alertas_historico():
    colunas = [
        "data_hora",
        "fixture_id",
        "jogo",
        "minuto",
        "placar",
        "nivel_anterior",
        "nivel_novo",
        "time_destaque",
        "indice",
        "momento_10_min",
        "qualidade_score",
        "qualidade_nivel",
        "origem"
    ]

    if not ARQUIVO_ALERTAS.exists():
        return pd.DataFrame(columns=colunas)

    try:
        df = pd.read_csv(ARQUIVO_ALERTAS)
    except Exception:
        return pd.DataFrame(columns=colunas)

    for coluna in colunas:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[colunas]


def salvar_alerta_csv(
    fixture_id,
    casa,
    visitante,
    minuto,
    placar,
    nivel_anterior,
    nivel_novo,
    dominante,
    indice,
    momento,
    posse_dominante=50,
    vantagem_escanteios=0,
    origem="REAL"
):
    qualidade = calcular_qualidade_alerta(
        indice,
        momento,
        posse_dominante,
        vantagem_escanteios
    )

    linha = pd.DataFrame(
        [
            {
                "data_hora": datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fixture_id": fixture_id,
                "jogo": f"{casa} x {visitante}",
                "minuto": minuto,
                "placar": placar,
                "nivel_anterior": nivel_anterior,
                "nivel_novo": nivel_novo,
                "time_destaque": dominante,
                "indice": round(indice, 1),
                "momento_10_min": round(momento, 1),
                "qualidade_score": qualidade["score"],
                "qualidade_nivel": qualidade["nivel"],
                "origem": origem
            }
        ]
    )

    historico = ler_alertas_historico()

    historico = pd.concat(
        [historico, linha],
        ignore_index=True
    )

    historico.to_csv(
        ARQUIVO_ALERTAS,
        index=False
    )



def registrar_transicao_alerta(
    fixture_id,
    casa,
    visitante,
    minuto,
    gols_h,
    gols_a,
    nivel,
    dominante,
    combinado_h,
    combinado_a,
    momento_h,
    momento_a,
    home=None,
    away=None
):
    anterior = st.session_state.ultimo_nivel_alerta.get(
        fixture_id
    )

    st.session_state.ultimo_nivel_alerta[
        fixture_id
    ] = nivel

    if anterior is None:
        if nivel == "ALTA":
            if combinado_h >= combinado_a:
                indice = combinado_h
                momento = momento_h
            else:
                indice = combinado_a
                momento = momento_a

            posse_dominante = 50
            vantagem_escanteios = 0

            if home is not None and away is not None:
                if combinado_h >= combinado_a:
                    posse_dominante = home.get(
                        "possession",
                        50
                    )
                    vantagem_escanteios = (
                        home.get("corners", 0)
                        - away.get("corners", 0)
                    )
                else:
                    posse_dominante = away.get(
                        "possession",
                        50
                    )
                    vantagem_escanteios = (
                        away.get("corners", 0)
                        - home.get("corners", 0)
                    )

            salvar_alerta_csv(
                fixture_id,
                casa,
                visitante,
                minuto,
                f"{gols_h} x {gols_a}",
                "INICIAL",
                nivel,
                dominante,
                indice,
                momento,
                posse_dominante,
                vantagem_escanteios,
                "REAL"
            )

            criar_validacao_alerta_alta(
                fixture_id,
                casa,
                visitante,
                minuto,
                gols_h,
                gols_a,
                dominante,
                indice,
                momento,
                posse_dominante,
                vantagem_escanteios
            )

        return

    if anterior == nivel:
        return

    if combinado_h >= combinado_a:
        indice = combinado_h
        momento = momento_h
    else:
        indice = combinado_a
        momento = momento_a

    posse_dominante = 50
    vantagem_escanteios = 0

    if home is not None and away is not None:
        if combinado_h >= combinado_a:
            posse_dominante = home.get(
                "possession",
                50
            )
            vantagem_escanteios = (
                home.get("corners", 0)
                - away.get("corners", 0)
            )
        else:
            posse_dominante = away.get(
                "possession",
                50
            )
            vantagem_escanteios = (
                away.get("corners", 0)
                - home.get("corners", 0)
            )

    salvar_alerta_csv(
        fixture_id,
        casa,
        visitante,
        minuto,
        f"{gols_h} x {gols_a}",
        anterior,
        nivel,
        dominante,
        indice,
        momento,
        posse_dominante,
        vantagem_escanteios,
        "REAL"
    )

    if nivel == "ALTA":
        criar_validacao_alerta_alta(
            fixture_id,
            casa,
            visitante,
            minuto,
            gols_h,
            gols_a,
            dominante,
            indice,
            momento,
            posse_dominante,
            vantagem_escanteios
        )




def ler_validacoes():
    colunas = [
        "id_alerta",
        "data_hora_alerta",
        "fixture_id",
        "jogo",
        "minuto_alerta",
        "placar_alerta",
        "time_destaque",
        "indice_alerta",
        "momento_10_min",
        "qualidade_score",
        "qualidade_nivel",
        "gol_ate_5_min",
        "gol_ate_10_min",
        "time_gol",
        "minuto_gol",
        "minutos_apos_alerta",
        "resultado_gol",
        "gol_time_destaque_5_min",
        "gol_time_destaque_10_min",
        "escanteio_ate_5_min",
        "escanteio_ate_10_min",
        "escanteio_time_destaque_5_min",
        "escanteio_time_destaque_10_min",
        "primeiro_escanteio_time",
        "primeiro_escanteio_minuto",
        "minutos_ate_escanteio",
        "status"
    ]

    if not ARQUIVO_VALIDACAO.exists():
        return pd.DataFrame(columns=colunas)

    try:
        df = pd.read_csv(ARQUIVO_VALIDACAO)
    except Exception:
        return pd.DataFrame(columns=colunas)

    for coluna in colunas:
        if coluna not in df.columns:
            df[coluna] = ""

    return df[colunas]


def salvar_validacoes(df):
    df.to_csv(
        ARQUIVO_VALIDACAO,
        index=False
    )


def criar_validacao_alerta_alta(
    fixture_id,
    casa,
    visitante,
    minuto,
    gols_h,
    gols_a,
    dominante,
    indice,
    momento,
    posse_dominante=50,
    vantagem_escanteios=0
):
    df = ler_validacoes()

    if not df.empty:
        fixture_num = pd.to_numeric(
            df["fixture_id"],
            errors="coerce"
        )

        minuto_num = pd.to_numeric(
            df["minuto_alerta"],
            errors="coerce"
        )

        duplicado = (
            (fixture_num == fixture_id)
            & (minuto_num == minuto)
            & (df["status"].astype(str) != "DEMO")
        ).any()

        if duplicado:
            return

    agora = datetime.now()

    qualidade = calcular_qualidade_alerta(
        indice,
        momento,
        posse_dominante,
        vantagem_escanteios
    )

    id_alerta = (
        f"{fixture_id}-"
        f"{agora.strftime('%Y%m%d%H%M%S')}"
    )

    nova = pd.DataFrame(
        [
            {
                "id_alerta": id_alerta,
                "data_hora_alerta": agora.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fixture_id": fixture_id,
                "jogo": f"{casa} x {visitante}",
                "minuto_alerta": minuto,
                "placar_alerta": f"{gols_h} x {gols_a}",
                "time_destaque": dominante,
                "indice_alerta": round(indice, 1),
                "momento_10_min": round(momento, 1),
                "qualidade_score": qualidade["score"],
                "qualidade_nivel": qualidade["nivel"],
                "gol_ate_5_min": "PENDENTE",
                "gol_ate_10_min": "PENDENTE",
                "time_gol": "",
                "minuto_gol": "",
                "minutos_apos_alerta": "",
                "resultado_gol": "PENDENTE",
                "gol_time_destaque_5_min": "PENDENTE",
                "gol_time_destaque_10_min": "PENDENTE",
                "escanteio_ate_5_min": "PENDENTE",
                "escanteio_ate_10_min": "PENDENTE",
                "escanteio_time_destaque_5_min": "PENDENTE",
                "escanteio_time_destaque_10_min": "PENDENTE",
                "primeiro_escanteio_time": "",
                "primeiro_escanteio_minuto": "",
                "minutos_ate_escanteio": "",
                "status": "ACOMPANHANDO"
            }
        ]
    )

    df = pd.concat(
        [df, nova],
        ignore_index=True
    )

    salvar_validacoes(df)


def atualizar_validacoes_jogo(
    fixture_id,
    minuto_atual,
    eventos
):
    df = ler_validacoes()

    if df.empty:
        return

    fixture_num = pd.to_numeric(
        df["fixture_id"],
        errors="coerce"
    )

    indices = df.index[
        (fixture_num == fixture_id)
        & (df["status"].astype(str) == "ACOMPANHANDO")
    ].tolist()

    if not indices:
        return

    alterou = False

    for idx in indices:
        try:
            minuto_alerta = int(
                float(df.at[idx, "minuto_alerta"])
            )
        except Exception:
            continue

        time_destaque = str(
            df.at[idx, "time_destaque"]
        )

        gols_depois = []

        for evento in eventos:
            nome = str(
                evento.get("Evento", "")
            ).lower()

            if "goal" not in nome:
                continue

            try:
                minuto_evento = int(
                    evento.get("minuto_num", 0)
                )
            except Exception:
                continue

            if (
                minuto_alerta
                < minuto_evento
                <= minuto_alerta + 10
            ):
                gols_depois.append(evento)

        gols_depois.sort(
            key=lambda e: e.get(
                "minuto_num",
                999
            )
        )

        primeiro_gol = (
            gols_depois[0]
            if gols_depois
            else None
        )

        # Escanteios após o alerta
        escanteios_depois = []

        for evento in eventos:
            nome_evento = str(
                evento.get("Evento", "")
            ).lower()

            if (
                "corner" not in nome_evento
                and "escanteio" not in nome_evento
            ):
                continue

            try:
                minuto_evento = int(
                    evento.get("minuto_num", 0)
                )
            except Exception:
                continue

            if (
                minuto_alerta
                < minuto_evento
                <= minuto_alerta + 10
            ):
                escanteios_depois.append(evento)

        escanteios_depois.sort(
            key=lambda e: e.get("minuto_num", 999)
        )

        primeiro_escanteio = (
            escanteios_depois[0]
            if escanteios_depois
            else None
        )

        if primeiro_escanteio:
            minuto_corner = int(
                primeiro_escanteio.get("minuto_num", 0)
            )
            delta_corner = minuto_corner - minuto_alerta
            time_corner = str(
                primeiro_escanteio.get("Time", "")
            )
            corner_destaque = (
                time_corner == time_destaque
            )

            df.at[idx, "primeiro_escanteio_time"] = time_corner
            df.at[idx, "primeiro_escanteio_minuto"] = minuto_corner
            df.at[idx, "minutos_ate_escanteio"] = delta_corner

            if delta_corner <= 5:
                df.at[idx, "escanteio_ate_5_min"] = "SIM"
                df.at[
                    idx,
                    "escanteio_time_destaque_5_min"
                ] = "SIM" if corner_destaque else "NÃO"

            if delta_corner <= 10:
                df.at[idx, "escanteio_ate_10_min"] = "SIM"
                df.at[
                    idx,
                    "escanteio_time_destaque_10_min"
                ] = "SIM" if corner_destaque else "NÃO"

            alterou = True

        else:
            if (
                minuto_atual >= minuto_alerta + 5
                and str(
                    df.at[idx, "escanteio_ate_5_min"]
                ) == "PENDENTE"
            ):
                df.at[idx, "escanteio_ate_5_min"] = "NÃO"
                df.at[
                    idx,
                    "escanteio_time_destaque_5_min"
                ] = "NÃO"
                alterou = True

            if (
                minuto_atual >= minuto_alerta + 10
                and str(
                    df.at[idx, "escanteio_ate_10_min"]
                ) == "PENDENTE"
            ):
                df.at[idx, "escanteio_ate_10_min"] = "NÃO"
                df.at[
                    idx,
                    "escanteio_time_destaque_10_min"
                ] = "NÃO"
                alterou = True

        if primeiro_gol:
            minuto_gol = int(
                primeiro_gol.get(
                    "minuto_num",
                    0
                )
            )

            delta = (
                minuto_gol
                - minuto_alerta
            )

            time_gol = str(
                primeiro_gol.get(
                    "Time",
                    ""
                )
            )

            marcou_destaque = (
                time_gol == time_destaque
            )

            df.at[idx, "time_gol"] = time_gol
            df.at[idx, "minuto_gol"] = minuto_gol
            df.at[idx, "minutos_apos_alerta"] = delta

            if marcou_destaque:
                df.at[idx, "resultado_gol"] = "TIME_DESTAQUE"
            else:
                df.at[idx, "resultado_gol"] = "ADVERSARIO"

            if delta <= 5:
                df.at[idx, "gol_ate_5_min"] = "SIM"

                df.at[
                    idx,
                    "gol_time_destaque_5_min"
                ] = (
                    "SIM"
                    if marcou_destaque
                    else "NÃO"
                )

            if delta <= 10:
                df.at[idx, "gol_ate_10_min"] = "SIM"

                df.at[
                    idx,
                    "gol_time_destaque_10_min"
                ] = (
                    "SIM"
                    if marcou_destaque
                    else "NÃO"
                )

            df.at[idx, "status"] = "VALIDADO_COM_GOL"
            alterou = True

        else:
            if (
                minuto_atual >= minuto_alerta + 5
                and str(
                    df.at[
                        idx,
                        "gol_ate_5_min"
                    ]
                ) == "PENDENTE"
            ):
                df.at[idx, "gol_ate_5_min"] = "NÃO"
                df.at[
                    idx,
                    "gol_time_destaque_5_min"
                ] = "NÃO"
                alterou = True

            if minuto_atual >= minuto_alerta + 10:
                df.at[idx, "gol_ate_10_min"] = "NÃO"
                df.at[
                    idx,
                    "gol_time_destaque_10_min"
                ] = "NÃO"
                df.at[idx, "resultado_gol"] = "SEM_GOL"
                df.at[idx, "status"] = "ENCERRADO_SEM_GOL"
                alterou = True

    if alterou:
        salvar_validacoes(df)


def criar_demo_validacao():
    df = ler_validacoes()

    if (
        not df.empty
        and (
            df["status"].astype(str)
            == "DEMO"
        ).any()
    ):
        return False

    agora = datetime.now()

    demo = pd.DataFrame(
        [
            {
                "id_alerta": "DEMO-ALTA",
                "data_hora_alerta": agora.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fixture_id": 0,
                "jogo": "Time A x Time B",
                "minuto_alerta": 60,
                "placar_alerta": "0 x 0",
                "time_destaque": "Time A",
                "indice_alerta": 68.1,
                "momento_10_min": 70.0,
                "qualidade_score": 72.5,
                "qualidade_nivel": "MUITO FORTE",
                "gol_ate_5_min": "SIM",
                "gol_ate_10_min": "SIM",
                "time_gol": "Time A",
                "minuto_gol": 64,
                "minutos_apos_alerta": 4,
                "resultado_gol": "TIME_DESTAQUE",
                "gol_time_destaque_5_min": "SIM",
                "gol_time_destaque_10_min": "SIM",
                "escanteio_ate_5_min": "SIM",
                "escanteio_ate_10_min": "SIM",
                "escanteio_time_destaque_5_min": "SIM",
                "escanteio_time_destaque_10_min": "SIM",
                "primeiro_escanteio_time": "Time A",
                "primeiro_escanteio_minuto": 62,
                "minutos_ate_escanteio": 2,
                "status": "DEMO"
            }
        ]
    )

    df = pd.concat(
        [df, demo],
        ignore_index=True
    )

    salvar_validacoes(df)
    return True



def criar_demo_gol_adversario():
    df = ler_validacoes()

    if (
        not df.empty
        and (
            df["id_alerta"].astype(str)
            == "DEMO-ADVERSARIO"
        ).any()
    ):
        return False

    agora = datetime.now()

    demo = pd.DataFrame(
        [
            {
                "id_alerta": "DEMO-ADVERSARIO",
                "data_hora_alerta": agora.strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "fixture_id": 0,
                "jogo": "Time A x Time B",
                "minuto_alerta": 70,
                "placar_alerta": "1 x 0",
                "time_destaque": "Time A",
                "indice_alerta": 66.0,
                "momento_10_min": 68.0,
                "qualidade_score": 66.0,
                "qualidade_nivel": "MUITO FORTE",
                "gol_ate_5_min": "SIM",
                "gol_ate_10_min": "SIM",
                "time_gol": "Time B",
                "minuto_gol": 73,
                "minutos_apos_alerta": 3,
                "resultado_gol": "ADVERSARIO",
                "gol_time_destaque_5_min": "NÃO",
                "gol_time_destaque_10_min": "NÃO",
                "escanteio_ate_5_min": "SIM",
                "escanteio_ate_10_min": "SIM",
                "escanteio_time_destaque_5_min": "NÃO",
                "escanteio_time_destaque_10_min": "NÃO",
                "primeiro_escanteio_time": "Time B",
                "primeiro_escanteio_minuto": 72,
                "minutos_ate_escanteio": 2,
                "status": "DEMO"
            }
        ]
    )

    df = pd.concat(
        [df, demo],
        ignore_index=True
    )

    salvar_validacoes(df)
    return True


def limpar_demo_validacao():
    df = ler_validacoes()

    if df.empty:
        return

    df = df[
        df["status"].astype(str)
        != "DEMO"
    ].copy()

    salvar_validacoes(df)



def classificar_resultado_validacao(row):
    resultado = str(
        row.get("resultado_gol", "")
    )

    if resultado == "TIME_DESTAQUE":
        return "🟢 GOL DO TIME EM DESTAQUE"

    if resultado == "ADVERSARIO":
        return "🔴 GOL DO ADVERSÁRIO"

    if resultado == "SEM_GOL":
        return "⚪ NENHUM GOL"

    return "⏳ EM ACOMPANHAMENTO"


def resumo_resultados_validacao(df):
    if df.empty:
        return {
            "total": 0,
            "gol_destaque": 0,
            "gol_adversario": 0,
            "sem_gol": 0,
            "pendentes": 0,
            "taxa_destaque": 0.0,
            "taxa_adversario": 0.0,
            "taxa_sem_gol": 0.0
        }

    resultados = df[
        "resultado_gol"
    ].astype(str)

    gol_destaque = int(
        (resultados == "TIME_DESTAQUE").sum()
    )

    gol_adversario = int(
        (resultados == "ADVERSARIO").sum()
    )

    sem_gol = int(
        (resultados == "SEM_GOL").sum()
    )

    concluidos = (
        gol_destaque
        + gol_adversario
        + sem_gol
    )

    pendentes = max(
        0,
        len(df) - concluidos
    )

    if concluidos > 0:
        taxa_destaque = (
            gol_destaque / concluidos
        ) * 100

        taxa_adversario = (
            gol_adversario / concluidos
        ) * 100

        taxa_sem_gol = (
            sem_gol / concluidos
        ) * 100
    else:
        taxa_destaque = 0.0
        taxa_adversario = 0.0
        taxa_sem_gol = 0.0

    return {
        "total": len(df),
        "gol_destaque": gol_destaque,
        "gol_adversario": gol_adversario,
        "sem_gol": sem_gol,
        "pendentes": pendentes,
        "taxa_destaque": taxa_destaque,
        "taxa_adversario": taxa_adversario,
        "taxa_sem_gol": taxa_sem_gol
    }


def tabela_faixas_desempenho(df):
    if df.empty:
        return pd.DataFrame()

    base = df.copy()

    base["indice_alerta_num"] = pd.to_numeric(
        base["indice_alerta"],
        errors="coerce"
    )

    base["momento_10_min_num"] = pd.to_numeric(
        base["momento_10_min"],
        errors="coerce"
    )

    base = base[
        base["resultado_gol"]
        .astype(str)
        .isin(
            [
                "TIME_DESTAQUE",
                "ADVERSARIO",
                "SEM_GOL"
            ]
        )
    ].copy()

    if base.empty:
        return pd.DataFrame()

    def faixa_indice(valor):
        if pd.isna(valor):
            return "Sem dado"
        if valor < 60:
            return "< 60"
        if valor < 65:
            return "60–64,9"
        if valor < 70:
            return "65–69,9"
        return "70+"

    def faixa_momento(valor):
        if pd.isna(valor):
            return "Sem dado"
        if valor < 60:
            return "< 60"
        if valor < 70:
            return "60–69,9"
        if valor < 80:
            return "70–79,9"
        return "80+"

    base["Faixa índice"] = base[
        "indice_alerta_num"
    ].apply(
        faixa_indice
    )

    base["Faixa momento"] = base[
        "momento_10_min_num"
    ].apply(
        faixa_momento
    )

    linhas = []

    for criterio, coluna in [
        ("Índice", "Faixa índice"),
        ("Momento 10 min", "Faixa momento")
    ]:
        for faixa, grupo in base.groupby(
            coluna,
            dropna=False
        ):
            total = len(grupo)

            destaque = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "TIME_DESTAQUE"
                ).sum()
            )

            adversario = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "ADVERSARIO"
                ).sum()
            )

            sem_gol = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "SEM_GOL"
                ).sum()
            )

            taxa = (
                destaque / total * 100
                if total > 0
                else 0
            )

            linhas.append(
                {
                    "Critério": criterio,
                    "Faixa": faixa,
                    "Alertas concluídos": total,
                    "Gol destaque": destaque,
                    "Gol adversário": adversario,
                    "Sem gol": sem_gol,
                    "Taxa gol destaque": round(
                        taxa,
                        1
                    )
                }
            )

    return pd.DataFrame(
        linhas
    )



def calcular_qualidade_alerta(
    indice,
    momento,
    posse=50,
    vantagem_escanteios=0
):
    """
    Índice experimental de qualidade do alerta.
    Ele NÃO é calibrado historicamente ainda.
    Serve como uma pontuação inicial para comparar alertas.
    """

    try:
        indice = float(indice)
    except Exception:
        indice = 50.0

    try:
        momento = float(momento)
    except Exception:
        momento = 50.0

    try:
        posse = float(posse)
    except Exception:
        posse = 50.0

    try:
        vantagem_escanteios = float(
            vantagem_escanteios
        )
    except Exception:
        vantagem_escanteios = 0.0

    pontos_indice = max(
        0,
        min(
            40,
            (indice - 50) * 2
        )
    )

    pontos_momento = max(
        0,
        min(
            35,
            (momento - 50) * 1.75
        )
    )

    pontos_posse = max(
        0,
        min(
            15,
            (posse - 50) * 1.0
        )
    )

    pontos_corners = max(
        0,
        min(
            10,
            vantagem_escanteios * 2.5
        )
    )

    score = (
        pontos_indice
        + pontos_momento
        + pontos_posse
        + pontos_corners
    )

    score = round(
        max(
            0,
            min(
                100,
                score
            )
        ),
        1
    )

    if score >= 80:
        nivel = "EXCEPCIONAL"
        icone = "🔥"
        estrelas = "⭐⭐⭐⭐"
    elif score >= 65:
        nivel = "MUITO FORTE"
        icone = "🚀"
        estrelas = "⭐⭐⭐"
    elif score >= 50:
        nivel = "FORTE"
        icone = "📈"
        estrelas = "⭐⭐"
    else:
        nivel = "COMUM"
        icone = "⚖️"
        estrelas = "⭐"

    return {
        "score": score,
        "nivel": nivel,
        "icone": icone,
        "estrelas": estrelas
    }


def resumo_qualidade_historica(df):
    """
    Resume desempenho real por faixa de qualidade.
    Usa somente registros concluídos e não-DEMO.
    """
    if df.empty:
        return pd.DataFrame()

    base = df.copy()

    if "qualidade_score" not in base.columns:
        return pd.DataFrame()

    base["qualidade_score_num"] = pd.to_numeric(
        base["qualidade_score"],
        errors="coerce"
    )

    base = base[
        base["resultado_gol"]
        .astype(str)
        .isin(
            [
                "TIME_DESTAQUE",
                "ADVERSARIO",
                "SEM_GOL"
            ]
        )
    ].copy()

    if base.empty:
        return pd.DataFrame()

    def faixa(score):
        if pd.isna(score):
            return "Sem score"
        if score >= 80:
            return "80–100 Excepcional"
        if score >= 65:
            return "65–79,9 Muito forte"
        if score >= 50:
            return "50–64,9 Forte"
        return "<50 Comum"

    base["Faixa qualidade"] = base[
        "qualidade_score_num"
    ].apply(faixa)

    linhas = []

    for faixa_nome, grupo in base.groupby(
        "Faixa qualidade",
        dropna=False
    ):
        total = len(grupo)

        gols_destaque = int(
            (
                grupo["resultado_gol"]
                .astype(str)
                == "TIME_DESTAQUE"
            ).sum()
        )

        gols_adversario = int(
            (
                grupo["resultado_gol"]
                .astype(str)
                == "ADVERSARIO"
            ).sum()
        )

        sem_gol = int(
            (
                grupo["resultado_gol"]
                .astype(str)
                == "SEM_GOL"
            ).sum()
        )

        corners_destaque = 0

        if (
            "escanteio_time_destaque_10_min"
            in grupo.columns
        ):
            corners_destaque = int(
                (
                    grupo[
                        "escanteio_time_destaque_10_min"
                    ].astype(str)
                    == "SIM"
                ).sum()
            )

        taxa_gol = (
            gols_destaque / total * 100
            if total > 0
            else 0
        )

        taxa_corner = (
            corners_destaque / total * 100
            if total > 0
            else 0
        )

        linhas.append(
            {
                "Faixa qualidade": faixa_nome,
                "Alertas concluídos": total,
                "Gol destaque": gols_destaque,
                "Gol adversário": gols_adversario,
                "Sem gol": sem_gol,
                "Taxa gol destaque": round(
                    taxa_gol,
                    1
                ),
                "Taxa corner destaque ≤10 min": round(
                    taxa_corner,
                    1
                )
            }
        )

    return pd.DataFrame(linhas)



def painel_desempenho_real(df_validacao):
    """
    Monta métricas apenas com registros REAIS e concluídos.
    Ignora DEMO e registros ainda pendentes.
    """

    if df_validacao.empty:
        return

    reais = df_validacao[
        df_validacao["status"].astype(str)
        != "DEMO"
    ].copy()

    if reais.empty:
        st.info(
            "Ainda não existem validações REAIS para calcular desempenho."
        )
        return

    concluidos = reais[
        reais["resultado_gol"]
        .astype(str)
        .isin(
            [
                "TIME_DESTAQUE",
                "ADVERSARIO",
                "SEM_GOL"
            ]
        )
    ].copy()

    pendentes = len(reais) - len(concluidos)

    st.write(
        "### 📊 Desempenho dos alertas REAIS"
    )

    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Alertas REAIS",
        len(reais)
    )

    m2.metric(
        "Concluídos",
        len(concluidos)
    )

    m3.metric(
        "Pendentes",
        pendentes
    )

    m4.metric(
        "Amostra concluída",
        (
            f"{(len(concluidos) / len(reais) * 100):.1f}%"
            if len(reais) > 0
            else "0.0%"
        )
    )

    if concluidos.empty:
        st.info(
            "Os alertas reais ainda estão em acompanhamento. "
            "As taxas aparecerão quando houver registros concluídos."
        )
        return

    resultados = concluidos[
        "resultado_gol"
    ].astype(str)

    gols_destaque = int(
        (resultados == "TIME_DESTAQUE").sum()
    )

    gols_adversario = int(
        (resultados == "ADVERSARIO").sum()
    )

    sem_gol = int(
        (resultados == "SEM_GOL").sum()
    )

    total = len(concluidos)

    taxa_destaque = (
        gols_destaque / total * 100
        if total > 0
        else 0
    )

    taxa_adversario = (
        gols_adversario / total * 100
        if total > 0
        else 0
    )

    taxa_sem_gol = (
        sem_gol / total * 100
        if total > 0
        else 0
    )

    g1, g2, g3 = st.columns(3)

    g1.metric(
        "🟢 Gol do destaque",
        f"{gols_destaque} ({taxa_destaque:.1f}%)"
    )

    g2.metric(
        "🔴 Gol do adversário",
        f"{gols_adversario} ({taxa_adversario:.1f}%)"
    )

    g3.metric(
        "⚪ Sem gol",
        f"{sem_gol} ({taxa_sem_gol:.1f}%)"
    )

    # Escanteios do time em destaque.
    if (
        "escanteio_time_destaque_5_min"
        in concluidos.columns
    ):
        base_corner5 = concluidos[
            concluidos[
                "escanteio_time_destaque_5_min"
            ]
            .astype(str)
            .isin(["SIM", "NÃO"])
        ]

        base_corner10 = concluidos[
            concluidos[
                "escanteio_time_destaque_10_min"
            ]
            .astype(str)
            .isin(["SIM", "NÃO"])
        ]

        corners5 = int(
            (
                base_corner5[
                    "escanteio_time_destaque_5_min"
                ].astype(str)
                == "SIM"
            ).sum()
        )

        corners10 = int(
            (
                base_corner10[
                    "escanteio_time_destaque_10_min"
                ].astype(str)
                == "SIM"
            ).sum()
        )

        taxa_corner5 = (
            corners5 / len(base_corner5) * 100
            if len(base_corner5) > 0
            else 0
        )

        taxa_corner10 = (
            corners10 / len(base_corner10) * 100
            if len(base_corner10) > 0
            else 0
        )

        st.write(
            "### 🚩 Escanteios do time em destaque"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Corner ≤5 min",
            corners5
        )

        c2.metric(
            "Taxa ≤5 min",
            f"{taxa_corner5:.1f}%"
        )

        c3.metric(
            "Corner ≤10 min",
            corners10
        )

        c4.metric(
            "Taxa ≤10 min",
            f"{taxa_corner10:.1f}%"
        )

    # Desempenho por qualidade.
    if (
        "qualidade_nivel" in concluidos.columns
        and "qualidade_score" in concluidos.columns
    ):
        qualidade = concluidos.copy()

        qualidade["qualidade_nivel"] = (
            qualidade["qualidade_nivel"]
            .fillna("SEM CLASSIFICAÇÃO")
            .astype(str)
            .replace("", "SEM CLASSIFICAÇÃO")
        )

        linhas = []

        for nivel, grupo in qualidade.groupby(
            "qualidade_nivel"
        ):
            total_nivel = len(grupo)

            destaque_nivel = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "TIME_DESTAQUE"
                ).sum()
            )

            adversario_nivel = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "ADVERSARIO"
                ).sum()
            )

            sem_gol_nivel = int(
                (
                    grupo["resultado_gol"]
                    .astype(str)
                    == "SEM_GOL"
                ).sum()
            )

            corner10_nivel = 0

            if (
                "escanteio_time_destaque_10_min"
                in grupo.columns
            ):
                corner10_nivel = int(
                    (
                        grupo[
                            "escanteio_time_destaque_10_min"
                        ].astype(str)
                        == "SIM"
                    ).sum()
                )

            score_medio = pd.to_numeric(
                grupo["qualidade_score"],
                errors="coerce"
            ).mean()

            linhas.append(
                {
                    "Qualidade": nivel,
                    "Alertas": total_nivel,
                    "Score médio": (
                        round(score_medio, 1)
                        if pd.notna(score_medio)
                        else None
                    ),
                    "Gol destaque": destaque_nivel,
                    "Taxa gol destaque": round(
                        (
                            destaque_nivel
                            / total_nivel
                            * 100
                        ),
                        1
                    ),
                    "Gol adversário": adversario_nivel,
                    "Sem gol": sem_gol_nivel,
                    "Corner destaque ≤10 min": corner10_nivel,
                    "Taxa corner destaque ≤10 min": round(
                        (
                            corner10_nivel
                            / total_nivel
                            * 100
                        ),
                        1
                    )
                }
            )

        tabela_qualidade = pd.DataFrame(
            linhas
        )

        if not tabela_qualidade.empty:
            ordem = {
                "EXCEPCIONAL": 4,
                "MUITO FORTE": 3,
                "FORTE": 2,
                "COMUM": 1,
                "SEM CLASSIFICAÇÃO": 0
            }

            tabela_qualidade["_ordem"] = (
                tabela_qualidade["Qualidade"]
                .map(ordem)
                .fillna(0)
            )

            tabela_qualidade = (
                tabela_qualidade
                .sort_values(
                    "_ordem",
                    ascending=False
                )
                .drop(
                    columns=["_ordem"]
                )
            )

            st.write(
                "### 💎 Desempenho por qualidade"
            )

            st.caption(
                "Esta é a tabela principal para calibrar o algoritmo. "
                "Com mais dados reais, compare a taxa de gol e de escanteio "
                "entre COMUM, FORTE, MUITO FORTE e EXCEPCIONAL."
            )

            st.dataframe(
                tabela_qualidade,
                width="stretch",
                hide_index=True
            )

            melhor = tabela_qualidade[
                tabela_qualidade["Alertas"] >= 5
            ]

            if not melhor.empty:
                melhor = melhor.sort_values(
                    "Taxa gol destaque",
                    ascending=False
                ).iloc[0]

                st.success(
                    "🏆 Melhor faixa até agora: "
                    f"{melhor['Qualidade']} — "
                    f"{melhor['Taxa gol destaque']:.1f}% "
                    "de gol do time em destaque."
                )
            else:
                st.info(
                    "Para destacar automaticamente a melhor faixa, "
                    "o sistema espera pelo menos 5 alertas concluídos "
                    "em uma mesma classificação."
                )


def classificar_pressao_simulador(
    indice_h,
    indice_a
):
    diferenca = abs(
        indice_h - indice_a
    )

    if indice_h >= indice_a:
        dominante = "Time A"
        indice = indice_h
    else:
        dominante = "Time B"
        indice = indice_a

    if diferenca >= 25:
        nivel = "ALTA"
        icone = "🔥"
    elif diferenca >= 12:
        nivel = "MODERADA"
        icone = "📈"
    else:
        nivel = "BAIXA"
        icone = "⚖️"

    return nivel, icone, dominante, indice


def registrar_alerta_simulador(
    nivel,
    dominante,
    indice,
    posse_dominante=50,
    vantagem_escanteios=0
):
    anterior = st.session_state.ultimo_nivel_simulador

    st.session_state.ultimo_nivel_simulador = nivel

    if anterior is None:
        return False

    if anterior == nivel:
        return False

    salvar_alerta_csv(
        0,
        "Time A",
        "Time B",
        0,
        "SIMULAÇÃO",
        anterior,
        nivel,
        dominante,
        indice,
        indice,
        posse_dominante,
        vantagem_escanteios,
        "SIMULACAO"
    )

    return True


def mostrar_partida_hibrida(
    jogo,
    modo_live=False
):
    fixture_id = jogo.get("id")

    (
        casa,
        visitante,
        ids,
        nomes_por_id
    ) = identificar_times(jogo)

    gols_h, gols_a = placar_atual(jogo)

    stats = ler_estatisticas(
        jogo,
        ids
    )

    home = stats["home"]
    away = stats["away"]

    dominio_h, dominio_a = calcular_indice(
        home,
        away
    )

    eventos = preparar_eventos(
        jogo,
        nomes_por_id
    )

    minuto = minuto_estimado(jogo)

    momento = pressao_eventos(
        eventos,
        minuto,
        casa,
        visitante,
        janela=10
    )

    combinado_h, combinado_a = combinar_indices(
        dominio_h,
        dominio_a,
        momento["indice_casa"],
        momento["indice_visitante"]
    )

    if modo_live:
        registrar_live(
            fixture_id,
            casa,
            visitante,
            gols_h,
            gols_a,
            combinado_h,
            combinado_a,
            home,
            away
        )

    nivel, icone, dominante = classificar_pressao_live(
        combinado_h,
        combinado_a,
        momento["indice_casa"],
        momento["indice_visitante"],
        casa,
        visitante
    )

    if modo_live:
        registrar_transicao_alerta(
            fixture_id,
            casa,
            visitante,
            minuto,
            gols_h,
            gols_a,
            nivel,
            dominante,
            combinado_h,
            combinado_a,
            momento["indice_casa"],
            momento["indice_visitante"],
            home,
            away
        )

        atualizar_validacoes_jogo(
            fixture_id,
            minuto,
            eventos
        )

    st.markdown(
        f"## ⚽ {casa} {gols_h} × {gols_a} {visitante}"
    )

    st.caption(
        f"⏱️ Minuto estimado: {minuto}' • "
        f"Atualizado às {datetime.now().strftime('%H:%M:%S')}"
    )

    topo1, topo2, topo3, topo4 = st.columns(4)

    topo1.metric(
        "Pressão",
        nivel
    )

    topo2.metric(
        "Time em destaque",
        dominante
    )

    topo3.metric(
        "Índice dominante",
        f"{max(combinado_h, combinado_a):.1f}%"
    )

    topo4.metric(
        "Diferença",
        f"{abs(combinado_h - combinado_a):.1f} pts"
    )

    barra_pressao_html(
        casa,
        visitante,
        combinado_h,
        combinado_a
    )

    c1, c2 = st.columns(2)

    with c1:
        st.markdown(f"### 🏠 {casa}")

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Índice geral",
            f"{combinado_h:.1f}%"
        )

        m2.metric(
            "Domínio acumulado",
            f"{dominio_h:.1f}%"
        )

        m3.metric(
            "Momento 10 min",
            f"{momento['indice_casa']:.1f}%"
        )

        a1, a2 = st.columns(2)

        a1.metric(
            "Posse",
            f"{home['possession']:.0f}%"
        )

        a2.metric(
            "Escanteios",
            f"{home['corners']:.0f}"
        )

    with c2:
        st.markdown(f"### ✈️ {visitante}")

        m1, m2, m3 = st.columns(3)

        m1.metric(
            "Índice geral",
            f"{combinado_a:.1f}%"
        )

        m2.metric(
            "Domínio acumulado",
            f"{dominio_a:.1f}%"
        )

        m3.metric(
            "Momento 10 min",
            f"{momento['indice_visitante']:.1f}%"
        )

        a1, a2 = st.columns(2)

        a1.metric(
            "Posse",
            f"{away['possession']:.0f}%"
        )

        a2.metric(
            "Escanteios",
            f"{away['corners']:.0f}"
        )

    alerta = gerar_alerta_hibrido(
        casa,
        visitante,
        combinado_h,
        combinado_a,
        momento["indice_casa"],
        momento["indice_visitante"],
        home,
        away
    )

    if combinado_h >= combinado_a:
        posse_dominante_live = home.get(
            "possession",
            50
        )
        vantagem_corners_live = (
            home.get("corners", 0)
            - away.get("corners", 0)
        )
    else:
        posse_dominante_live = away.get(
            "possession",
            50
        )
        vantagem_corners_live = (
            away.get("corners", 0)
            - home.get("corners", 0)
        )

    qualidade_live = calcular_qualidade_alerta(
        max(combinado_h, combinado_a),
        max(
            momento["indice_casa"],
            momento["indice_visitante"]
        ),
        posse_dominante_live,
        vantagem_corners_live
    )

    st.write("### 💎 Qualidade do alerta")

    q1, q2 = st.columns(2)

    q1.metric(
        "Score de qualidade",
        f"{qualidade_live['score']:.1f}/100"
    )

    q2.metric(
        "Classificação",
        f"{qualidade_live['icone']} "
        f"{qualidade_live['nivel']} "
        f"{qualidade_live['estrelas']}"
    )

    st.caption(
        "Pontuação experimental baseada em índice, momento recente, posse e "
        "vantagem de escanteios. Ela ainda não é calibrada historicamente."
    )

    st.write("### 🚨 Alerta automático")

    if nivel == "ALTA":
        st.error(
            f"🔥 PRESSÃO ALTA — {dominante} | "
            f"Índice {max(combinado_h, combinado_a):.1f}%"
        )
    elif nivel == "MODERADA":
        st.warning(
            f"📈 PRESSÃO MODERADA — {dominante} | "
            f"Índice {max(combinado_h, combinado_a):.1f}%"
        )
    else:
        st.info(
            "⚖️ Pressão baixa ou cenário equilibrado neste momento."
        )

    st.caption(
        f"Leitura recente: {momento['leitura']} "
        f"• {alerta['texto']}"
    )

    st.write("### 🎯 Leitura híbrida")

    diferenca = combinado_h - combinado_a

    if diferenca >= 15:
        st.success(
            f"🔥 Controle estatístico forte: {casa}"
        )
    elif diferenca <= -15:
        st.success(
            f"🔥 Controle estatístico forte: {visitante}"
        )
    elif diferenca >= 8:
        st.warning(
            f"📈 Vantagem estatística: {casa}"
        )
    elif diferenca <= -8:
        st.warning(
            f"📈 Vantagem estatística: {visitante}"
        )
    else:
        st.info(
            "⚖️ Jogo equilibrado"
        )

    recentes = momento.get("recentes", [])

    if recentes:
        st.write("### 🕒 Eventos recentes")

        for evento in recentes[-5:]:
            linha = (
                f"**{evento['Tempo']}** — "
                f"{evento['Time']} — "
                f"{evento['Evento']}"
            )

            if evento.get("Jogador"):
                linha += f" — {evento['Jogador']}"

            st.write(linha)

    if modo_live:
        historico = (
            st.session_state
            .historico_live
            .get(
                fixture_id,
                []
            )
        )

        if len(historico) >= 2:
            df = pd.DataFrame(historico)

            grafico = df.copy()

            grafico.columns = [
                "Hora",
                casa,
                visitante
            ]

            grafico = grafico.set_index("Hora")

            st.write(
                "### 📈 Evolução do índice geral"
            )

            st.line_chart(grafico)


def data_hoje_brasil():
    return datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()


def buscar_jogos_hoje_sportmonks():
    hoje = data_hoje_brasil()

    url = (
        f"{BASE_URL}/fixtures/"
        f"between/"
        f"{hoje.isoformat()}/"
        f"{hoje.isoformat()}"
    )

    params = {
        "api_token": TOKEN,
        "include": "participants;state;scores",
        "per_page": 100
    }

    dados, status = requisicao(
        url,
        params
    )

    if status != 200:
        return [], status

    jogos = dados.get(
        "data",
        []
    )

    jogos = [
        jogo
        for jogo in jogos
        if jogo.get("league_id") in LIGAS
    ]

    jogos.sort(
        key=lambda jogo: str(
            jogo.get("starting_at", "")
        )
    )

    return jogos, 200


def buscar_jogos_hoje_apifootball():
    if not APIFOOTBALL_KEY:
        return [], "SEM_CHAVE", None

    hoje = data_hoje_brasil()

    url = "https://v3.football.api-sports.io/fixtures"

    params = {
        "date": hoje.isoformat(),
        "timezone": "America/Sao_Paulo"
    }

    headers = {
        "x-apisports-key": APIFOOTBALL_KEY
    }

    try:
        resposta = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=25
        )

        restante = resposta.headers.get(
            "x-ratelimit-requests-remaining"
        )

        if resposta.status_code != 200:
            return [], resposta.status_code, restante

        payload = resposta.json()

        erros = payload.get("errors")
        if erros:
            return [], f"API: {erros}", restante

        return (
            payload.get("response", []) or [],
            200,
            restante
        )

    except requests.exceptions.RequestException:
        return [], -1, None



@st.cache_data(ttl=60, show_spinner=False)
def buscar_estatisticas_api_football(fixture_id):
    if not APIFOOTBALL_KEY:
        return [], "SEM_CHAVE", None

    url = "https://v3.football.api-sports.io/fixtures/statistics"

    headers = {
        "x-apisports-key": APIFOOTBALL_KEY
    }

    params = {
        "fixture": fixture_id
    }

    try:
        resposta = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=25
        )

        restante = resposta.headers.get(
            "x-ratelimit-requests-remaining"
        )

        if resposta.status_code != 200:
            return [], resposta.status_code, restante

        payload = resposta.json()

        erros = payload.get("errors")
        if erros:
            return [], f"API: {erros}", restante

        return (
            payload.get("response", []) or [],
            200,
            restante
        )

    except requests.exceptions.RequestException:
        return [], -1, None


def normalizar_valor_api_football(valor):
    if valor is None:
        return 0.0

    if isinstance(valor, str):
        valor = valor.strip().replace("%", "")

    try:
        return float(valor)
    except Exception:
        return 0.0


def extrair_estatisticas_api_football(resposta):
    times = []

    for bloco in resposta:
        nome_time = (
            (bloco.get("team") or {}).get("name")
            or "Time"
        )

        mapa = {}

        for stat in bloco.get("statistics", []) or []:
            tipo = str(stat.get("type", "")).strip()
            valor = normalizar_valor_api_football(
                stat.get("value")
            )
            mapa[tipo] = valor

        times.append(
            {
                "nome": nome_time,
                "stats": mapa
            }
        )

    return times


def participacao_segura(a, b):
    total = float(a) + float(b)

    if total <= 0:
        return 50.0, 50.0

    pct_a = float(a) / total * 100
    return pct_a, 100 - pct_a


def calcular_pressao_api_football(times):
    if len(times) < 2:
        return None

    a = times[0]
    b = times[1]

    sa = a["stats"]
    sb = b["stats"]

    sog_a = sa.get("Shots on Goal", 0)
    sog_b = sb.get("Shots on Goal", 0)

    shots_a = sa.get("Total Shots", 0)
    shots_b = sb.get("Total Shots", 0)

    corners_a = sa.get("Corner Kicks", 0)
    corners_b = sb.get("Corner Kicks", 0)

    posse_a = sa.get("Ball Possession", 0)
    posse_b = sb.get("Ball Possession", 0)

    sog_pa, sog_pb = participacao_segura(sog_a, sog_b)
    shots_pa, shots_pb = participacao_segura(shots_a, shots_b)
    corners_pa, corners_pb = participacao_segura(corners_a, corners_b)

    if posse_a + posse_b <= 0:
        posse_pa, posse_pb = 50.0, 50.0
    else:
        posse_pa, posse_pb = participacao_segura(posse_a, posse_b)

    indice_a = (
        sog_pa * 0.35
        + shots_pa * 0.25
        + corners_pa * 0.20
        + posse_pa * 0.20
    )

    indice_b = (
        sog_pb * 0.35
        + shots_pb * 0.25
        + corners_pb * 0.20
        + posse_pb * 0.20
    )

    total = indice_a + indice_b

    if total <= 0:
        final_a = 50.0
        final_b = 50.0
    else:
        final_a = indice_a / total * 100
        final_b = 100 - final_a

    if final_a >= final_b:
        dominante = a["nome"]
        dominante_indice = final_a
    else:
        dominante = b["nome"]
        dominante_indice = final_b

    diferenca = abs(final_a - final_b)

    if dominante_indice >= 67 and diferenca >= 20:
        nivel = "ALTA"
        icone = "🔥"
    elif dominante_indice >= 58 and diferenca >= 10:
        nivel = "MODERADA"
        icone = "📈"
    else:
        nivel = "BAIXA"
        icone = "⚖️"

    return {
        "time_a": a["nome"],
        "time_b": b["nome"],
        "indice_a": round(final_a, 1),
        "indice_b": round(final_b, 1),
        "dominante": dominante,
        "nivel": nivel,
        "icone": icone,
        "sog_a": int(sog_a),
        "sog_b": int(sog_b),
        "shots_a": int(shots_a),
        "shots_b": int(shots_b),
        "corners_a": int(corners_a),
        "corners_b": int(corners_b),
        "posse_a": round(posse_a, 1),
        "posse_b": round(posse_b, 1),
        "yellow_a": int(sa.get("Yellow Cards", 0)),
        "yellow_b": int(sb.get("Yellow Cards", 0)),
        "red_a": int(sa.get("Red Cards", 0)),
        "red_b": int(sb.get("Red Cards", 0)),
        "saves_a": int(sa.get("Goalkeeper Saves", 0)),
        "saves_b": int(sb.get("Goalkeeper Saves", 0)),
    }



@st.cache_data(ttl=60, show_spinner=False)
def buscar_eventos_api_football(fixture_id):
    if not APIFOOTBALL_KEY:
        return [], "SEM_CHAVE", None

    url = "https://v3.football.api-sports.io/fixtures/events"

    headers = {
        "x-apisports-key": APIFOOTBALL_KEY
    }

    params = {
        "fixture": fixture_id
    }

    try:
        resposta = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=25
        )

        restante = resposta.headers.get(
            "x-ratelimit-requests-remaining"
        )

        if resposta.status_code != 200:
            return [], resposta.status_code, restante

        payload = resposta.json()

        erros = payload.get("errors")
        if erros:
            return [], f"API: {erros}", restante

        return (
            payload.get("response", []) or [],
            200,
            restante
        )

    except requests.exceptions.RequestException:
        return [], -1, None


def resumir_evento_api_football(evento):
    tempo = evento.get("time", {}) or {}
    time = evento.get("team", {}) or {}
    jogador = evento.get("player", {}) or {}

    minuto = tempo.get("elapsed")
    extra = tempo.get("extra")

    minuto_txt = "-"
    if minuto is not None:
        minuto_txt = str(minuto)
        if extra:
            minuto_txt += f"+{extra}"

    tipo = str(evento.get("type", "") or "")
    detalhe = str(evento.get("detail", "") or "")
    comentario = str(evento.get("comments", "") or "")

    icone = "📌"

    if tipo.lower() == "goal":
        icone = "⚽"
    elif tipo.lower() == "card":
        if "yellow" in detalhe.lower():
            icone = "🟨"
        elif "red" in detalhe.lower():
            icone = "🟥"
        else:
            icone = "🟨"
    elif tipo.lower() == "subst":
        icone = "🔄"
    elif "var" in tipo.lower():
        icone = "🖥️"

    return {
        "minuto": minuto_txt,
        "time": time.get("name") or "Time",
        "jogador": jogador.get("name") or "",
        "tipo": tipo,
        "detalhe": detalhe,
        "comentario": comentario,
        "icone": icone
    }



def calcular_momento_por_eventos(eventos, time_casa, time_fora, minuto_atual=None):
    """
    Indicador simplificado de momento baseado somente em eventos oficiais.
    Sempre parte de 50/50 e conhece os dois times pelo fixture.
    """
    if minuto_atual is None:
        minutos_validos = [
            (evento.get("time") or {}).get("elapsed")
            for evento in eventos
            if (evento.get("time") or {}).get("elapsed") is not None
        ]
        minuto_atual = max(minutos_validos) if minutos_validos else 0

    janela = 10
    inicio = max(0, minuto_atual - janela)

    # Pontuação pequena de propósito: eventos não equivalem a estatísticas de pressão.
    pontos = {time_casa: 0.0, time_fora: 0.0}

    for evento in eventos:
        tempo = evento.get("time", {}) or {}
        minuto = tempo.get("elapsed")
        if minuto is None or minuto < inicio:
            continue

        nome_time = (evento.get("team") or {}).get("name")
        if nome_time not in pontos:
            continue

        tipo = str(evento.get("type", "") or "")
        detalhe = str(evento.get("detail", "") or "")

        # Quanto mais antigo dentro da janela, menor o peso.
        idade = max(0, minuto_atual - minuto)
        fator_recencia = max(0.25, 1.0 - (idade / max(1, janela)))

        impacto = 0.0
        if tipo == "Goal":
            impacto = 12.0
        elif tipo == "Card":
            if "Red" in detalhe:
                impacto = -10.0
            elif "Yellow" in detalhe:
                impacto = -2.0
        elif tipo == "subst":
            impacto = 0.5
        elif "Var" in tipo:
            impacto = 2.0

        pontos[nome_time] += impacto * fator_recencia

    # Base igual para os dois lados. Limita o indicador para não parecer
    # uma probabilidade matemática ou estatística completa.
    base = 50.0
    bruto_casa = base + pontos[time_casa]
    bruto_fora = base + pontos[time_fora]
    total = max(1.0, bruto_casa + bruto_fora)

    pct_casa = 100.0 * bruto_casa / total
    pct_fora = 100.0 - pct_casa

    # Evita extremos quando temos apenas eventos.
    pct_casa = min(75.0, max(25.0, pct_casa))
    pct_fora = 100.0 - pct_casa

    diferenca = abs(pct_casa - pct_fora)
    if diferenca >= 22:
        nivel, icone = "FORTE", "🔥"
    elif diferenca >= 10:
        nivel, icone = "ATENÇÃO", "🟡"
    else:
        nivel, icone = "EQUILIBRADO", "⚖️"

    destaque = time_casa if pct_casa > pct_fora else time_fora if pct_fora > pct_casa else "Equilíbrio"

    return {
        "janela": janela,
        "time_casa": time_casa,
        "time_fora": time_fora,
        "pct_casa": round(pct_casa, 1),
        "pct_fora": round(pct_fora, 1),
        "destaque": destaque,
        "nivel": nivel,
        "icone": icone,
    }



def classificar_alerta_momento(leitura):
    diferenca = abs(
        leitura["pct_casa"]
        - leitura["pct_fora"]
    )

    if leitura["pct_casa"] > leitura["pct_fora"]:
        destaque = leitura["time_casa"]
        indice = leitura["pct_casa"]
    elif leitura["pct_fora"] > leitura["pct_casa"]:
        destaque = leitura["time_fora"]
        indice = leitura["pct_fora"]
    else:
        destaque = "Equilíbrio"
        indice = 50.0

    if diferenca >= 22:
        return {
            "nivel": "ALERTA",
            "icone": "🔥",
            "mensagem": (
                f"Momento forte para {destaque}"
            ),
            "destaque": destaque,
            "indice": indice
        }

    if diferenca >= 10:
        return {
            "nivel": "ATENÇÃO",
            "icone": "🟡",
            "mensagem": (
                f"Momento crescendo para {destaque}"
            ),
            "destaque": destaque,
            "indice": indice
        }

    return {
        "nivel": "EQUILIBRADO",
        "icone": "⚖️",
        "mensagem": (
            "Sem desequilíbrio relevante por eventos"
        ),
        "destaque": destaque,
        "indice": indice
    }


def renderizar_momento_eventos_api_football(eventos, time_casa, time_fora):
    leitura = calcular_momento_por_eventos(eventos, time_casa, time_fora)

    st.markdown("#### 📈 Momento por eventos")

    c1, c2, c3 = st.columns(3)
    c1.metric(leitura["time_casa"], f"{leitura['pct_casa']:.1f}%")
    c2.metric("Momento recente", f"{leitura['icone']} {leitura['nivel']}")
    c3.metric(leitura["time_fora"], f"{leitura['pct_fora']:.1f}%")

    st.caption(
        f"Janela aproximada: últimos {leitura['janela']} minutos • "
        f"Destaque: {leitura['destaque']}"
    )
    st.progress(max(0.0, min(1.0, leitura["pct_casa"] / 100)))

    alerta = classificar_alerta_momento(
        leitura
    )

    st.markdown("#### 🚨 Alerta automático")

    if alerta["nivel"] == "ALERTA":
        st.error(
            f"{alerta['icone']} {alerta['mensagem']}"
        )
    elif alerta["nivel"] == "ATENÇÃO":
        st.warning(
            f"{alerta['icone']} {alerta['mensagem']}"
        )
    else:
        st.info(
            f"{alerta['icone']} {alerta['mensagem']}"
        )

    st.caption(
        f"Índice do time em destaque: {alerta['indice']:.1f}% • "
        "Este alerta usa somente eventos recentes quando não há estatísticas completas."
    )

    st.caption(
        "Indicador experimental baseado somente em eventos oficiais recentes. "
        "Parte de 50/50; cartões amarelos têm impacto pequeno e eventos antigos "
        "perdem peso. Não representa probabilidade de vitória nem substitui "
        "pressão calculada com posse, chutes e escanteios."
    )


def renderizar_eventos_api_football(fixture_id, time_casa=None, time_fora=None):
    eventos, status, restante = (
        buscar_eventos_api_football(
            fixture_id
        )
    )

    st.markdown("#### 🧭 Eventos ao vivo")

    if status != 200:
        st.warning(
            f"Não foi possível carregar os eventos deste jogo agora ({status})."
        )
        return False

    if restante is not None:
        st.caption(
            f"Requisições restantes na API-Football: {restante}"
        )

    if not eventos:
        st.info(
            "Ainda não há eventos detalhados disponíveis para esta partida."
        )
        return False

    # Os nomes vêm do fixture; se não vierem, tentamos inferir dos eventos.
    nomes_eventos = []
    for _evento in eventos:
        _nome = ((_evento.get("team") or {}).get("name"))
        if _nome and _nome not in nomes_eventos:
            nomes_eventos.append(_nome)

    if not time_casa:
        time_casa = nomes_eventos[0] if nomes_eventos else "Mandante"
    if not time_fora:
        time_fora = nomes_eventos[1] if len(nomes_eventos) > 1 else "Visitante"

    renderizar_momento_eventos_api_football(
        eventos, time_casa, time_fora
    )

    eventos_formatados = [
        resumir_evento_api_football(evento)
        for evento in eventos
    ]

    for evento in reversed(eventos_formatados[-12:]):
        linha = (
            f"{evento['icone']} **{evento['minuto']}' — "
            f"{evento['time']}**"
        )

        if evento["jogador"]:
            linha += f" • {evento['jogador']}"

        if evento["detalhe"]:
            linha += f" • {evento['detalhe']}"

        st.write(linha)

        if evento["comentario"]:
            st.caption(evento["comentario"])

    return True


def renderizar_analise_api_football(fixture_id, time_casa=None, time_fora=None):
    estatisticas, status, restante = (
        buscar_estatisticas_api_football(
            fixture_id
        )
    )

    if status != 200:
        st.warning(
            f"Não foi possível carregar as estatísticas "
            f"deste jogo agora ({status})."
        )
        return

    times = extrair_estatisticas_api_football(
        estatisticas
    )

    leitura = calcular_pressao_api_football(
        times
    )

    if leitura is None:
        st.info(
            "A API-Football ainda não disponibilizou estatísticas "
            "detalhadas para esta partida."
        )

        teve_eventos = renderizar_eventos_api_football(
            fixture_id,
            time_casa,
            time_fora
        )

        if teve_eventos:
            st.caption(
                "Como não há estatísticas completas, o painel mostra "
                "os eventos oficiais disponíveis. Eles ajudam no acompanhamento, "
                "mas não são suficientes para calcular pressão com a mesma qualidade."
            )

        return

    st.markdown("#### 📊 Análise ao vivo")

    if restante is not None:
        st.caption(
            f"Requisições restantes na API-Football: {restante}"
        )

    c1, c2, c3 = st.columns(3)

    c1.metric(
        leitura["time_a"],
        f"{leitura['indice_a']:.1f}%"
    )

    c2.metric(
        "Pressão atual",
        f"{leitura['icone']} {leitura['nivel']}"
    )

    c3.metric(
        leitura["time_b"],
        f"{leitura['indice_b']:.1f}%"
    )

    st.progress(
        max(
            0.0,
            min(
                1.0,
                leitura["indice_a"] / 100
            )
        )
    )

    st.caption(
        f"Time em destaque: **{leitura['dominante']}**"
    )

    tabela = pd.DataFrame(
        {
            "Estatística": [
                "Chutes no gol",
                "Finalizações",
                "Escanteios",
                "Posse (%)",
                "Amarelos",
                "Vermelhos",
                "Defesas"
            ],
            leitura["time_a"]: [
                leitura["sog_a"],
                leitura["shots_a"],
                leitura["corners_a"],
                leitura["posse_a"],
                leitura["yellow_a"],
                leitura["red_a"],
                leitura["saves_a"]
            ],
            leitura["time_b"]: [
                leitura["sog_b"],
                leitura["shots_b"],
                leitura["corners_b"],
                leitura["posse_b"],
                leitura["yellow_b"],
                leitura["red_b"],
                leitura["saves_b"]
            ]
        }
    )

    st.dataframe(
        tabela,
        hide_index=True,
        width="stretch"
    )

    if leitura["nivel"] == "ALTA":
        st.error(
            f"🔥 PRESSÃO ALTA — {leitura['dominante']}"
        )
    elif leitura["nivel"] == "MODERADA":
        st.warning(
            f"📈 PRESSÃO MODERADA — {leitura['dominante']}"
        )
    else:
        st.info(
            "⚖️ Pressão baixa/equilibrada neste momento."
        )

    st.caption(
        "Índice experimental calculado com chutes no gol (35%), "
        "finalizações (25%), escanteios (20%) e posse (20%). "
        "Não é previsão de gol nem garantia de resultado."
    )



def jogo_api_football_ao_vivo(jogo):
    status_curto = str(
        jogo.get("status_curto", "")
    ).upper()

    status_longo = str(
        jogo.get("status_longo", "")
    ).lower()

    status_live = {
        "1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"
    }

    if status_curto in status_live:
        return True

    if jogo.get("elapsed") is not None:
        return True

    termos = (
        "first half",
        "second half",
        "extra time",
        "in progress",
        "primeiro tempo",
        "segundo tempo",
        "ao vivo"
    )

    return any(
        termo in status_longo
        for termo in termos
    )


def chave_competicao_api_football(jogo):
    pais = jogo.get("pais") or "Internacional"
    liga = jogo.get("liga") or "Competição"
    return f"{pais} • {liga}"


def separar_libertadores_api_football(jogos):
    libertadores = []

    for item in jogos:
        liga = item.get("league", {}) or {}
        liga_id = liga.get("id")
        nome = str(liga.get("name", "")).lower()

        if liga_id == 13 or "libertadores" in nome:
            libertadores.append(item)

    return libertadores


def formatar_fixture_api_football(item):
    fixture = item.get("fixture", {}) or {}
    teams = item.get("teams", {}) or {}
    league = item.get("league", {}) or {}
    goals = item.get("goals", {}) or {}
    status = fixture.get("status", {}) or {}

    casa = (teams.get("home") or {}).get("name") or "Casa"
    visitante = (teams.get("away") or {}).get("name") or "Visitante"
    liga = league.get("name") or "Competição"
    pais = league.get("country") or ""

    data_iso = str(fixture.get("date", ""))
    horario = "-"
    if "T" in data_iso:
        horario = data_iso.split("T", 1)[1][:5]

    return {
        "id": fixture.get("id"),
        "casa": casa,
        "visitante": visitante,
        "liga": liga,
        "pais": pais,
        "horario": horario,
        "status_longo": str(status.get("long", "")),
        "elapsed": status.get("elapsed"),
        "gols_h": goals.get("home"),
        "gols_a": goals.get("away")
    }


def nome_estado_jogo(jogo):
    estado = jogo.get(
        "state",
        {}
    ) or {}

    nome = (
        estado.get("name")
        or estado.get("state")
        or estado.get("short_name")
        or ""
    )

    return str(nome).strip()


def buscar_jogos_live():
    url = (
        f"{BASE_URL}/livescores/inplay"
    )

    params = {
        "api_token": TOKEN,
        "include": "participants;state"
    }

    dados, status = requisicao(
        url,
        params
    )

    if status != 200:
        return [], status

    lives = dados.get(
        "data",
        []
    )

    lives = [
        jogo
        for jogo in lives
        if jogo.get("league_id") in LIGAS
    ]

    completos = []

    for live in lives:
        fixture_id = live.get("id")

        jogo = buscar_fixture(
            fixture_id,
            incluir_eventos=True
        )

        if jogo:
            completos.append(
                jogo
            )

    return completos, 200



def criar_central_oportunidades(
    jogos
):
    oportunidades = []

    for jogo in jogos:
        (
            casa,
            visitante,
            ids,
            nomes_por_id
        ) = identificar_times(jogo)

        gols_h, gols_a = placar_atual(jogo)

        stats = ler_estatisticas(
            jogo,
            ids
        )

        home = stats["home"]
        away = stats["away"]

        dominio_h, dominio_a = calcular_indice(
            home,
            away
        )

        eventos = preparar_eventos(
            jogo,
            nomes_por_id
        )

        minuto = minuto_estimado(
            jogo
        )

        momento = pressao_eventos(
            eventos,
            minuto,
            casa,
            visitante,
            janela=10
        )

        combinado_h, combinado_a = combinar_indices(
            dominio_h,
            dominio_a,
            momento["indice_casa"],
            momento["indice_visitante"]
        )

        nivel, icone, destaque = classificar_pressao_live(
            combinado_h,
            combinado_a,
            momento["indice_casa"],
            momento["indice_visitante"],
            casa,
            visitante
        )

        if combinado_h >= combinado_a:
            indice = combinado_h
            momento_destaque = momento["indice_casa"]
            posse_dominante = home.get(
                "possession",
                50
            )
            vantagem_corners = (
                home.get("corners", 0)
                - away.get("corners", 0)
            )
        else:
            indice = combinado_a
            momento_destaque = momento["indice_visitante"]
            posse_dominante = away.get(
                "possession",
                50
            )
            vantagem_corners = (
                away.get("corners", 0)
                - home.get("corners", 0)
            )

        qualidade = calcular_qualidade_alerta(
            indice,
            momento_destaque,
            posse_dominante,
            vantagem_corners
        )

        prioridade_nivel = {
            "ALTA": 3,
            "MODERADA": 2,
            "BAIXA": 1
        }.get(
            nivel,
            0
        )

        score_prioridade = (
            prioridade_nivel * 1000
            + qualidade["score"] * 10
            + indice
        )

        oportunidades.append(
            {
                "Jogo": f"{casa} × {visitante}",
                "Placar": f"{gols_h} × {gols_a}",
                "Minuto": minuto,
                "Nível": nivel,
                "Ícone": icone,
                "Destaque": destaque,
                "Índice": round(indice, 1),
                "Momento": round(momento_destaque, 1),
                "Qualidade score": qualidade["score"],
                "Qualidade": qualidade["nivel"],
                "Qualidade ícone": qualidade["icone"],
                "Estrelas": qualidade["estrelas"],
                "Posse destaque": round(
                    float(posse_dominante),
                    1
                ),
                "Vantagem corners": round(
                    float(vantagem_corners),
                    1
                ),
                "_prioridade": score_prioridade
            }
        )

    oportunidades.sort(
        key=lambda x: x["_prioridade"],
        reverse=True
    )

    return oportunidades


def criar_ranking_hibrido(
    jogos
):
    ranking = []

    for jogo in jogos:
        (
            casa,
            visitante,
            ids,
            nomes_por_id
        ) = identificar_times(jogo)

        gols_h, gols_a = placar_atual(jogo)

        stats = ler_estatisticas(
            jogo,
            ids
        )

        home = stats["home"]
        away = stats["away"]

        dominio_h, dominio_a = calcular_indice(
            home,
            away
        )

        eventos = preparar_eventos(
            jogo,
            nomes_por_id
        )

        minuto = minuto_estimado(jogo)

        momento = pressao_eventos(
            eventos,
            minuto,
            casa,
            visitante,
            janela=10
        )

        combinado_h, combinado_a = combinar_indices(
            dominio_h,
            dominio_a,
            momento["indice_casa"],
            momento["indice_visitante"]
        )

        nivel, icone, destaque = classificar_pressao_live(
            combinado_h,
            combinado_a,
            momento["indice_casa"],
            momento["indice_visitante"],
            casa,
            visitante
        )

        if combinado_h >= combinado_a:
            indice = combinado_h
            momento_destaque = momento["indice_casa"]
        else:
            indice = combinado_a
            momento_destaque = momento["indice_visitante"]

        diferenca = abs(
            combinado_h - combinado_a
        )

        peso_nivel = {
            "ALTA": 3,
            "MODERADA": 2,
            "BAIXA": 1
        }.get(nivel, 0)

        score_ranking = (
            peso_nivel * 1000
            + indice * 10
            + diferenca
            + momento_destaque / 100
        )

        ranking.append(
            {
                "Jogo": f"{casa} × {visitante}",
                "Placar": f"{gols_h} × {gols_a}",
                "Minuto": minuto,
                "Destaque": destaque,
                "Índice": round(indice, 1),
                "Diferença": round(diferenca, 1),
                "Momento 10 min": round(momento_destaque, 1),
                "Nível": nivel,
                "Ícone": icone,
                "Posse casa": home["possession"],
                "Posse visitante": away["possession"],
                "Escanteios casa": home["corners"],
                "Escanteios visitante": away["corners"],
                "Leitura": momento["leitura"],
                "_score": score_ranking
            }
        )

    ranking.sort(
        key=lambda x: x["_score"],
        reverse=True
    )

    return ranking


(
    aba_live,
    aba_central,
    aba_ranking,
    aba_replay,
    aba_sim,
    aba_hoje,
    aba_futuros,
    aba_historico,
    aba_alertas,
    aba_validacao
) = st.tabs(
    [
        "🔴 Ao vivo",
        "🎯 Central de oportunidades",
        "🏆 Ranking",
        "🎞️ Replay histórico",
        "🧪 Simulador",
        "⚽ Jogos de hoje",
        "📅 Próximas partidas",
        "💾 Histórico salvo",
        "🚨 Histórico de alertas",
        "🎯 Validação dos alertas"
    ]
)


with aba_live:

    @st.fragment(
        run_every="20s"
    )
    def monitor_live():

        st.subheader(
            "🔴 Monitor híbrido ao vivo"
        )

        st.caption(
            "Atualização automática a cada 20 segundos • "
            "70% domínio acumulado + 30% momento dos últimos 10 minutos"
        )

        st.info(
            "O painel exibe pressão estatística, não previsão de gol. "
            "Os alertas dependem da cobertura disponível na sua conta."
        )

        st.success(
            "🟢 CAPTURA REAL ATIVA — quando uma partida entrar em PRESSÃO ALTA, "
            "o sistema salva o alerta, o score de qualidade e acompanha "
            "gol/escanteio nos próximos 5 e 10 minutos."
        )

        jogos, status = buscar_jogos_live()

        if status != 200:
            st.error(
                f"Erro na API: {status}"
            )
            return

        if not jogos:
            st.info(
                "Nenhum jogo ao vivo "
                "nas ligas disponíveis."
            )
            return

        st.success(
            f"✅ {len(jogos)} jogo(s) ao vivo"
        )

        for jogo in jogos:
            st.divider()

            mostrar_partida_hibrida(
                jogo,
                modo_live=True
            )

    monitor_live()


with aba_central:

    @st.fragment(
        run_every="20s"
    )
    def central_oportunidades_live():

        st.subheader(
            "🎯 Central de oportunidades"
        )

        st.caption(
            "Prioriza automaticamente os jogos ao vivo por nível de pressão "
            "e qualidade do alerta. Atualização a cada 20 segundos."
        )

        jogos, status = buscar_jogos_live()

        if status != 200:
            st.error(
                f"Erro na API: {status}"
            )
            return

        if not jogos:
            st.info(
                "Nenhum jogo ao vivo nas ligas disponíveis neste momento."
            )
            return

        oportunidades = criar_central_oportunidades(
            jogos
        )

        filtro1, filtro2, filtro3 = st.columns(
            [1, 1, 2]
        )

        with filtro1:
            nivel_filtro = st.selectbox(
                "Pressão",
                [
                    "Todos",
                    "ALTA",
                    "MODERADA",
                    "BAIXA"
                ],
                key="central_nivel"
            )

        with filtro2:
            qualidade_filtro = st.selectbox(
                "Qualidade",
                [
                    "Todas",
                    "EXCEPCIONAL",
                    "MUITO FORTE",
                    "FORTE",
                    "COMUM"
                ],
                key="central_qualidade"
            )

        with filtro3:
            busca_central = st.text_input(
                "Buscar time",
                "",
                placeholder="Digite parte do nome",
                key="central_busca"
            )

        if nivel_filtro != "Todos":
            oportunidades = [
                item
                for item in oportunidades
                if item["Nível"] == nivel_filtro
            ]

        if qualidade_filtro != "Todas":
            oportunidades = [
                item
                for item in oportunidades
                if item["Qualidade"] == qualidade_filtro
            ]

        if busca_central.strip():
            termo = busca_central.strip().lower()

            oportunidades = [
                item
                for item in oportunidades
                if termo in item["Jogo"].lower()
            ]

        if not oportunidades:
            st.warning(
                "Nenhum jogo corresponde aos filtros escolhidos."
            )
            return

        alta = sum(
            1
            for item in oportunidades
            if item["Nível"] == "ALTA"
        )

        moderada = sum(
            1
            for item in oportunidades
            if item["Nível"] == "MODERADA"
        )

        excepcionais = sum(
            1
            for item in oportunidades
            if item["Qualidade"] == "EXCEPCIONAL"
        )

        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Jogos na central",
            len(oportunidades)
        )

        c2.metric(
            "🔥 Pressão ALTA",
            alta
        )

        c3.metric(
            "📈 Pressão MODERADA",
            moderada
        )

        c4.metric(
            "💎 Excepcionais",
            excepcionais
        )

        st.divider()

        for posicao, item in enumerate(
            oportunidades,
            start=1
        ):
            st.markdown(
                f"## {posicao}º — {item['Jogo']}"
            )

            st.caption(
                f"⏱️ {item['Minuto']}' • "
                f"Placar {item['Placar']}"
            )

            a1, a2, a3, a4, a5 = st.columns(5)

            a1.metric(
                "Pressão",
                f"{item['Ícone']} {item['Nível']}"
            )

            a2.metric(
                "Destaque",
                item["Destaque"]
            )

            a3.metric(
                "Índice",
                f"{item['Índice']:.1f}%"
            )

            a4.metric(
                "Momento 10 min",
                f"{item['Momento']:.1f}%"
            )

            a5.metric(
                "Qualidade",
                f"{item['Qualidade score']:.1f}/100"
            )

            st.write(
                f"💎 **{item['Qualidade ícone']} "
                f"{item['Qualidade']} {item['Estrelas']}**"
            )

            st.caption(
                f"Posse do time em destaque: "
                f"{item['Posse destaque']:.1f}% • "
                f"Vantagem de escanteios: "
                f"{item['Vantagem corners']:+.0f}"
            )

            if item["Nível"] == "ALTA":
                st.error(
                    f"🔥 PRIORIDADE ALTA — {item['Destaque']}"
                )
            elif item["Nível"] == "MODERADA":
                st.warning(
                    f"📈 OBSERVAR — {item['Destaque']}"
                )
            else:
                st.info(
                    "⚖️ Sem prioridade alta neste momento."
                )

            st.divider()

    central_oportunidades_live()


with aba_ranking:

    @st.fragment(
        run_every="20s"
    )
    def ranking_live():

        st.subheader(
            "🏆 Classificação de pressão ao vivo"
        )

        st.caption(
            "Atualização automática a cada 20 segundos • "
            "prioriza pressão ALTA, depois MODERADA e BAIXA"
        )

        jogos, status = buscar_jogos_live()

        if status != 200:
            st.error(
                f"Erro na API: {status}"
            )
            return

        if not jogos:
            st.info(
                "Nenhum jogo ao vivo para montar a classificação."
            )
            return

        ranking = criar_ranking_hibrido(
            jogos
        )

        f1, f2 = st.columns([1, 2])

        with f1:
            filtro_nivel = st.selectbox(
                "Filtrar pressão",
                [
                    "Todos",
                    "ALTA",
                    "MODERADA",
                    "BAIXA"
                ],
                key="ranking_filtro_nivel"
            )

        with f2:
            busca_time = st.text_input(
                "Buscar time",
                "",
                placeholder="Digite parte do nome do time",
                key="ranking_busca_time"
            )

        if filtro_nivel != "Todos":
            ranking = [
                item
                for item in ranking
                if item["Nível"] == filtro_nivel
            ]

        if busca_time.strip():
            termo = busca_time.strip().lower()

            ranking = [
                item
                for item in ranking
                if termo in item["Jogo"].lower()
            ]

        if not ranking:
            st.warning(
                "Nenhuma partida corresponde aos filtros escolhidos."
            )
            return

        alta = sum(
            1 for item in ranking
            if item["Nível"] == "ALTA"
        )

        moderada = sum(
            1 for item in ranking
            if item["Nível"] == "MODERADA"
        )

        baixa = sum(
            1 for item in ranking
            if item["Nível"] == "BAIXA"
        )

        r1, r2, r3, r4 = st.columns(4)

        r1.metric(
            "Jogos monitorados",
            len(ranking)
        )

        r2.metric(
            "Pressão alta",
            alta
        )

        r3.metric(
            "Pressão moderada",
            moderada
        )

        r4.metric(
            "Pressão baixa",
            baixa
        )

        st.divider()

        for posicao, item in enumerate(
            ranking,
            start=1
        ):
            st.markdown(
                f"## {posicao}º — {item['Jogo']}"
            )

            st.caption(
                f"⏱️ {item['Minuto']}' • "
                f"Placar {item['Placar']}"
            )

            c1, c2, c3, c4, c5 = st.columns(5)

            c1.metric(
                "Nível",
                f"{item['Ícone']} {item['Nível']}"
            )

            c2.metric(
                "Time em destaque",
                item["Destaque"]
            )

            c3.metric(
                "Índice",
                f"{item['Índice']:.1f}%"
            )

            c4.metric(
                "Momento 10 min",
                f"{item['Momento 10 min']:.1f}%"
            )

            c5.metric(
                "Diferença",
                f"{item['Diferença']:.1f} pts"
            )

            if item["Nível"] == "ALTA":
                st.error(
                    f"🔥 PRESSÃO ALTA — {item['Destaque']}"
                )
            elif item["Nível"] == "MODERADA":
                st.warning(
                    f"📈 PRESSÃO MODERADA — {item['Destaque']}"
                )
            else:
                st.info(
                    "⚖️ Pressão baixa ou jogo equilibrado."
                )

            st.caption(
                f"Posse: {item['Posse casa']:.0f}% × "
                f"{item['Posse visitante']:.0f}% • "
                f"Escanteios: {item['Escanteios casa']:.0f} × "
                f"{item['Escanteios visitante']:.0f} • "
                f"{item['Leitura']}"
            )

            st.divider()

    ranking_live()


with aba_replay:

    st.subheader(
        "🎞️ Replay histórico"
    )

    jogo_replay = buscar_fixture(
        FIXTURE_REPLAY,
        incluir_eventos=True
    )

    if not jogo_replay:
        st.error(
            "Não foi possível carregar "
            "o replay."
        )

    else:
        (
            casa,
            visitante,
            ids,
            nomes_por_id
        ) = identificar_times(
            jogo_replay
        )

        eventos = preparar_eventos(
            jogo_replay,
            nomes_por_id
        )

        minuto_maximo = max(
            [
                e["minuto_num"]
                for e in eventos
            ]
            or [90]
        )

        minuto_replay = st.slider(
            "⏱️ Minuto da partida",
            min_value=0,
            max_value=max(
                90,
                minuto_maximo
            ),
            value=0
        )

        eventos_ate_agora = [
            e
            for e in eventos
            if e["minuto_num"]
            <= minuto_replay
        ]

        gols_casa = 0
        gols_visitante = 0

        for evento in eventos_ate_agora:
            nome = str(
                evento["Evento"]
            ).lower()

            if "goal" in nome:
                if evento["Time"] == casa:
                    gols_casa += 1

                elif evento["Time"] == visitante:
                    gols_visitante += 1

        st.markdown(
            f"## ⚽ {casa} "
            f"{gols_casa} × "
            f"{gols_visitante} "
            f"{visitante}"
        )

        pressao = pressao_eventos(
            eventos,
            minuto_replay,
            casa,
            visitante,
            janela=10
        )

        p1, p2 = st.columns(2)

        p1.metric(
            casa,
            f"{pressao['indice_casa']}%"
        )

        p2.metric(
            visitante,
            f"{pressao['indice_visitante']}%"
        )

        st.write(
            pressao["leitura"]
        )

        if eventos_ate_agora:
            df_eventos = pd.DataFrame(
                eventos_ate_agora
            )

            st.dataframe(
                df_eventos[
                    [
                        "Tempo",
                        "Time",
                        "Evento",
                        "Jogador",
                        "Resultado"
                    ]
                ],
                width="stretch",
                hide_index=True
            )


with aba_sim:

    st.subheader(
        "🧪 Simulador"
    )

    st.caption(
        "Use esta aba para testar o motor de pressão e também o Histórico de Alertas."
    )

    s1, s2 = st.columns(2)

    with s1:
        st.markdown("### 🏠 Time A")

        sim_posse_h = st.slider(
            "Posse Time A",
            0,
            100,
            50,
            key="sim_posse_h"
        )

        sim_corners_h = st.number_input(
            "Escanteios Time A",
            min_value=0,
            value=3,
            key="sim_corners_h"
        )

        sim_dribles_h = st.slider(
            "Dribles certos Time A",
            0,
            100,
            50,
            key="sim_dribles_h"
        )

        sim_amarelos_h = st.number_input(
            "Amarelos Time A",
            min_value=0,
            value=1,
            key="sim_amarelos_h"
        )

    with s2:
        st.markdown("### ✈️ Time B")

        sim_posse_a = st.slider(
            "Posse Time B",
            0,
            100,
            50,
            key="sim_posse_a"
        )

        sim_corners_a = st.number_input(
            "Escanteios Time B",
            min_value=0,
            value=3,
            key="sim_corners_a"
        )

        sim_dribles_a = st.slider(
            "Dribles certos Time B",
            0,
            100,
            50,
            key="sim_dribles_a"
        )

        sim_amarelos_a = st.number_input(
            "Amarelos Time B",
            min_value=0,
            value=1,
            key="sim_amarelos_a"
        )

    sim_home = {
        "possession": sim_posse_h,
        "corners": sim_corners_h,
        "dribbles": sim_dribles_h,
        "yellow": sim_amarelos_h,
        "red": 0
    }

    sim_away = {
        "possession": sim_posse_a,
        "corners": sim_corners_a,
        "dribbles": sim_dribles_a,
        "yellow": sim_amarelos_a,
        "red": 0
    }

    sim_indice_h, sim_indice_a = calcular_indice(
        sim_home,
        sim_away
    )

    if sim_indice_h >= sim_indice_a:
        sim_posse_dominante = sim_home["possession"]
        sim_vantagem_corners = (
            sim_home["corners"]
            - sim_away["corners"]
        )
        sim_momento_aprox = sim_indice_h
    else:
        sim_posse_dominante = sim_away["possession"]
        sim_vantagem_corners = (
            sim_away["corners"]
            - sim_home["corners"]
        )
        sim_momento_aprox = sim_indice_a

    sim_qualidade = calcular_qualidade_alerta(
        max(sim_indice_h, sim_indice_a),
        sim_momento_aprox,
        sim_posse_dominante,
        sim_vantagem_corners
    )

    nivel_sim, icone_sim, dominante_sim, indice_sim = (
        classificar_pressao_simulador(
            sim_indice_h,
            sim_indice_a
        )
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Índice Time A",
        f"{sim_indice_h:.1f}%"
    )

    m2.metric(
        "Índice Time B",
        f"{sim_indice_a:.1f}%"
    )

    m3.metric(
        "Nível atual",
        f"{icone_sim} {nivel_sim}"
    )

    if nivel_sim == "ALTA":
        st.error(
            f"🔥 PRESSÃO ALTA — {dominante_sim}"
        )
    elif nivel_sim == "MODERADA":
        st.warning(
            f"📈 PRESSÃO MODERADA — {dominante_sim}"
        )
    else:
        st.info(
            "⚖️ Cenário equilibrado ou pressão baixa."
        )

    st.write(
        "### 💎 Qualidade do alerta"
    )

    q1, q2 = st.columns(2)

    q1.metric(
        "Score de qualidade",
        f"{sim_qualidade['score']:.1f}/100"
    )

    q2.metric(
        "Classificação",
        f"{sim_qualidade['icone']} "
        f"{sim_qualidade['nivel']} "
        f"{sim_qualidade['estrelas']}"
    )

    st.caption(
        "No simulador, o momento recente é aproximado pelo maior índice atual. "
        "Esse score é experimental e serve para testar o comportamento do modelo."
    )

    sim_qualidade_gravacao = calcular_qualidade_alerta(
        indice_sim,
        indice_sim,
        sim_posse_dominante,
        sim_vantagem_corners
    )

    st.write(
        "### 💾 Score que será gravado"
    )

    sg1, sg2 = st.columns(2)

    sg1.metric(
        "Qualidade persistida",
        f"{sim_qualidade_gravacao['score']:.1f}/100"
    )

    sg2.metric(
        "Classificação persistida",
        sim_qualidade_gravacao["nivel"]
    )

    st.write(
        "### 🧪 Teste do Histórico de Alertas"
    )

    st.caption(
        "O botão abaixo grava somente quando o nível muda. "
        "Exemplo: BAIXA → MODERADA → ALTA."
    )

    if st.button(
        "🚨 Registrar nível atual no histórico",
        key="sim_registrar_alerta"
    ):
        mudou = registrar_alerta_simulador(
            nivel_sim,
            dominante_sim,
            indice_sim,
            sim_posse_dominante,
            sim_vantagem_corners
        )

        if mudou:
            st.success(
                f"✅ Mudança registrada: {nivel_sim}"
            )
        else:
            if (
                st.session_state.ultimo_nivel_simulador
                == nivel_sim
            ):
                st.info(
                    "ℹ️ Nível inicializado ou não houve mudança desde o último registro."
                )

    st.write(
        "Último nível registrado no simulador:",
        st.session_state.ultimo_nivel_simulador
        or "Nenhum"
    )

    if st.button(
        "🔄 Reiniciar teste de alertas",
        key="sim_reset_alertas"
    ):
        st.session_state.ultimo_nivel_simulador = None
        st.rerun()


with aba_hoje:

    hoje_br = data_hoje_brasil()

    st.subheader(
        "⚽ Jogos de hoje"
    )

    st.caption(
        f"Data no Brasil: {hoje_br.strftime('%d/%m/%Y')} • "
        "SportMonks + fonte gratuita complementar."
    )

    jogos_sm, status_sm = buscar_jogos_hoje_sportmonks()

    st.write(
        "### 🟢 Jogos cobertos pela SportMonks"
    )

    if status_sm != 200:
        st.warning(
            f"Não foi possível consultar a SportMonks agora "
            f"(status {status_sm})."
        )

    elif not jogos_sm:
        st.info(
            "Nenhuma partida de hoje foi encontrada nas ligas "
            "SportMonks configuradas no sistema."
        )

    else:
        st.success(
            f"✅ {len(jogos_sm)} partida(s) encontrada(s)"
        )

        for jogo in jogos_sm:
            (
                casa,
                visitante,
                _,
                _
            ) = identificar_times(
                jogo
            )

            liga = LIGAS.get(
                jogo.get("league_id"),
                "Liga"
            )

            gols_h, gols_a = placar_atual(
                jogo
            )

            estado = nome_estado_jogo(
                jogo
            )

            inicio = str(
                jogo.get(
                    "starting_at",
                    "-"
                )
            )

            st.markdown(
                f"⚽ **{casa} × {visitante}**"
            )

            detalhes = (
                f"🏆 {liga} • 🕒 {inicio}"
            )

            if estado:
                detalhes += f" • 📍 {estado}"

            if gols_h or gols_a:
                detalhes += (
                    f" • Placar: {gols_h} × {gols_a}"
                )

            st.caption(
                detalhes
            )

            st.divider()

    st.write(
        "### 🏆 Libertadores — API-Football"
    )

    jogos_api, status_api, restante_api = (
        buscar_jogos_hoje_apifootball()
    )

    if status_api == "SEM_CHAVE":
        st.warning(
            "A chave APIFOOTBALL_KEY ainda não está disponível neste ambiente."
        )

    elif status_api != 200:
        st.warning(
            f"API-Football não respondeu corretamente: {status_api}"
        )

    else:
        libertadores = separar_libertadores_api_football(jogos_api)

        if restante_api is not None:
            st.caption(
                f"Requisições restantes hoje na API-Football: {restante_api}"
            )

        if not libertadores:
            st.info(
                "Nenhum jogo da Libertadores foi retornado para hoje."
            )
        else:
            st.success(
                f"✅ {len(libertadores)} jogo(s) da Libertadores hoje"
            )

            for item in libertadores:
                jogo = formatar_fixture_api_football(item)

                st.markdown(
                    f"⚽ **{jogo['casa']} × {jogo['visitante']}**"
                )

                detalhes = (
                    f"🕒 {jogo['horario']} • "
                    f"🏆 {jogo['liga']}"
                )

                if jogo["status_longo"]:
                    detalhes += f" • {jogo['status_longo']}"

                if (
                    jogo["gols_h"] is not None
                    and jogo["gols_a"] is not None
                ):
                    detalhes += (
                        f" • Placar: {jogo['gols_h']} × {jogo['gols_a']}"
                    )

                if jogo["elapsed"] is not None:
                    detalhes += f" • {jogo['elapsed']}'"

                st.caption(detalhes)

                status_jogo = str(
                    jogo.get("status_longo", "")
                ).lower()

                esta_ao_vivo = (
                    jogo.get("elapsed") is not None
                    or "first half" in status_jogo
                    or "second half" in status_jogo
                    or "primeiro tempo" in status_jogo
                    or "segundo tempo" in status_jogo
                    or "in progress" in status_jogo
                )

                if esta_ao_vivo:
                    renderizar_analise_api_football(
                        jogo["id"]
                    )
                else:
                    st.caption(
                        "📌 A análise detalhada será liberada quando "
                        "a partida estiver ao vivo e a API enviar estatísticas."
                    )

                st.divider()

        st.write(
            "### 🌎 Todos os jogos de hoje — API-Football"
        )

        if not jogos_api:
            st.info(
                "A API-Football não retornou jogos para esta data."
            )
        else:
            filtro_competicao = st.text_input(
                "Filtrar competição ou time",
                "",
                placeholder="Ex.: Brasil, Premier League, Corinthians...",
                key="filtro_api_football_hoje"
            )

            jogos_formatados = [
                formatar_fixture_api_football(item)
                for item in jogos_api
            ]

            if filtro_competicao.strip():
                termo = filtro_competicao.strip().lower()

                jogos_formatados = [
                    jogo
                    for jogo in jogos_formatados
                    if (
                        termo in jogo["casa"].lower()
                        or termo in jogo["visitante"].lower()
                        or termo in jogo["liga"].lower()
                        or termo in jogo["pais"].lower()
                    )
                ]

            jogos_ao_vivo = [
                jogo
                for jogo in jogos_formatados
                if jogo_api_football_ao_vivo(jogo)
            ]

            c1, c2, c3 = st.columns(3)

            c1.metric(
                "Jogos encontrados",
                len(jogos_formatados)
            )

            c2.metric(
                "🔴 Ao vivo agora",
                len(jogos_ao_vivo)
            )

            competicoes = sorted(
                {
                    chave_competicao_api_football(jogo)
                    for jogo in jogos_formatados
                }
            )

            c3.metric(
                "Competições",
                len(competicoes)
            )

            if jogos_ao_vivo:
                st.success(
                    f"🔴 {len(jogos_ao_vivo)} jogo(s) ao vivo. "
                    "Abra uma competição e clique em 'Analisar este jogo agora' "
                    "somente no jogo que quiser acompanhar."
                )

            grupos = {}

            for jogo in jogos_formatados:
                chave = chave_competicao_api_football(
                    jogo
                )

                grupos.setdefault(
                    chave,
                    []
                ).append(
                    jogo
                )

            for competicao in sorted(grupos):
                jogos_comp = grupos[competicao]

                ao_vivo_comp = sum(
                    1
                    for jogo in jogos_comp
                    if jogo_api_football_ao_vivo(jogo)
                )

                titulo_comp = (
                    f"🏆 {competicao} — "
                    f"{len(jogos_comp)} jogo(s)"
                )

                if ao_vivo_comp:
                    titulo_comp += (
                        f" • 🔴 {ao_vivo_comp} ao vivo"
                    )

                with st.expander(
                    titulo_comp,
                    expanded=bool(ao_vivo_comp)
                ):
                    for jogo in jogos_comp:
                        ao_vivo = (
                            jogo_api_football_ao_vivo(
                                jogo
                            )
                        )

                        prefixo = (
                            "🔴"
                            if ao_vivo
                            else "⚽"
                        )

                        st.markdown(
                            f"{prefixo} **{jogo['casa']} × "
                            f"{jogo['visitante']}**"
                        )

                        detalhes = (
                            f"🕒 {jogo['horario']} • "
                            f"{jogo['status_longo'] or 'Status indisponível'}"
                        )

                        if (
                            jogo["gols_h"] is not None
                            and jogo["gols_a"] is not None
                        ):
                            detalhes += (
                                f" • Placar: "
                                f"{jogo['gols_h']} × {jogo['gols_a']}"
                            )

                        if jogo["elapsed"] is not None:
                            detalhes += (
                                f" • {jogo['elapsed']}'"
                            )

                        st.caption(
                            detalhes
                        )

                        if ao_vivo:
                            st.caption(
                                "🔎 Jogo ao vivo. A análise detalhada só será "
                                "consultada quando você pedir, para economizar "
                                "a cota diária da API-Football."
                            )

                            if st.button(
                                "📊 Analisar este jogo agora",
                                key=f"analisar_api_{jogo['id']}"
                            ):
                                renderizar_analise_api_football(
                                    jogo["id"],
                                    jogo.get("casa"),
                                    jogo.get("visitante")
                                )
                        else:
                            st.caption(
                                "📌 A análise ficará disponível quando "
                                "a partida entrar ao vivo."
                            )

                        st.divider()

    st.info(
        "ℹ️ A aba 'Jogos de hoje' reúne SportMonks + API-Football. "
        "A API-Football amplia a agenda, incluindo Libertadores quando disponível. "
        "Por enquanto, pressão, score e validação automática continuam na estrutura SportMonks."
    )


with aba_futuros:

    st.subheader(
        "📅 Próximas partidas"
    )

    inicio = date.today()
    fim = inicio + timedelta(
        days=14
    )

    url = (
        f"{BASE_URL}/fixtures/"
        f"between/"
        f"{inicio.isoformat()}/"
        f"{fim.isoformat()}"
    )

    params = {
        "api_token": TOKEN,
        "include": "participants;state",
        "per_page": 100
    }

    dados, status = requisicao(
        url,
        params
    )

    if status == 200:
        jogos = dados.get(
            "data",
            []
        )

        jogos = [
            jogo
            for jogo in jogos
            if jogo.get("league_id") in LIGAS
        ]

        st.write(
            "Partidas encontradas:",
            len(jogos)
        )

        for jogo in jogos[:30]:
            (
                casa,
                visitante,
                _,
                _
            ) = identificar_times(
                jogo
            )

            liga = LIGAS.get(
                jogo.get("league_id"),
                "Liga"
            )

            st.write(
                f"⚽ **{casa} × {visitante}** "
                f"— {liga} — "
                f"{jogo.get('starting_at', '-')}"
            )


with aba_historico:

    st.subheader(
        "💾 Histórico salvo"
    )

    if ARQUIVO_HISTORICO.exists():
        historico_salvo = pd.read_csv(
            ARQUIVO_HISTORICO
        )

        st.success(
            f"✅ {len(historico_salvo)} "
            "registros salvos"
        )

        st.dataframe(
            historico_salvo,
            width="stretch"
        )

    else:
        st.info(
            "Ainda não existe histórico salvo."
        )

with aba_alertas:

    st.subheader(
        "🚨 Histórico de alertas"
    )

    st.caption(
        "Registra mudanças de nível de pressão e salva também "
        "o score de qualidade calculado no momento do alerta."
    )

    alertas_salvos = ler_alertas_historico()

    if not alertas_salvos.empty:

        # Compatibilidade com registros antigos:
        # placar SIMULAÇÃO => SIMULACAO; demais => REAL.
        origem_atual = (
            alertas_salvos["origem"]
            .fillna("")
            .astype(str)
            .str.strip()
        )

        mascara_sem_origem = origem_atual.eq("")

        alertas_salvos.loc[
            mascara_sem_origem
            & alertas_salvos["placar"]
            .astype(str)
            .str.upper()
            .str.contains("SIMULA"),
            "origem"
        ] = "SIMULACAO"

        alertas_salvos.loc[
            mascara_sem_origem
            & ~alertas_salvos["placar"]
            .astype(str)
            .str.upper()
            .str.contains("SIMULA"),
            "origem"
        ] = "REAL"

        reais_alertas = alertas_salvos[
            alertas_salvos["origem"]
            .astype(str)
            .eq("REAL")
        ].copy()

        simulados_alertas = alertas_salvos[
            alertas_salvos["origem"]
            .astype(str)
            .eq("SIMULACAO")
        ].copy()

        st.success(
            f"✅ {len(alertas_salvos)} mudança(s) de pressão registrada(s)"
        )

        r1, r2, r3 = st.columns(3)

        r1.metric(
            "🟢 Alertas REAIS",
            len(reais_alertas)
        )

        r2.metric(
            "🧪 Alertas de SIMULAÇÃO",
            len(simulados_alertas)
        )

        scores_reais = pd.to_numeric(
            reais_alertas["qualidade_score"],
            errors="coerce"
        ).dropna()

        qualidade_real_media = (
            scores_reais.mean()
            if len(scores_reais) > 0
            else 0
        )

        r3.metric(
            "💎 Qualidade média REAL",
            (
                f"{qualidade_real_media:.1f}/100"
                if len(scores_reais) > 0
                else "Sem dados"
            )
        )

        a1, a2, a3, a4 = st.columns(4)

        a1.metric(
            "Entradas em ALTA",
            int(
                (
                    alertas_salvos["nivel_novo"]
                    .astype(str)
                    == "ALTA"
                ).sum()
            )
        )

        a2.metric(
            "Entradas em MODERADA",
            int(
                (
                    alertas_salvos["nivel_novo"]
                    .astype(str)
                    == "MODERADA"
                ).sum()
            )
        )

        a3.metric(
            "Entradas em BAIXA",
            int(
                (
                    alertas_salvos["nivel_novo"]
                    .astype(str)
                    == "BAIXA"
                ).sum()
            )
        )

        scores = pd.to_numeric(
            alertas_salvos["qualidade_score"],
            errors="coerce"
        ).dropna()

        score_medio = (
            scores.mean()
            if len(scores) > 0
            else 0
        )

        a4.metric(
            "Qualidade média geral",
            f"{score_medio:.1f}/100"
        )

        st.write(
            "### 💎 Distribuição por qualidade"
        )

        qualidade_counts = (
            alertas_salvos["qualidade_nivel"]
            .fillna("Sem classificação")
            .astype(str)
            .replace("", "Sem classificação")
            .value_counts()
            .rename_axis("Qualidade")
            .reset_index(name="Quantidade")
        )

        st.dataframe(
            qualidade_counts,
            width="stretch",
            hide_index=True
        )

        st.write(
            "### 📋 Registros"
        )

        colunas_exibir = [
            "data_hora",
            "jogo",
            "minuto",
            "placar",
            "nivel_anterior",
            "nivel_novo",
            "time_destaque",
            "indice",
            "momento_10_min",
            "qualidade_score",
            "qualidade_nivel",
            "origem"
        ]

        st.dataframe(
            alertas_salvos[
                colunas_exibir
            ].sort_values(
                "data_hora",
                ascending=False
            ),
            width="stretch",
            hide_index=True
        )

        st.write(
            "### 🟢 Base REAL para calibração"
        )

        if reais_alertas.empty:
            st.info(
                "Ainda não existem alertas REAIS. "
                "As simulações ficam armazenadas, mas não entram na calibração real."
            )
        else:
            st.dataframe(
                reais_alertas[
                    colunas_exibir
                ].sort_values(
                    "data_hora",
                    ascending=False
                ),
                width="stretch",
                hide_index=True
            )

        st.download_button(
            "⬇️ Baixar histórico de alertas",
            data=alertas_salvos.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="historico_alertas.csv",
            mime="text/csv"
        )

        st.caption(
            "Registros antigos podem aparecer sem score. "
            "Os próximos alertas reais serão gravados com qualidade automaticamente."
        )

    else:

        st.info(
            "Ainda não há mudanças de pressão registradas. "
            "O arquivo será criado automaticamente quando um jogo ao vivo "
            "mudar de nível."
        )


with aba_validacao:

    st.subheader(
        "🎯 Validação dos alertas ALTA"
    )

    st.caption(
        "Avalia o que acontece após alertas de pressão ALTA em até 10 minutos "
        "e separa a performance REAL por gol, escanteio e qualidade do alerta."
    )

    st.info(
        "A captura REAL é automática. Para validar gols e eventos corretamente, "
        "o fixture ao vivo é consultado com events.type e statistics.type."
    )

    df_validacao = ler_validacoes()

    if not df_validacao.empty:
        painel_desempenho_real(
            df_validacao
        )

        st.divider()

    if df_validacao.empty:

        st.info(
            "Ainda não há alertas ALTA em acompanhamento. "
            "Quando uma partida ao vivo entrar em ALTA, "
            "o sistema criará uma avaliação automaticamente."
        )

    else:

        reais = df_validacao[
            df_validacao["status"].astype(str)
            != "DEMO"
        ].copy()

        demos = df_validacao[
            df_validacao["status"].astype(str)
            == "DEMO"
        ].copy()

        resumo_reais = resumo_resultados_validacao(
            reais
        )

        st.write(
            "### 📊 Resumo real"
        )

        if resumo_reais["total"] == 0:

            st.info(
                "Ainda não existem alertas reais concluídos. "
                "Os registros DEMO ficam separados das estatísticas."
            )

        else:

            r1, r2, r3, r4, r5 = st.columns(5)

            r1.metric(
                "Alertas reais",
                resumo_reais["total"]
            )

            r2.metric(
                "🟢 Gol destaque",
                resumo_reais["gol_destaque"]
            )

            r3.metric(
                "🔴 Gol adversário",
                resumo_reais["gol_adversario"]
            )

            r4.metric(
                "⚪ Sem gol",
                resumo_reais["sem_gol"]
            )

            r5.metric(
                "⏳ Pendentes",
                resumo_reais["pendentes"]
            )

            t1, t2, t3 = st.columns(3)

            t1.metric(
                "Taxa gol destaque",
                f"{resumo_reais['taxa_destaque']:.1f}%"
            )

            t2.metric(
                "Taxa gol adversário",
                f"{resumo_reais['taxa_adversario']:.1f}%"
            )

            t3.metric(
                "Taxa sem gol",
                f"{resumo_reais['taxa_sem_gol']:.1f}%"
            )

            st.caption(
                "As taxas usam apenas alertas concluídos; "
                "os que ainda estão em acompanhamento ficam fora do denominador."
            )

            st.write(
                "### 🚩 Escanteios após PRESSÃO ALTA"
            )

            base_corner5 = reais[
                reais["escanteio_time_destaque_5_min"]
                .astype(str)
                .isin(["SIM", "NÃO"])
            ]

            base_corner10 = reais[
                reais["escanteio_time_destaque_10_min"]
                .astype(str)
                .isin(["SIM", "NÃO"])
            ]

            corners5 = int(
                (
                    reais["escanteio_time_destaque_5_min"]
                    .astype(str)
                    == "SIM"
                ).sum()
            )

            corners10 = int(
                (
                    reais["escanteio_time_destaque_10_min"]
                    .astype(str)
                    == "SIM"
                ).sum()
            )

            taxa_corner5 = (
                (
                    base_corner5[
                        "escanteio_time_destaque_5_min"
                    ].astype(str)
                    == "SIM"
                ).mean() * 100
                if len(base_corner5) > 0
                else 0
            )

            taxa_corner10 = (
                (
                    base_corner10[
                        "escanteio_time_destaque_10_min"
                    ].astype(str)
                    == "SIM"
                ).mean() * 100
                if len(base_corner10) > 0
                else 0
            )

            c1, c2, c3, c4 = st.columns(4)

            c1.metric(
                "Corner destaque ≤5 min",
                corners5
            )
            c2.metric(
                "Taxa corner ≤5 min",
                f"{taxa_corner5:.1f}%"
            )
            c3.metric(
                "Corner destaque ≤10 min",
                corners10
            )
            c4.metric(
                "Taxa corner ≤10 min",
                f"{taxa_corner10:.1f}%"
            )

            faixas = tabela_faixas_desempenho(
                reais
            )

            if not faixas.empty:

                st.write(
                    "### 🧠 Desempenho por faixa"
                )

                st.caption(
                    "Ajuda a descobrir quais níveis de índice e momento recente "
                    "têm melhor taxa de gol do time em destaque."
                )

                st.dataframe(
                    faixas,
                    width="stretch",
                    hide_index=True
                )

            qualidade_hist = resumo_qualidade_historica(
                reais
            )

            if not qualidade_hist.empty:

                st.write(
                    "### 💎 Eficiência por qualidade do alerta"
                )

                st.caption(
                    "Quando houver amostra real suficiente, esta tabela permitirá "
                    "comparar quais faixas de qualidade têm melhor desempenho."
                )

                st.dataframe(
                    qualidade_hist,
                    width="stretch",
                    hide_index=True
                )

        st.write(
            "### 📋 Registros"
        )

        tabela = df_validacao.copy()

        tabela[
            "resultado_resumido"
        ] = tabela.apply(
            classificar_resultado_validacao,
            axis=1
        )

        colunas_prioridade = [
            "data_hora_alerta",
            "jogo",
            "minuto_alerta",
            "placar_alerta",
            "time_destaque",
            "indice_alerta",
            "momento_10_min",
            "qualidade_score",
            "qualidade_nivel",
            "resultado_resumido",
            "time_gol",
            "minuto_gol",
            "minutos_apos_alerta",
            "gol_time_destaque_5_min",
            "gol_time_destaque_10_min",
            "escanteio_time_destaque_5_min",
            "escanteio_time_destaque_10_min",
            "primeiro_escanteio_time",
            "primeiro_escanteio_minuto",
            "minutos_ate_escanteio",
            "status"
        ]

        colunas_existentes = [
            c
            for c in colunas_prioridade
            if c in tabela.columns
        ]

        st.dataframe(
            tabela[
                colunas_existentes
            ].sort_values(
                "data_hora_alerta",
                ascending=False
            ),
            width="stretch",
            hide_index=True
        )

        st.download_button(
            "⬇️ Baixar validação em CSV",
            data=df_validacao.to_csv(
                index=False
            ).encode("utf-8"),
            file_name="validacao_alertas.csv",
            mime="text/csv"
        )

        if not demos.empty:
            st.caption(
                f"🧪 {len(demos)} registro(s) DEMO presente(s). "
                "Eles não entram nas métricas reais."
            )

    st.divider()

    st.write(
        "### 🧪 Teste do validador"
    )

    st.caption(
        "Use os DEMOs apenas para verificar o painel. "
        "Eles não entram nas taxas reais."
    )

    d1, d2, d3 = st.columns(3)

    with d1:
        if st.button(
            "DEMO: gol do destaque",
            key="criar_demo_validacao"
        ):
            criado = criar_demo_validacao()

            if criado:
                st.success(
                    "✅ DEMO criado: Time A marcou 4 min após o alerta."
                )
                st.rerun()
            else:
                st.info(
                    "Esse DEMO já existe."
                )

    with d2:
        if st.button(
            "DEMO: gol do adversário",
            key="criar_demo_adversario"
        ):
            criado = criar_demo_gol_adversario()

            if criado:
                st.success(
                    "✅ DEMO criado: adversário marcou 3 min após o alerta."
                )
                st.rerun()
            else:
                st.info(
                    "Esse DEMO já existe."
                )

    with d3:
        if st.button(
            "Remover testes DEMO",
            key="remover_demo_validacao"
        ):
            limpar_demo_validacao()
            st.success(
                "✅ DEMOs removidos."
            )
            st.rerun()
