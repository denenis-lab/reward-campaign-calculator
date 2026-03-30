import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Калькулятор Reward-кампании",
    page_icon="💰",
    layout="wide",
)

# ── Sidebar: Параметры кампании ───────────────────────────────────────────────

st.sidebar.header("Параметры кампании")

budget = st.sidebar.number_input("Бюджет (USD)", value=100_000, step=10_000, format="%d")
reward_rate = st.sidebar.number_input("Годовая ставка (%)", value=15.0, step=1.0, format="%.1f") / 100

interest_mode = st.sidebar.radio(
    "Тип процентов",
    ["Simple", "Compound (monthly)"],
    index=0,
    help="Simple: reward = баланс × ставка × дни/365. Compound: reward = баланс × ((1 + ставка/12)^месяцев − 1)",
)

st.sidebar.subheader("Сроки (дни)")
col1, col2, col3 = st.sidebar.columns(3)
period_1 = col1.number_input("30д", value=30, step=10, key="p1")
period_2 = col2.number_input("60д", value=60, step=10, key="p2")
period_3 = col3.number_input("90д", value=90, step=10, key="p3")
periods = [period_1, period_2, period_3]

st.sidebar.subheader("Cap на баланс (USD)")
col1, col2, col3 = st.sidebar.columns(3)
cap_1 = col1.number_input("$500", value=500, step=100, key="c1")
cap_2 = col2.number_input("$1k", value=1000, step=100, key="c2")
cap_3 = col3.number_input("$2k", value=2000, step=100, key="c3")
caps = [cap_1, cap_2, cap_3]

# ── Заголовок ─────────────────────────────────────────────────────────────────

st.title("Калькулятор Reward-кампании")
st.caption("Сценарный анализ маркетинговой кампании с вознаграждением за хранение средств на балансе")

# ── Расчётные функции ────────────────────────────────────────────────────────


def calc_reward(balance: float, rate: float, days: int, mode: str) -> float:
    """Calculate reward per user for a given balance."""
    if mode == "Simple":
        return balance * rate * (days / 365)
    else:
        months = days / 30
        return balance * ((1 + rate / 12) ** months - 1)


def calculate_campaign_cost(users_df: pd.DataFrame, rate: float, days: int, cap: float, mode: str) -> pd.DataFrame:
    df = users_df.copy()
    df["Учитываемый баланс"] = df["Ср. баланс ($)"].clip(upper=cap)
    df["Reward на юзера"] = df["Учитываемый баланс"].apply(lambda b: calc_reward(b, rate, days, mode))
    df["Стоимость бакета"] = df["Reward на юзера"] * df["Пользователи"]
    return df


def build_cost_matrix(users_df: pd.DataFrame, rate: float, periods: list, caps: list, mode: str) -> pd.DataFrame:
    rows = []
    for days in periods:
        row = {"Срок (дни)": days}
        for cap in caps:
            result = calculate_campaign_cost(users_df, rate, days, cap, mode)
            row[f"Cap ${cap:,.0f}"] = result["Стоимость бакета"].sum()
        rows.append(row)
    return pd.DataFrame(rows)


# ── Рекомендации — 3 сценария ────────────────────────────────────────────────

