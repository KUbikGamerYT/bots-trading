"""
Bot de PAPER TRADING "Prueba FTMO": simula una prueba de fondeo de FTMO (2 fases) con una cuenta de 10.000 $.

Estrategia (elegida en fondeo/disenar_bot_fondeo.py con datos 2017-2020 y comprobada con 2022-2025):
  - 75 % de la cuenta sigue al bot "4 horas · BTC" (copia su rentabilidad: ruptura de 55 velas de 4h,
    stop 3 ATR, solo en tendencia alcista).
  - 75 % de la cuenta en tendencia lenta de índices y oro: S&P 500, Nasdaq 100, oro y Euro Stoxx 50,
    18,75 % cada uno, comprado mientras el cierre diario esté por encima de su media de 200 sesiones.
  - Total hasta 1,5 veces la cuenta (FTMO da apalancamiento con CFD). Coste 0,04 % por operación en índices
    y swap (coste de mantener) ~6 % al año en índices y ~10 % al año en BTC.

Reglas FTMO simuladas:
  - Fase 1: ganar +10 % (11.000 $). Fase 2: ganar +5 % (10.500 $). Mínimo 4 días con operaciones por fase.
  - Pérdida diaria máxima: 500 $ desde el valor de la cuenta a medianoche (hora de Madrid).
  - Pérdida total máxima: la cuenta no puede bajar de 9.000 $.
  - Sin límite de tiempo. Si pasan 25 días sin operar, hace una mini-operación para no caer en inactividad.
  - Si suspende, "paga" otra prueba (155 € simulados) y empieza de nuevo. Si aprueba las 2 fases pasa a
    cuenta fondeada: cada 30 días cobra el 80 % del beneficio (se devuelve la cuota en el primer cobro).

Archivos: estado_bot_ftmo.json, operaciones_ftmo.csv, capital_ftmo.csv
Uso:  python paper_bot_ftmo.py          python paper_bot_ftmo.py --reset
Se ejecuta DESPUÉS de paper_bot_4h.py (lee estado_bot_4h.json).
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd


def usd(x):
    return f"{x:,.0f}".replace(",", ".")

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_ftmo.json")
TRADES = os.path.join(HERE, "operaciones_ftmo.csv")
EQUITY = os.path.join(HERE, "capital_ftmo.csv")
BOT4H = os.path.join(HERE, "estado_bot_4h.json")
MADRID = ZoneInfo("Europe/Madrid")

CUENTA, CUOTA = 10_000.0, 155.0
OBJETIVO = {1: 0.10, 2: 0.05}
PERD_DIA, PERD_MAX, DIAS_MIN = 0.05, 0.10, 4
PESO_BTC, PESO_IDX = 0.75, 0.1875
COSTE_IDX, SWAP_IDX, SWAP_BTC = 0.0004, 0.06, 0.10
NOMBRE = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "GLD": "Oro", "^STOXX50E": "Euro Stoxx 50"}
TICKERS = list(NOMBRE)


def descargar():
    import yfinance as yf
    d = yf.download(TICKERS, period="2y", interval="1d", auto_adjust=True, progress=False, threads=False)
    c = d["Close"].dropna(how="all").ffill()
    hoy = datetime.now(MADRID).date()
    return c[c.index.date < hoy], c.iloc[-1]


def valor_4h():
    with open(BOT4H) as f:
        s = json.load(f)
    px = s.get("prices") or {}
    v = s["cash"] + sum(p["units"] * px.get(k, p["entry"]) for k, p in s["positions"].items())
    return float(v), len(s["positions"]) > 0


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def nueva_cuenta(st, fase, motivo, log):
    st.update(fase=fase, balance=CUENTA, positions={}, inicio_fase=hoy_str(), dias_op=[], dia=hoy_str(),
              inicio_dia=CUENTA, ultima_op=hoy_str())
    if fase == 1:
        st["intentos"] = st.get("intentos", 0) + 1
        st["cuotas"] = st.get("cuotas", 0.0) + CUOTA
    if fase == "fondeada":
        st["proximo_cobro"] = (pd.Timestamp(hoy_str()) + pd.Timedelta(days=30)).date().isoformat()
    log(f"  >>> {motivo}")
    st.setdefault("historial", []).append(dict(fecha=hoy_str(), evento=motivo))


def hoy_str():
    return datetime.now(MADRID).date().isoformat()


def flotante(st, px):
    return sum(p["units"] * (float(px[s]) - p["entry"]) for s, p in st["positions"].items())


def operar_dia(st, c, fecha, log):
    """Al cerrar una sesión: compra/vende índices según la media de 200."""
    px, s200 = c.iloc[-1], c.iloc[-200:].mean()
    eq = st["balance"] + flotante(st, px)
    opero = False
    for s in TICKERS:
        dentro = pd.notna(px[s]) and px[s] > s200[s]
        if s in st["positions"] and not dentro:
            p = st["positions"].pop(s)
            pnl = p["units"] * (float(px[s]) - p["entry"]) - p["units"] * float(px[s]) * COSTE_IDX
            st["balance"] += pnl
            append_csv(TRADES, dict(simbolo=NOMBRE[s], entrada=p["time"], salida=fecha, precio_entrada=round(p["entry"], 2),
                                    precio_salida=round(float(px[s]), 2), beneficio=round(pnl, 2),
                                    motivo="cierra por debajo de su media de 200", fase=st["fase"]))
            log(f"  VENTA  {NOMBRE[s]:<14} a {float(px[s]):.2f}  resultado {pnl:+.2f} $")
            opero = True
        elif s not in st["positions"] and dentro:
            uds = PESO_IDX * eq / float(px[s])
            st["balance"] -= uds * float(px[s]) * COSTE_IDX
            st["positions"][s] = dict(units=uds, entry=float(px[s]), time=fecha, stop=0)
            log(f"  COMPRA {NOMBRE[s]:<14} a {float(px[s]):.2f}  por {uds * float(px[s]):.0f} $ (sobre su media de 200)")
            opero = True
    return opero


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (STATE, TRADES, EQUITY):
            if os.path.exists(f):
                os.remove(f)
    try:
        c, ultimo = descargar()
        v4h, btc_dentro = valor_4h()
    except Exception as e:
        sys.exit(f"Error al leer datos: {e}")
    if len(c) < 210:
        sys.exit("No hay suficiente historial de precios.")

    ahora = datetime.now(timezone.utc)
    log = print
    if os.path.exists(STATE):
        with open(STATE) as f:
            st = json.load(f)
    else:
        st = dict(start=ahora.isoformat(), last_bar=None, v4h=v4h, btc_dentro=btc_dentro, ultima_vez=ahora.isoformat(),
                  cobrado=0.0, cobros=0)
        nueva_cuenta(st, 1, "Empieza la prueba FTMO 10.000 $ (intento 1, cuota simulada 155 €)", log)

    # 1) parte BTC: copia la rentabilidad del bot 4h desde la última ejecución, menos swap si estaba dentro
    horas = max((ahora - datetime.fromisoformat(st["ultima_vez"])).total_seconds() / 3600, 0)
    r_btc = v4h / st["v4h"] - 1 if st["v4h"] else 0.0
    base = st["balance"]
    st["balance"] += PESO_BTC * base * r_btc - (PESO_BTC * base * SWAP_BTC * horas / 8760 if st["btc_dentro"] else 0)
    if btc_dentro != st["btc_dentro"]:
        st["dias_op"] = sorted(set(st["dias_op"]) | {hoy_str()})
        st["ultima_op"] = hoy_str()
        log(f"  BTC 4h {'COMPRA' if btc_dentro else 'VENDE'} (parte BTC: {PESO_BTC * 100:.0f} % de la cuenta)")
    st.update(v4h=v4h, btc_dentro=btc_dentro, ultima_vez=ahora.isoformat())

    # 2) swap de índices por día y cambio de día (límite diario desde medianoche de Madrid)
    hoy = hoy_str()
    if st["dia"] != hoy:
        ndias = (pd.Timestamp(hoy) - pd.Timestamp(st["dia"])).days
        st["balance"] -= sum(p["units"] * p["entry"] for p in st["positions"].values()) * SWAP_IDX / 365 * ndias
        st["dia"] = hoy
        st["inicio_dia"] = st["balance"] + flotante(st, ultimo)

    # 3) nueva sesión cerrada: operar índices
    bar = str(c.index[-1].date())
    if st["last_bar"] != bar:
        log(f"Procesando cierre del {bar} (fase {st['fase']})")
        if operar_dia(st, c, bar, log):
            st["dias_op"] = sorted(set(st["dias_op"]) | {hoy})
            st["ultima_op"] = hoy
        st["last_bar"] = bar
    if (pd.Timestamp(hoy) - pd.Timestamp(st["ultima_op"])).days >= 25:
        st["dias_op"] = sorted(set(st["dias_op"]) | {hoy})
        st["ultima_op"] = hoy
        st["balance"] -= 0.5
        log("  Mini-operación (abrir y cerrar 0,01 lotes) para no caer en la regla de inactividad")

    # 4) reglas FTMO
    eq = st["balance"] + flotante(st, ultimo)
    if eq <= st["inicio_dia"] - PERD_DIA * CUENTA or eq <= CUENTA * (1 - PERD_MAX):
        motivo = "pérdida diaria de 500 $" if eq <= st["inicio_dia"] - PERD_DIA * CUENTA else "pérdida total del 10 %"
        fase = st["fase"]
        nueva_cuenta(st, 1, f"SUSPENDIDA ({'cuenta fondeada' if fase == 'fondeada' else 'fase ' + str(fase)}) por {motivo} "
                            f"con {usd(eq)} $. Nueva prueba: intento {st.get('intentos', 0) + 1}, otra cuota de 155 €", log)
        eq = CUENTA
    elif st["fase"] in (1, 2) and eq >= CUENTA * (1 + OBJETIVO[st["fase"]]) and len(st["dias_op"]) >= DIAS_MIN:
        dias = (pd.Timestamp(hoy) - pd.Timestamp(st["inicio_fase"])).days
        if st["fase"] == 1:
            nueva_cuenta(st, 2, f"FASE 1 APROBADA en {dias} días con {usd(eq)} $. Empieza la fase 2 (+5 %)", log)
        else:
            nueva_cuenta(st, "fondeada", f"FASE 2 APROBADA en {dias} días. ¡Cuenta fondeada de 10.000 $!", log)
        eq = CUENTA
    elif st["fase"] == "fondeada" and hoy >= st["proximo_cobro"]:
        if eq > CUENTA:
            cobro = 0.8 * (eq - CUENTA) + (CUOTA if st.get("cobros", 0) == 0 else 0)
            st["cobrado"] = st.get("cobrado", 0.0) + cobro
            st["cobros"] = st.get("cobros", 0) + 1
            for s in list(st["positions"]):   # FTMO pide cerrar posiciones para cobrar
                p = st["positions"][s]
                p["entry"] = float(ultimo[s])
            st["balance"] = CUENTA
            log(f"  COBRO simulado: {usd(cobro)} $ (80 % del beneficio{' + cuota devuelta' if st['cobros'] == 1 else ''})")
            st.setdefault("historial", []).append(dict(fecha=hoy, evento=f"Cobro de {usd(cobro)} $"))
            eq = CUENTA
        st["proximo_cobro"] = (pd.Timestamp(hoy) + pd.Timedelta(days=30)).date().isoformat()

    append_csv(EQUITY, dict(fecha=ahora.isoformat(timespec="seconds"), capital=round(eq, 2), fase=st["fase"],
                            posiciones=len(st["positions"]) + (1 if btc_dentro else 0)))

    # 5) datos para el panel (cash + unidades x precio = valor de la cuenta)
    st["prices"] = {s: float(ultimo[s]) for s in st["positions"]}
    st["cash"] = eq - sum(p["units"] * st["prices"][s] for s, p in st["positions"].items())
    objetivo = CUENTA * (1 + OBJETIVO[st["fase"]]) if st["fase"] in (1, 2) else None
    fase_txt = {1: "Fase 1 (objetivo +10 %)", 2: "Fase 2 (objetivo +5 %)", "fondeada": "Cuenta fondeada"}[st["fase"]]
    filas = [
        ["Situación", "cartera" if st["fase"] == "fondeada" else "cerca",
         f"{fase_txt}. Cuenta: {usd(eq)} $"
         + (f", faltan {usd(objetivo - eq)} $ para el objetivo ({usd(objetivo)} $)." if objetivo else
            f". Próximo cobro: {st['proximo_cobro']}. Cobrado en total: {usd(st.get('cobrado', 0))} $.")
         + f" Días con operaciones en esta fase: {len(st['dias_op'])} (mínimo {DIAS_MIN})."],
        ["Límites", "info",
         f"Hoy no puede bajar de {usd(st['inicio_dia'] - PERD_DIA * CUENTA)} $ (margen {usd(eq - (st['inicio_dia'] - PERD_DIA * CUENTA))} $). "
         f"Nunca de {usd(CUENTA * (1 - PERD_MAX))} $ (margen {usd(eq - CUENTA * (1 - PERD_MAX))} $)."],
        ["Intentos", "info", f"Pruebas empezadas: {st.get('intentos', 1)} · cuotas simuladas pagadas: {usd(st.get('cuotas', CUOTA))} €."],
        ["BTC 4h (75 %)", "cartera" if btc_dentro else "no",
         "Comprado: sigue al bot de 4 horas." if btc_dentro else "En liquidez: el bot de 4 horas espera una ruptura en tendencia alcista."],
    ]
    s200 = c.iloc[-200:].mean()
    for s in TICKERS:
        dentro = s in st["positions"]
        filas.append([NOMBRE[s], "cartera" if dentro else "no",
                      f"{'Comprado' if dentro else 'Fuera'}: último cierre {float(c[s].iloc[-1]):.2f}, media de 200 sesiones {float(s200[s]):.2f}."])
    st["analisis"] = dict(fecha=ahora.isoformat(timespec="seconds"), filas=filas,
                          resumen="Simulación de la prueba FTMO de 10.000 $ con el bot combinado (BTC 4h + índices y oro). "
                                  "Backtest: ~40-65 % de aprobar las 2 fases en 12 meses, unos 7-8 meses de media.")
    st["actualizado"] = ahora.isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)
    print(f"Prueba FTMO: {fase_txt}, cuenta {eq:,.2f} $, intento {st.get('intentos', 1)}")


if __name__ == "__main__":
    main()
