# PROJECT_CONTEXT.md

## 1. Project Overview
This project is an advanced, production-grade **Options Trading Strategy Scanner, Analytics Engine, and Automated Execution System** tailored for financial markets (specifically supporting the Tehran Stock Exchange / Iranian capital market ecosystem).

The platform continuously monitors underlying assets and option chains, generates and evaluates single-leg and multi-leg option strategies, computes financial Greeks, margins, and probabilities, ranks opportunities using customizable scoring models, and provides automated order execution and instant alert dispatching.

---

## 2. High-Level Architecture & Workflow

[ Market Data APIs / Broker WebServices ]
                  │
                  ▼
         [ data/ (Downloader & Cleaner) ]
                  │
                  ▼
     [ strategies/ (Generators & Pattern Matcher) ]
                  │
                  ▼
       [ analytics/ (Greeks, Margins, Payoffs) ]
                  │
                  ▼
     [ filters/ & scoring/ (Ranking Engine) ]
                  │
      ┌───────────┼───────────────────┐
      ▼           ▼                   ▼
 [ ui/ (Desktop GUI) ]   [ alerts/ (Bale Bot) ]   [ automation/ (Broker Orders) ]
 

---

## 3. Directory & Module Breakdown

### 3.1. Core (`core/`)
Defines foundational domain models and enumerated types used across the application.
* **`models.py`**: Data structures for option contracts, ticks, positions, orders, strategy legs, and portfolio candidates.
* **`enums.py`**: Enumerations for option types (`CALL`, `PUT`), position directions (`BUY`, `SELL`), order statuses, and strategy classifications.

### 3.2. Data Management (`data/`)
Handles market data ingestion, synchronization, normalization, and local caching.
* **`downloader.py`**: Fetches option chains, underlying asset prices, and market depth from exchange endpoints or broker APIs.
* **`cleaner.py`**: Normalizes strike prices, adjusts for corporate actions, filters anomalous bids/asks, and handles expiry dates.
* **`manager.py`**: Coordinates data runtime states with the local disk/memory cache (`data/cache/`).

### 3.3. Strategy Generation & Matching (`strategies/`)
Contains business logic for option strategy construction, combination generation, and fast pattern matching.
* **`definitions/`**: Mathematical logic, maximum risk/reward models, and break-even calculations for standard strategies:
  * *Single-Leg*: `long_call`, `short_call`, `long_put`, `short_put`
  * *Vertical & Complex Spreads*: `bull_call_spread`, `bear_put_spread`, `iron_condor`, `long_box`
  * *Volatility Strategies*: `long_straddle`, `long_strangle`, `long_guts`, `strap`, `strip`
  * *Stock + Option Hybrids*: `covered_call`, `married_put`, `collar`, `conversion`
* **`generators/`**: Combinatorial generation engines (`single_leg`, `two_leg`, `three_leg`, `four_leg`, `stock_option`).
* **`matching/`**:
  * `contract_index.py`: High-performance lookup index for active contracts.
  * `fast_filter.py`: Fast pre-filtering to eliminate non-viable combinations before heavy computation.
  * `pattern_matcher.py`: Core algorithm matching real-time market states against strategy definitions.

### 3.4. Analytics & Financial Engineering (`analytics/`)
Computes quantitative indicators, derivatives pricing, and risk measures.
* **`graaks_calculator.py`**: Computes Option Greeks ($\Delta$, $\Gamma$, $\Theta$, $\mathcal{V}$, $\rho$) using pricing models.
* **`margin_calculator.py`**: Calculates exchange-mandated collateral and initial margin requirements (وجه تضمین).
* **`cost_calculator.py`**: Computes transaction fees, brokerage commissions, and slippage estimates.
* **`payoff_calculator.py`**: Generates full expiration PnL curves and calculates exact break-even thresholds.
* **`probabilities_calculator.py`**: Calculates Probability of Profit (PoP), Delta-derived probabilities, and statistical expected value.
* **`risk_engine.py`**: Evaluates overall portfolio risk, tail risk, and maximum drawdown scenarios.
* **`strategy_classifier.py`**: Inspects arbitrary option combinations and classifies them into standard strategy names.

### 3.5. Engine & Filtering (`engine/`, `filters/`)
The operational backbone executing recurring scans and pipeline processing.
* **`scanner_engine.py` / `scanner.py` / `scanner1.py`**: Orchestrates market iterations, runs strategy matching, and coordinates analysis passes.
* **`opportunity_builder.py`**: Assembles analyzed candidates into concrete, actionable trade opportunities.
* **`strategy_filters.py`**: Applies dynamic constraints (Days-to-Maturity, Open Interest, Minimum ROI, Max Margin, Bid-Ask Spread).

### 3.6. Scoring & Prioritization (`scoring/`)
* **`liquidity_score.py`**: Evaluates market depth, order book liquidity, and bid-ask tightness to compute liquidity risk.
* **`metrics.py`**: Aggregates yield-to-margin, Sharpe/Sortino ratios, and risk-reward metrics.
* **`ranker.py`**: Sorts and ranks scanned opportunities to surface optimal risk-adjusted setups.

### 3.7. Automation & Alerts (`automation/`, `alerts/`)
* **`automation/brokers/Omex_khobregan.py`**: API/Web-automation integration with Iranian brokerage trading platforms (Omex / Khobregan) for multi-leg order routing.
* **`alerts/bale_notifier.py`**: Automated notification bot pushing high-priority arbitrage and strategy signals to the **Bale** messaging platform.

### 3.8. User Interface (`ui/`)
Modern desktop graphical user interface built with PyQt / PySide.
* **`main_window.py`**: Real-time dashboard displaying market scanners, opportunity grids, and telemetry.
* **`workers.py`**: Background multithreading (`QThread` / `QRunnable`) ensuring the UI remains responsive during intensive calculations.
* **`settings_dialog.py` & `symbol_filter_dialog.py`**: User configuration for watchlist symbols, risk tolerance, and broker credentials.
* **`settings_manager.py`**: Manages persistent storage and retrieval of application configuration.
* **`theme.py`**: UI theming, dark/light stylesheets, and layout aesthetics.

### 3.9. Reporting & Visualizations (`reports/`)
* **`chart_plotter.py`**: Payoff diagram visualization engine (interactive PnL graphs vs. underlying price).
* **`excel_exporter.py`**: Formatted `.xlsx` export utilities for historical analysis and portfolio tracking.

### 3.10. Application Entry & Config
* **`main.py`**: Application bootstrap and main lifecycle orchestrator.
* **`config.py`**: Global configuration constants, API endpoints, and market rules.

---

## 4. Key Technologies & Design Patterns
* **Language:** Python 3.10+
* **GUI Framework:** PyQt / PySide
* **Concurrency:** Asynchronous IO / ThreadPool workers for non-blocking I/O and heavy computational math
* **Design Patterns:** Factory Pattern (Strategy Generators), Strategy Pattern (Definitions), Observer/Worker Pattern (UI & Scanner synchronization).
