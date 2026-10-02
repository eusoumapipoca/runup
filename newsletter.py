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
MARCA = "✍️"   # tudo o que comeca por isto e para ti escreveres (e apagares a instrucao)
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


def caixa_humana(rotulo, perguntas):
    """Espaco para o autor escrever. Tracejado ambar = ainda por preencher."""
    itens = "".join(f"<li>{e(p)}</li>" for p in perguntas)
    return (f'<div style="font-family:{MONO};font-size:12px;line-height:1.5;border:1px dashed {AVISO};'
            f'color:{AVISO};padding:10px 12px;margin:10px 0;">{MARCA} <b>{e(rotulo)}</b>'
            f'<ul style="margin:6px 0 0;padding-left:18px;">{itens}</ul></div>')


def sinal_pt(v, casas=1):
    return pct(v, casas).replace(".", ",").replace("-", "−")


def razao_rejeicao(c, R):
    """Traduz o codigo do filtro para uma frase com o valor que o chumbou."""
    out = []
    for m in c.get("motivo") or []:
        if m == "tendencia":
            out.append("tendência quebrada (MM50 abaixo da MM200 ou preço abaixo da MM200)")
        elif m == "drawdown_52s":
            out.append(f"{sinal_pt(c.get('drawdown_52s_%'))} desde o máximo de 52 semanas "
                       f"(limite −{R.get('max_drawdown_52s_pct', 15):.0f}%)")
        elif m == "beta":
            b = c.get("beta")
            out.append(f"beta {b:.2f} (limite {R.get('beta_max', 1.2)})".replace(".", ",") if b is not None
                       else "beta acima do limite")
        elif m == "gap_anterior":
            out.append(f"caiu {sinal_pt(c.get('gap_ultimo_anuncio_%'))} no último anúncio")
        elif m == "mov_historico":
            out.append(f"move em média {c.get('mov_historico_%', 0):.1f}% nos resultados "
                       f"(limite {R.get('max_movimento_historico_pct', 8):.0f}%)".replace(".", ","))
        elif m == "liquidez":
            out.append("pouca liquidez")
        elif m == "preco":
            out.append("preço abaixo de 10 dólares")
        elif m == "datas":
            out.append("datas de entrada/saída indeterminadas")
        else:
            out.append(m)
    return "; ".join(out) or "—"


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

    entradas = [t for t in trades if d(t.get("data_entrada")) and d(t["data_entrada"]) > semana_ini]

    cand = D.get("candidatos", [])
    R = D.get("regras") or {}
    por_ticker = {c["ticker"]: c for c in cand}
    aprov = [c for c in cand if c.get("estado") == "OK"]
    # chumbados com janela aberta agora ou a abrir nos proximos 7 dias
    # (so existem no JSON se o earnings_runup.py correr com --all)
    chumbados = sorted(
        [c for c in cand if c.get("estado") == "FALHA" and d(c.get("T_minus_15"))
         and d(c.get("T_minus_12")) and d(c["T_minus_12"]) >= hoje
         and d(c["T_minus_15"]) <= hoje + timedelta(days=7)],
        key=lambda c: c.get("data_anuncio") or "")
    detidos = {t["ticker"] for t in trades}
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

    # --- entradas da semana: o porque de cada uma ---
    if entradas:
        L.append(titulo("Entrei esta semana"))
        for t in entradas:
            c = por_ticker.get(t["ticker"], {})
            crit = []
            if c.get("tendencia_ok"):
                crit.append("tendência ok (MM50 &gt; MM200)")
            b = t.get("beta") if t.get("beta") is not None else c.get("beta")
            if b is not None:
                crit.append(f"beta {b:.2f}".replace(".", ","))
            if c.get("drawdown_52s_%") is not None:
                crit.append(f"{e(sinal_pt(c['drawdown_52s_%']))} do máximo")
            if c.get("mov_historico_%") is not None:
                crit.append(f"move {c['mov_historico_%']:.1f}% nos resultados".replace(".", ","))
            crit.append("estimativas a subir e data confirmada (verificação manual)")
            L.append(f'<div style="font-family:{MONO};font-size:12px;line-height:1.55;'
                     f'background:{LISTRA};padding:8px 10px;margin:0 0 6px;">'
                     f'<b>{e(t["ticker"])}</b> · {e(t.get("setor"))} · entrada {e(fdata(t.get("data_entrada")))}, '
                     f'saída planeada {e(fdata(t.get("data_saida_planeada")))}<br>'
                     f'<span style="color:{FRACA};">{" · ".join(crit)}</span></div>')
        L.append(caixa_humana("Porquê estas (uma frase por ação)", [
            "O que te fez carregar no botão além dos filtros? Ex.: setor com vento a favor, "
            "reação forte no trimestre anterior, ou só regra cumprida.",
            "Alguma hesitação? Ex.: entrei mais tarde na janela, tamanho reduzido."]))

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

    # --- funil numa linha ---
    f = D.get("funil") or {}
    L.append(titulo("O que o sistema viu"))
    L.append(f'<p style="font-family:{MONO};font-size:12px;line-height:1.6;color:{TINTA};margin:0 0 8px;">'
             f'{e(f.get("universo"))} ações → {e(f.get("com_anuncio"))} com resultados em 8 semanas → '
             f'<b>{len(aprov)}</b> passam os filtros automáticos → <b>{len(em_janela)}</b> em janela hoje.</p>')

    # aprovados em janela onde nao entrei: a decisao manual e conteudo
    sem_entrada = [c for c in em_janela if c["ticker"] not in detidos]
    if sem_entrada:
        L.append(nota("Passaram os filtros e estão em janela, mas não entrei: <b>"
                      + e(", ".join(c["ticker"] for c in sem_entrada)) + "</b>.", TINTA))
        L.append(caixa_humana("Porque ficaram de fora", [
            "Zacks 3 ou pior? Data por confirmar no site da empresa? Notícia pendente "
            "(como a DGX com os cortes do Medicare)?"]))

    # --- chumbados: o sistema a dizer que nao ---
    if chumbados:
        L.append(titulo("Chumbados pelo sistema"))
        L.append(tabela(["Ação", "Resultados", "Porquê"],
                        [[f"<b>{e(c['ticker'])}</b>", e(fdata(c.get("data_anuncio"))),
                          e(razao_rejeicao(c, R))] for c in chumbados[:8]]))
        if len(chumbados) > 8:
            L.append(nota(f"E mais {len(chumbados) - 8} com a janela a abrir esta semana."))

    # --- proxima semana ---
    if proximos:
        L.append(titulo("A abrir janela na próxima semana"))
        linhas = [[f"<b>{e(c['ticker'])}</b>",
                   f"{e(fdata(c.get('T_minus_15')))} a {e(fdata(c.get('T_minus_12')))}",
                   e(fdata(c.get("data_anuncio")))] for c in proximos[:8]]
        L.append(tabela(["Ação", "Janela de compra", "Resultados"], linhas))
        L.append(nota("Lista de observação, não de compra. Ainda falta a verificação manual."))

    # --- assunto: o que realmente aconteceu ---
    assunto = []
    if entradas:
        assunto.append("Entrada em " + ", ".join(t["ticker"] for t in entradas))
    for t in fechados_semana[:2]:
        assunto.append(f"{t['ticker']} fechou {sinal_pt(t.get('retorno_pct'))}")
    if not assunto and abertos:
        prox = min(abertos, key=lambda t: t.get("data_saida_planeada") or "9999")
        fim = d(prox.get("data_saida_planeada"))
        if fim and fim >= hoje:
            assunto.append(f"{prox['ticker']} a {(fim - hoje).days} dias da saída")
    if proximos and len(assunto) < 2:
        assunto.append(proximos[0]["ticker"] + " em observação")
    if not assunto:
        assunto.append(f"Semana sem entradas — {len(chumbados)} chumbados pelo sistema")

    return {"linhas": L, "detidas": [t["ticker"] for t in abertos], "assunto": assunto}


