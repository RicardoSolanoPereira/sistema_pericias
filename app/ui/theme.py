# app/ui/theme.py
from __future__ import annotations
import streamlit as st


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
          :root{
            --bg: #F5F7FA;
            --surface: #ffffff;
            --border: #e5e7eb;

            --text: #0f172a;
            --muted: #64748b;

            --primary: #1E2A38;     /* corporativo */
            --primary-2: #2F4F6F;   /* secundária */

            --info: #1976d2;
            --success: #2E7D32;
            --warning: #ED6C02;
            --danger: #C62828;

            --radius-lg: 16px;
            --radius-md: 12px;
            --shadow: 0 1px 2px rgba(0,0,0,0.045);
            --shadow-2: 0 4px 10px rgba(0,0,0,0.10);
          }

          /* --------------------------------------------------
             APP / LAYOUT
          -------------------------------------------------- */
          .stApp{
            background: var(--bg);
          }

          .block-container {
            padding-top: 1.6rem;
            padding-bottom: 1.4rem;
            max-width: 1560px;
          }

          header[data-testid="stHeader"] {
            background: rgba(0,0,0,0);
          }

          h1, h2, h3, h4 {
            letter-spacing: -0.015em;
            color: var(--text);
          }
          h1 { margin-top: 0.2rem; }
          h2 { margin-top: 0.4rem; }
          h3 { margin-top: 0.5rem; }

          .stCaption { color: var(--muted) !important; }

          /* Containers com border=True: arredondamento consistente */
          div[data-testid="stContainer"] > div:has(> div[data-testid="stVerticalBlock"]){
            border-radius: var(--radius-lg);
          }

          /* --------------------------------------------------
             SIDEBAR
          -------------------------------------------------- */
          section[data-testid="stSidebar"]{
            background-color: #f4f6f8;
            border-right: 1px solid var(--border);
          }

          section[data-testid="stSidebar"] .block-container{
            padding-top: 1.1rem;
            padding-bottom: 1rem;
          }

          section[data-testid="stSidebar"] hr{
            border-color: var(--border) !important;
          }

          /* --------------------------------------------------
             SIDEBAR - MENU RADIO (pill corporativa)
          -------------------------------------------------- */
          section[data-testid="stSidebar"]
          div[role="radiogroup"]
          label[data-baseweb="radio"] > div:first-child{
            display: none !important;
          }

          section[data-testid="stSidebar"]
          div[role="radiogroup"]
          label[data-baseweb="radio"] > div:last-child{
            margin-left: 0 !important;
          }

          section[data-testid="stSidebar"]
          div[role="radiogroup"]
          label[data-baseweb="radio"]{
            display: block;
            width: 100%;
            padding: 10px 14px;
            border-radius: 12px;
            margin-bottom: 6px;
            cursor: pointer;
            transition: all 0.12s ease;
            border: 1px solid rgba(30,42,56,0.10);
            background: rgba(255,255,255,0.60);
          }

          section[data-testid="stSidebar"]
          div[role="radiogroup"]
          label[data-baseweb="radio"]:hover{
            background: rgba(30,42,56,0.06);
            border-color: rgba(30,42,56,0.22);
            transform: translateY(-1px);
          }

          section[data-testid="stSidebar"]
          div[role="radiogroup"]
          label[data-baseweb="radio"]:has(input:checked){
            background: rgba(30,42,56,0.12);
            border: 1px solid rgba(30,42,56,0.35);
            border-left: 5px solid var(--primary);
            padding-left: 11px;
            font-weight: 780;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05);
            transform: none;
          }

          /* --------------------------------------------------
             TABS (Cadastrar | Lista | Editar/Excluir)
             - Segmented control corporativo (alto contraste)
          -------------------------------------------------- */
          div[data-baseweb="tab-list"]{
            background: #ffffff !important;
            border: 1px solid rgba(30,42,56,0.18) !important;
            border-radius: 14px !important;
            padding: 6px !important;
            gap: 6px !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
          }

          button[data-baseweb="tab"]{
            border-radius: 12px !important;
            padding: 10px 14px !important;
            font-weight: 760 !important;

            background: #f8fafc !important;
            border: 1px solid rgba(30,42,56,0.16) !important;
            color: rgba(15,23,42,0.86) !important;

            box-shadow: none !important;
            transition: all 0.12s ease !important;
          }

          button[data-baseweb="tab"]:hover{
            background: #ffffff !important;
            border-color: rgba(30,42,56,0.30) !important;
            transform: translateY(-1px);
          }

          button[data-baseweb="tab"][aria-selected="true"]{
            background: var(--primary) !important;
            border-color: var(--primary) !important;
            color: #ffffff !important;
            box-shadow: var(--shadow-2) !important;
            transform: none !important;
          }

          /* remove inkbar para evitar conflito com segmented control */
          div[data-baseweb="tab-highlight"]{
            display: none !important;
          }

          /* --------------------------------------------------
             BOTÕES
          -------------------------------------------------- */
          .stButton > button{
            border-radius: var(--radius-md);
            padding: 0.52rem 0.90rem;
            font-weight: 720;
            border: 1px solid rgba(49,51,63,0.15);
            background: #ffffff;
          }

          .stButton > button:hover{
            border-color: rgba(30,42,56,0.30);
            transform: translateY(-1px);
          }

          /* Streamlit 1.32+ reconhece kind="primary" quando usa type="primary" */
          .stButton > button[kind="primary"]{
            background: var(--primary) !important;
            border-color: var(--primary) !important;
            color: #ffffff !important;
          }

          .stButton > button[kind="primary"]:hover{
            background: #16202B !important;
            border-color: #16202B !important;
          }

          /* --------------------------------------------------
             INPUTS / SELECTS - foco visível e corporativo
          -------------------------------------------------- */
          div[data-baseweb="input"] > div,
          div[data-baseweb="textarea"] > div,
          div[data-baseweb="select"] > div{
            border-radius: var(--radius-md) !important;
            border-color: rgba(30,42,56,0.18) !important;
            background: #ffffff !important;
          }

          div[data-baseweb="input"] > div:hover,
          div[data-baseweb="textarea"] > div:hover,
          div[data-baseweb="select"] > div:hover{
            border-color: rgba(30,42,56,0.32) !important;
          }

          /* foco (quando clica) */
          div[data-baseweb="input"] > div:focus-within,
          div[data-baseweb="textarea"] > div:focus-within,
          div[data-baseweb="select"] > div:focus-within{
            border-color: rgba(30,42,56,0.75) !important;
            box-shadow: 0 0 0 3px rgba(30,42,56,0.12) !important;
          }

          /* --------------------------------------------------
             ALERTAS compactos
          -------------------------------------------------- */
          div[data-testid="stAlert"]{
            border-radius: var(--radius-md) !important;
            padding: 8px 12px !important;
          }
          div[data-testid="stAlert"] p{ margin: 0 !important; }

          /* --------------------------------------------------
             CARDS
          -------------------------------------------------- */
          .sp-card{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 14px 16px;
            box-shadow: var(--shadow);
          }
          .sp-card-title{
            font-size: 0.78rem;
            color: rgba(15,23,42,0.62);
            margin-bottom: 6px;
            font-weight: 740;
          }
          .sp-card-value{
            font-size: 1.42rem;
            font-weight: 840;
            color: var(--text);
            line-height: 1.1;
          }
          .sp-card-value.emph{
            font-size: 1.86rem;
            font-weight: 900;
          }
          .sp-muted{
            color: rgba(15,23,42,0.58);
            font-size: 0.82rem;
            margin-top: 6px;
          }

          /* tonalidades (borda esquerda) */
          .sp-tone-danger{ border-left: 6px solid var(--danger); padding-left: 12px; }
          .sp-tone-warning{ border-left: 6px solid var(--warning); padding-left: 12px; }
          .sp-tone-success{ border-left: 6px solid var(--success); padding-left: 12px; }
          .sp-tone-info{ border-left: 6px solid var(--info); padding-left: 12px; }
          .sp-tone-neutral{ border-left: 6px solid #cbd5e1; padding-left: 12px; }

          /* --------------------------------------------------
             DATAFRAME
          -------------------------------------------------- */
          div[data-testid="stDataFrame"]{
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid var(--border);
            background: var(--surface);
          }

          details{
            border-radius: 14px !important;
            border: 1px solid var(--border) !important;
            background: var(--surface);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card(
    title: str,
    value: str,
    subtitle: str = "",
    *,
    tone: str = "neutral",
    emphasize: bool = False,
) -> None:
    """
    tone: neutral | danger | warning | success | info
    emphasize: deixa o valor maior (pra KPIs críticos)
    """
    tone = (tone or "neutral").strip().lower()
    if tone not in {"neutral", "danger", "warning", "success", "info"}:
        tone = "neutral"

    emph_class = "emph" if emphasize else ""
    st.markdown(
        f"""
        <div class="sp-card sp-tone-{tone}">
          <div class="sp-card-title">{title}</div>
          <div class="sp-card-value {emph_class}">{value}</div>
          <div class="sp-muted">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(text: str) -> None:
    st.markdown(f"#### {text}")


def subtle_divider() -> None:
    st.markdown(
        "<hr style='border:0;border-top:1px solid #e5e7eb;margin:0.8rem 0;'/>",
        unsafe_allow_html=True,
    )
