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
import html
import json
import os
import sys
from datetime import date, timedelta

DASHBOARD_URL = "https://eusoumapipoca.github.io/runup/"
HUB_URL = "https://confluens.carrd.co/"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
MARCADOR_NOTA = "✍️ ESCREVE AQUI A TUA NOTA DA SEMANA (e apaga esta caixa)"
CHART_URL = DASHBOARD_URL + "curva.png"

# Paleta do dashboard (papel de listagem de mainframe). Tudo inline: os clientes
# de email ignoram <style> e fontes web, por isso o fallback e Courier.
PAPEL, LISTRA, TINTA = "#F4F2E9", "#DCE7D5", "#1B241C"
FRACA, LINHA, GANHO, PERDA, AVISO = "#5C6B5E", "#A9B6A4", "#2C6B41", "#A8392C", "#9A6B10"
MONO = "'IBM Plex Mono','Courier New',Courier,monospace"


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
# Blocos visuais (HTML inline, sem linhas em branco: o Markdown do Buttondown
# termina um bloco HTML na primeira linha vazia)
# ----------------------------------------------------------------------------
def e(x):
    return html.escape(str(x if x is not None else "—"))


def cor_sinal(v):
    if v is None:
        return FRACA
    return GANHO if v > 0 else PERDA if v < 0 else TINTA


def titulo(txt):
    return (f'<div style="font-family:{MONO};font-size:12px;letter-spacing:.14em;'
            f'text-transform:uppercase;color:{TINTA};border-bottom:2px solid {TINTA};'
            f'padding:18px 0 4px;margin:0 0 10px;font-weight:600;">{e(txt)}</div>')


def nota(txt, cor=FRACA):
    return (f'<p style="font-family:{MONO};font-size:12px;line-height:1.5;color:{cor};'
            f'margin:6px 0 10px;">{txt}</p>')


def tabela(cabecalho, linhas, alinhar_dir=()):
    """Tabela com faixas verdes alternadas. `linhas` = lista de listas de HTML ja escapado."""
    th = "".join(
        f'<th style="font-family:{MONO};font-size:10px;letter-spacing:.08em;text-transform:uppercase;'
        f'color:{FRACA};text-align:{"right" if i in alinhar_dir else "left"};padding:5px 6px;'
        f'border-bottom:1px solid {LINHA};font-weight:500;">{e(h)}</th>'
        for i, h in enumerate(cabecalho))
    trs = []
    for n, l in enumerate(linhas):
        fundo = LISTRA if n % 2 == 0 else PAPEL
        tds = "".join(
            f'<td style="font-family:{MONO};font-size:12px;color:{TINTA};'
            f'text-align:{"right" if i in alinhar_dir else "left"};padding:6px;">{c}</td>'
            for i, c in enumerate(l))
        trs.append(f'<tr style="background:{fundo};">{tds}</tr>')
    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="border-collapse:collapse;margin:0 0 6px;"><tr>{th}</tr>{"".join(trs)}</table>')


def cartoes(itens):
    """Fila de cartoes: itens = [(rotulo, valor, cor, subtitulo)]."""
    w = int(100 / len(itens))
    tds = "".join(
        f'<td width="{w}%" valign="top" style="padding:10px 8px;border:1px solid {LINHA};background:{PAPEL};">'
        f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.1em;text-transform:uppercase;'
        f'color:{FRACA};">{e(r)}</div>'
        f'<div style="font-family:{MONO};font-size:22px;font-weight:600;color:{c};padding:4px 0 2px;">{e(v)}</div>'
        f'<div style="font-family:{MONO};font-size:10px;color:{FRACA};">{e(s)}</div></td>'
        for r, v, c, s in itens)
    return (f'<table width="100%" cellpadding="0" cellspacing="6" border="0" '
            f'style="border-collapse:separate;margin:0 -6px;"><tr>{tds}</tr></table>')


def barra(n, total=30):
    p = max(2, min(100, round(100 * n / total)))
    return (f'<table width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 2px;">'
            f'<tr><td style="background:{LISTRA};border:1px solid {LINHA};height:10px;font-size:0;line-height:0;">'
            f'<div style="width:{p}%;height:10px;background:{TINTA};font-size:0;line-height:0;">&nbsp;</div>'
            f'</td></tr></table>')


