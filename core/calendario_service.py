from datetime import date, timedelta
from sqlalchemy import select
from db.connection import get_session
from db.models import Feriado


class CalendarioService:

    @staticmethod
    def listar_feriados_ano(ano: int, comarca: str | None = None) -> set[date]:
        with get_session() as s:
            stmt = select(Feriado.data)

            rows = s.execute(stmt).all()

        return {row[0].date() for row in rows if row[0].year == ano}

    @staticmethod
    def eh_dia_util(d: date, feriados: set[date]) -> bool:
        if d.weekday() >= 5:  # sábado/domingo
            return False
        if d in feriados:
            return False
        return True

    @staticmethod
    def somar_dias_uteis(
        data_inicial: date, dias: int, comarca: str | None = None
    ) -> date:
        ano = data_inicial.year
        feriados = CalendarioService.listar_feriados_ano(ano, comarca)

        atual = data_inicial
        contador = 0

        while contador < dias:
            atual += timedelta(days=1)
            if CalendarioService.eh_dia_util(atual, feriados):
                contador += 1

        return atual