def generate_scenarios(cost_matrix: pd.DataFrame, caps: list, periods: list, budget: float, users_df: pd.DataFrame, rate: float, mode: str):
    """Find conservative, balanced, and aggressive scenarios from the cost matrix."""
    cap_cols = [c for c in cost_matrix.columns if c.startswith("Cap")]

    combos = []
    for _, row in cost_matrix.iterrows():
        days = int(row["Срок (дни)"])
        for cap, col in zip(caps, cap_cols):
            cost = row[col]
            capped_users = users_df.loc[users_df["Ср. баланс ($)"] > cap, "Пользователи"].sum()
            total = users_df["Пользователи"].sum()
            capped_pct = capped_users / total * 100
            cost_per_user = cost / total
            combos.append({
                "days": days, "cap": cap, "cost": cost,
                "pct_budget": cost / budget * 100,
                "capped_pct": capped_pct,
                "cost_per_user": cost_per_user,
            })

    in_budget = [c for c in combos if c["cost"] <= budget]
    over_budget = [c for c in combos if c["cost"] > budget]

    scenarios = []

    # Conservative: cheapest in budget
    if in_budget:
        conservative = min(in_budget, key=lambda c: c["cost"])
        conservative["label"] = "Консервативный"
        conservative["desc"] = "Минимальная стоимость, комфортно в бюджете"
        scenarios.append(conservative)

    # Balanced: best coverage within budget (max days × cap while in budget)
    if in_budget:
        balanced = max(in_budget, key=lambda c: (c["days"] * c["cap"], -c["capped_pct"]))
        if not scenarios or (balanced["days"] != scenarios[0]["days"] or balanced["cap"] != scenarios[0]["cap"]):
            balanced["label"] = "Сбалансированный ⭐"
            balanced["desc"] = "Лучший охват в рамках бюджета"
            scenarios.append(balanced)
        else:
            candidates = [c for c in in_budget if not (c["days"] == balanced["days"] and c["cap"] == balanced["cap"])]
            if candidates:
                alt = max(candidates, key=lambda c: (c["days"] * c["cap"], -c["capped_pct"]))
                alt["label"] = "Сбалансированный ⭐"
                alt["desc"] = "Лучший охват в рамках бюджета"
                scenarios.append(alt)

    # Aggressive: cheapest over budget, or most expensive in budget
    if over_budget:
        aggressive = min(over_budget, key=lambda c: c["cost"])
        aggressive["label"] = "Агрессивный"
        aggressive["desc"] = "Максимальный охват, превышает бюджет"
        scenarios.append(aggressive)
    elif in_budget:
        aggressive = max(in_budget, key=lambda c: c["cost"])
        if not any(s["days"] == aggressive["days"] and s["cap"] == aggressive["cap"] for s in scenarios):
            aggressive["label"] = "Агрессивный"
            aggressive["desc"] = "Максимальный охват в рамках бюджета"
            scenarios.append(aggressive)

    return scenarios


st.subheader("Рекомендуемые сценарии")

# Распределение пользователей
default_data = pd.DataFrame({
    "Бакет": ["0–200", "200–500", "500–1,000", "1,000–2,000", "2,000+"],
    "Пользователи": [2500, 4000, 1500, 700, 300],
    "Ср. баланс ($)": [120, 320, 700, 1400, 3500],
})

st.caption("Распределение пользователей (можно редактировать в таблице ниже)")

edited_df = st.data_editor(
    default_data,
    width="stretch",
    num_rows="fixed",
    hide_index=True,
    column_config={
        "Бакет": st.column_config.TextColumn(disabled=True),
        "Пользователи": st.column_config.NumberColumn(min_value=0, step=100),
        "Ср. баланс ($)": st.column_config.NumberColumn(min_value=0, step=50),
    },
    key="user_dist",
)

total_users = edited_df["Пользователи"].sum()
total_balance = (edited_df["Пользователи"] * edited_df["Ср. баланс ($)"]).sum()

# Build cost matrix for scenarios
cost_matrix = build_cost_matrix(edited_df, reward_rate, periods, caps, interest_mode)
cap_cols = [c for c in cost_matrix.columns if c.startswith("Cap")]

scenarios = generate_scenarios(cost_matrix, caps, periods, budget, edited_df, reward_rate, interest_mode)

if scenarios:
    cols = st.columns(len(scenarios))
    for col, s in zip(cols, scenarios):
        with col:
            in_budget = s["cost"] <= budget
            delta_color = "normal" if in_budget else "inverse"
            st.metric(
                label=s["label"],
                value=f"{s['days']}д × ${s['cap']:,.0f} cap",
                delta=f"${s['cost']:,.0f} ({s['pct_budget']:.0f}% бюджета)",
                delta_color=delta_color,
            )
            st.caption(s["desc"])
            st.markdown(f"""
- **Стоимость/юзер:** ${s['cost_per_user']:.2f}
- **Обрезаны cap'ом:** {s['capped_pct']:.0f}%
""")

    st.info("**После запуска:** замерить retention на 30-й и 60-й день. Использовать реальные данные для калибровки следующей кампании — data-driven, а не гадание.")
