import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Reward Campaign Calculator",
    page_icon="💰",
    layout="wide",
)

# ── Sidebar: Параметры кампании ───────────────────────────────────────────────

st.sidebar.header("Campaign Parameters")

budget = st.sidebar.number_input("Budget (USD)", value=100_000, step=10_000, format="%d")
reward_rate = st.sidebar.number_input("Annual Rate (%)", value=15.0, step=1.0, format="%.1f") / 100

interest_mode = st.sidebar.radio(
    "Interest Type",
    ["Simple", "Compound (monthly)"],
    index=0,
    help="Simple: reward = balance × rate × days/365. Compound: reward = balance × ((1 + rate/12)^months − 1)",
)

st.sidebar.subheader("Periods (days)")
col1, col2, col3 = st.sidebar.columns(3)
period_1 = col1.number_input("P1", value=30, step=10, key="p1")
period_2 = col2.number_input("P2", value=60, step=10, key="p2")
period_3 = col3.number_input("P3", value=90, step=10, key="p3")
periods = [period_1, period_2, period_3]

st.sidebar.subheader("Balance Cap (USD)")
col1, col2, col3 = st.sidebar.columns(3)
cap_1 = col1.number_input("C1", value=500, step=100, key="c1")
cap_2 = col2.number_input("C2", value=1000, step=100, key="c2")
cap_3 = col3.number_input("C3", value=2000, step=100, key="c3")
caps = [cap_1, cap_2, cap_3]

# ── Заголовок ─────────────────────────────────────────────────────────────────

st.title("Reward Campaign Calculator")
st.caption("Scenario analysis for a marketing campaign rewarding users for holding balance")

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
    df["Eligible Balance"] = df["Avg Balance ($)"].clip(upper=cap)
    df["Reward / User"] = df["Eligible Balance"].apply(lambda b: calc_reward(b, rate, days, mode))
    df["Bucket Cost"] = df["Reward / User"] * df["Users"]
    return df


def build_cost_matrix(users_df: pd.DataFrame, rate: float, periods: list, caps: list, mode: str) -> pd.DataFrame:
    rows = []
    for days in periods:
        row = {"Period (days)": days}
        for cap in caps:
            result = calculate_campaign_cost(users_df, rate, days, cap, mode)
            row[f"Cap ${cap:,.0f}"] = result["Bucket Cost"].sum()
        rows.append(row)
    return pd.DataFrame(rows)


# ── Рекомендации — 3 сценария ────────────────────────────────────────────────

def generate_scenarios(cost_matrix: pd.DataFrame, caps: list, periods: list, budget: float, users_df: pd.DataFrame, rate: float, mode: str):
    """Find conservative, balanced, and aggressive scenarios from the cost matrix."""
    cap_cols = [c for c in cost_matrix.columns if c.startswith("Cap")]

    # Collect all (period, cap, cost) combos
    combos = []
    for _, row in cost_matrix.iterrows():
        days = int(row["Period (days)"])
        for cap, col in zip(caps, cap_cols):
            cost = row[col]
            # Calculate capped users %
            capped_users = users_df.loc[users_df["Avg Balance ($)"] > cap, "Users"].sum()
            total = users_df["Users"].sum()
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
        conservative["label"] = "Conservative"
        conservative["desc"] = "Lowest cost, fits budget comfortably"
        scenarios.append(conservative)

    # Balanced: best coverage within budget (max days × cap while in budget)
    if in_budget:
        balanced = max(in_budget, key=lambda c: (c["days"] * c["cap"], -c["capped_pct"]))
        # Avoid duplicate with conservative
        if not scenarios or (balanced["days"] != scenarios[0]["days"] or balanced["cap"] != scenarios[0]["cap"]):
            balanced["label"] = "Balanced ⭐"
            balanced["desc"] = "Best coverage within budget"
            scenarios.append(balanced)
        else:
            # Pick second best
            candidates = [c for c in in_budget if not (c["days"] == balanced["days"] and c["cap"] == balanced["cap"])]
            if candidates:
                alt = max(candidates, key=lambda c: (c["days"] * c["cap"], -c["capped_pct"]))
                alt["label"] = "Balanced ⭐"
                alt["desc"] = "Best coverage within budget"
                scenarios.append(alt)

    # Aggressive: cheapest over budget, or most expensive in budget
    if over_budget:
        aggressive = min(over_budget, key=lambda c: c["cost"])
        aggressive["label"] = "Aggressive"
        aggressive["desc"] = "Maximum reach, exceeds budget"
        scenarios.append(aggressive)
    elif in_budget:
        aggressive = max(in_budget, key=lambda c: c["cost"])
        if not any(s["days"] == aggressive["days"] and s["cap"] == aggressive["cap"] for s in scenarios):
            aggressive["label"] = "Aggressive"
            aggressive["desc"] = "Maximum reach within budget"
            scenarios.append(aggressive)

    return scenarios


