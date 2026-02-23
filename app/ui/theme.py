import streamlit as st


def inject_global_css() -> None:
    st.markdown(
        """
        <style>
          /* Container geral (corrige topo "comendo") */
          .block-container {
            padding-top: 2.6rem;
            padding-bottom: 2rem;
            max-width: 1280px;
          }

          /* Header do Streamlit (deixa mais limpo) */
          header[data-testid="stHeader"] {
            background: rgba(0,0,0,0);
          }

          /* Títulos */
          h1 { margin-top: 0.4rem; letter-spacing: -0.02em; }
          h2, h3 { letter-spacing: -0.02em; }

          /* Sidebar: mais clara e profissional (degradê suave) */
          section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #111827 0%, #1f2937 100%);
          }
          section[data-testid="stSidebar"] * {
            color: #e5e7eb !important;
          }
          section[data-testid="stSidebar"] .stRadio label {
            font-weight: 500;
          }
          section[data-testid="stSidebar"] .stCaption {
            opacity: 0.9;
          }

          /* Cards */
          .sp-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 16px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
          }
          .sp-card-title {
            font-size: 0.82rem;
            color: #6b7280;
            margin-bottom: 6px;
          }
          .sp-card-value {
            font-size: 1.55rem;
            font-weight: 750;
            color: #0f172a;
            line-height: 1.1;
          }
          .sp-muted {
            color: #6b7280;
            font-size: 0.9rem;
            margin-top: 6px;
          }

          /* Dataframe */
          div[data-testid="stDataFrame"] {
            border-radius: 14px;
            overflow: hidden;
            border: 1px solid #e5e7eb;
          }

          /* Botões */
          .stButton>button {
            border-radius: 12px;
            padding: 0.55rem 0.9rem;
            font-weight: 600;
          }

          /* Expanders */
          details {
            border-radius: 14px !important;
            border: 1px solid #e5e7eb !important;
          }

          /* Inputs */
          div[data-baseweb="input"] > div,
          div[data-baseweb="textarea"] > div,
          div[data-baseweb="select"] > div {
            border-radius: 12px !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def card(title: str, value: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="sp-card">
          <div class="sp-card-title">{title}</div>
          <div class="sp-card-value">{value}</div>
          <div class="sp-muted">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
