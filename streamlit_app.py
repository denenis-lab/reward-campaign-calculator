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

st.sidebar.subheader("Сроки (дни)")
col1, col2, col3 = st.sidebar.columns(3)
period_1 = col1.number_input("С1", value=30, step=10, key="p1")
period_2 = col2.number_input("С2", value=60, step=10, key="p2")
period_3 = col3.number_input("С3", value=90, step=10, key="p3")
periods = [period_1, period_2, period_3]

st.sidebar.subheader("Cap на баланс (USD)")
col1, col2, col3 = st.sidebar.columns(3)
cap_1 = col1.number_input("К1", value=500, step=100, key="c1")
cap_2 = col2.number_input("К2", value=1000, step=100, key="c2")
cap_3 = col3.number_input("К3", value=2000, step=100, key="c3")
caps = [cap_1, cap_2, cap_3]

# ── Заголовок ─────────────────────────────────────────────────────────────────

st.title("Калькулятор Reward-кампании")
st.caption("Сценарный анализ маркетинговой кампании с вознаграждением за хранение средств на балансе")

# ── Распределение пользователей ───────────────────────────────────────────────

st.subheader("Распределение пользователей")
st.caption("В продакшене данные берутся SQL-запросом из таблицы балансов. Здесь можно редактировать значения для моделирования разных распределений.")

default_data = pd.DataFrame({
    "Бакет": ["0–200", "200–500", "500–1,000", "1,000–2,000", "2,000+"],
    "Пользователи": [2500, 4000, 1500, 700, 300],
    "Ср. баланс ($)": [120, 320, 700, 1400, 3500],
})

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
)

total_users = edited_df["Пользователи"].sum()
total_balance = (edited_df["Пользователи"] * edited_df["Ср. баланс ($)"]).sum()
c1, c2 = st.columns(2)
c1.metric("Всего пользователей", f"{total_users:,.0f}")
c2.metric("Общий баланс", f"${total_balance:,.0f}")

# ── Расчётные функции ────────────────────────────────────────────────────────


def calculate_campaign_cost(users_df: pd.DataFrame, rate: float, days: int, cap: float) -> pd.DataFrame:
    df = users_df.copy()
    df["Учитываемый баланс"] = df["Ср. баланс ($)"].clip(upper=cap)
    df["Reward на юзера"] = df["Учитываемый баланс"] * rate * (days / 365)
    df["Стоимость бакета"] = df["Reward на юзера"] * df["Пользователи"]
    return df


def build_cost_matrix(users_df: pd.DataFrame, rate: float, periods: list, caps: list) -> pd.DataFrame:
    rows = []
    for days in periods:
        row = {"Срок (дни)": days}
        for cap in caps:
            result = calculate_campaign_cost(users_df, rate, days, cap)
            row[f"Cap ${cap:,.0f}"] = result["Стоимость бакета"].sum()
        rows.append(row)
    return pd.DataFrame(rows)


# ── Матрица стоимости ─────────────────────────────────────────────────────────

st.divider()
st.subheader("Матрица стоимости")

cost_matrix = build_cost_matrix(edited_df, reward_rate, periods, caps)
cap_cols = [c for c in cost_matrix.columns if c.startswith("Cap")]

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
            row["Пользователи"] * max(0, row["Ср. баланс ($)"] - cap) * reward_rate * (max(periods) / 365)
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

detail_df = calculate_campaign_cost(edited_df, reward_rate, selected_period, selected_cap)
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

st.markdown("""
**Допущения модели:**
- Простые проценты: `учитываемый_баланс × годовая_ставка × (дни / 365)`
- Статичное распределение пользователей (без притока/оттока во время кампании)
- Единоразовая выплата в конце периода
- Штраф за досрочный вывод не моделируется

**Открытые вопросы:**
- Выплата разовая или помесячная? (помесячная → compound interest, чуть дороже)
- Ожидаемый приток новых пользователей во время кампании?
- Риск оттока китов при слишком низком cap'е?
- Какой revenue uplift ожидается от увеличения балансов? (ROI кампании)
- Возможно ли увеличение бюджета, если длинный срок покажет лучший retention?
""")
