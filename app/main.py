# app/main.py
import os
import json
import sys
import subprocess
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import select

from db.init_db import init_db
from db.connection import get_session
from db.models import User
from app.ui import dashboard, processos, prazos, agendamentos, andamentos, financeiro
from app.ui.theme import inject_global_css

load_dotenv()
init_db()

st.set_page_config(
    page_title="Gestão Técnica",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()

DEFAULT_EMAIL = os.getenv("DEFAULT_USER_EMAIL", "admin@local")


@st.cache_data(show_spinner=False)
def get_owner_user_id(default_email: str) -> int:
    with get_session() as s:
        user = (
            s.execute(select(User).where(User.email == default_email)).scalars().first()
        )
        if not user:
            raise RuntimeError(
                "Usuário default não encontrado. Rode: python -m db.init_db"
            )
        return user.id


# -------------------------
# PATHS / BACKUP HELPERS
# -------------------------
def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _backup_dir() -> Path:
    return _project_root() / "backups"


def _backup_manifest_path() -> Path:
    return _backup_dir() / "last_backup.json"


def _format_bytes(num: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num < 1024:
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} PB"


def read_last_backup() -> dict | None:
    manifest = _backup_manifest_path()
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _check_sqlite_integrity(db_path: Path) -> tuple[bool, str]:
    """
    PRAGMA integrity_check no arquivo SQLite (backup).
    """
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute("PRAGMA integrity_check;").fetchone()
            msg = (row[0] if row else "unknown").strip()
            ok = msg.lower() == "ok"
            return ok, msg
        finally:
            conn.close()
    except Exception as e:
        return False, f"erro: {e}"


def run_backup_now() -> None:
    root = _project_root()
    script = root / "scripts" / "backup_diario.py"
    if not script.exists():
        st.error("Script de backup não encontrado em scripts/backup_diario.py")
        return

    try:
        with st.spinner("Executando backup..."):
            subprocess.run([sys.executable, str(script)], check=True)
        st.success("Backup executado com sucesso.")
    except subprocess.CalledProcessError as e:
        st.error(f"Falha ao executar backup: {e}")


# -------------------------
# BACKUP STATE (remove repetição no UI)
# -------------------------
@dataclass(frozen=True)
class BackupState:
    exists: bool
    created_at: str
    filename: str
    path: Optional[Path]
    size_str: str
    integrity_label: str  # "OK" | "FALHA" | "—" | "Sem backup"
    integrity_detail: (
        str  # "Integridade ok" | "Integridade: ..." | "Integridade: não verificada"
    )
    checked_at: Optional[str]


def _build_backup_state(last: dict | None) -> BackupState:
    if not last:
        return BackupState(
            exists=False,
            created_at="—",
            filename="",
            path=None,
            size_str="",
            integrity_label="Sem backup",
            integrity_detail="—",
            checked_at=None,
        )

    created_at = last.get("created_at") or "—"
    filename = last.get("backup_file") or ""
    size_bytes = last.get("size_bytes")
    checked_at = last.get("integrity_checked_at")

    path = (_backup_dir() / filename).resolve() if filename else None
    exists = bool(path and path.exists())

    # tamanho
    size_str = _format_bytes(size_bytes) if isinstance(size_bytes, int) else ""

    # integridade
    integrity_ok = last.get("integrity_ok", None)
    integrity_message = last.get("integrity_message") or ""

    if integrity_ok is True:
        integrity_label = "OK"
        integrity_detail = "Integridade ok"
    elif integrity_ok is False:
        integrity_label = "FALHA"
        integrity_detail = f"Integridade: {integrity_message or 'falha'}"
    else:
        integrity_label = "—"
        integrity_detail = "Integridade: não verificada"

    return BackupState(
        exists=exists,
        created_at=created_at,
        filename=filename,
        path=path,
        size_str=size_str,
        integrity_label=integrity_label,
        integrity_detail=integrity_detail,
        checked_at=checked_at,
    )


# -------------------------
# BOOTSTRAP USER
# -------------------------
try:
    owner_user_id = get_owner_user_id(DEFAULT_EMAIL)
except RuntimeError as e:
    st.error(str(e))
    st.stop()


# -------------------------
# SIDEBAR
# -------------------------
st.sidebar.markdown("## 📐 Gestão Técnica")
st.sidebar.caption("Trabalhos • Prazos • Agenda • Financeiro")
st.sidebar.divider()

MENU_LABELS = {
    "Dashboard": "📊 Painel",
    "Processos": "📁 Trabalhos",
    "Prazos": "⏳ Prazos",
    "Agendamentos": "📅 Agenda",
    "Andamentos": "🧾 Andamentos",  # ✅ renomeado
    "Financeiro": "💰 Financeiro",
}

# Navegação segura
if "nav_target" in st.session_state:
    st.session_state["sidebar_menu"] = st.session_state.pop("nav_target")

st.sidebar.subheader("Menu")
menu = st.sidebar.radio(
    label="Menu",
    options=list(MENU_LABELS.keys()),
    format_func=lambda k: MENU_LABELS[k],
    key="sidebar_menu",
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.subheader("⚡ Ações rápidas")

if st.sidebar.button(
    "🔄 Atualizar", use_container_width=True, key="sidebar_refresh_btn"
):
    st.rerun()

# ---- Backup
st.session_state.setdefault("backup_running", False)
st.session_state.setdefault("backup_confirm", False)
st.session_state.setdefault("backup_confirm_reset", False)

last = read_last_backup()
state = _build_backup_state(last)

with st.sidebar.expander(f"📦 Backup  •  {state.integrity_label}", expanded=False):

    # ✅ reset do checkbox ANTES do widget existir
    if st.session_state.get("backup_confirm_reset", False):
        st.session_state["backup_confirm"] = False
        st.session_state["backup_confirm_reset"] = False

    st.caption(f"Último: {state.created_at}")
    st.caption(state.integrity_detail)

    col1, col2 = st.columns(2)

    with col1:
        if state.exists and state.path:
            with open(state.path, "rb") as f:
                st.download_button(
                    label="⬇️ Baixar",
                    data=f,
                    file_name=state.filename,
                    mime="application/octet-stream",
                    use_container_width=True,
                    key="download_backup_btn",
                )
        else:
            st.button(
                "⬇️ Baixar",
                use_container_width=True,
                disabled=True,
                key="download_backup_btn_disabled",
            )

    with col2:
        st.checkbox("Confirmar", key="backup_confirm")
        can_run = bool(st.session_state.get("backup_confirm", False))
        execute_clicked = st.button(
            "Executar",
            use_container_width=True,
            disabled=(not can_run) or st.session_state["backup_running"],
            key="sidebar_backup_execute_btn",
        )

    # Integridade manual (só se o manifest ainda não tiver)
    if state.exists and state.path and (last or {}).get("integrity_ok", None) is None:
        if st.button(
            "🧪 Verificar integridade agora",
            use_container_width=True,
            key="check_integrity_btn",
        ):
            ok, msg = _check_sqlite_integrity(state.path)
            # Atualiza o manifest existente (sem mexer em script), mantendo padrão simples:
            # escreve só o que falta
            manifest = _backup_manifest_path()
            try:
                payload = (
                    json.loads(manifest.read_text(encoding="utf-8"))
                    if manifest.exists()
                    else {}
                )
            except Exception:
                payload = {}
            payload.update(
                {
                    "integrity_ok": bool(ok),
                    "integrity_message": None if ok else msg,
                    "integrity_checked_at": datetime.now().strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )
            manifest.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            st.rerun()

    with st.expander("Detalhes", expanded=False):
        st.caption(f"Arquivo: {state.filename or '—'}")
        if state.size_str:
            st.caption(f"Tamanho: {state.size_str}")
        if state.checked_at:
            st.caption(f"Verificado em: {state.checked_at}")
        if state.filename and not state.exists:
            st.warning("Arquivo de backup não encontrado na pasta backups.")

    if execute_clicked:
        st.session_state["backup_running"] = True
        run_backup_now()
        st.session_state["backup_running"] = False

        # ✅ pede reset para o próximo run (antes do checkbox)
        st.session_state["backup_confirm_reset"] = True
        st.rerun()


# -------------------------
# ROTAS
# -------------------------
ROUTES = {
    "Dashboard": dashboard.render,
    "Processos": processos.render,
    "Prazos": prazos.render,
    "Agendamentos": agendamentos.render,
    "Andamentos": andamentos.render,
    "Financeiro": financeiro.render,
}

ROUTES[menu](owner_user_id)
