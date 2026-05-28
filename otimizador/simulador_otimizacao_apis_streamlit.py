from __future__ import annotations

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "otimizador"

API_ORDER = [
    "Comportamento Financeiro Digital",
    "Presenca Online",
    "Passagens pela Web",
    "Presenca Online Familiar",
]
API_COLORS = {
    "Comportamento Financeiro Digital": "#2F7D6D",
    "Presenca Online": "#4C78A8",
    "Passagens pela Web": "#F2B134",
    "Presenca Online Familiar": "#D95F59",
}
TYPE_COLORS = {
    "Associados novos": "#2F7D6D",
    "Associados da base": "#4C78A8",
}


st.set_page_config(page_title="Simulador de Enriquecimento API", layout="wide")


@st.cache_data
def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    population = pd.read_csv(DATA_DIR / "population_summary.csv")
    prices = pd.read_csv(DATA_DIR / "api_prices.csv")
    return population, prices


def br_int(value: float) -> str:
    return f"{value:,.0f}".replace(",", ".")


def br_money(value: float, decimals: int = 2) -> str:
    return "R$ " + f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md_money(value: float, decimals: int = 2) -> str:
    return br_money(value, decimals).replace("$", "\\$")


def br_pct(value: float) -> str:
    return f"{value * 100:.1f}%".replace(".", ",")


def recurring_base_text(base_rows: int, base_ids: int) -> list[str]:
    if base_ids <= 0 or base_rows <= 0:
        return ["Nenhum associado da base seria enriquecido com a configuração atual."]

    full_rounds = base_rows // base_ids
    remainder = base_rows % base_ids

    if full_rounds == 0:
        not_enriched = base_ids - base_rows
        return [
            f"{br_int(base_rows)} associados da base enriquecidos 1x.",
            f"{br_int(not_enriched)} associados da base ainda ficariam sem enriquecimento.",
        ]

    lines = []
    if remainder > 0:
        lines.append(f"{br_int(remainder)} associados da base enriquecidos {full_rounds + 1}x.")
        lines.append(f"{br_int(base_ids - remainder)} associados da base enriquecidos {full_rounds}x.")
    else:
        lines.append(f"{br_int(base_ids)} associados da base enriquecidos {full_rounds}x.")
    return lines


def unit_price(api_name: str, volume: int, prices: pd.DataFrame) -> float:
    if volume <= 0:
        return 0.0

    api_prices = prices[prices["nome_api"].eq(api_name)]
    match = api_prices[(api_prices["faixa_min"] <= volume) & (volume <= api_prices["faixa_max"])]
    if match.empty:
        max_volume = int(api_prices["faixa_max"].max())
        raise ValueError(f"{api_name}: volume {br_int(volume)} acima da maior faixa cadastrada ({br_int(max_volume)}).")
    return float(match.iloc[0]["valor_por_consulta"])


def calculate_cost(
    new_rows: int,
    base_rows: int,
    new_apis: list[str],
    base_apis: list[str],
    prices: pd.DataFrame,
) -> tuple[float, pd.DataFrame]:
    rows = []
    selected_apis = [api for api in API_ORDER if api in set(new_apis) | set(base_apis)]

    for api in selected_apis:
        volume_new = new_rows if api in new_apis else 0
        volume_base = base_rows if api in base_apis else 0
        volume_total = volume_new + volume_base
        price = unit_price(api, volume_total, prices)

        if volume_new > 0:
            rows.append(
                {
                    "api": api,
                    "tipo_associado": "Associados novos",
                    "volume_linhas": volume_new,
                    "preco_unitario": price,
                    "custo": volume_new * price,
                }
            )
        if volume_base > 0:
            rows.append(
                {
                    "api": api,
                    "tipo_associado": "Associados da base",
                    "volume_linhas": volume_base,
                    "preco_unitario": price,
                    "custo": volume_base * price,
                }
            )

    detail = pd.DataFrame(rows)
    if detail.empty:
        return 0.0, pd.DataFrame(columns=["api", "tipo_associado", "volume_linhas", "preco_unitario", "custo"])
    return float(detail["custo"].sum()), detail


def find_max_base_rows(
    budget: float,
    new_rows: int,
    max_base_rows: int,
    new_apis: list[str],
    base_apis: list[str],
    prices: pd.DataFrame,
) -> tuple[int, float, pd.DataFrame]:
    lo, hi = 0, max_base_rows
    best_rows = 0
    best_cost = 0.0
    best_detail = pd.DataFrame()

    while lo <= hi:
        mid = (lo + hi) // 2
        try:
            cost, detail = calculate_cost(new_rows, mid, new_apis, base_apis, prices)
        except ValueError:
            hi = mid - 1
            continue

        if cost <= budget:
            best_rows = mid
            best_cost = cost
            best_detail = detail
            lo = mid + 1
        else:
            hi = mid - 1

    return best_rows, best_cost, best_detail


