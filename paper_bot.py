"""
Bot de PAPER TRADING (dinero simulado) para la estrategia de tendencia en cripto.

- Descarga velas diarias reales del exchange (por defecto Binance, sin necesidad de cuenta ni claves).
- Aplica las mismas reglas que el backtest: ruptura del máximo de 55 días + SMA50 > SMA200,
  stop dinámico a 4 x ATR(20), salida si rompe el mínimo de 20 días.
  Riesgo 1 % por operación, máx. 25 % del capital por moneda, sin apalancamiento.
- Simula las órdenes al precio actual con un coste del 0,2 % y guarda todo en:
    estado_bot.json        (capital y posiciones abiertas)
    operaciones.csv        (historial de operaciones cerradas)
    capital_diario.csv     (evolución del capital)

Uso (una vez al día, mejor poco después de las 02:00 hora de España = cierre diario UTC):
    pip install pandas      (ccxt sólo si usas --exchange distinto de binance)
    python paper_bot.py
Opciones:
    --capital 100        capital inicial simulado (sólo la primera vez)
    --exchange kraken    usar otro exchange compatible con ccxt
    --reset              borrar el estado y empezar de cero
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
import pandas as pd

SYMBOLS = ["BTC", "ETH", "BNB", "XRP", "ADA", "DOGE", "LTC", "LINK", "TRX", "XLM", "BCH", "DOT"]
P = dict(entry_n=55, exit_n=20, fast=50, slow=200, atr_n=20, atr_mult=4.0,
         risk=0.01, max_total_risk=0.06, max_pos_weight=0.25, max_gross=1.0, cost=0.002)
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "estado_bot.json")
TRADES = os.path.join(HERE, "operaciones.csv")
EQUITY = os.path.join(HERE, "capital_diario.csv")


# ---------- datos ----------
class BinanceVision:
    """Datos públicos de Binance desde data-api.binance.vision (sin cuenta ni claves).
    Funciona también desde servidores en EE. UU. (GitHub), donde api.binance.com está bloqueado."""
    BASE = "https://data-api.binance.vision/api/v3"

    def _get(self, path):
        import urllib.request
        req = urllib.request.Request(self.BASE + path, headers={"User-Agent": "paper-bot"})
        last = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(req, timeout=20) as r:
                    return json.loads(r.read())
            except Exception as e:  # reintenta ante fallos puntuales de red
                last = e
        raise last

    def fetch_ohlcv(self, symbol, timeframe="1d", limit=300):
        rows = self._get(f"/klines?symbol={symbol.replace('/', '')}&interval={timeframe}&limit={limit}")
        return [[int(r[0])] + [float(x) for x in r[1:6]] for r in rows]

    def fetch_ticker(self, symbol):
        return {"last": float(self._get(f"/ticker/price?symbol={symbol.replace('/', '')}")["price"])}


def make_exchange(name: str):
    if name == "binance":
        return BinanceVision()
    import ccxt
    return getattr(ccxt, name)({"enableRateLimit": True})


def fetch_daily(exchange, sym: str, quote: str) -> pd.DataFrame:
    rows = exchange.fetch_ohlcv(f"{sym}/{quote}", timeframe="1d", limit=300)
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df.ts, unit="ms")
    df = df.set_index("time")[["open", "high", "low", "close"]]
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    return df[df.index < today]  # sólo velas cerradas


def indicators(d: pd.DataFrame) -> pd.Series:
    """Devuelve los indicadores de la última vela cerrada."""
    prev = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - prev).abs(), (d.low - prev).abs()], axis=1).max(axis=1)
    last = d.iloc[-1]
    return pd.Series(dict(
        time=d.index[-1], close=last.close, high=last.high, low=last.low,
        atr=tr.rolling(P["atr_n"]).mean().iloc[-1],
        hh=d.close.iloc[-P["entry_n"] - 1:-1].max(), ll=d.close.iloc[-P["entry_n"] - 1:-1].min(),
        xh=d.close.iloc[-P["exit_n"] - 1:-1].max(), xl=d.close.iloc[-P["exit_n"] - 1:-1].min(),
        fast=d.close.rolling(P["fast"]).mean().iloc[-1], slow=d.close.rolling(P["slow"]).mean().iloc[-1],
    ))


# ---------- estado ----------
def load_state(capital: float) -> dict:
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return dict(cash=capital, positions={}, last_bar=None, start=datetime.now(timezone.utc).isoformat())


def save_state(st: dict):
    st["actualizado"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(STATE, "w") as f:
        json.dump(st, f, indent=2, default=str)


def append_csv(path: str, row: dict):
    pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)


# ---------- lógica de un día ----------
def step(st: dict, ind: dict[str, pd.Series], price: dict[str, float], log=print) -> dict:
    """Procesa la última vela cerrada de cada símbolo y simula las órdenes al precio actual."""
    pos = st["positions"]

    def equity():
        return st["cash"] + sum(p["units"] * price.get(s, p["entry"]) for s, p in pos.items())

    def close(s, px, motivo):
        p = pos.pop(s)
        fill = px * (1 - P["cost"])
        st["cash"] += p["units"] * fill
        pnl = p["units"] * (fill - p["entry"])
        append_csv(TRADES, dict(simbolo=s, entrada=p["time"], salida=str(ind[s].time.date()),
                                precio_entrada=p["entry"], precio_salida=fill, unidades=p["units"],
                                beneficio=round(pnl, 4), r=round(pnl / p["risk_cash"], 2), motivo=motivo))
        log(f"  VENTA  {s:<5} a {fill:.6g}  ({motivo})  resultado {pnl:+.2f}")

    # 1) salidas: stop tocado en la vela, o ruptura del canal de salida
    for s in list(pos):
        if s not in ind:
            continue
        r, p = ind[s], pos[s]
        if r.low <= p["stop"]:
            close(s, min(price[s], p["stop"]), "stop")
        elif r.close < r.xl:
            close(s, price[s], f"rompe mínimo {P['exit_n']} días")
        else:
            p["stop"] = max(p["stop"], r.close - P["atr_mult"] * r.atr)

    # 2) entradas
    for s, r in ind.items():
        if s in pos or pd.isna(r.slow) or pd.isna(r.atr):
            continue
        if r.close > r.hh and r.fast > r.slow:
            eq = equity()
            open_risk = sum(p["risk_cash"] for p in pos.values())
            risk_cash = min(P["risk"] * eq, max(0.0, P["max_total_risk"] * eq - open_risk))
            px = price[s] * (1 + P["cost"])
            stop_dist = P["atr_mult"] * r.atr
            units = risk_cash / stop_dist if stop_dist > 0 else 0
            units = min(units, P["max_pos_weight"] * eq / px)
            gross = sum(p["units"] * price.get(k, p["entry"]) for k, p in pos.items())
            units = min(units, max(0.0, P["max_gross"] * eq - gross) / px, st["cash"] / px)
            if units * px < 1:  # menos de 1 € no merece la pena
                log(f"  señal de compra en {s} pero no queda capital/riesgo disponible")
                continue
            st["cash"] -= units * px
            pos[s] = dict(units=units, entry=px, stop=px - stop_dist, risk_cash=units * stop_dist,
                          time=str(r.time.date()))
            log(f"  COMPRA {s:<5} {units:.6g} a {px:.6g}  (stop {px - stop_dist:.6g}, {units * px:.2f} invertido)")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--exchange", default="binance")
    ap.add_argument("--quote", default="USDT")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset:
        for f in (STATE, TRADES, EQUITY):
            if os.path.exists(f):
                os.remove(f)

    ex = make_exchange(a.exchange)
    st = load_state(a.capital)

    ind, price = {}, {}
    for s in SYMBOLS:
        try:
            d = fetch_daily(ex, s, a.quote)
            if len(d) < P["slow"] + 1:
                print(f"{s}: historial insuficiente, se omite"); continue
            ind[s] = indicators(d)
            price[s] = ex.fetch_ticker(f"{s}/{a.quote}")["last"]
        except Exception as e:
            print(f"{s}: error al descargar datos ({e})")
    if not ind:
        sys.exit("No se pudo descargar ningún dato. Revisa la conexión o prueba con --exchange kraken")

    bar = str(max(r.time for r in ind.values()).date())
    if st["last_bar"] == bar:
        print(f"Ya se procesó la vela del {bar}. Vuelve a ejecutarlo mañana.")
    else:
        print(f"Procesando vela diaria del {bar}")
        step(st, ind, price)
        st["last_bar"] = bar
        eq = st["cash"] + sum(p["units"] * price.get(s, p["entry"]) for s, p in st["positions"].items())
        append_csv(EQUITY, dict(fecha=bar, capital=round(eq, 2),
                                liquidez=round(st["cash"], 2), posiciones=len(st["positions"])))

    eq = st["cash"] + sum(p["units"] * price.get(s, p["entry"]) for s, p in st["positions"].items())
    st["prices"] = {k: float(v) for k, v in price.items()}  # para el panel
    save_state(st)
    print(f"\nCapital simulado: {eq:.2f} {a.quote}  (liquidez {st['cash']:.2f})")
    for s, p in st["positions"].items():
        val = p["units"] * price.get(s, p["entry"])
        print(f"  {s:<5} valor {val:7.2f}  entrada {p['entry']:.6g}  stop {p['stop']:.6g}")


if __name__ == "__main__":
    main()
