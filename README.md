# Bots de trading (dinero simulado)

Dos bots de *paper trading* que funcionan solos en GitHub, sin usar el PC:

- **Bot diario**: 12 criptos grandes, velas diarias, 100 USDT simulados.
- **Bot 4 horas**: solo BTC, velas de 4 h, otros 100 USDT simulados.

GitHub los ejecuta cada hora (pestaña **Actions**). Leen precios públicos de Binance, simulan las operaciones y guardan los resultados en este repositorio. **No usan dinero real ni claves de ningún exchange.**

**Panel:** se publica en GitHub Pages (enlace en la parte derecha del repositorio, "Deployments" / "github-pages"), o abre `panel.html`.

Archivos que se actualizan solos: `estado_bot*.json`, `capital_*.csv`, `operaciones*.csv`, `registro_bot*.txt`.

Para lanzarlo a mano: Actions → "Bots de trading (simulado)" → **Run workflow**.