else:
    st.warning("Нет доступных сценариев с текущими параметрами.")

# ── Сводка пользователей ─────────────────────────────────────────────────────

st.divider()
st.subheader("Распределение пользователей")

c1, c2 = st.columns(2)
c1.metric("Всего пользователей", f"{total_users:,.0f}")
c2.metric("Общий баланс", f"${total_balance:,.0f}")

# ── Матрица стоимости ─────────────────────────────────────────────────────────

st.divider()
st.subheader("Матрица стоимости")

display_matrix = cost_matrix.copy()
for col in cap_cols:
    display_matrix[col] = cost_matrix[col].apply(
        lambda v: f"${v:,.0f} ✓" if v <= budget else f"${v:,.0f} ✗"
    )
display_matrix["Срок (дни)"] = display_matrix["Срок (дни)"].astype(int)

col_config = {col: st.column_config.TextColumn(label=col) for col in cap_cols}
col_config["Срок (дни)"] = st.column_config.NumberColumn(format="%d")

st.dataframe(display_matrix, width="stretch", hide_index=True, column_config=col_config)
st.caption("✓ Укладывается в бюджет · ✗ Превышает бюджет")

# ── Тепловая карта ────────────────────────────────────────────────────────────

st.subheader("Тепловая карта стоимости")

z_values = cost_matrix[cap_cols].values
x_labels = [f"Cap ${c:,.0f}" for c in caps]
y_labels = [f"{p} дней" for p in periods]

annotations = []
for i, row_vals in enumerate(z_values):
    for j, val in enumerate(row_vals):
        pct = val / budget * 100
        symbol = "✓" if val <= budget else "✗"
        annotations.append(
            dict(
                x=j, y=i,
                text=f"<b>${val:,.0f}</b><br>{pct:.0f}% {symbol}",
                showarrow=False,
                font=dict(size=16, color="white", family="Arial"),
            )
        )

fig_heatmap = go.Figure(
    data=go.Heatmap(
        z=z_values,
        colorscale=[
            [0, "#1a472a"],
            [0.5, "#f59e0b"],
            [1, "#991b1b"],
        ],
        zmin=0,
        zmax=budget * 1.8,
        showscale=False,
    )
)
fig_heatmap.update_layout(
    xaxis=dict(tickvals=list(range(len(x_labels))), ticktext=x_labels, side="top"),
    yaxis=dict(tickvals=list(range(len(y_labels))), ticktext=y_labels, autorange="reversed"),
    annotations=annotations,
    height=280,
    margin=dict(l=80, r=20, t=40, b=20),
)
st.plotly_chart(fig_heatmap, width="stretch")

# ── Анализ влияния cap'а ─────────────────────────────────────────────────────

st.divider()
st.subheader("Влияние cap'а на охват")
st.caption("Сколько пользователей получают reward не на весь баланс, а только на часть (обрезанную cap'ом)?")

cap_impact_rows = []
for cap in caps:
    capped_users = edited_df.loc[edited_df["Ср. баланс ($)"] > cap, "Пользователи"].sum()
    uncapped_users = total_users - capped_users
    cap_impact_rows.append({
        "Cap": f"${cap:,.0f}",
        "Обрезаны": int(capped_users),
        "Полный reward": int(uncapped_users),
        "% обрезанных": capped_users / total_users * 100,
        "Упущенный reward ($)": sum(
            row["Пользователи"] * calc_reward(max(0, row["Ср. баланс ($)"] - cap), reward_rate, max(periods), interest_mode)
            for _, row in edited_df.iterrows()
            if row["Ср. баланс ($)"] > cap
        ),
    })

