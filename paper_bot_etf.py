"""
Bot de PAPER TRADING "tendencias en varios mercados" con ETF (valorado en euros).

Estrategia (validada en acciones/etf.py y combo.py):
  - 12 mercados: bolsa EE. UU. (S&P 500, Nasdaq, pequeñas), bolsa desarrollada fuera de EE. UU., emergentes,
    bonos largos, medios, corporativos y ligados a inflación, oro, materias primas e inmobiliario.
  - Al empezar cada mes calcula la "fuerza" de cada uno: media de su subida en 1, 3, 6 y 12 meses (en euros).
  - Se queda con los 3 más fuertes, 1/3 del capital cada uno, sólo si su fuerza es positiva.
    Si no hay 3 positivos, esa parte queda en liquidez.
  - Coste simulado 0,1 % por compra y por venta.
Para la simulación usa los precios de los ETF de EE. UU. pasados a euros; en Trading 212 se usarían
sus equivalentes europeos (UCITS), que siguen los mismos índices (ver EQUIVALENTE).

Archivos: estado_bot_etf.json, operaciones_etf.csv, capital_etf.csv
Uso:  python paper_bot_etf.py          python paper_bot_etf.py --reset
"""
import argparse, json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot_etf.json")
TRADES = os.path.join(HERE, "operaciones_etf.csv")
EQUITY = os.path.join(HERE, "capital_etf.csv")
TOP_N, COST = 3, 0.001

NOMBRE = {"SPY": "Bolsa EE.UU. S&P 500", "QQQ": "Nasdaq 100", "IWM": "Pequeñas EE.UU.", "EFA": "Bolsa desarrollada ex-EE.UU.",
          "EEM": "Emergentes", "TLT": "Bonos EE.UU. 20+ años", "IEF": "Bonos EE.UU. 7-10 años",
          "LQD": "Bonos corporativos", "TIP": "Bonos ligados a inflación", "GLD": "Oro", "DBC": "Materias primas",
          "VNQ": "Inmobiliario"}
EQUIVALENTE = {"SPY": "CSPX/VUAA", "QQQ": "EQQQ", "IWM": "R2US", "EFA": "IWDA (aprox.)", "EEM": "EIMI",
               "TLT": "IDTL", "IEF": "IBTM", "LQD": "LQDE", "TIP": "ITPS", "GLD": "SGLN/4GLD", "DBC": "CMOD",
               "VNQ": "IUSP"}
TICKERS = list(NOMBRE)


def descargar():
    import yfinance as yf
    d = yf.download(TICKERS + ["EURUSD=X"], period="2y", interval="1d", auto_adjust=True, progress=False, threads=False)
    c = d["Close"].dropna(how="all").ffill()
    eur = c[TICKERS].div(c["EURUSD=X"], axis=0)       # precios en euros
    hoy = datetime.now(ZoneInfo("Europe/Madrid")).date()
    return eur[eur.index.date < hoy], eur.iloc[-1]


def load_state(capital):
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(cash=capital, positions={}, last_bar=None, last_rebalance=None,
                start=datetime.now(timezone.utc).isoformat())


def save_state(st):
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)


def append_csv(path, row):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


def fuerza(c):
    m = c.resample("ME").last()
    m = m[m.index < pd.Timestamp(c.index[-1]).to_period("M").to_timestamp()]  # sólo meses ya cerrados
    s = sum(m.iloc[-1] / m.iloc[-1 - k] - 1 for k in (1, 3, 6, 12)) / 4
    return s.sort_values(ascending=False)