def make_bar_chart(data: pd.DataFrame, group_col: str, value_col: str, title: str, colors: dict[str, str]) -> alt.Chart:
    plot = data.groupby(group_col, as_index=False)[value_col].sum()
    return (
        alt.Chart(plot)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X(f"{group_col}:N", sort=None, title=""),
            y=alt.Y(f"{value_col}:Q", title=title),
            color=alt.Color(
                f"{group_col}:N",
                scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip(f"{group_col}:N", title="Grupo"),
                alt.Tooltip(f"{value_col}:Q", title=title, format=",.2f"),
            ],
        )
        .properties(height=310)
    )


def make_stacked_chart(data: pd.DataFrame, color_col: str, title: str, colors: dict[str, str]) -> alt.Chart:
    return (
        alt.Chart(data)
        .mark_bar()
        .encode(
            x=alt.X("custo:Q", title="Custo estimado"),
            y=alt.Y("cenario:N", title="", sort=None),
            color=alt.Color(
                f"{color_col}:N",
                scale=alt.Scale(domain=list(colors.keys()), range=list(colors.values())),
                title="",
            ),
            tooltip=[
                alt.Tooltip(f"{color_col}:N", title="Abertura"),
                alt.Tooltip("volume_linhas:Q", title="Linhas", format=",.0f"),
                alt.Tooltip("preco_unitario:Q", title="Preco unitario", format=".4f"),
                alt.Tooltip("custo:Q", title="Custo", format=",.2f"),
            ],
        )
        .properties(title=title, height=170)
    )


population, prices = load_inputs()
metrics = dict(zip(population["metrica"], population["valor"]))

default_new_rows = int(metrics.get("Linhas de associados novos", 0))
default_base_rows = int(metrics.get("Linhas de associados da base", 0))
total_rows = int(metrics.get("Linhas totais", default_new_rows + default_base_rows))
total_ids = int(metrics.get("IDs unicos", 0))
new_ids = int(metrics.get("IDs de associados novos", default_new_rows))
base_ids = int(metrics.get("IDs de associados da base", 0))

st.title("Simulador de otimizacao de enriquecimento por APIs")

st.subheader("Premissas gerais")
general_cols = st.columns(5)
general_cols[0].metric("Orcamento padrao", br_money(20_000, 0))
general_cols[1].metric("Linhas novos", br_int(default_new_rows))
general_cols[2].metric("IDs novos", br_int(new_ids))
general_cols[3].metric("Linhas base", br_int(default_base_rows))
general_cols[4].metric("IDs base", br_int(base_ids))

with st.expander("Custos das APIs por faixa de volumetria", expanded=True):
    price_view = prices.copy()
    price_view["faixa"] = price_view["faixa_min"].map(br_int) + " a " + price_view["faixa_max"].map(br_int)
    price_view["valor_por_consulta"] = price_view["valor_por_consulta"].map(lambda x: br_money(x, 3))
    st.dataframe(
        price_view[["nome_api", "faixa", "valor_por_consulta", "papel_analitico"]],
        use_container_width=True,
        hide_index=True,
    )

with st.sidebar:
    st.header("Configuracao")
    budget = st.number_input("Orcamento geral", min_value=0.0, value=20_000.0, step=1_000.0, format="%.2f")
    new_rows = st.number_input(
        "Linhas de associados novos",
        min_value=0,
        max_value=total_rows,
        value=default_new_rows,
        step=1_000,
    )
    max_base_rows = st.number_input(
        "Limite de linhas da base",
        min_value=0,
        max_value=default_base_rows,
        value=default_base_rows,
        step=10_000,
    )
    new_apis = st.multiselect(
        "APIs para associados novos",
        options=API_ORDER,
        default=API_ORDER,
    )
    base_apis = st.multiselect(
        "APIs para associados da base",
        options=API_ORDER,
        default=["Comportamento Financeiro Digital"],
    )

if not new_apis and not base_apis:
    st.warning("Selecione pelo menos uma API para simular.")
    st.stop()

try:
    base_rows, total_cost, detail = find_max_base_rows(
        budget=budget,
        new_rows=int(new_rows),
        max_base_rows=int(max_base_rows),
        new_apis=new_apis,
        base_apis=base_apis,
        prices=prices,
    )
