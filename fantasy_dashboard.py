import streamlit as st
import pandas as pd
import plotly.express as px

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(
    page_title="CPC Fantasy Football Hall of Fame",
    page_icon="🏆",
    layout="wide"
)

st.title("🏆 CPC Fantasy Football Hall of Fame")
st.caption("All-time stats, legends, and league degeneracy")

# -----------------------------
# Load Data
# -----------------------------
FILE_PATH = "CPC Fantasy Football Leagues - CPC Home League (2).csv"
df_raw = pd.read_csv(FILE_PATH)

# -----------------------------
# Normalize column names for matching
# -----------------------------
df = df_raw.copy()
original_cols = list(df.columns)

def norm(s: str) -> str:
    return str(s).strip().lower().replace("\ufeff", "")

normalized_map = {norm(c): c for c in df.columns}  # normalized -> original

def pick_col(candidates):
    """Return the first matching original column name from candidates (normalized comparisons)."""
    for cand in candidates:
        cand_n = norm(cand)
        if cand_n in normalized_map:
            return normalized_map[cand_n]
    return None

# ---- Define candidate names ----
owner_col = pick_col(["Owner(s)", "Owners", "Owner", "Username", "Team Owner"])
season_col = pick_col(["Season", "FF Year", "Year"])
champ_col = pick_col(["Fantasy Champ", "Champion", "Champ", "Is Champ"])

wins_col = pick_col(["Wins", "W", "Win", "Total Wins"])
losses_col = pick_col(["Losses", "L", "Loss", "Total Losses"])
pf_col = pick_col(["PF", "Points For", "PointsFor", "Pts For", "Total PF"])
pa_col = pick_col(["PA", "Points Against", "PointsAgainst", "Pts Against", "Total PA"])
tx_col = pick_col(["Transactions", "Total Transactions", "Moves", "Total Moves"])

required = {
    "Owner(s)": owner_col,
    "Season": season_col,
    "Fantasy Champ": champ_col,
    "Wins": wins_col,
    "Losses": losses_col,
    "PF": pf_col,
    "PA": pa_col,
    "Transactions": tx_col
}

missing = [k for k, v in required.items() if v is None]
if missing:
    st.error("I couldn't find these required columns in your CSV: " + ", ".join(missing))
    st.write("Columns I *did* find:", original_cols)
    st.info("Fix: rename the columns in the CSV OR tell me what your column headers are and I’ll map them.")
    st.stop()

# -----------------------------
# Build working dataframe
# -----------------------------
work = pd.DataFrame({
    "Owner(s)": df[owner_col].astype(str).str.strip(),
    "Season": df[season_col],
    "Fantasy Champ": df[champ_col].fillna("").astype(str).str.strip().str.upper(),
    "Wins": df[wins_col],
    "Losses": df[losses_col],
    "PF": df[pf_col],
    "PA": df[pa_col],
    "Transactions": df[tx_col],
})

# Numeric cleanup
for col in ["Wins", "Losses", "PF", "PA", "Transactions"]:
    work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

work["Is Champ"] = work["Fantasy Champ"] == "Y"

# Derived year (ZERO-RISK: does not overwrite Season)
work["Season_Year"] = (
    work["Season"]
    .astype(str)
    .str.extract(r"(\d{4})")[0]
)
work["Season_Year"] = pd.to_numeric(work["Season_Year"], errors="coerce")

# -----------------------------
# IMPORTANT RULE NOTE
# -----------------------------
st.info(
    "📌 **Data rule:** Seasons **2008–2013** are used **ONLY** for championship history (PF/W/L/Transactions are missing). "
    "All stats, win%, superlatives, and visuals are calculated using **2014+** seasons only."
)

# Modern-era filter (2014+ only for stats)
work_modern = work[work["Season_Year"].fillna(0) >= 2014].copy()

# -----------------------------
# Championship helpers (ALL seasons)
# -----------------------------
def champ_years(subdf):
    years = (
        subdf.loc[subdf["Is Champ"], "Season"]
        .dropna()
        .astype(str)
        .tolist()
    )
    return ", ".join(sorted(years)) if years else ""

def champ_points(subdf):
    seasons = (
        subdf.loc[subdf["Is Champ"], "Season"]
        .dropna()
        .astype(str)
        .str.extract(r"(\d{4})")[0]
        .dropna()
        .astype(int)
    )
    early = (seasons < 2014).sum()      # 2008–2013
    modern = (seasons >= 2014).sum()    # 2014+
    return int(early * 25 + modern * 50)

