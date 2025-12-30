import streamlit as st
import pandas as pd

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

# ---- Aggregate ----
def champ_years(subdf):
    years = subdf.loc[subdf["Is Champ"], "Season"].astype(str).tolist()
    return ", ".join(sorted(years)) if years else ""

agg = (
    work.groupby("Owner(s)", dropna=False)
    .apply(lambda g: pd.Series({
        "Championships": int(g["Is Champ"].sum()),
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

# GOAT Score 😈
agg["GOAT Score"] = (agg["Championships"] * 50 + agg["Total Wins"] * 2 + (agg["Total PF"] / 100)).round(1)

with st.expander("🐐 How is the GOAT Score calculated?"):
    st.markdown("""
**The GOAT Score is a fun, all-time legacy metric designed to reward winning *and* dominance.**

**Formula:**

🏆 **Championships** × 50  
➕ **Total Wins** × 2  
➕ **Total Points For** ÷ 100  

---

### Why this works
- 🏆 **Championships matter most** (rings > everything)
- 📊 **Wins reward consistency**
- 🏈 **Points For rewards dominance**, not just luck

This isn’t science — it’s **fantasy football propaganda** 😈
""")

agg = agg.sort_values(by=["Championships", "Win %", "Total Wins"], ascending=[False, False, False])

# ---- Display ----
st.subheader("🏆 All-Time Leaderboard")

st.dataframe(
    agg[[
        "Owner(s)",
        "Championships",
        "Championship Years",
        "Total Wins",
        "Total Losses",
        "Win %",
        "Total PF",
        "Total PA",
        "Point Diff",
        "Total Transactions",
        "GOAT Score"
    ]],
    use_container_width=True
)

st.subheader("🔥 League Superlatives")

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

st.caption("Built for trash talk. Data does not lie.")
