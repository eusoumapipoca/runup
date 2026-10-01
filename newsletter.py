#!/usr/bin/env python3
"""
newsletter.py — gera o rascunho semanal da newsletter a partir do dashboard.json.

Nunca envia nada. Escreve newsletter.md e, com --buttondown, cria um RASCUNHO
no Buttondown para reveres, completares a nota do autor e enviares tu.

Usa sempre a versao publica dos dados (sem euros, sem n.o de acoes), a mesma
que vai para o site. Cada estrategia e uma "seccao": para acrescentar o FDA ou
o stock picking mais tarde, basta escrever outra funcao e junta-la a SECCOES.

Uso:
    py earnings_runup.py --weeks 8          # gera o dashboard.json
    py newsletter.py                        # escreve newsletter.md
    py newsletter.py --buttondown           # e cria o rascunho no Buttondown
"""

import argparse
import json
import os
import sys
from datetime import date, timedelta

DASHBOARD_URL = "https://eusoumapipoca.github.io/runup/"
HUB_URL = "https://confluens.carrd.co/"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MARCADOR_NOTA = "✍️ ESCREVE AQUI A TUA NOTA DA SEMANA (e apaga esta linha)"


# ----------------------------------------------------------------------------
# Utilitarios
# ----------------------------------------------------------------------------
def d(s):
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def fdata(s):
    x = d(s)
    return f"{x.day} {MESES[x.month - 1]}" if x else "—"


def pct(v, casas=1):
    if v is None:
        return "—"
    return f"{'+' if v > 0 else ''}{v:.{casas}f}%"


def versao_publica(payload):
    """A mesma limpeza que o site usa. Se o import falhar, falha alto."""
    from earnings_runup import _versao_publica
    return _versao_publica(payload)


# ----------------------------------------------------------------------------
# Seccao: Earnings Run-up
# ----------------------------------------------------------------------------
def seccao_runup(D, hoje):
    linhas = []
    h = D.get("historico") or {}
    trades = h.get("trades", [])
    versao = h.get("versao_atual") or (D.get("meta") or {}).get("versao_sistema")
    resumo = (h.get("resumo_por_versao") or {}).get(versao) or {}
    # aberto = sem preco de saida E sem qualquer sinal de saida registado
    abertos = [t for t in trades if not t.get("fechado")
               and not t.get("motivo_saida") and not t.get("data_saida_real")]
    meio_preenchidos = [t for t in trades if not t.get("fechado")
                        and (t.get("motivo_saida") or t.get("data_saida_real"))]
    semana_ini = hoje - timedelta(days=7)
    fechados_semana = [t for t in trades if t.get("fechado")
                       and d(t.get("data_saida_real")) and d(t["data_saida_real"]) > semana_ini]

    cand = D.get("candidatos", [])
    aprov = [c for c in cand if c.get("estado") == "OK"]
    em_janela = [c for c in aprov if c.get("janela_aberta_hoje")]
    proximos = sorted(
        [c for c in aprov if not c.get("janela_aberta_hoje") and d(c.get("T_minus_15"))
         and hoje < d(c["T_minus_15"]) <= hoje + timedelta(days=7)],
        key=lambda c: c["T_minus_15"])

    linhas.append("## Earnings Run-up")
    linhas.append("")
    linhas.append(f"*Compra cerca de 15 sessões antes dos resultados, venda obrigatória na véspera. "
                  f"Sistema {versao or '—'}.*")
    linhas.append("")

    # --- placar ---
    n = resumo.get("n_fechados", 0) or 0
    linhas.append("**Placar**")
    linhas.append("")
    linhas.append(f"- Trades fechados na {versao}: **{n} de 30** "
                  f"(abaixo de 30 nenhuma conclusão é válida)")
    if n:
        linhas.append(f"- Retorno médio: {pct(resumo.get('retorno_medio_pct'), 2)} · "
                      f"alfa médio vs S&P 500: {pct(resumo.get('alfa_medio_pct'), 2)} · "
                      f"acerto: {resumo.get('taxa_acerto_pct', 0):.0f}%")
    linhas.append(f"- Posições abertas: {len(abertos)}")
    linhas.append("")

    # --- fechados esta semana ---
    if fechados_semana:
        linhas.append("**Fechados esta semana**")
        linhas.append("")
        linhas.append("| Ação | Entrada | Saída | Retorno | Índice | Alfa | Motivo |")
        linhas.append("|---|---|---|---|---|---|---|")
        for t in fechados_semana:
            linhas.append(f"| {t['ticker']} | {fdata(t.get('data_entrada'))} | "
                          f"{fdata(t.get('data_saida_real'))} | {pct(t.get('retorno_pct'))} | "
                          f"{pct(t.get('retorno_spy_pct'))} | {pct(t.get('alfa_pct'))} | "
                          f"{t.get('motivo_saida') or '—'} |")
        linhas.append("")

    # --- abertos ---
    if abertos:
        linhas.append("**Posições abertas**")
        linhas.append("")
        linhas.append("| Ação | Setor | Entrada | Saída planeada | Faltam |")
        linhas.append("|---|---|---|---|---|")
        for t in sorted(abertos, key=lambda t: t.get("data_saida_planeada") or ""):
            fim = d(t.get("data_saida_planeada"))
            if fim is None:
                faltam = "—"
            elif fim < hoje:
                faltam = "⚠️ saída já passou — confirma o journal"
            else:
                faltam = f"{(fim - hoje).days} dias"
            linhas.append(f"| {t['ticker']} | {t.get('setor') or '—'} | {fdata(t.get('data_entrada'))} | "
                          f"{fdata(t.get('data_saida_planeada'))} | {faltam} |")
        linhas.append("")

    # aviso so para ti: trades com saida registada mas sem preco nao entram
    # nas estatisticas. Aparece no rascunho para corrigires antes de enviar.
    if meio_preenchidos:
        linhas.append("> ⚠️ **Antes de enviar:** "
                      + ", ".join(t["ticker"] for t in meio_preenchidos)
                      + " tem saída registada no journal mas sem preço de saída, "
                        "por isso não conta para o placar. Preenche e volta a gerar, "
                        "e apaga este aviso.")
        linhas.append("")

    # --- funil da semana ---
    f = D.get("funil") or {}
    linhas.append("**O funil desta semana**")
    linhas.append("")
    linhas.append(f"{f.get('universo', '—')} ações do S&P 500 → "
                  f"{f.get('com_anuncio', '—')} com resultados nas próximas 8 semanas → "
                  f"{len(aprov)} passaram os filtros automáticos → "
                  f"{len(em_janela)} em janela de compra hoje.")
    linhas.append("")
    linhas.append("Os que passam os filtros ainda precisam de duas verificações manuais: "
                  "revisões de estimativas em alta e data confirmada pela empresa.")
    linhas.append("")

    # --- proxima semana ---
    if proximos:
        linhas.append("**A abrir janela na próxima semana**")
        linhas.append("")
        for c in proximos[:8]:
            linhas.append(f"- **{c['ticker']}** — janela {fdata(c.get('T_minus_15'))} a "
                          f"{fdata(c.get('T_minus_12'))}, resultados a {fdata(c.get('data_anuncio'))}")
        linhas.append("")
        linhas.append("*Lista de observação, não de compra. Ainda falta a verificação manual.*")
        linhas.append("")

    return linhas, [t["ticker"] for t in abertos]


