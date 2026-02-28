# core/calendario_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta, datetime
from functools import lru_cache
from typing import Optional, FrozenSet

import unicodedata
from sqlalchemy import select

from db.connection import get_session
from db.models import Feriado


# ============================================================
# Tipos / Regras
# ============================================================


@dataclass(frozen=True)
class _ContextoLocal:
    comarca: Optional[str]
    municipio: Optional[str]


@dataclass(frozen=True)
class RegrasCalendario:
    incluir_nacional: bool = True
    incluir_estadual_sp: bool = True

    # TJSP geral (inclui CPC 220 automático se habilitado)
    incluir_tjsp_geral: bool = True

    # TJSP por comarca
    incluir_tjsp_comarca: bool = True

    # Municipais
    incluir_municipal: bool = True


class CalendarioService:
    _MARGEM_INICIAL_DIAS = 120
    _MARGEM_CRESCIMENTO_DIAS = 120

    AUTO_MUNICIPIO_BY_COMARCA = {
        "ilhabela": "ilhabela",
    }

    _ESCOPO_ALIASES = {
        "ESTADUAL": "ESTADUAL_SP",
        "SP_ESTADUAL": "ESTADUAL_SP",
        "ESTADUAL-SP": "ESTADUAL_SP",
        "ESTADUAL SP": "ESTADUAL_SP",
        "TJSP": "TJSP_GERAL",
        "RECESSO_TJSP": "TJSP_GERAL",
        "RECESSO TJSP": "TJSP_GERAL",
        "CPC220": "TJSP_GERAL",
        "CPC 220": "TJSP_GERAL",
        "CPC_220": "TJSP_GERAL",
        "CPC-220": "TJSP_GERAL",
        "ART_220": "TJSP_GERAL",
        "ART 220": "TJSP_GERAL",
        "ARTIGO_220": "TJSP_GERAL",
        "ARTIGO 220": "TJSP_GERAL",
    }

    # ============================================================
    # Cache
    # ============================================================

    @staticmethod
    def clear_cache() -> None:
        CalendarioService._feriados_aplicaveis_cached.cache_clear()

    # ============================================================
    # Normalização
    # ============================================================

    @staticmethod
    def _to_dt(d: date) -> datetime:
        return datetime(d.year, d.month, d.day)

    @staticmethod
    def _strip_accents(s: str) -> str:
        return "".join(
            c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
        )

    @staticmethod
    def _norm(s: str | None) -> str | None:
        """
        Normaliza labels de local/comarca/município para casar com Feriado.local.
        Ex.: "Foro de Ilhabela", "Ilhabela/SP", "Município de Ilhabela" -> "ilhabela"
        """
        if not s:
            return None
        v = s.strip()
        if not v:
            return None

        v = CalendarioService._strip_accents(v).lower()
        v = " ".join(v.split())

        # remove prefixos comuns
        for prefix in (
            "comarca de ",
            "foro de ",
            "foro da ",
            "foro do ",
            "municipio de ",
        ):
            if v.startswith(prefix):
                v = v[len(prefix) :].strip()

        # remove UF/formatos comuns
        if "/" in v:
            v = v.split("/", 1)[0].strip()
        if " - " in v:
            v = v.split(" - ", 1)[0].strip()

        # remove "sp" no fim
        if v.endswith(" sp"):
            v = v[:-3].strip()

        return v or None

    @staticmethod
    def _norm_escopo(s: str | None) -> str:
        esc = (s or "").strip().upper()
        return CalendarioService._ESCOPO_ALIASES.get(esc, esc)

    # ============================================================
    # Match tolerante de local
    # ============================================================

    @staticmethod
    def _match_local(loc_norm: str | None, alvo_norm: str | None) -> bool:
        """
        Match tolerante para evitar erros por variações:
        - "ilhabela" == "ilhabela"
        - "ilhabela/sp" ~ "ilhabela"  (normalização remove)
        - "foro de ilhabela" ~ "ilhabela"
        - "municipio de ilhabela" ~ "ilhabela"
        """
        if not loc_norm or not alvo_norm:
            return False

        if loc_norm == alvo_norm:
            return True

        # contém / prefixo
        if loc_norm.startswith(alvo_norm) or alvo_norm.startswith(loc_norm):
            return True
        if alvo_norm in loc_norm or loc_norm in alvo_norm:
            return True

        # tokens
        loc_tokens = set(loc_norm.split())
        alvo_tokens = set(alvo_norm.split())
        return len(loc_tokens & alvo_tokens) > 0

    # ============================================================
    # CPC art. 220 — RECESSO AUTOMÁTICO (20/12 a 20/01) INCLUSIVE
    # ============================================================

    @staticmethod
    def _dias_recesso_cpc220(inicio: date, fim: date) -> set[date]:
        if fim < inicio:
            return set()

        out: set[date] = set()
        years = {inicio.year, fim.year, inicio.year - 1, fim.year + 1}

        for y in years:
            start = date(y, 12, 20)
            end = date(y + 1, 1, 20)  # inclusive

            a = max(inicio, start)
            b = min(fim, end)
            if a > b:
                continue

            d = a
            while d <= b:
                out.add(d)
                d += timedelta(days=1)

        return out

    # ============================================================
    # Feriados BD
    # ============================================================

    @staticmethod
    def _feriados_periodo(inicio: date, fim: date) -> list[Feriado]:
        """
        Busca feriados no intervalo [inicio, fim] (inclusive).
        """
        ini_dt = CalendarioService._to_dt(inicio)
        fim_exclusivo = CalendarioService._to_dt(fim + timedelta(days=1))

        with get_session() as s:
            stmt = (
                select(Feriado)
                .where(Feriado.data >= ini_dt, Feriado.data < fim_exclusivo)
                .order_by(Feriado.data.asc())
            )
            return list(s.execute(stmt).scalars().all())

    @staticmethod
    def _resolve_context(
        comarca: str | None,
        municipio: str | None,
        aplicar_local: bool,
    ) -> _ContextoLocal:
        if not aplicar_local:
            return _ContextoLocal(None, None)

        comarca_norm = CalendarioService._norm(comarca)
        municipio_norm = CalendarioService._norm(municipio)

        if comarca_norm and not municipio_norm:
            municipio_norm = CalendarioService.AUTO_MUNICIPIO_BY_COMARCA.get(
                comarca_norm, comarca_norm
            )

        return _ContextoLocal(comarca_norm, municipio_norm)

    @staticmethod
    def _eh_aplicavel(
        f: Feriado,
        ctx: _ContextoLocal,
        regras: RegrasCalendario,
    ) -> bool:
        esc = CalendarioService._norm_escopo(getattr(f, "escopo", None))
        loc = CalendarioService._norm(getattr(f, "local", None))

        if esc == "NACIONAL":
            return regras.incluir_nacional

        if esc == "ESTADUAL_SP":
            return regras.incluir_estadual_sp

        if esc == "TJSP_GERAL":
            return regras.incluir_tjsp_geral

        if esc == "MUNICIPAL":
            if not regras.incluir_municipal:
                return False
            # ✅ aceita casar por município OU por comarca (cadastros variam muito)
            return CalendarioService._match_local(
                loc, ctx.municipio
            ) or CalendarioService._match_local(loc, ctx.comarca)

        if esc == "TJSP_COMARCA":
            if not regras.incluir_tjsp_comarca:
                return False
            return CalendarioService._match_local(loc, ctx.comarca)

        return False

    @staticmethod
    @lru_cache(maxsize=4096)
    def _feriados_aplicaveis_cached(
        inicio_iso: str,
        fim_iso: str,
        comarca_norm: str | None,
        municipio_norm: str | None,
        regras_key: tuple,
    ) -> FrozenSet[date]:
        inicio = date.fromisoformat(inicio_iso)
        fim = date.fromisoformat(fim_iso)
        ctx = _ContextoLocal(comarca_norm, municipio_norm)

        regras = RegrasCalendario(
            incluir_nacional=bool(regras_key[0]),
            incluir_estadual_sp=bool(regras_key[1]),
            incluir_tjsp_geral=bool(regras_key[2]),
            incluir_tjsp_comarca=bool(regras_key[3]),
            incluir_municipal=bool(regras_key[4]),
        )

        aplicaveis: set[date] = set()

        # 1) Feriados do BD
        feriados_bd = CalendarioService._feriados_periodo(inicio, fim)
        for f in feriados_bd:
            if CalendarioService._eh_aplicavel(f, ctx, regras):
                aplicaveis.add(f.data.date())

        # 2) CPC art. 220 automático (somente se TJSP geral estiver habilitado)
        if regras.incluir_tjsp_geral:
            aplicaveis |= CalendarioService._dias_recesso_cpc220(inicio, fim)

        return frozenset(aplicaveis)

    @staticmethod
    def feriados_aplicaveis(
        inicio: date,
        fim: date,
        comarca: str | None,
        municipio: str | None,
        aplicar_local: bool = True,
        regras: RegrasCalendario | None = None,
    ) -> set[date]:
        ctx = CalendarioService._resolve_context(comarca, municipio, aplicar_local)
        r = regras or RegrasCalendario()

        regras_key = (
            int(r.incluir_nacional),
            int(r.incluir_estadual_sp),
            int(r.incluir_tjsp_geral),
            int(r.incluir_tjsp_comarca),
            int(r.incluir_municipal),
        )

        return set(
            CalendarioService._feriados_aplicaveis_cached(
                inicio.isoformat(),
                fim.isoformat(),
                ctx.comarca,
                ctx.municipio,
                regras_key,
            )
        )

    # ============================================================
    # Dia útil / Próximo útil
    # ============================================================

    @staticmethod
    def eh_dia_util(d: date, feriados: set[date]) -> bool:
        return d.weekday() < 5 and d not in feriados

    @staticmethod
    def proximo_dia_util(
        d: date,
        comarca: str | None = None,
        municipio: str | None = None,
        aplicar_local: bool = True,
        regras: RegrasCalendario | None = None,
    ) -> date:
        """
        Primeiro dia útil >= d, considerando feriados e regras.
        """
        r = regras or RegrasCalendario()
        fer = CalendarioService.feriados_aplicaveis(
            d,
            d + timedelta(days=60),
            comarca=comarca,
            municipio=municipio,
            aplicar_local=aplicar_local,
            regras=r,
        )
        atual = d
        while not CalendarioService.eh_dia_util(atual, fer):
            atual += timedelta(days=1)
        return atual

    # ============================================================
    # Soma de dias úteis
    # ============================================================

    @staticmethod
    def somar_dias_uteis(
        data_base: date,
        dias: int,
        comarca: str | None = None,
        municipio: str | None = None,
        excluir_dia_inicial: bool = True,
        aplicar_local: bool = True,
        regras: RegrasCalendario | None = None,
    ) -> date:
        if dias < 0:
            raise ValueError("dias deve ser >= 0")

        r = regras or RegrasCalendario()
        atual = data_base + timedelta(days=1) if excluir_dia_inicial else data_base

        fim_janela = atual + timedelta(
            days=dias + CalendarioService._MARGEM_INICIAL_DIAS
        )
        feriados = CalendarioService.feriados_aplicaveis(
            atual,
            fim_janela,
            comarca=comarca,
            municipio=municipio,
            aplicar_local=aplicar_local,
            regras=r,
        )

        contador = 0
        while contador < dias:
            if atual > fim_janela:
                novo_fim = fim_janela + timedelta(
                    days=CalendarioService._MARGEM_CRESCIMENTO_DIAS
                )
                feriados |= CalendarioService.feriados_aplicaveis(
                    fim_janela + timedelta(days=1),
                    novo_fim,
                    comarca=comarca,
                    municipio=municipio,
                    aplicar_local=aplicar_local,
                    regras=r,
                )
                fim_janela = novo_fim

            if CalendarioService.eh_dia_util(atual, feriados):
                contador += 1
                if contador == dias:
                    break

            atual += timedelta(days=1)

        # garante retorno em dia útil
        while True:
            if atual > fim_janela:
                novo_fim = fim_janela + timedelta(
                    days=CalendarioService._MARGEM_CRESCIMENTO_DIAS
                )
                feriados |= CalendarioService.feriados_aplicaveis(
                    fim_janela + timedelta(days=1),
                    novo_fim,
                    comarca=comarca,
                    municipio=municipio,
                    aplicar_local=aplicar_local,
                    regras=r,
                )
                fim_janela = novo_fim

            if CalendarioService.eh_dia_util(atual, feriados):
                break
            atual += timedelta(days=1)

        return atual

    # ============================================================
    # DJE TJSP: disponibilização -> publicação -> contagem
    # ============================================================

    @staticmethod
    def prazo_dje_tjsp(
        disponibilizacao: date,
        dias_uteis: int,
        comarca: str | None = None,
        municipio: str | None = None,
        aplicar_local: bool = True,
        regras: RegrasCalendario | None = None,
    ) -> date:
        """
        Padrão DJE:
        - Publicação: primeiro dia útil seguinte à disponibilização.
        - Contagem: dia útil seguinte à publicação (exclui a publicação).
        - Considera CPC 220 automaticamente se incluir_tjsp_geral=True.
        """
        r = regras or RegrasCalendario()

        # publicação = próximo dia útil após disponibilização
        publicacao_base = disponibilizacao + timedelta(days=1)
        publicacao = CalendarioService.proximo_dia_util(
            publicacao_base,
            comarca=comarca,
            municipio=municipio,
            aplicar_local=aplicar_local,
            regras=r,
        )

        # contagem exclui o dia da publicação
        return CalendarioService.somar_dias_uteis(
            publicacao,
            int(dias_uteis),
            comarca=comarca,
            municipio=municipio,
            excluir_dia_inicial=True,
            aplicar_local=aplicar_local,
            regras=r,
        )
