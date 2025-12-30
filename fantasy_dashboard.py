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

# Seasons played since 2014 (for normalization)
seasons_played = (
    work_modern.groupby("Owner(s)")["Season_Year"]
    .nunique()
    .reset_index(name="Seasons_Played")
)

agg = agg.merge(seasons_played, on="Owner(s)", how="left")
agg["Seasons_Played"] = agg["Seasons_Played"].fillna(0)

# Per-season averages (used for fair quadrants)
agg["Avg PF / Season"] = (agg["Total_PF"] / agg["Seasons_Played"].clip(lower=1)).round(1)
agg["Avg PA / Season"] = (agg["Total_PA"] / agg["Seasons_Played"].clip(lower=1)).round(1)


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

with st.expander("🏰 How is the Dynasty Index calculated?"):
    st.markdown("""
**The Dynasty Index is a “who built a real empire?” score.**  
It rewards **rings first**, but also gives credit for **modern-era consistency and scoring dominance** (2014+).

**Formula:**

🏆 **Championship Points** (all-time)  
➕ **Modern Win %** × 100  
➕ **Modern Total PF** ÷ 500  

---

### What each part means
- 🏆 **Championship Points:**  
  - 2008–2013 titles = **25** points each  
  - 2014+ titles = **50** points each  
  (Rings are forever — even the ancient ones.)

- 📈 **Modern Win % × 100 (2014+):**  
  Rewards owners who win consistently *in the tracked era*.

- 🏈 **Modern PF ÷ 500 (2014+):**  
  Adds a scoring “dominance” boost so it’s not only about record luck.

---

### Why we like it
- It’s a **dynasty** score, not a single-season flex
- It respects the early era (titles count), but doesn’t pretend we have PF data back then
- It’s still **trash-talk friendly** 😈
""")


agg = agg.sort_values(by=["Championships", "Win %", "Total_Wins"], ascending=[False, False, False])

# -----------------------------
# Leaderboard Table
# -----------------------------
st.subheader("🏆 All-Time Leaderboard (Champs all-time, stats from 2014+)")

st.dataframe(
    agg[[
        "Owner(s)",
        "Seasons_Played",
        "Championships",
        "Dynasty Index",
        "GOAT Score",
        "Championship Years",
        "Total_Wins",
        "Total_Losses",
        "Win %",
        "Total_PF",
        "Total_PA",
        "Point Diff",
        "Total_Transactions",
        "PF per Transaction"
    ]],
    use_container_width=True
)

# -----------------------------
# Eligibility filter for "career awards" (GOAT + Mr. Consistency)
# -----------------------------
QUAL_SEASONS = 7
qualified = agg[agg["Seasons_Played"] >= QUAL_SEASONS].copy()
qualified_names = set(qualified["Owner(s)"])


# -----------------------------
# League Superlatives (MODERN-only logic for stats)
# -----------------------------
st.subheader("🔥 League Superlatives (2014+ stats only)")

col1, col2, col3 = st.columns(3)

with col1:
    if not qualified.empty:
        goat = qualified.sort_values(["GOAT Score", "Championships"], ascending=[False, False]).iloc[0]
        st.metric("👑 GOAT (7+ seasons)", goat["Owner(s)"], f"{int(goat['Championships'])} Rings")
    else:
        st.metric("👑 GOAT (7+ seasons)", "No one qualifies yet", "—")

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
    season_team = (
        work_modern[work_modern["Owner(s)"].isin(qualified_names)]
        .dropna(subset=["Season_Year"])
        .copy()
    )

    season_team["Season Win %"] = (
        season_team["Wins"] / (season_team["Wins"] + season_team["Losses"]).replace(0, pd.NA)
    ).fillna(0)

    stds = (
        season_team.groupby("Owner(s)")["Season Win %"]
        .agg(["count", "std"])
        .reset_index()
    )
    stds = stds[stds["count"] >= QUAL_SEASONS].copy()

    if not stds.empty:
        mr_consistency = stds.sort_values("std", ascending=True).iloc[0]
        st.metric(
            "🧱 Mr. Consistency (7+ seasons)",
            mr_consistency["Owner(s)"],
            f"σ={mr_consistency['std']:.3f}",
            help=(
                "Measures how steady an owner's season-to-season performance is.\n\n"
                "We compute each owner's Win% for every season since 2014, then take the "
                "standard deviation (σ) of those season Win% values.\n\n"
                "Lower σ = more consistent year-to-year.\n"
                "Only owners with 7+ seasons since 2014 are eligible."
            )
        )
    else:
        st.metric("🧱 Mr. Consistency (7+ seasons)", "No one qualifies yet", "—")