st.subheader("Recommended Scenarios")

# We need user data first — define it before recommendations
default_data = pd.DataFrame({
    "Bucket": ["0–200", "200–500", "500–1,000", "1,000–2,000", "2,000+"],
    "Users": [2500, 4000, 1500, 700, 300],
    "Avg Balance ($)": [120, 320, 700, 1400, 3500],
})

st.caption("User distribution (editable below)")

edited_df = st.data_editor(
    default_data,
    width="stretch",
    num_rows="fixed",
    hide_index=True,
    column_config={
        "Bucket": st.column_config.TextColumn(disabled=True),
        "Users": st.column_config.NumberColumn(min_value=0, step=100),
        "Avg Balance ($)": st.column_config.NumberColumn(min_value=0, step=50),
    },
    key="user_dist",
)

total_users = edited_df["Users"].sum()
total_balance = (edited_df["Users"] * edited_df["Avg Balance ($)"]).sum()

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
                value=f"{s['days']}d × ${s['cap']:,.0f} cap",
                delta=f"${s['cost']:,.0f} ({s['pct_budget']:.0f}% of budget)",
                delta_color=delta_color,
            )
            st.caption(s["desc"])
            st.markdown(f"""
- **Cost/user:** ${s['cost_per_user']:.2f}
- **Users capped:** {s['capped_pct']:.0f}%
""")

    st.info("**Next steps after launch:** measure retention at day 30 and day 60. Use real data to decide whether to run a longer campaign next iteration — data-driven, not guessing.")
else:
    st.warning("No scenarios available with current parameters.")

# ── Сводка пользователей ─────────────────────────────────────────────────────

st.divider()
st.subheader("User Distribution")

c1, c2 = st.columns(2)
c1.metric("Total Users", f"{total_users:,.0f}")
c2.metric("Total Balance", f"${total_balance:,.0f}")

# ── Матрица стоимости ─────────────────────────────────────────────────────────

st.divider()
st.subheader("Cost Matrix")

display_matrix = cost_matrix.copy()
for col in cap_cols:
    display_matrix[col] = cost_matrix[col].apply(
        lambda v: f"${v:,.0f} ✓" if v <= budget else f"${v:,.0f} ✗"
    )
display_matrix["Period (days)"] = display_matrix["Period (days)"].astype(int)

col_config = {col: st.column_config.TextColumn(label=col) for col in cap_cols}
col_config["Period (days)"] = st.column_config.NumberColumn(format="%d")

st.dataframe(display_matrix, width="stretch", hide_index=True, column_config=col_config)
st.caption("✓ Within budget · ✗ Over budget")

# ── Тепловая карта ────────────────────────────────────────────────────────────

st.subheader("Cost Heatmap")

z_values = cost_matrix[cap_cols].values
x_labels = [f"Cap ${c:,.0f}" for c in caps]
y_labels = [f"{p} days" for p in periods]

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
st.subheader("Cap Impact Analysis")
st.caption("How many users receive reward on a capped (reduced) balance?")

