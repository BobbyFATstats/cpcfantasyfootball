import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="CPC Fantasy Football Hall of Fame", page_icon="🏆", layout="wide")
st.title("🏆 CPC Fantasy Football Hall of Fame")
st.caption("All-time stats, legends, and league degeneracy")

# ---- Load ----
FILE_PATH = "CPC Fantasy Football Leagues - CPC Home League (2).csv"
df_raw = pd.read_csv(FILE_PATH)

# ---- Normalize column names for matching ----
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

# ---- Define candidate names (edit if needed) ----
owner_col = pick_col(["Owner(s)", "Owners", "Owner", "Username", "Team Owner"])
season_col = pick_col(["Season", "FF Year"])
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

# ---- Build working dataframe with standard column names ----
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

# ---- Numeric cleanup ----
for col in ["Wins", "Losses", "PF", "PA", "Transactions"]:
    work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)

work["Is Champ"] = work["Fantasy Champ"] == "Y"

# ---- Season_Year (ZERO-RISK: derived field used only for charts/superlatives) ----
work["Season_Year"] = (
    work["Season"]
    .astype(str)
    .str.extract(r"(\d{4})")[0]
)
work["Season_Year"] = pd.to_numeric(work["Season_Year"], errors="coerce")

# ---- Aggregate helpers ----
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
        .str.extract(r"(\d{4})")[0]   # safely pull a 4-digit year from strings
        .astype(int)
    )
    early = (seasons < 2014).sum()      # 2008–2013
    modern = (seasons >= 2014).sum()    # 2014+
    return int(early * 25 + modern * 50)

# ---- Aggregate (All-Time by Owner) ----
agg = (
    work.groupby("Owner(s)", dropna=False)
    .apply(lambda g: pd.Series({
        "Championships": int(g["Is Champ"].sum()),
        "Championship Points": champ_points(g),
        "Championship Years": champ_years(g),
        "Total Wins": int(g["Wins"].sum()),
        "Total Losses": int(g["Losses"].sum()),
        "Total PF": float(g["PF"].sum()),
        "Total PA": float(g["PA"].sum()),
        "Total Transactions": int(g["Transactions"].sum()),
    }))
    .reset_index()
)

agg["Games"] = agg["Total Wins"] + agg["Total Losses"]
agg["Win %"] = (agg["Total Wins"] / agg["Games"]).fillna(0).round(3)
agg["Point Diff"] = (agg["Total PF"] - agg["Total PA"]).round(1)

# ---- New sortable metrics ----
# Dynasty Index (fun + slightly skill-based)
# (Rings still matter, but we bake in win% and PF)
agg["Dynasty Index"] = (
    agg["Championship Points"]
    + (agg["Win %"] * 100)
    + (agg["Total PF"] / 500)
).round(2)

# Transaction Efficiency (skill-based-ish): PF per transaction
# Avoid divide-by-zero while still not exploding to infinity
agg["PF per Transaction"] = (agg["Total PF"] / agg["Total Transactions"].clip(lower=1)).round(2)

# GOAT Score 😈 (era-adjusted rings)
agg["GOAT Score"] = (
    agg["Championship Points"]
    + agg["Total Wins"] * 2
    + (agg["Total PF"] / 100)
).round(1)

with st.expander("🐐 How is the GOAT Score calculated?"):
    st.markdown("""
**The GOAT Score is a fun, all-time legacy metric designed to reward winning *and* dominance.**

**Formula:**

🏆 **Championship Points** (era-adjusted)  
➕ **Total Wins** × 2  
➕ **Total Points For** ÷ 100  

**Championship Points:**
- 🏆 Titles from **2008–2013** = **25** points each  
- 👑 Titles from **2014+** = **50** points each  

This isn’t science — it’s **fantasy football propaganda** 😈
""")

agg = agg.sort_values(by=["Championships", "Win %", "Total Wins"], ascending=[False, False, False])

# ---- Display ----
st.subheader("🏆 All-Time Leaderboard")

st.dataframe(
    agg[[
        "Owner(s)",
        "Championships",
        "Championship Points",
        "Championship Years",
        "Total Wins",
        "Total Losses",
        "Win %",
        "Total PF",
        "Total PA",
        "Point Diff",
        "Total Transactions",
        "PF per Transaction",
        "Dynasty Index",
        "GOAT Score"
    ]],
    use_container_width=True
)

# ---- League Superlatives ----
st.subheader("🔥 League Superlatives")

# Existing 3
col1, col2, col3 = st.columns(3)

with col1:
    goat = agg.iloc[0]
    st.metric("👑 GOAT", goat["Owner(s)"], f"{int(goat['Championships'])} Rings")

with col2:
    most_tx = agg.sort_values("Total Transactions", ascending=False).iloc[0]
    st.metric("🤡 Transaction Terrorist", most_tx["Owner(s)"], int(most_tx["Total Transactions"]))

with col3:
    no_ring = agg[agg["Championships"] == 0].sort_values("Total Wins", ascending=False)
    if len(no_ring) > 0:
        heartbreak = no_ring.iloc[0]
        st.metric("💀 Most Wins, No Ring", heartbreak["Owner(s)"], int(heartbreak["Total Wins"]))
    else:
        st.metric("💀 Most Wins, No Ring", "Everyone has a ring?!", "😳")

