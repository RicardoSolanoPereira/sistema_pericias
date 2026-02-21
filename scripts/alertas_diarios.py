from __future__ import annotations

import os
from dotenv import load_dotenv
from sqlalchemy import select

from db.connection import get_session
from db.init_db import init_db
from db.models import User
from core.utils import now_br
from core.alertas_service import AlertasService
from core.email_service import send_email_smtp


def montar_email(atrasados, vencendo, due_days: int) -> tuple[str, str]:
    data_ref = now_br().strftime("%d/%m/%Y %H:%M")
    subject = f"[Perícias] Alertas de prazos - {data_ref}"

    lines = []
    lines.append(f"Relatório automático de prazos ({data_ref})")
    lines.append("")

    if not atrasados and not vencendo:
        lines.append("✅ Nenhum prazo atrasado ou vencendo nos próximos dias.")
        return subject, "\n".join(lines)

    if atrasados:
        lines.append("🔴 PRAZOS ATRASADOS")
        for it in atrasados:
            lines.append(
                f"- ({it.prioridade}) {it.processo_numero} – {it.tipo_acao} | {it.evento} | "
                f"Venceu em {it.data_limite_br} | {it.dias_restantes} dias"
            )
        lines.append("")

    if vencendo:
        lines.append(f"🟠 PRAZOS VENCENDO EM ATÉ {due_days} DIAS")
        for it in vencendo:
            lines.append(
                f"- ({it.prioridade}) {it.processo_numero} – {it.tipo_acao} | {it.evento} | "
                f"Vence em {it.data_limite_br} | faltam {it.dias_restantes} dias"
            )
        lines.append("")

    lines.append("—")
    lines.append("Sistema de Perícias (MVP local)")
    return subject, "\n".join(lines)


def main():
    load_dotenv()
    init_db()

    if os.getenv("ALERTS_ENABLED", "1") != "1":
        print("ALERTS_ENABLED != 1; abortando.")
        return

    due_days = int(os.getenv("ALERTS_DUE_DAYS", "3"))
    default_email = os.getenv("DEFAULT_USER_EMAIL", "admin@local")

    with get_session() as s:
        user = (
            s.execute(select(User).where(User.email == default_email)).scalars().first()
        )
        if not user:
            raise RuntimeError(
                "Usuário default não encontrado. Rode: python -m db.init_db"
            )

        atrasados, vencendo = AlertasService.coletar_prazos_alerta(
            s, owner_user_id=user.id, due_days=due_days
        )

    # Só envia se tiver algo relevante
    if not atrasados and not vencendo:
        print("Sem alertas hoje.")
        return

    subject, body = montar_email(atrasados, vencendo, due_days)
    send_email_smtp(subject, body)
    print("E-mail de alertas enviado com sucesso.")


if __name__ == "__main__":
    main()
