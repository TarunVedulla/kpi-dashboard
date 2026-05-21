"""
Pliant Commercial KPI Dashboard — Streamlit Web App
=====================================================
Author  : Tarun Vedulla
Version : 1.0 Streamlit

Deploy free at streamlit.io — anyone with the link can use it.

Run locally:
    pip install streamlit pandas plotly groq openpyxl
    streamlit run pliant_streamlit_app.py
"""

import os
import io
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import streamlit as st

# ── Try importing groq (optional) ────────────────────────
try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# ════════════════════════════════════════════════════════
# PAGE CONFIG
# ════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Pliant KPI Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ════════════════════════════════════════════════════════
# CUSTOM CSS — Power BI style
# ════════════════════════════════════════════════════════

st.markdown("""
<style>
    /* Main background */
    .main { background-color: #F2F7FD; }
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }

    /* KPI Cards */
    .kpi-card {
        background: white;
        border-radius: 10px;
        padding: 20px 24px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        margin-bottom: 8px;
    }
    .kpi-label {
        font-size: 12px;
        font-weight: 700;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-bottom: 6px;
    }
    .kpi-value-blue   { font-size: 32px; font-weight: 900; color: #4472C4; }
    .kpi-value-red    { font-size: 32px; font-weight: 900; color: #C0504D; }
    .kpi-value-green  { font-size: 32px; font-weight: 900; color: #70AD47; }
    .kpi-value-purple { font-size: 32px; font-weight: 900; color: #7030A0; }

    /* Section headers */
    .section-header {
        font-size: 14px;
        font-weight: 700;
        color: #1A1A2E;
        padding: 34px 0 2px 0;
        border-bottom: 2px solid #4472C4;
        margin-bottom: 8px;
    }

    /* AI Summary cards */
    .exec-summary {
        background: #1F4E79;
        border-radius: 10px;
        padding: 20px 24px;
        color: white;
        font-size: 14px;
        line-height: 1.8;
        margin-bottom: 16px;
    }
    .ai-card {
        background: white;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 12px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        font-size: 13px;
        line-height: 1.7;
        color: #333;
    }
    .ai-card-title {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 6px;
    }

    /* Anomaly badge */
    .badge-anomaly { color: #B71C1C; font-weight: 700; }
    .badge-normal  { color: #2E7D32; font-weight: 700; }

    /* Sidebar */
    .css-1d391kg { background-color: #1F4E79; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# COLOURS
# ════════════════════════════════════════════════════════

C_BLUE     = "#4472C4"
C_PINK     = "#F4A7B9"
C_ANOMALY  = "#C0504D"
C_AMBER    = "#E8A838"
C_GREEN    = "#70AD47"
C_PURPLE   = "#7030A0"
C_NAV      = "#1F4E79"
C_GREY     = "#666666"
C_GRID     = "#EEEEEE"
PIE_COLORS = ["#4472C4","#ED7D31","#70AD47","#C0504D","#7030A0","#00B0F0","#FFC000"]

ANOMALY_THRESHOLD = 1.0

SAMPLE_DATA = [
    ("NovaTech",   1200, 1800, 360, "DE"),
    ("BluePeak",    850, 1105, 255, "AT"),
    ("Starline",   2100, 3150, 840, "UK"),
    ("Redwood",     430,  645,  86, "NL"),
    ("Crestview",  1750, 2275, 700, "DE"),
    ("Ironclad",    980, 1470, 220, "FR"),
    ("Skybridge",  1400, 2100, 630, "DE"),
]

# ════════════════════════════════════════════════════════
# DATA HELPERS
# ════════════════════════════════════════════════════════

def get_sample_df():
    return pd.DataFrame(SAMPLE_DATA,
        columns=["Partner","Transactions","Revenue_EUR","Cashback_EUR","Market"])

def auto_rename(df):
    lower = {col.lower().replace(" ","_"): col for col in df.columns}
    hints = {
        "Partner":      ["partner","name","company"],
        "Revenue_EUR":  ["revenue","sales","spend"],
        "Cashback_EUR": ["cashback","rebate"],
        "Transactions": ["transactions","txns","volume"],
        "Market":       ["market","country","region"],
    }
    rmap = {}
    for target, words in hints.items():
        for w in words:
            for lc, orig in lower.items():
                if w in lc and orig not in rmap.values():
                    rmap[orig] = target
                    break
    return df.rename(columns=rmap)

def calculate_metrics(df):
    df = df.copy()
    df["Margin_EUR"]    = df["Revenue_EUR"] - df["Cashback_EUR"]
    df["Margin_Pct"]    = (df["Margin_EUR"]  / df["Revenue_EUR"] * 100).round(2)
    df["Cashback_Rate"] = (df["Cashback_EUR"] / df["Revenue_EUR"] * 100).round(2)
    avg = df["Cashback_Rate"].mean()
    std = df["Cashback_Rate"].std()
    threshold = avg + ANOMALY_THRESHOLD * std
    df["Anomaly"] = df["Cashback_Rate"] > threshold
    df["Status"]  = df["Anomaly"].map({True: "⚠️ Anomaly", False: "✅ Normal"})
    return df, threshold, avg

def abbreviate(name, max_len=8):
    name = str(name).strip()
    if len(name) <= max_len: return name
    first = name.split()[0]
    return first if len(first) <= max_len else name[:max_len-1]+"…"

def smart_positions(x_vals, y_vals):
    x_med = np.median(x_vals)
    y_med = np.median(y_vals)
    counters = {"top right":0,"bottom right":0,"top left":0,"bottom left":0}
    result = []
    for x, y in zip(x_vals, y_vals):
        base = ("top" if y >= y_med else "bottom")+" "+("right" if x >= x_med else "left")
        pos  = ("middle right" if "right" in base else "middle left") if counters[base]%2==1 else base
        counters[base] += 1
        result.append(pos)
    return result

# ════════════════════════════════════════════════════════
# GROQ AI SUMMARY
# ════════════════════════════════════════════════════════

def call_groq(prompt, api_key):
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content":prompt}],
            max_tokens=250, temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {e}"

def generate_summaries(df, avg_cb, avg_margin, api_key):
    anomalies   = df[df["Anomaly"]]["Partner"].tolist()
    top_partner = df.loc[df["Margin_EUR"].idxmax(),"Partner"]
    top_market  = df.groupby("Market")["Revenue_EUR"].sum().idxmax()
    market_df   = df.groupby("Market")["Revenue_EUR"].sum().reset_index().sort_values("Revenue_EUR",ascending=False)

    summaries = {}
    with st.spinner("🤖 Generating AI summaries via Groq..."):
        summaries["executive"] = call_groq(f"""
Senior commercial analyst at a fintech. Write 3 sentences executive summary.
Revenue: €{df['Revenue_EUR'].sum():,.0f} | Margin: €{df['Margin_EUR'].sum():,.0f} | Avg Margin: {avg_margin:.1f}%
Partners: {len(df)} | Top: {top_partner} | Anomalies: {', '.join(anomalies) if anomalies else 'None'}
End with one clear action. Write for CFO. No bullets.
""", api_key)

        summaries["revenue"] = call_groq(f"""
2 sentences on revenue vs cashback. Revenue: €{df['Revenue_EUR'].sum():,.0f}, Cashback: €{df['Cashback_EUR'].sum():,.0f}, Avg CB rate: {avg_cb:.1f}%, Anomalies: {', '.join(anomalies) if anomalies else 'None'}. Data-driven, no bullets.
""", api_key)

        summaries["margin"] = call_groq(f"""
2 sentences on margin performance. Avg: {avg_margin:.1f}%, Best: {df.loc[df['Margin_Pct'].idxmax(),'Partner']} at {df['Margin_Pct'].max():.1f}%, Worst: {df.loc[df['Margin_Pct'].idxmin(),'Partner']} at {df['Margin_Pct'].min():.1f}%. No bullets.
""", api_key)

        summaries["market"] = call_groq(f"""
2 sentences on market distribution. Top: {top_market}. Split: {', '.join([f"{r['Market']}: €{r['Revenue_EUR']:,.0f}" for _,r in market_df.iterrows()])}. No bullets.
""", api_key)

        summaries["transactions"] = call_groq(f"""
2 sentences on transaction volume. Total: {int(df['Transactions'].sum()):,}, Highest: {df.loc[df['Transactions'].idxmax(),'Partner']}, Lowest: {df.loc[df['Transactions'].idxmin(),'Partner']}. No bullets.
""", api_key)

    return summaries

# ════════════════════════════════════════════════════════
# CHART BUILDER
# ════════════════════════════════════════════════════════

def build_charts(df, avg_cb, avg_margin):
    bar_colors = [C_ANOMALY if a else C_BLUE for a in df["Anomaly"]]
    n          = len(df)
    tick_angle = -38 if n > 7 else 0
    tick_size  = 9   if n > 7 else 11

    # ── Row 1: Revenue vs Cashback ───────────────────────────
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(name="Revenue", x=df["Partner"], y=df["Revenue_EUR"],
        marker_color=C_BLUE, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Revenue: €%{y:,.0f}<extra></extra>"))
    fig1.add_trace(go.Bar(name="Cashback", x=df["Partner"], y=df["Cashback_EUR"],
        marker_color=C_PINK, marker_line_width=0,
        hovertemplate="<b>%{x}</b><br>Cashback: €%{y:,.0f}<extra></extra>"))
    fig1.update_layout(
        barmode="group", height=320, template="plotly_white",
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(t=10,b=80,l=50,r=20),
        legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
        yaxis_title="EUR (€)", xaxis_title="Partners",
    )
    fig1.update_xaxes(tickangle=tick_angle, tickfont=dict(size=tick_size), showgrid=False)
    fig1.update_yaxes(gridcolor=C_GRID)

    # ── Row 1: Margin % ──────────────────────────────────────
    fig2 = go.Figure()
    fig2.add_trace(go.Bar(name="Margin %", x=df["Partner"], y=df["Margin_Pct"],
        marker_color=bar_colors, marker_line_width=0, showlegend=False,
        hovertemplate="<b>%{x}</b><br>Margin: %{y:.1f}%<extra></extra>"))
    fig2.add_trace(go.Scatter(x=df["Partner"], y=[avg_margin]*n,
        mode="lines", showlegend=False, hoverinfo="skip",
        line=dict(color=C_AMBER, dash="dash", width=2)))
    fig2.add_annotation(text=f"Avg {avg_margin:.1f}%",
        x=df["Partner"].iloc[-1], y=avg_margin,
        showarrow=False, font=dict(color=C_AMBER, size=10),
        xanchor="left", xshift=8)
    fig2.update_layout(
        height=320, template="plotly_white",
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(t=10,b=80,l=50,r=20),
        yaxis_title="Margin %", xaxis_title="Partners",
    )
    fig2.update_xaxes(tickangle=tick_angle, tickfont=dict(size=tick_size), showgrid=False)
    fig2.update_yaxes(gridcolor=C_GRID)

    # ── Row 2: Transactions ──────────────────────────────────
    fig3 = go.Figure()
    fig3.add_trace(go.Bar(name="Transactions", x=df["Partner"], y=df["Transactions"],
        marker=dict(color=df["Transactions"], colorscale=[[0,C_PINK],[1,C_BLUE]], showscale=False),
        marker_line_width=0, showlegend=False,
        hovertemplate="<b>%{x}</b><br>Transactions: %{y:,}<extra></extra>"))
    fig3.update_layout(
        height=320, template="plotly_white",
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(t=10,b=80,l=50,r=20),
        yaxis_title="Transactions", xaxis_title="Partners",
    )
    fig3.update_xaxes(tickangle=tick_angle, tickfont=dict(size=tick_size), showgrid=False)
    fig3.update_yaxes(gridcolor=C_GRID)

    # ── Row 2: Market Donut ──────────────────────────────────
    market_df = df.groupby("Market")["Revenue_EUR"].sum().reset_index()
    market_df = market_df.sort_values("Revenue_EUR", ascending=False)
    fig4 = go.Figure()
    fig4.add_trace(go.Pie(
        labels=market_df["Market"], values=market_df["Revenue_EUR"],
        hole=0.42, textinfo="label+percent", textposition="outside",
        textfont=dict(size=11), sort=True,
        marker=dict(colors=PIE_COLORS[:len(market_df)], line=dict(color="white", width=3)),
        pull=[0.03]*len(market_df),
        hovertemplate="<b>%{label}</b><br>€%{value:,.0f}<br>%{percent}<extra></extra>",
        hoverlabel=dict(bgcolor=C_NAV, font=dict(color="white", size=11)),
        showlegend=False,
    ))
    fig4.update_layout(
        height=320, paper_bgcolor="white",
        margin=dict(t=10,b=10,l=10,r=10),
    )

    # ── Row 3: Scatter ───────────────────────────────────────
    x_vals      = df["Cashback_Rate"].tolist()
    y_vals      = df["Margin_Pct"].tolist()
    short_names = [abbreviate(p) for p in df["Partner"]]
    positions   = smart_positions(x_vals, y_vals)
    hover_texts = [f"<b>{p}</b><br>Cashback: {x:.1f}%<br>Margin: {y:.1f}%"
                   for p,x,y in zip(df["Partner"],x_vals,y_vals)]

    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(
        x=x_vals, y=y_vals, mode="markers+text",
        text=short_names, textposition=positions,
        textfont=dict(size=9, color="#333"),
        hovertext=hover_texts, hoverinfo="text",
        marker=dict(size=11, color=bar_colors, line=dict(width=1.5, color="white")),
        showlegend=False,
    ))
    xp = (max(x_vals)-min(x_vals))*0.18
    yp = (max(y_vals)-min(y_vals))*0.18
    fig5.add_hline(y=avg_margin, line_dash="dot", line_color="#CCCCCC", line_width=1.2)
    fig5.add_vline(x=avg_cb,    line_dash="dot", line_color="#CCCCCC", line_width=1.2)
    fig5.update_layout(
        height=360, template="plotly_white",
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(t=10,b=50,l=50,r=20),
        xaxis_title="Cashback Rate %", yaxis_title="Margin %",
        xaxis=dict(range=[min(x_vals)-xp, max(x_vals)+xp], showgrid=False),
        yaxis=dict(range=[min(y_vals)-yp, max(y_vals)+yp], gridcolor=C_GRID),
    )

    return fig1, fig2, fig3, fig4, fig5

# ════════════════════════════════════════════════════════
# ANOMALY TABLE
# ════════════════════════════════════════════════════════

def render_anomaly_table(df):
    tbl = df.sort_values("Cashback_Rate", ascending=False).reset_index(drop=True)

    def style_row(row):
        if row["Anomaly"]:
            return ["background-color:#FDECEA; color:#B71C1C; font-weight:bold"]*7
        return ["background-color:#F0F6FF; color:#1A1A2E"]*7

    display = tbl[["Partner","Revenue_EUR","Cashback_EUR","Margin_EUR",
                    "Margin_Pct","Cashback_Rate","Status"]].copy()
    display.columns = ["Partner","Revenue €","Cashback €","Margin €",
                       "Margin %","CB Rate %","Status"]
    display["Revenue €"]  = display["Revenue €"].apply(lambda v: f"€{v:,.0f}")
    display["Cashback €"] = display["Cashback €"].apply(lambda v: f"€{v:,.0f}")
    display["Margin €"]   = display["Margin €"].apply(lambda v: f"€{v:,.0f}")
    display["Margin %"]   = display["Margin %"].apply(lambda v: f"{v:.1f}%")
    display["CB Rate %"]  = display["CB Rate %"].apply(lambda v: f"{v:.1f}%")

    styled = display.style.apply(
        lambda row: ["background-color:#FDECEA; color:#B71C1C; font-weight:bold"
                     if tbl.loc[row.name,"Anomaly"]
                     else "background-color:#F0F6FF; color:#1A1A2E"]*7,
        axis=1
    ).set_table_styles([
        {"selector":"thead th",
         "props":[("background-color","#1F4E79"),("color","white"),
                  ("font-weight","bold"),("text-align","center"),
                  ("padding","10px"),("font-size","12px")]},
        {"selector":"tbody td",
         "props":[("text-align","center"),("padding","8px"),
                  ("font-size","12px"),("border","1px solid #D5E0F0")]},
    ])
    st.dataframe(styled, use_container_width=True, height=380)

# ════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center; padding:10px 0 20px 0;'>
        <div style='font-size:28px;'>📊</div>
        <div style='font-size:16px; font-weight:700; color:#1F4E79;'>Pliant KPI Dashboard</div>
        <div style='font-size:11px; color:#999; margin-top:4px;'>Commercial Analytics</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📁 Data Source")
    data_source = st.radio("", ["Upload CSV/Excel", "Use Sample Data"], label_visibility="collapsed")

    df_raw = None
    if data_source == "Upload CSV/Excel":
        uploaded = st.file_uploader("Drop your file here", type=["csv","xlsx","xls"])
        if uploaded:
            try:
                df_raw = pd.read_excel(uploaded) if uploaded.name.endswith((".xlsx",".xls")) else pd.read_csv(uploaded)
                df_raw.columns = df_raw.columns.str.strip()
                required = ["Partner","Transactions","Revenue_EUR","Cashback_EUR","Market"]
                missing  = [c for c in required if c not in df_raw.columns]
                if missing:
                    df_raw = auto_rename(df_raw)
                    missing = [c for c in required if c not in df_raw.columns]
                if missing:
                    st.error(f"Missing columns: {missing}")
                    df_raw = None
                else:
                    st.success(f"✅ {len(df_raw)} rows loaded")
            except Exception as e:
                st.error(f"Error: {e}")
    else:
        df_raw = get_sample_df()
        st.info("Using sample data")

    st.markdown("---")
    st.markdown("### 🤖 AI Summaries (Groq)")
    groq_key = st.text_input("Groq API Key", type="password",
                              placeholder="gsk_...",
                              help="Free at console.groq.com")
    enable_ai = st.checkbox("Enable AI Summaries", value=bool(groq_key))

    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    anomaly_thresh = st.slider("Anomaly Sensitivity", 0.5, 2.0, 1.0, 0.1,
                               help="Lower = more anomalies detected")

    st.markdown("---")
    st.markdown("""
    <div style='font-size:11px; color:#999; text-align:center;'>
        Built by <b>Tarun Vedulla</b><br>
        Pliant Case Study · 2026
    </div>
    """, unsafe_allow_html=True)

# ════════════════════════════════════════════════════════
# MAIN DASHBOARD
# ════════════════════════════════════════════════════════

st.markdown(f"""
<div style='text-align:center; padding:20px 0 16px 0;'>
    <span style='font-size:24px; font-weight:700; color:#1A1A2E;'>
        📊 Company Analytics — Commercial KPI Dashboard
    </span>
</div>
""", unsafe_allow_html=True)

if df_raw is None:
    st.info("👈 Upload your data file or select Sample Data from the sidebar to begin.")
    st.stop()

# Apply custom threshold
ANOMALY_THRESHOLD = anomaly_thresh
df, threshold, avg_cb = calculate_metrics(df_raw)
avg_margin = df["Margin_Pct"].mean()

# ── KPI CARDS ────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
kpi_data = [
    (c1, "Total Revenue",  f"€{df['Revenue_EUR'].sum():,.0f}",  "kpi-value-blue",   C_BLUE),
    (c2, "Total Cashback", f"€{df['Cashback_EUR'].sum():,.0f}", "kpi-value-red",    C_ANOMALY),
    (c3, "Total Margin",   f"€{df['Margin_EUR'].sum():,.0f}",   "kpi-value-green",  C_GREEN),
    (c4, "Avg Margin %",   f"{avg_margin:.1f}%",                "kpi-value-purple", C_PURPLE),
]
for col, label, value, css_class, border_color in kpi_data:
    with col:
        st.markdown(f"""
        <div class="kpi-card" style="border-top: 4px solid {border_color};">
            <div class="kpi-label">{label}</div>
            <div class="{css_class}">{value}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── ROW 1: Revenue vs Cashback | Margin % ────────────────
fig1, fig2, fig3, fig4, fig5 = build_charts(df, avg_cb, avg_margin)

col_l, col_r = st.columns(2)
with col_l:
    st.markdown('<div class="section-header">💰 Revenue vs Cashback by Partner</div>', unsafe_allow_html=True)
    st.plotly_chart(fig1, use_container_width=True)
with col_r:
    st.markdown('<div class="section-header">📊 Margin % by Partner</div>', unsafe_allow_html=True)
    st.plotly_chart(fig2, use_container_width=True)

# ── ROW 2: Transactions | Market Donut ───────────────────
col_l, col_r = st.columns(2)
with col_l:
    st.markdown('<div class="section-header">🔄 Transaction Volume by Partner</div>', unsafe_allow_html=True)
    st.plotly_chart(fig3, use_container_width=True)
with col_r:
    st.markdown('<div class="section-header">🌍 Revenue by Market</div>', unsafe_allow_html=True)
    st.plotly_chart(fig4, use_container_width=True)

# ── ROW 3: Anomaly Table | Scatter ───────────────────────
col_l, col_r = st.columns(2)
with col_l:
    st.markdown('<div class="section-header">⚠️ Partner Anomaly Detection Table</div>', unsafe_allow_html=True)
    render_anomaly_table(df)
with col_r:
    st.markdown('<div class="section-header">📈 Cashback Rate vs Margin %</div>', unsafe_allow_html=True)
    st.plotly_chart(fig5, use_container_width=True)

# ── AI SUMMARIES ─────────────────────────────────────────
st.markdown("<br>", unsafe_allow_html=True)
st.markdown('<div class="section-header">🤖 AI Executive Summary — Groq API</div>', unsafe_allow_html=True)

if enable_ai and groq_key and GROQ_AVAILABLE:
    summaries = generate_summaries(df, avg_cb, avg_margin, groq_key)

    st.markdown(f"""
    <div class="exec-summary">
        <div style="font-size:12px; font-weight:700; color:#BDD7EE;
                    text-transform:uppercase; letter-spacing:0.06em; margin-bottom:8px;">
            Executive Summary
        </div>
        {summaries.get('executive','—')}
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    ai_cards = [
        (col1, "💰 Revenue & Cashback Analysis", summaries.get("revenue","—"),      C_BLUE),
        (col2, "📊 Margin Performance",          summaries.get("margin","—"),       C_ANOMALY),
        (col1, "🌍 Market Distribution",         summaries.get("market","—"),       C_GREEN),
        (col2, "🔄 Transaction Volume Analysis", summaries.get("transactions","—"), C_PURPLE),
    ]
    for col, title, text, color in ai_cards:
        with col:
            st.markdown(f"""
            <div class="ai-card" style="border-left:4px solid {color};">
                <div class="ai-card-title" style="color:{color};">{title}</div>
                {text}
            </div>
            """, unsafe_allow_html=True)
elif enable_ai and not groq_key:
    st.warning("Enter your Groq API key in the sidebar to enable AI summaries. Free at console.groq.com")
elif not GROQ_AVAILABLE:
    st.warning("Install groq: `pip install groq`")
else:
    st.info("Enable AI Summaries in the sidebar to generate insights.")

st.markdown("""
<div style='text-align:center; margin-top:24px; font-size:11px; color:#999;'>
    Built by Tarun Vedulla · Pliant Case Study · 2026
</div>
""", unsafe_allow_html=True)