cap_impact_rows = []
for cap in caps:
    capped_users = edited_df.loc[edited_df["Avg Balance ($)"] > cap, "Users"].sum()
    uncapped_users = total_users - capped_users
    cap_impact_rows.append({
        "Cap": f"${cap:,.0f}",
        "Capped": int(capped_users),
        "Full Reward": int(uncapped_users),
        "% Capped": capped_users / total_users * 100,
        "Missed Reward ($)": sum(
            row["Users"] * calc_reward(max(0, row["Avg Balance ($)"] - cap), reward_rate, max(periods), interest_mode)
            for _, row in edited_df.iterrows()
            if row["Avg Balance ($)"] > cap
        ),
    })

cap_impact_df = pd.DataFrame(cap_impact_rows)

col_left, col_right = st.columns(2)

with col_left:
    fig_cap = go.Figure()
    fig_cap.add_trace(go.Bar(
        x=cap_impact_df["Cap"],
        y=cap_impact_df["Full Reward"],
        name="Full reward",
        marker_color="#4ade80",
    ))
    fig_cap.add_trace(go.Bar(
        x=cap_impact_df["Cap"],
        y=cap_impact_df["Capped"],
        name="Capped by limit",
        marker_color="#f87171",
    ))
    fig_cap.update_layout(
        barmode="stack",
        title="Users: full reward vs capped",
        yaxis_title="Users",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig_cap, width="stretch")

with col_right:
    st.dataframe(
        cap_impact_df.style.format({
            "Capped": "{:,.0f}",
            "Full Reward": "{:,.0f}",
            "% Capped": "{:.1f}%",
            "Missed Reward ($)": "${:,.0f}",
        }),
        width="stretch",
        hide_index=True,
    )

# ── Детализация по бакетам ────────────────────────────────────────────────────

st.divider()
st.subheader("Bucket Breakdown")

col_period, col_cap = st.columns(2)
selected_period = col_period.selectbox("Period", periods, index=1, format_func=lambda x: f"{x} days")
selected_cap = col_cap.selectbox("Cap", caps, index=1, format_func=lambda x: f"${x:,.0f}")

detail_df = calculate_campaign_cost(edited_df, reward_rate, selected_period, selected_cap, interest_mode)
detail_display = detail_df[["Bucket", "Users", "Avg Balance ($)", "Eligible Balance", "Reward / User", "Bucket Cost"]].copy()

total_cost = detail_display["Bucket Cost"].sum()
remaining = budget - total_cost

mcol1, mcol2, mcol3 = st.columns(3)
mcol1.metric("Campaign Cost", f"${total_cost:,.0f}")
mcol2.metric("Budget Remaining", f"${remaining:,.0f}", delta=f"{remaining/budget*100:.0f}%")
mcol3.metric("Cost per User", f"${total_cost/total_users:.2f}")

st.dataframe(
    detail_display.style.format({
        "Users": "{:,.0f}",
        "Avg Balance ($)": "${:,.0f}",
        "Eligible Balance": "${:,.0f}",
        "Reward / User": "${:.2f}",
        "Bucket Cost": "${:,.0f}",
    }),
    width="stretch",
    hide_index=True,
)

# ── Допущения и открытые вопросы ──────────────────────────────────────────────

st.divider()
st.subheader("Assumptions & Open Questions")

mode_desc = (
    "Simple interest: `eligible_balance × annual_rate × (days / 365)`"
    if interest_mode == "Simple"
    else "Compound interest (monthly): `eligible_balance × ((1 + rate/12)^months − 1)`"
)

st.markdown(f"""
**Model Assumptions:**
- Interest: {mode_desc}
- Static user distribution (no inflow/outflow during campaign)
- Single payout at end of period
- No early withdrawal penalty modeled

**Open Questions:**
- Single payout or monthly accrual? (toggle above to compare)
- Expected user inflow during campaign?
- Whale churn risk if cap is too low?
- Expected revenue uplift from increased balances? (campaign ROI)
- Is budget flexible if longer period shows better retention?

**After Launch — What to Measure:**
- Retention rate at day 30 vs day 60 vs day 90
- Balance growth during campaign (did users deposit more?)
- Churn rate of capped users (whales leaving?)
- Revenue uplift vs campaign cost → actual ROI
- Use these metrics to calibrate next campaign iteration
""")