with col6:
    best_season = work_modern.sort_values("PF", ascending=False)
    if not best_season.empty:
        b = best_season.iloc[0]
        label = f"{b['Owner(s)']} ({str(b['Season'])})"
        st.metric("🔥 Best Single Season Ever", label, f"{float(b['PF']):.1f} PF")
    else:
        st.metric("🔥 Best Single Season Ever", "No modern PF data", "—")

quad_df = agg[agg["Seasons_Played"] > 0][[
    "Owner(s)",
    "Avg PF / Season",
    "Avg PA / Season",
    "Seasons_Played",
    "Championships",
    "GOAT Score"
]].copy()


# -----------------------------
# Visuals (NO Win % line chart)
# -----------------------------
st.subheader("📊 Trends & Visuals (2014+ only)")
st.markdown("### ⚖️ PF vs PA (Per-Season Averages since 2014) — Quadrants of Truth 😈")

# Use the per-season averages for the quadrant lines (FAIR across tenure)
pf_avg = quad_df["Avg PF / Season"].mean()
pa_avg = quad_df["Avg PA / Season"].mean()

# Plotly interactive scatter: different color per owner, hover tooltip
fig = px.scatter(
    quad_df,
    x="Avg PF / Season",
    y="Avg PA / Season",
    color="Owner(s)",
    size="Seasons_Played",
    hover_name="Owner(s)",
    hover_data={
        "Avg PF / Season": ":.1f",
        "Avg PA / Season": ":.1f",
        "Seasons_Played": True,
        "Championships": True,
        "GOAT Score": True,
        "Owner(s)": False
    },
    title="Avg PF vs Avg PA per Season (2014+) — hover for receipts"
)

fig.update_layout(
    height=700,
    legend_title_text="Owner(s)"
)

# Quadrant lines (visible on dark theme)
fig.add_vline(
    x=pf_avg,
    line_dash="dash",
    line_color="rgba(255,255,255,0.85)",
    line_width=2
)
fig.add_hline(
    y=pa_avg,
    line_dash="dash",
    line_color="rgba(255,255,255,0.85)",
    line_width=2
)

st.plotly_chart(fig, use_container_width=True)

st.caption(f"League averages since 2014 — Avg PF/Season: {pf_avg:.1f} | Avg PA/Season: {pa_avg:.1f}")

# Quadrant lists MUST use the same averaged columns
dominant = quad_df[(quad_df["Avg PF / Season"] >= pf_avg) & (quad_df["Avg PA / Season"] < pa_avg)]
good_unlucky = quad_df[(quad_df["Avg PF / Season"] >= pf_avg) & (quad_df["Avg PA / Season"] >= pa_avg)]
fraud_alert = quad_df[(quad_df["Avg PF / Season"] < pf_avg) & (quad_df["Avg PA / Season"] < pa_avg)]
bad_doomed = quad_df[(quad_df["Avg PF / Season"] < pf_avg) & (quad_df["Avg PA / Season"] >= pa_avg)]

cA, cB, cC, cD = st.columns(4)
with cA:
    st.markdown("**Dominant 😈**")
    st.write(", ".join(dominant["Owner(s)"].head(8).tolist()) or "—")
with cB:
    st.markdown("**Good & Unlucky**")
    st.write(", ".join(good_unlucky["Owner(s)"].head(8).tolist()) or "—")
with cC:
    st.markdown("**Sneaky Wins 🕵️‍♂️**")
    st.write(", ".join(fraud_alert["Owner(s)"].head(8).tolist()) or "—")
with cD:
    st.markdown("**Bad & Doomed 💀**")
    st.write(", ".join(bad_doomed["Owner(s)"].head(8).tolist()) or "—")


st.caption("Built for trash talk. Data does not lie.")