except ValueError as exc:
    st.error(str(exc))
    st.stop()

remaining = budget - total_cost
new_cost = detail.loc[detail["tipo_associado"].eq("Associados novos"), "custo"].sum()
base_cost = detail.loc[detail["tipo_associado"].eq("Associados da base"), "custo"].sum()
total_enriched_rows = int(new_rows) * len(new_apis) + base_rows * len(base_apis)

st.subheader("Resultado da simulacao")
kpi_cols = st.columns(5)
kpi_cols[0].metric("Custo total", br_money(total_cost))
kpi_cols[1].metric("Sobra orcamento", br_money(remaining))
kpi_cols[2].metric("Linhas base possiveis", br_int(base_rows))
kpi_cols[3].metric("Chamadas novos", br_int(int(new_rows) * len(new_apis)))
kpi_cols[4].metric("Chamadas totais", br_int(total_enriched_rows))

if total_cost == 0:
    st.info("Nenhum custo calculado com a configuracao atual.")
    st.stop()

bullet_cols = st.columns([1.1, 1])
with bullet_cols[0]:
    st.markdown("**Leitura executiva**")
    st.markdown(
        f"""
- O pacote selecionado usa **{len(new_apis)} API(s)** para associados novos e **{len(base_apis)} API(s)** para associados da base.
- Com orçamento de **{md_money(budget)}**, a base comporta **{br_int(base_rows)} linhas adicionais**.
- O custo dos associados novos fica em **{md_money(new_cost)}**; a base consome **{md_money(base_cost)}**.
- A sobra estimada e **{md_money(remaining)}**, considerando preços por faixa de volume total de cada API.
"""
    )

with bullet_cols[1]:
    st.markdown("**Cobertura aproximada da base**")
    pct_base_lines = base_rows / default_base_rows if default_base_rows else 0
    pct_base_ids = min(base_rows / base_ids, 1.0) if base_ids else 0
    recurring_lines = recurring_base_text(base_rows, base_ids)
    st.markdown(
        f"""
- Linhas da base cobertas: **{br_pct(pct_base_lines)}** do universo disponivel.
- Equivalente a ate **{br_pct(pct_base_ids)}** dos IDs da base com 1 ponto, se a alocacao for distribuida.
- Se houver mais APIs na base, o mesmo orçamento cobre menos linhas por associado.
"""
    )
    st.markdown("**Recorrencia possivel nos IDs da base**")
    st.markdown("\n".join(f"- {line}" for line in recurring_lines))

chart_data = detail.copy()
chart_data["cenario"] = "Simulacao"

left_chart, right_chart = st.columns(2)
with left_chart:
    st.altair_chart(
        make_stacked_chart(chart_data, "api", "Orcamento por API", API_COLORS),
        use_container_width=True,
    )
with right_chart:
    st.altair_chart(
        make_stacked_chart(chart_data, "tipo_associado", "Orcamento por tipo de associado", TYPE_COLORS),
        use_container_width=True,
    )

volume_chart, cost_chart = st.columns(2)
with volume_chart:
    st.altair_chart(
        make_bar_chart(chart_data, "tipo_associado", "volume_linhas", "Linhas enriquecidas", TYPE_COLORS),
        use_container_width=True,
    )
with cost_chart:
    st.altair_chart(
        make_bar_chart(chart_data, "api", "custo", "Custo por API", API_COLORS),
        use_container_width=True,
    )

st.subheader("Detalhamento da conta")
detail_view = detail.copy()
detail_view["volume_linhas"] = detail_view["volume_linhas"].map(br_int)
detail_view["preco_unitario"] = detail_view["preco_unitario"].map(lambda x: br_money(x, 3))
detail_view["custo"] = detail_view["custo"].map(lambda x: br_money(x, 2))
st.dataframe(detail_view, use_container_width=True, hide_index=True)

api_summary = (
    detail.groupby("api", as_index=False)
    .agg(volume_total=("volume_linhas", "sum"), preco_unitario=("preco_unitario", "first"), custo_total=("custo", "sum"))
)
api_summary["volume_total"] = api_summary["volume_total"].map(br_int)
api_summary["preco_unitario"] = api_summary["preco_unitario"].map(lambda x: br_money(x, 3))
api_summary["custo_total"] = api_summary["custo_total"].map(lambda x: br_money(x, 2))

st.subheader("Resumo por API")
st.dataframe(api_summary, use_container_width=True, hide_index=True)