# Para acrescentar estrategias: escreve seccao_fda(D, hoje) / seccao_picks(...)
# com a mesma assinatura e junta-as aqui.
SECCOES = [seccao_runup]


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def montar(D, hoje):
    semana = hoje.isocalendar()[1]
    corpo, detidas = [], []
    for s in SECCOES:
        linhas, tickers = s(D, hoje)
        corpo += linhas
        detidas += tickers

    abertos = len(detidas)
    assunto = f"Confluens · semana {semana} — {abertos} posição(ões) aberta(s)"

    md = []
    md.append(f"*Semana {semana} · {fdata(hoje.isoformat())} {hoje.year}*")
    md.append("")
    md.append(MARCADOR_NOTA)
    md.append("")
    md += corpo
    md.append("---")
    md.append("")
    md.append(f"Dashboard com todos os candidatos e o histórico: [{DASHBOARD_URL}]({DASHBOARD_URL})")
    md.append("")
    md.append("**Declaração de interesses.** "
              + (f"O autor detém posição em: {', '.join(sorted(set(detidas)))}. " if detidas
                 else "O autor não detém posições nas ações mencionadas. ")
              + "As posições são abertas antes da publicação. Registo pessoal de uma estratégia "
                "em teste, sem qualquer relação com os emitentes. Não é recomendação de "
                "investimento nem aconselhamento financeiro; resultados passados não garantem "
                "resultados futuros.")
    md.append("")
    return assunto, "\n".join(md)


def criar_rascunho_buttondown(assunto, corpo):
    import requests
    chave = os.getenv("BUTTONDOWN_API_KEY")
    if not chave:
        sys.exit("Falta BUTTONDOWN_API_KEY")
    r = requests.post(
        "https://api.buttondown.com/v1/emails",
        headers={"Authorization": f"Token {chave}"},
        # status explicito: nunca depender do valor por defeito da API
        json={"subject": assunto, "body": corpo, "status": "draft"},
        timeout=30,
    )
    if r.status_code >= 300:
        sys.exit(f"Buttondown recusou ({r.status_code}): {r.text[:300]}")
    print(f"Rascunho criado no Buttondown: {assunto}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="dashboard.json")
    ap.add_argument("--out", default="newsletter.md")
    ap.add_argument("--buttondown", action="store_true",
                    help="cria um rascunho no Buttondown (nunca envia)")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        D = versao_publica(json.load(f))
    hoje = d((D.get("meta") or {}).get("data_corrida")) or date.today()

    assunto, corpo = montar(D, hoje)

    # rede de seguranca: a versao publica nao pode levar euros
    if "€" in corpo or "_eur" in corpo:
        sys.exit("ERRO: valor monetário encontrado na newsletter — não publicado.")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"# {assunto}\n\n{corpo}")
    print(f"Newsletter -> {args.out}", file=sys.stderr)

    if args.buttondown:
        criar_rascunho_buttondown(assunto, corpo)


if __name__ == "__main__":
    main()