def analisis(st, c, mes):
    f = fuerza(c)
    top = f[f > 0].head(TOP_N)
    filas = []
    for i, (s, v) in enumerate(f.items()):
        dentro = s in st["positions"]
        if s in top.index:
            estado, txt = ("cartera", "Entre los 3 más fuertes: se mantiene.") if dentro else ("si", "Entre los 3 más fuertes: entraría en la próxima revisión.")
        elif dentro:
            estado, txt = "no", "Ha salido de los 3 más fuertes: se vendería en la próxima revisión."
        else:
            estado, txt = ("cerca" if i < TOP_N + 2 and v > 0 else "no",
                           "Fuerza negativa: nunca compra algo que esté bajando." if v <= 0 else "No llega al top 3.")
        filas.append([f"{s} · {NOMBRE[s]}", estado, f"Fuerza media 1/3/6/12 meses {v * 100:+.1f} % (puesto {i + 1}). {txt}"])
    sig = (pd.Timestamp(mes + "-01") + pd.DateOffset(months=1)).strftime("%d/%m/%Y")
    st["analisis"] = dict(fecha=datetime.now(timezone.utc).isoformat(timespec="seconds"), filas=filas,
                          resumen=f"Solo opera una vez al mes (próxima revisión desde el {sig}). Ranking con meses cerrados.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (STATE, TRADES, EQUITY):
            if os.path.exists(f):
                os.remove(f)
    try:
        c, ultimo = descargar()
    except Exception as e:
        sys.exit(f"Error al descargar precios: {e}")

    st = load_state(a.capital)
    pos = st["positions"]
    precio = {s: float(ultimo[s]) for s in TICKERS if pd.notna(ultimo[s])}
    bar = str(c.index[-1].date())
    mes = bar[:7]

    def equity():
        return st["cash"] + sum(p["units"] * precio.get(s, p["entry"]) for s, p in pos.items())

    if st["last_bar"] == bar:
        print(f"La sesión del {bar} ya está procesada. Nada que hacer.")
    else:
        print(f"Procesando sesión del {bar}")
        if st.get("last_rebalance") != mes:
            f = fuerza(c)
            top = f[f > 0].head(TOP_N)
            print("  Revisión mensual. Fuerza: " + ", ".join(f"{s} {v * 100:+.1f} %" for s, v in f.items()))
            for s in list(pos):
                if s not in top.index:
                    p = pos.pop(s)
                    px = precio.get(s, p["entry"]) * (1 - COST)
                    st["cash"] += p["units"] * px
                    pnl = p["units"] * (px - p["entry"])
                    append_csv(TRADES, dict(simbolo=s, entrada=p["time"], salida=bar, precio_entrada=p["entry"],
                                            precio_salida=round(px, 4), unidades=p["units"], beneficio=round(pnl, 4),
                                            motivo="ya no está entre los 3 más fuertes"))
                    print(f"  VENTA  {s:<4} ({NOMBRE[s]}) resultado {pnl:+.2f} €")
            hueco = equity() / TOP_N
            for s in top.index:
                if s in pos or s not in precio:
                    continue
                gasto = min(hueco, st["cash"])
                if gasto < 1:
                    break
                px = precio[s] * (1 + COST)
                pos[s] = dict(units=gasto / px, entry=px, time=bar, stop=0)
                st["cash"] -= gasto
                print(f"  COMPRA {s:<4} ({NOMBRE[s]}, en Trading 212: {EQUIVALENTE[s]}) por {gasto:.2f} €")
            st["last_rebalance"] = mes
        st["last_bar"] = bar
        append_csv(EQUITY, dict(fecha=bar, capital=round(equity(), 2), liquidez=round(st["cash"], 2),
                                posiciones=len(pos)))
    st["prices"] = {s: precio[s] for s in pos if s in precio}
    analisis(st, c, mes)
    save_state(st)
    print(f"Capital simulado (ETF): {equity():.2f} EUR")
    for s, p in pos.items():
        px = precio.get(s, p["entry"])
        print(f"  {s:<4} {NOMBRE[s]:<28} valor {p['units'] * px:.2f} €  ({(px / p['entry'] - 1) * 100:+.1f} %)")


if __name__ == "__main__":
    main()
