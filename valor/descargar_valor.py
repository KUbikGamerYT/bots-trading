"""Descarga precios (la parte de la SEC se hace desde el PC con descargar_sec.py)
Descarga datos para el backtest de inversión en valor (se ejecuta en GitHub Actions).
- SEC EDGAR: companyfacts.zip (resultados XBRL con fecha de presentación) y sub.txt
  de los Financial Statement Data Sets (para saber qué CIK corresponde a cada ticker).
- Yahoo: cierres sin ajustar por dividendos y splits, para calcular capitalización.
"""
import io, os, json, zipfile, time, requests, pandas as pd
UA = {'User-Agent': 'bots-trading value backtest research noreply@github.com', 'Accept-Encoding': 'gzip, deflate'}
OUT = 'datos_valor'; os.makedirs(OUT, exist_ok=True)
tick = [t.strip() for t in open('valor/tickers.txt') if t.strip()]

def get(url, stream=False):
    for i in range(6):
        try:
            r = requests.get(url, headers=UA, timeout=300, stream=stream)
            if r.status_code == 200: return r
            print(url, r.status_code)
        except Exception as e: print(url, e)
        time.sleep(3 * (i + 1))
    return None

# 4) precios sin ajustar por dividendos + splits
import yfinance as yf
d = yf.download(tick, start='2008-01-01', auto_adjust=False, actions=True, group_by='column', threads=True, progress=False)
d['Close'].to_csv(f'{OUT}/Close_raw.csv.gz', float_format='%.4f')
d['Adj Close'].to_csv(f'{OUT}/Close_adj.csv.gz', float_format='%.4f')
sp = d['Stock Splits']; sp = sp.where(sp > 0).dropna(how='all').stack().rename('ratio')
sp.to_csv(f'{OUT}/splits.csv.gz')
print('precios', d['Close'].dropna(axis=1, how='all').shape, 'splits', len(sp))