# -----------------------------
# Aggregate
# Champs = ALL seasons
# Stats = MODERN seasons only
# -----------------------------
champs_agg = (
    work.groupby("Owner(s)", dropna=False)
    .apply(lambda g: pd.Series({
        "Championships": int(g["Is Champ"].sum()),
        "Championship Points": champ_points(g),
        "Championship Years": champ_years(g),
    }))
    .reset_index()
)

stats_agg = (
    work_modern.groupby("Owner(s)", dropna=False)
    .agg(
        Total_Wins=("Wins", "sum"),
        Total_Losses=("Losses", "sum"),
        Total_PF=("PF", "sum"),
        Total_PA=("PA", "sum"),
        Total_Transactions=("Transactions", "sum"),
    )
    .reset_index()
)

agg = champs_agg.merge(stats_agg, on="Owner(s)", how="left")

for c in ["Total_Wins", "Total_Losses", "Total_PF", "Total_PA", "Total_Transactions"]:
    agg[c] = agg[c].fillna(0)

agg["Games"] = agg["Total_Wins"] + agg["Total_Losses"]
agg["Win %"] = (agg["Total_Wins"] / agg["Games"]).fillna(0).round(3)
agg["Point Diff"] = (agg["Total_PF"] - agg["Total_PA"]).round(1)

# Sortable table metrics
agg["PF per Transaction"] = (agg["Total_PF"] / agg["Total_Transactions"].clip(lower=1)).round(2)

agg["Dynasty Index"] = (
    agg["Championship Points"]
    + (agg["Win %"] * 100)
    + (agg["Total_PF"] / 500)
).round(2)

agg["GOAT Score"] = (
    agg["Championship Points"]
    + agg["Total_Wins"] * 2
    + (agg["Total_PF"] / 100)
).round(1)

with st.expander("🐐 How is the GOAT Score calculated?"):
    st.markdown("""
**GOAT Score = Championship Points + (Modern Wins × 2) + (Modern PF ÷ 100)**

**Championship Points (all-time):**
- 🏆 Titles from **2008–2013** = **25** points each  
- 👑 Titles from **2014+** = **50** points each  

**Modern Wins / PF:** calculated using **2014+** seasons only.

This isn’t science — it’s **fantasy football propaganda** 😈
""")

agg = agg.sort_values(by=["Championships", "Win %", "Total_Wins"], ascending=[False, False, False])

# -----------------------------
# Leaderboard Table
# -----------------------------
st.subheader("🏆 All-Time Leaderboard (Champs all-time, stats from 2014+)")

st.dataframe(
    agg[[
        "Owner(s)",
        "Championships",
        "Championship Points",
        "Championship Years",
        "Total_Wins",
        "Total_Losses",
        "Win %",
        "Total_PF",
        "Total_PA",
        "Point Diff",
        "Total_Transactions",
        "PF per Transaction",
        "Dynasty Index",
        "GOAT Score"
    ]],
    use_container_width=True
)

# -----------------------------
# League Superlatives (MODERN-only logic for stats)
# -----------------------------
st.subheader("🔥 League Superlatives (2014+ stats only)")

col1, col2, col3 = st.columns(3)

with col1:
    goat = agg.sort_values(["GOAT Score", "Championships"], ascending=[False, False]).iloc[0]
    st.metric("👑 GOAT", goat["Owner(s)"], f"{int(goat['Championships'])} Rings")

with col2:
    most_tx = agg.sort_values("Total_Transactions", ascending=False).iloc[0]
    st.metric("🤡 Transaction Terrorist", most_tx["Owner(s)"], int(most_tx["Total_Transactions"]))

with col3:
    no_ring = agg[agg["Championships"] == 0].sort_values("Total_Wins", ascending=False)
    if len(no_ring) > 0:
        heartbreak = no_ring.iloc[0]
        st.metric("💀 Most Wins, No Ring", heartbreak["Owner(s)"], int(heartbreak["Total_Wins"]))
    else:
        st.metric("💀 Most Wins, No Ring", "Everyone has a ring?!", "😳")

col4, col5, col6 = st.columns(3)

