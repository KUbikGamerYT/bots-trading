"""Descarga datos para el backtest de inversión en valor (se ejecuta en GitHub Actions).
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

# 1) tickers actuales -> CIK
ct = get('https://www.sec.gov/files/company_tickers.json').json()
rows = [(v['ticker'].upper().replace('.', '-'), int(v['cik_str']), 'actual', '', '') for v in ct.values()]
# 2) prefijos de los ficheros XBRL históricos (suelen ser el ticker de esa época)
for y in range(2009, 2027):
    for q in range(1, 5):
        url = f'https://www.sec.gov/files/dera/data/financial-statement-data-sets/{y}q{q}.zip'
        r = get(url, stream=True)
        if r is None: continue
        tmp = '/tmp/fs.zip'
        with open(tmp, 'wb') as f:
            for ch in r.iter_content(1 << 20): f.write(ch)
        try:
            with zipfile.ZipFile(tmp) as z:
                s = pd.read_csv(z.open('sub.txt'), sep='\t', usecols=['cik', 'instance', 'form', 'filed'], dtype=str)
        except Exception as e:
            print('fallo', y, q, e); continue
        s = s[s.form.isin(['10-K', '10-Q', '10-K/A', '10-Q/A', '10-KT'])]
        s['pre'] = s.instance.str.split('-').str[0].str.upper()
        g = s.groupby(['pre', 'cik']).filed.agg(['min', 'max']).reset_index()
        rows += [(p, int(c), 'xbrl', a, b) for p, c, a, b in g.itertuples(index=False)]
        print(y, q, len(g), flush=True)
m = pd.DataFrame(rows, columns=['ticker', 'cik', 'fuente', 'desde', 'hasta'])
m = m.groupby(['ticker', 'cik', 'fuente']).agg(desde=('desde', 'min'), hasta=('hasta', 'max')).reset_index()
m.to_csv(f'{OUT}/ticker_cik.csv.gz', index=False)
ciks = set(m[m.ticker.isin(tick)].cik)
print('CIKs a extraer', len(ciks))

# 3) companyfacts.zip
TAGS = {'NetIncomeLoss', 'ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'EarningsPerShareDiluted',
        'EarningsPerShareBasic', 'StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest',
        'Assets', 'Liabilities', 'LiabilitiesCurrent', 'AssetsCurrent', 'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax',
        'SalesRevenueNet', 'OperatingIncomeLoss', 'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest',
        'InterestExpense', 'LongTermDebt', 'LongTermDebtNoncurrent', 'LongTermDebtCurrent', 'DebtCurrent', 'ShortTermBorrowings',
        'CashAndCashEquivalentsAtCarryingValue', 'NetCashProvidedByUsedInOperatingActivities', 'PaymentsToAcquirePropertyPlantAndEquipment',
        'WeightedAverageNumberOfDilutedSharesOutstanding', 'CommonStockSharesOutstanding', 'PaymentsOfDividends',
        'PaymentsOfDividendsCommonStock', 'GrossProfit', 'EntityCommonStockSharesOutstanding'}
FORMS = {'10-K', '10-Q', '10-KT'}
r = get('https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip', stream=True)
with open('/tmp/cf.zip', 'wb') as f:
    for ch in r.iter_content(1 << 22): f.write(ch)
print('companyfacts MB', os.path.getsize('/tmp/cf.zip') >> 20)
out = []
with zipfile.ZipFile('/tmp/cf.zip') as z:
    for n in z.namelist():
        try: c = int(n.replace('CIK', '').replace('.json', ''))
        except ValueError: continue
        if c not in ciks: continue
        d = json.loads(z.read(n))
        for tax, tags in d.get('facts', {}).items():
            for tag, v in tags.items():
                if tag not in TAGS: continue
                for unit, lst in v['units'].items():
                    for e in lst:
                        if e.get('form') in FORMS:
                            out.append((c, tag, unit, e.get('start', ''), e['end'], e['val'], e['form'], e['filed'], e.get('fp', '')))
f = pd.DataFrame(out, columns=['cik', 'tag', 'unit', 'start', 'end', 'val', 'form', 'filed', 'fp'])
# valor tal como se publicó la primera vez (sin revisiones posteriores = sin mirar al futuro)
f = f.sort_values('filed').drop_duplicates(['cik', 'tag', 'unit', 'start', 'end'], keep='first')
f.to_csv(f'{OUT}/hechos.csv.gz', index=False)
print('hechos', f.shape)

# 4) precios sin ajustar por dividendos + splits
import yfinance as yf
d = yf.download(tick, start='2008-01-01', auto_adjust=False, actions=True, group_by='column', threads=True, progress=False)
d['Close'].to_csv(f'{OUT}/Close_raw.csv.gz', float_format='%.4f')
d['Adj Close'].to_csv(f'{OUT}/Close_adj.csv.gz', float_format='%.4f')
sp = d['Stock Splits']; sp = sp.where(sp > 0).dropna(how='all').stack().rename('ratio')
sp.to_csv(f'{OUT}/splits.csv.gz')
print('precios', d['Close'].dropna(axis=1, how='all').shape, 'splits', len(sp))