cap_impact_df = pd.DataFrame(cap_impact_rows)

col_left, col_right = st.columns(2)

with col_left:
    fig_cap = go.Figure()
    fig_cap.add_trace(go.Bar(
        x=cap_impact_df["Cap"],
        y=cap_impact_df["Полный reward"],
        name="Полный reward",
        marker_color="#4ade80",
    ))
    fig_cap.add_trace(go.Bar(
        x=cap_impact_df["Cap"],
        y=cap_impact_df["Обрезаны"],
        name="Обрезаны cap'ом",
        marker_color="#f87171",
    ))
    fig_cap.update_layout(
        barmode="stack",
        title="Пользователи: полный reward vs обрезанный",
        yaxis_title="Пользователи",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_cap, width="stretch")

with col_right:
    st.dataframe(
        cap_impact_df.style.format({
            "Обрезаны": "{:,.0f}",
            "Полный reward": "{:,.0f}",
            "% обрезанных": "{:.1f}%",
            "Упущенный reward ($)": "${:,.0f}",
        }),
        width="stretch",
        hide_index=True,
    )

# ── Детализация по бакетам ────────────────────────────────────────────────────

st.divider()
st.subheader("Детализация по бакетам")

col_period, col_cap = st.columns(2)
selected_period = col_period.selectbox("Срок", periods, index=1, format_func=lambda x: f"{x} дней")
selected_cap = col_cap.selectbox("Cap", caps, index=1, format_func=lambda x: f"${x:,.0f}")

detail_df = calculate_campaign_cost(edited_df, reward_rate, selected_period, selected_cap, interest_mode)
detail_display = detail_df[["Бакет", "Пользователи", "Ср. баланс ($)", "Учитываемый баланс", "Reward на юзера", "Стоимость бакета"]].copy()

total_cost = detail_display["Стоимость бакета"].sum()
remaining = budget - total_cost

mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("Стоимость кампании", f"${total_cost:,.0f}")
mcol2.metric("Остаток бюджета", f"${remaining:,.0f}", delta=f"{remaining/budget*100:.0f}%")
mcol3.metric("Стоимость на юзера", f"${total_cost/total_users:.2f}")

st.dataframe(
    detail_display.style.format({
        "Пользователи": "{:,.0f}",
        "Ср. баланс ($)": "${:,.0f}",
        "Учитываемый баланс": "${:,.0f}",
        "Reward на юзера": "${:.2f}",
        "Стоимость бакета": "${:,.0f}",
    }),
    width="stretch",
    hide_index=True,
)

# ── Допущения и открытые вопросы ──────────────────────────────────────────────

st.divider()
st.subheader("Допущения и открытые вопросы")

mode_desc = (
    "Simple interest: `учитываемый_баланс × годовая_ставка × (дни / 365)`"
    if interest_mode == "Simple"
    else "Compound interest (monthly): `учитываемый_баланс × ((1 + ставка/12)^месяцев − 1)`"
)

st.markdown(f"""
**Допущения модели:**
- Проценты: {mode_desc}
- Статичное распределение пользователей (без притока/оттока во время кампании)
- Единоразовая выплата в конце периода
- Штраф за досрочный вывод не моделируется

**Открытые вопросы:**
- Выплата разовая или помесячная? (переключатель в sidebar для сравнения)
- Ожидаемый приток новых пользователей во время кампании?
- Риск оттока китов при слишком низком cap'е?
- Какой revenue uplift ожидается от увеличения балансов? (ROI кампании)
- Возможно ли увеличение бюджета, если длинный срок покажет лучший retention?

**Что замерять после запуска:**
- Retention rate на 30-й, 60-й и 90-й день
- Рост балансов во время кампании (довносили ли юзеры?)
- Отток обрезанных cap'ом юзеров (уходят ли киты?)
- Revenue uplift vs стоимость кампании → реальный ROI
- Использовать эти метрики для калибровки следующей итерации
""")