# ----------------------------------------------------------------------------
# Grafico: evolucao da estrategia (PNG, porque email nao corre JavaScript)
# ----------------------------------------------------------------------------
def pontos_curva(trades, versao):
    """Soma acumulada dos retornos % por trade fechado, por data de saida."""
    fech = sorted(
        [t for t in trades if t.get("fechado") and t.get("retorno_pct") is not None
         and d(t.get("data_saida_real")) and (not versao or t.get("versao_sistema") == versao)],
        key=lambda t: t["data_saida_real"])
    if len(fech) < 2:
        return None
    ini = min(d(t.get("data_entrada")) or d(t["data_saida_real"]) for t in fech)
    datas, est, spy = [ini], [0.0], [0.0]
    com_spy = all(t.get("retorno_spy_pct") is not None for t in fech)
    for t in fech:
        datas.append(d(t["data_saida_real"]))
        est.append(est[-1] + t["retorno_pct"])
        spy.append(spy[-1] + (t["retorno_spy_pct"] if com_spy else 0.0))
    return datas, est, (spy if com_spy else None), [t["ticker"] for t in fech]


def desenhar_curva(trades, versao, caminho):
    """Escreve o PNG e devolve True; devolve False se houver poucos dados."""
    pts = pontos_curva(trades, versao)
    if not pts:
        return False
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    datas, est, spy, nomes = pts
    fig, ax = plt.subplots(figsize=(6.4, 3.0), dpi=200)
    fig.patch.set_facecolor(PAPEL)
    ax.set_facecolor(PAPEL)
    plt.rcParams["font.family"] = "DejaVu Sans Mono"

    ax.axhline(0, color=FRACA, lw=0.8)
    if spy:
        ax.step(datas, spy, where="post", color=FRACA, lw=1.4, ls="--", label="S&P 500 (mesmos períodos)")
    ax.step(datas, est, where="post", color=TINTA, lw=2.0, label="Estratégia")
    ax.plot(datas[1:], est[1:], "s", color=TINTA, ms=4)
    for i, (x, y, nm) in enumerate(zip(datas[1:], est[1:], nomes), start=1):
        desce = y < est[i - 1]        # etiqueta por baixo quando o trade perdeu
        ax.annotate(nm, (x, y), textcoords="offset points", xytext=(0, -12 if desce else 7),
                    ha="center", fontsize=6.5, color=TINTA)

    ax.set_ylabel("soma dos retornos (%)", fontsize=7, color=FRACA)
    ax.tick_params(colors=FRACA, labelsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))
    ax.grid(axis="y", color=LINHA, lw=0.5, alpha=0.7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(LINHA)
    ax.legend(loc="upper left", fontsize=6.5, frameon=False, labelcolor=TINTA)
    fig.tight_layout()
    fig.savefig(caminho, facecolor=PAPEL)
    plt.close(fig)
    return True


# ----------------------------------------------------------------------------
# Seccao: Earnings Run-up
# ----------------------------------------------------------------------------
def seccao_runup(D, hoje, com_grafico=False):
    L = []
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

    L.append(titulo("Earnings Run-up"))
    L.append(nota(f"Compra cerca de 15 sessões antes dos resultados, venda obrigatória na véspera. "
                  f"Sistema {e(versao)}."))

    # --- placar ---
    n = resumo.get("n_fechados", 0) or 0
    if n:
        L.append(cartoes([
            ("Retorno médio", pct(resumo.get("retorno_medio_pct"), 2),
             cor_sinal(resumo.get("retorno_medio_pct")), "por trade"),
            ("Alfa médio", pct(resumo.get("alfa_medio_pct"), 2),
             cor_sinal(resumo.get("alfa_medio_pct")), "vs. S&P 500"),
            ("Acerto", f"{resumo.get('taxa_acerto_pct', 0):.0f}%", TINTA, f"{n} fechados"),
            ("Abertas", str(len(abertos)), TINTA, "posições"),
        ]))
    else:
        L.append(cartoes([("Fechados", "0", TINTA, f"na {e(versao)}"),
                          ("Abertas", str(len(abertos)), TINTA, "posições")]))
    L.append(barra(n))
    L.append(nota(f"{n} de 30 trades fechados na {e(versao)}. Abaixo de 30 nenhuma conclusão é válida."))

    # --- evolucao ---
    L.append(titulo("Evolução da estratégia"))
    if com_grafico:
        L.append(f'<img src="{CHART_URL}" alt="Evolução acumulada da estratégia face ao S&P 500" '
                 f'width="600" style="display:block;width:100%;max-width:600px;height:auto;'
                 f'border:1px solid {LINHA};">')
        L.append(nota("Soma acumulada do retorno de cada trade fechado, por data de saída, "
                      "contra o índice nos mesmos períodos. Só trades do sistema em vigor."))
    else:
        L.append(nota("Poucos trades fechados para traçar a evolução (mínimo 2). "
                      "O gráfico aparece assim que houver dados."))

    # --- fechados esta semana ---
    if fechados_semana:
        L.append(titulo("Fechados esta semana"))
        linhas = [[f"<b>{e(t['ticker'])}</b>", e(fdata(t.get("data_entrada"))), e(fdata(t.get("data_saida_real"))),
                   f'<span style="color:{cor_sinal(t.get("retorno_pct"))}">{e(pct(t.get("retorno_pct")))}</span>',
                   f'<span style="color:{cor_sinal(t.get("alfa_pct"))}">{e(pct(t.get("alfa_pct")))}</span>',
                   e(t.get("motivo_saida") or "—")] for t in fechados_semana]
        L.append(tabela(["Ação", "Entrada", "Saída", "Retorno", "Alfa", "Motivo"], linhas, alinhar_dir=(3, 4)))

    # --- abertos ---
    if abertos:
        L.append(titulo("Posições abertas"))
        linhas = []
        for t in sorted(abertos, key=lambda t: t.get("data_saida_planeada") or ""):
            fim = d(t.get("data_saida_planeada"))
            if fim is None:
                faltam = "—"
            elif fim < hoje:
                faltam = f'<span style="color:{AVISO}">⚠️ confirma o journal</span>'
            else:
                faltam = f"{(fim - hoje).days} dias"
            linhas.append([f"<b>{e(t['ticker'])}</b>", e(t.get("setor")), e(fdata(t.get("data_entrada"))),
                           e(fdata(t.get("data_saida_planeada"))), faltam])
        L.append(tabela(["Ação", "Setor", "Entrada", "Saída", "Faltam"], linhas, alinhar_dir=(4,)))

    # aviso so para ti: trades com saida registada mas sem preco nao entram
    # nas estatisticas. Aparece no rascunho para corrigires antes de enviar.
    if meio_preenchidos:
        L.append(f'<div style="font-family:{MONO};font-size:12px;border:1px solid {AVISO};color:{AVISO};'
                 f'padding:8px;margin:8px 0;">⚠️ <b>Antes de enviar:</b> '
                 + e(", ".join(t["ticker"] for t in meio_preenchidos))
                 + " tem saída registada no journal mas sem preço de saída, por isso não conta para o "
                   "placar. Preenche e volta a gerar, e apaga este aviso.</div>")

    # --- funil da semana ---
    f = D.get("funil") or {}
    L.append(titulo("O funil desta semana"))
    L.append(tabela(["Etapa", "Ações"], [
        ["Universo (S&P 500)", e(f.get("universo"))],
        ["Com resultados nas próximas 8 semanas", e(f.get("com_anuncio"))],
        ["Passaram os filtros automáticos", str(len(aprov))],
        ["Em janela de compra hoje", f"<b>{len(em_janela)}</b>"],
    ], alinhar_dir=(1,)))
    L.append(nota("Os que passam os filtros ainda precisam de duas verificações manuais: "
                  "revisões de estimativas em alta e data confirmada pela empresa."))

    # --- proxima semana ---
    if proximos:
        L.append(titulo("A abrir janela na próxima semana"))
        linhas = [[f"<b>{e(c['ticker'])}</b>",
                   f"{e(fdata(c.get('T_minus_15')))} a {e(fdata(c.get('T_minus_12')))}",
                   e(fdata(c.get("data_anuncio")))] for c in proximos[:8]]
        L.append(tabela(["Ação", "Janela de compra", "Resultados"], linhas))
        L.append(nota("Lista de observação, não de compra. Ainda falta a verificação manual."))

    return L, [t["ticker"] for t in abertos]


# Para acrescentar estrategias: escreve seccao_fda(D, hoje, ...) / seccao_picks(...)
# com a mesma assinatura e junta-as aqui.
SECCOES = [seccao_runup]


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def montar(D, hoje, com_grafico=False):
    semana = hoje.isocalendar()[1]
    corpo, detidas = [], []
    for s in SECCOES:
        linhas, tickers = s(D, hoje, com_grafico)
        corpo += linhas
        detidas += tickers

    assunto = f"Confluens · semana {semana} — {len(detidas)} posição(ões) aberta(s)"

    decl = ((f"O autor detém posição em: {e(', '.join(sorted(set(detidas))))}. " if detidas
             else "O autor não detém posições nas ações mencionadas. ")
            + "As posições são abertas antes da publicação. Registo pessoal de uma estratégia "
              "em teste, sem qualquer relação com os emitentes. Não é recomendação de "
              "investimento nem aconselhamento financeiro; resultados passados não garantem "
              "resultados futuros.")

    md = [
        f'<div style="background:{PAPEL};padding:20px 18px;color:{TINTA};font-family:{MONO};">',
        f'<div style="font-family:{MONO};font-size:20px;font-weight:600;letter-spacing:.04em;">CONFLUENS</div>',
        f'<div style="font-family:{MONO};font-size:11px;color:{FRACA};letter-spacing:.1em;'
        f'text-transform:uppercase;border-bottom:2px solid {TINTA};padding:2px 0 8px;margin-bottom:10px;">'
        f'Semana {semana} · {e(fdata(hoje.isoformat()))} {hoje.year}</div>',
        f'<div style="font-family:{MONO};font-size:13px;border:1px dashed {AVISO};color:{AVISO};'
        f'padding:10px;margin:10px 0;">{e(MARCADOR_NOTA)}</div>',
    ]
    md += corpo
    md += [
        f'<div style="border-top:2px solid {TINTA};margin-top:18px;padding-top:10px;'
        f'font-family:{MONO};font-size:12px;">Dashboard com todos os candidatos e o histórico: '
        f'<a href="{DASHBOARD_URL}" style="color:{TINTA};">{DASHBOARD_URL}</a></div>',
        f'<p style="font-family:{MONO};font-size:10px;line-height:1.5;color:{FRACA};margin:10px 0 0;">'
        f'<b>Declaração de interesses.</b> {decl}</p>',
        '</div>',
    ]
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
    ap.add_argument("--grafico", default="curva.png",
                    help="PNG da evolucao da estrategia (publicado no site; o email aponta para la)")
    ap.add_argument("--buttondown", action="store_true",
                    help="cria um rascunho no Buttondown (nunca envia)")
    args = ap.parse_args()

    with open(args.json, encoding="utf-8") as f:
        D = versao_publica(json.load(f))
    hoje = d((D.get("meta") or {}).get("data_corrida")) or date.today()

    h = D.get("historico") or {}
    com_grafico = desenhar_curva(h.get("trades", []), h.get("versao_atual"), args.grafico)
    print(f"Gráfico -> {args.grafico}" if com_grafico else "Gráfico: poucos dados, omitido",
          file=sys.stderr)

    assunto, corpo = montar(D, hoje, com_grafico)

    # rede de seguranca: a versao publica nao pode levar euros
    if "€" in corpo or "_eur" in corpo:
        sys.exit("ERRO: valor monetário encontrado na newsletter — não publicado.")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(corpo)
    # pre-visualizacao no browser (o email final e renderizado pelo Buttondown)
    prev = os.path.splitext(args.out)[0] + ".html"
    with open(prev, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><meta charset="utf-8"><title>{html.escape(assunto)}</title>'
                f'<body style="margin:0;background:#e9e7dd"><div style="max-width:640px;margin:0 auto">'
                f'{corpo}</div>')
    print(f"Newsletter -> {args.out} (pré-visualização: {prev})", file=sys.stderr)

    if args.buttondown:
        criar_rascunho_buttondown(assunto, corpo)


if __name__ == "__main__":
    main()