# Para acrescentar estrategias: escreve seccao_fda(D, hoje, ...) / seccao_picks(...)
# com a mesma assinatura e junta-as aqui.
SECCOES = [seccao_runup]


# ----------------------------------------------------------------------------
# Montagem
# ----------------------------------------------------------------------------
def caixa_metodo(D):
    R = D.get("regras") or {}
    return (f'<div style="font-family:{MONO};font-size:11px;line-height:1.55;color:{FRACA};'
            f'border:1px solid {LINHA};padding:10px 12px;margin:16px 0 0;">'
            f'<b style="color:{TINTA};">O método em três linhas.</b> '
            f'Compro ações do S&amp;P 500 cerca de 15 sessões antes dos resultados e vendo sempre na véspera '
            f'do anúncio: nunca atravesso os números. Só entram empresas em tendência de subida, '
            f'pouco voláteis (beta até {e(R.get("beta_max", 1.2))}) e com estimativas a ser revistas em alta. '
            f'Cada trade arrisca 0,5% da carteira; ao fim de 30 trades, se não bater o índice, o sistema é '
            f'abandonado. <b>Alfa</b> = o meu retorno menos o do S&amp;P 500 no mesmo período. '
            f'<a href="{DASHBOARD_URL}" style="color:{TINTA};">Regras completas</a>.</div>')


def montar(D, hoje, com_grafico=False):
    semana = hoje.isocalendar()[1]
    corpo, detidas, partes = [], [], []
    for s in SECCOES:
        r = s(D, hoje, com_grafico)
        corpo += r["linhas"]
        detidas += r["detidas"]
        partes += r["assunto"]

    assunto = f"Confluens #{semana} · " + " · ".join(partes[:3])

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
        caixa_humana("Abertura (3 a 6 frases, é o que as pessoas leem)", [
            "O que aconteceu esta semana, em linguagem de café: entrei, saí, esperei, errei?",
            "Uma coisa que te surpreendeu: no mercado, numa ação, ou em ti a seguir as regras.",
            "Se não houve trades: porque é que não fazer nada também é o sistema a funcionar.",
        ]),
    ]
    md += corpo
    md += [
        caixa_humana("Lição ou dúvida da semana (opcional, 2 a 3 frases)", [
            "Algo que mudarias no sistema, mas que só vais testar depois dos 30 trades?",
            "Um erro teu (de execução, não do sistema) e como o vais evitar?",
        ]),
        caixa_metodo(D),
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

    n_caixas = corpo.count(MARCA)
    if n_caixas:
        print(f"{n_caixas} caixa(s) {MARCA} para preencheres no Buttondown antes de enviar.",
              file=sys.stderr)

    if args.buttondown:
        criar_rascunho_buttondown(assunto, corpo)


if __name__ == "__main__":
    main()