with col4:
    champ_seasons = work_modern[(work_modern["Is Champ"]) & (work_modern["PF"] > 0)].copy()
    if not champ_seasons.empty:
        luckiest = champ_seasons.sort_values("PF", ascending=True).iloc[0]
        label = f"{luckiest['Owner(s)']} ({str(luckiest['Season'])})"
        st.metric("📉 Luckiest Champion", label, f"{float(luckiest['PF']):.1f} PF")
    else:
        st.metric("📉 Luckiest Champion", "No modern champ PF data", "—")

with col5:
    season_team = work_modern.dropna(subset=["Season_Year"]).copy()
    season_team["Season Win %"] = (
        season_team["Wins"] / (season_team["Wins"] + season_team["Losses"]).replace(0, pd.NA)
    ).fillna(0)

    stds = (
        season_team.groupby("Owner(s)")["Season Win %"]
        .agg(["count", "std"])
        .reset_index()
    )
    stds = stds[stds["count"] >= 2].copy()
    if not stds.empty:
        mr_consistency = stds.sort_values("std", ascending=True).iloc[0]
        st.metric("🧱 Mr. Consistency", mr_consistency["Owner(s)"], f"σ={mr_consistency['std']:.3f}")
    else:
        st.metric("🧱 Mr. Consistency", "Need 2+ modern seasons", "—")

with col6:
    best_season = work_modern.sort_values("PF", ascending=False)
    if not best_season.empty:
        b = best_season.iloc[0]
        label = f"{b['Owner(s)']} ({str(b['Season'])})"
        st.metric("🔥 Best Single Season Ever", label, f"{float(b['PF']):.1f} PF")
    else:
        st.metric("🔥 Best Single Season Ever", "No modern PF data", "—")

# -----------------------------
# Visuals (NO Win % line chart)
# -----------------------------
st.subheader("📊 Trends & Visuals (2014+ only)")

st.markdown("### ⚖️ PF vs PA (All-Time since 2014) — Quadrants of Truth 😈")

pf_avg = agg["Total_PF"].mean()
pa_avg = agg["Total_PA"].mean()

quad_df = agg[["Owner(s)", "Total_PF", "Total_PA", "Championships", "GOAT Score"]].copy()

# Plotly interactive scatter: different color per owner, hover tooltip
fig = px.scatter(
    quad_df,
    x="Total_PF",
    y="Total_PA",
    color="Owner(s)",
    hover_name="Owner(s)",
    hover_data={
        "Total_PF": ":.1f",
        "Total_PA": ":.1f",
        "Championships": True,
        "GOAT Score": True,
        "Owner(s)": False
    },
    title="PF vs PA (2014+) — hover for receipts"
)

# Make chart bigger + readable
fig.update_layout(
    height=650,
    legend_title_text="Owner(s)"
)

# Quadrant lines (make them WHITE so they pop on dark theme)
fig.add_vline(
    x=pf_avg,
    line_dash="dash",
    line_color="rgba(255,255,255,0.8)",
    line_width=2
)

fig.add_hline(
    y=pa_avg,
    line_dash="dash",
    line_color="rgba(255,255,255,0.8)"
    line_width=2
)

st.plotly_chart(fig, use_container_width=True)

st.caption(f"League averages since 2014 — PF: {pf_avg:.1f} | PA: {pa_avg:.1f}")

dominant = quad_df[(quad_df["Total_PF"] >= pf_avg) & (quad_df["Total_PA"] < pa_avg)]
good_unlucky = quad_df[(quad_df["Total_PF"] >= pf_avg) & (quad_df["Total_PA"] >= pa_avg)]
fraud_alert = quad_df[(quad_df["Total_PF"] < pf_avg) & (quad_df["Total_PA"] < pa_avg)]
bad_doomed = quad_df[(quad_df["Total_PF"] < pf_avg) & (quad_df["Total_PA"] >= pa_avg)]

cA, cB, cC, cD = st.columns(4)
with cA:
    st.markdown("**Dominant 😈**")
    st.write(", ".join(dominant["Owner(s)"].head(8).tolist()) or "—")
with cB:
    st.markdown("**Good & Unlucky**")
    st.write(", ".join(good_unlucky["Owner(s)"].head(8).tolist()) or "—")
with cC:
    st.markdown("**Fraud Alert 🤡**")
    st.write(", ".join(fraud_alert["Owner(s)"].head(8).tolist()) or "—")
with cD:
    st.markdown("**Bad & Doomed 💀**")
    st.write(", ".join(bad_doomed["Owner(s)"].head(8).tolist()) or "—")

st.caption("Built for trash talk. Data does not lie.")