# New 3 (second row)
col4, col5, col6 = st.columns(3)

# 📉 Luckiest Champion = champ season with lowest PF
champ_seasons = work[work["Is Champ"]].copy()
with col4:
    if not champ_seasons.empty:
        luckiest = champ_seasons.sort_values("PF", ascending=True).iloc[0]
        label = f"{luckiest['Owner(s)']} ({str(luckiest['Season'])})"
        st.metric("📉 Luckiest Champion", label, f"{float(luckiest['PF']):.1f} PF")
    else:
        st.metric("📉 Luckiest Champion", "No champ data", "—")

# 🧱 Mr. Consistency = lowest std dev of season win%
with col5:
    season_team = work.dropna(subset=["Season_Year"]).copy()
    if not season_team.empty:
        season_team["Season Win %"] = (
            season_team["Wins"] / (season_team["Wins"] + season_team["Losses"]).replace(0, pd.NA)
        ).fillna(0)

        stds = (
            season_team.groupby("Owner(s)")["Season Win %"]
            .agg(["count", "std"])
            .reset_index()
        )
        stds = stds[stds["count"] >= 2].copy()  # need at least 2 seasons to be "consistent"
        if not stds.empty:
            mr_consistency = stds.sort_values("std", ascending=True).iloc[0]
            st.metric("🧱 Mr. Consistency", mr_consistency["Owner(s)"], f"σ={mr_consistency['std']:.3f}")
        else:
            st.metric("🧱 Mr. Consistency", "Need 2+ seasons", "—")
    else:
        st.metric("🧱 Mr. Consistency", "No season years", "—")

# 🔥 Best Single Season Ever = highest PF in any season
with col6:
    best_season = work.dropna(subset=["Season_Year"]).sort_values("PF", ascending=False)
    if not best_season.empty:
        b = best_season.iloc[0]
        label = f"{b['Owner(s)']} ({str(b['Season'])})"
        st.metric("🔥 Best Single Season Ever", label, f"{float(b['PF']):.1f} PF")
    else:
        st.metric("🔥 Best Single Season Ever", "No season data", "—")

# ---- Visuals ----
st.subheader("📊 Trends & Visuals")

# 📈 Win % Over Time (Line Chart)
st.markdown("### 📈 Win % Over Time")

season_df = work.dropna(subset=["Season_Year"]).copy()
season_df["Season Win %"] = (
    season_df["Wins"] / (season_df["Wins"] + season_df["Losses"]).replace(0, pd.NA)
).fillna(0)

# Choose owners (default: top 5 by games)
default_owners = agg.sort_values("Games", ascending=False)["Owner(s)"].head(5).tolist()
owners = st.multiselect("Pick Owners to Plot", options=sorted(agg["Owner(s)"].tolist()), default=default_owners)

plot_df = season_df[season_df["Owner(s)"].isin(owners)].copy()
if plot_df.empty:
    st.info("Pick at least one owner to view the Win % trend.")
else:
    pivot = (
        plot_df.pivot_table(index="Season_Year", columns="Owner(s)", values="Season Win %", aggfunc="mean")
        .sort_index()
    )
    st.line_chart(pivot)

# ⚖️ PF vs PA Scatter Plot (Luck vs Skill) — with quadrant lines + labels 😈
st.markdown("### ⚖️ PF vs PA (All-Time) — Luck vs Skill")

pf_avg = agg["Total PF"].mean()
pa_avg = agg["Total PA"].mean()

fig, ax = plt.subplots()
ax.scatter(agg["Total PF"], agg["Total PA"])

# Average lines (quadrants)
ax.axvline(pf_avg, linestyle="--")
ax.axhline(pa_avg, linestyle="--")

ax.set_xlabel("Total PF (Points For)")
ax.set_ylabel("Total PA (Points Against)")
ax.set_title("PF vs PA (All-Time) — Quadrants of Truth")

# Quadrant labels (placed inside plot bounds)
x_min, x_max = ax.get_xlim()
y_min, y_max = ax.get_ylim()

# Add some padding for label placement
x_pad = (x_max - x_min) * 0.02
y_pad = (y_max - y_min) * 0.04

# Top-right: High PF, High PA
ax.text(pf_avg + x_pad, pa_avg + y_pad, "Good & Unlucky\n(High PF, High PA)", fontsize=10, va="bottom")
# Bottom-right: High PF, Low PA
ax.text(pf_avg + x_pad, pa_avg - y_pad, "Dominant 😈\n(High PF, Low PA)", fontsize=10, va="top")
# Bottom-left: Low PF, Low PA
ax.text(pf_avg - x_pad, pa_avg - y_pad, "Fraud Alert 🤡\n(Low PF, Low PA)", fontsize=10, va="top", ha="right")
# Top-left: Low PF, High PA
ax.text(pf_avg - x_pad, pa_avg + y_pad, "Bad & Doomed 💀\n(Low PF, High PA)", fontsize=10, va="bottom", ha="right")

# Optional: label the points
label_points = st.checkbox("Label points with Owner(s) (can get messy)", value=False)
if label_points:
    for _, row in agg.iterrows():
        ax.annotate(str(row["Owner(s)"]), (row["Total PF"], row["Total PA"]), fontsize=8)

st.pyplot(fig)

st.caption("Built for trash talk. Data does not lie.")
