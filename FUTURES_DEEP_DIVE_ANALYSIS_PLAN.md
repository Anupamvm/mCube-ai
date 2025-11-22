# Futures Trading Deep-Dive Analysis System

## System Architecture Overview

### Workflow Design
```
Level 1 (Automatic) → PASS/FAIL Filter
    ↓ (Only PASSED stocks)
Level 2 (Manual Trigger) → Deep Fundamental & Technical Analysis
    ↓ (Comprehensive Report)
Human Decision → Execute/Reject/Modify Trade
```

## Level 1: Current System (No Changes)
**Purpose:** Initial filtering to identify viable candidates
**Output:** PASS/FAIL with composite score
**Threshold:** Score ≥ 50 and Direction != NEUTRAL

## Level 2: Deep-Dive Analysis System

### Purpose
Provide comprehensive, actionable intelligence on Level 1 PASSED stocks to enable informed trading decisions. This is NOT a filter but a detailed investigation tool.

### Trigger Mechanism

```python
# UI Button appears only for PASSED stocks
if level1_result['verdict'] == 'PASS':
    show_deep_dive_button = True

# When clicked, triggers comprehensive analysis
def trigger_deep_dive(symbol, expiry_date, level1_results):
    deep_dive = Level2DeepDiveAnalyzer(symbol, expiry_date, level1_results)
    report = deep_dive.generate_comprehensive_report()
    return report
```

## Level 2 Deep-Dive Components

### A. FUNDAMENTAL STRENGTH ANALYSIS

#### 1. Financial Performance Deep-Dive
```python
class FinancialPerformanceAnalyzer:
    def analyze(self, stock_data):
        analysis = {
            'profitability': {
                'current_status': {
                    'roe': stock_data.roe_annual_pct,
                    'roe_vs_sector': stock_data.roe_annual_pct - stock_data.sector_return_on_equity_roe,
                    'roe_interpretation': self.interpret_roe(),
                    'roa': stock_data.roa_annual_pct,
                    'roa_vs_sector': stock_data.roa_annual_pct - stock_data.sector_return_on_assets,
                    'operating_margin': stock_data.operating_profit_margin_qtr_pct,
                    'margin_trend': stock_data.operating_profit_margin_qtr_pct - stock_data.operating_profit_margin_qtr_1yr_ago_pct
                },
                'quality_score': self.calculate_quality_score(),
                'red_flags': self.identify_red_flags(),
                'green_flags': self.identify_green_flags(),
                'trader_interpretation': self.generate_trader_view()
            },

            'revenue_analysis': {
                'growth_metrics': {
                    'qtr_yoy': stock_data.revenue_growth_qtr_yoy_pct,
                    'qtr_qoq': stock_data.revenue_qoq_growth_pct,
                    'annual_yoy': stock_data.revenue_growth_annual_yoy_pct,
                    'ttm': stock_data.operating_revenue_ttm
                },
                'relative_performance': {
                    'vs_sector_qtr': stock_data.revenue_growth_qtr_yoy_pct - stock_data.sector_revenue_growth_qtr_yoy_pct,
                    'vs_sector_annual': stock_data.revenue_growth_annual_yoy_pct - stock_data.sector_revenue_growth_annual_yoy_pct
                },
                'consistency': self.check_revenue_consistency(),
                'momentum': 'ACCELERATING' if stock_data.revenue_qoq_growth_pct > 0 else 'DECELERATING'
            },

            'earnings_quality': {
                'profit_growth': {
                    'qtr_yoy': stock_data.net_profit_qtr_growth_yoy_pct,
                    'qtr_qoq': stock_data.net_profit_qoq_growth_pct,
                    'annual_yoy': stock_data.net_profit_annual_yoy_growth_pct
                },
                'vs_sector': {
                    'qtr': stock_data.net_profit_qtr_growth_yoy_pct - stock_data.sector_net_profit_growth_qtr_yoy_pct,
                    'annual': stock_data.net_profit_annual_yoy_growth_pct - stock_data.sector_net_profit_growth_annual_yoy_pct
                },
                'eps_analysis': {
                    'basic_eps_ttm': stock_data.basic_eps_ttm,
                    'eps_growth': stock_data.eps_ttm_growth_pct
                },
                'quality_indicators': self.assess_earnings_quality()
            },

            'cash_flow_analysis': {
                'operating_cash': stock_data.cash_from_operating_activity_annual,
                'investing_cash': stock_data.cash_from_investing_activity_annual,
                'financing_cash': stock_data.cash_from_financing_annual_activity,
                'net_cash_flow': stock_data.net_cash_flow_annual,
                'free_cash_flow': self.calculate_free_cash_flow(),
                'cash_conversion_ratio': self.calculate_cash_conversion(),
                'interpretation': self.interpret_cash_flows()
            },

            'balance_sheet_strength': {
                'piotroski_score': stock_data.piotroski_score,
                'piotroski_interpretation': self.interpret_piotroski(),
                'debt_analysis': self.analyze_debt_levels(),
                'working_capital': self.analyze_working_capital(),
                'asset_efficiency': self.calculate_asset_turnover()
            }
        }

        # Generate actionable summary
        analysis['summary'] = self.generate_fundamental_summary(analysis)
        analysis['risk_factors'] = self.identify_fundamental_risks(analysis)
        analysis['opportunity_factors'] = self.identify_opportunities(analysis)

        return analysis
```

#### 2. Results & Estimates Analysis
```python
class ResultsEstimatesAnalyzer:
    def analyze(self, symbol, forecaster_data):
        # Load all forecaster CSV files
        bullishness = pd.read_csv('tldata/forecaster/trendlyne_High_Bullishness.csv')
        bearishness = pd.read_csv('tldata/forecaster/trendlyne_High_Bearishness.csv')
        beat_revenue_annual = pd.read_csv('tldata/forecaster/trendlyne_Beat_Annual_Revenue_Estimates.csv')
        missed_revenue_annual = pd.read_csv('tldata/forecaster/trendlyne_Missed_Annual_Revenue_Estimates.csv')
        # ... load all 21 files

        analysis = {
            'analyst_sentiment': {
                'bullish_count': self.get_analyst_count(bullishness, symbol),
                'bearish_count': self.get_analyst_count(bearishness, symbol),
                'consensus': self.calculate_consensus(),
                'recent_upgrades': self.check_upgrades(symbol),
                'target_price': self.get_target_price(symbol),
                'upside_potential': self.calculate_upside()
            },

            'earnings_surprise_history': {
                'revenue_beats': {
                    'annual': self.check_in_list(beat_revenue_annual, symbol),
                    'quarterly': self.check_in_list(beat_revenue_qtr, symbol),
                    'beat_margin': self.calculate_beat_margin()
                },
                'revenue_misses': {
                    'annual': self.check_in_list(missed_revenue_annual, symbol),
                    'quarterly': self.check_in_list(missed_revenue_qtr, symbol)
                },
                'eps_beats': self.check_eps_beats(symbol),
                'eps_misses': self.check_eps_misses(symbol),
                'consistency_score': self.calculate_consistency()
            },

            'forward_estimates': {
                'eps_growth': self.get_forward_eps_growth(symbol),
                'revenue_growth': self.get_forward_revenue_growth(symbol),
                'capex_plans': self.get_capex_growth(symbol),
                'dividend_yield': self.get_dividend_yield(symbol)
            },

            'estimate_revisions': {
                'recent_changes': self.track_estimate_changes(symbol),
                'revision_trend': 'UPWARD' if self.positive_revisions() else 'DOWNWARD',
                'confidence_level': self.calculate_estimate_confidence()
            }
        }

        return analysis
```

### B. VALUATION DEEP-DIVE

```python
class ValuationDeepDive:
    def analyze(self, stock_data):
        analysis = {
            'absolute_valuation': {
                'pe_analysis': {
                    'current_pe': stock_data.pe_ttm_price_to_earnings,
                    'forward_pe': stock_data.forecaster_estimates_1y_forward_pe,
                    'pe_to_growth': stock_data.pe_ttm_price_to_earnings / stock_data.eps_ttm_growth_pct if stock_data.eps_ttm_growth_pct > 0 else None,
                    'historical_context': {
                        '3yr_avg': stock_data.pe_3yr_average,
                        '5yr_avg': stock_data.pe_5yr_average,
                        'current_vs_3yr': ((stock_data.pe_ttm_price_to_earnings / stock_data.pe_3yr_average) - 1) * 100,
                        'percentile': stock_data.pctdays_traded_below_current_pe_price_to_earnings,
                        'interpretation': self.interpret_pe_percentile()
                    }
                },

                'peg_analysis': {
                    'current_peg': stock_data.peg_ttm_pe_to_growth,
                    'forward_peg': stock_data.forecaster_estimates_1y_forward_peg,
                    'interpretation': 'UNDERVALUED' if stock_data.peg_ttm_pe_to_growth < 1 else 'OVERVALUED'
                },

                'price_to_book': {
                    'current': stock_data.price_to_book_value,
                    'percentile': stock_data.pctdays_traded_below_current_price_to_book_value,
                    'interpretation': self.interpret_pb_ratio()
                },

                'dcf_estimate': self.estimate_intrinsic_value(stock_data)
            },

            'relative_valuation': {
                'vs_sector': {
                    'pe_premium_discount': ((stock_data.pe_ttm_price_to_earnings / stock_data.sector_pe_ttm) - 1) * 100,
                    'peg_premium_discount': ((stock_data.peg_ttm_pe_to_growth / stock_data.sector_peg_ttm) - 1) * 100,
                    'pb_premium_discount': ((stock_data.price_to_book_value / stock_data.sector_price_to_book_ttm) - 1) * 100,
                    'justified': self.is_premium_justified(stock_data)
                },

                'vs_industry': {
                    'pe_position': stock_data.pe_ttm_price_to_earnings / stock_data.industry_pe_ttm,
                    'peg_position': stock_data.peg_ttm_pe_to_growth / stock_data.industry_peg_ttm,
                    'pb_position': stock_data.price_to_book_value / stock_data.industry_price_to_book_ttm
                },

                'peer_comparison': self.compare_with_peers(stock_data)
            },

            'valuation_summary': {
                'overall_assessment': self.calculate_valuation_score(),
                'key_insights': self.extract_valuation_insights(),
                'risk_reward': self.assess_risk_reward_ratio()
            }
        }

        return analysis
```

### C. INSTITUTIONAL BEHAVIOR ANALYSIS

```python
class InstitutionalBehaviorAnalyzer:
    def analyze(self, stock_data, contract_stock_data):
        analysis = {
            'promoter_analysis': {
                'current_holding': stock_data.promoter_holding_latest_pct,
                'trend_analysis': {
                    'qoq_change': stock_data.promoter_holding_change_qoq_pct,
                    '1yr_change': stock_data.promoter_holding_change_4qtr_pct,
                    '2yr_change': stock_data.promoter_holding_change_8qtr_pct,
                    'trend': self.determine_trend('promoter')
                },
                'pledge_analysis': {
                    'current_pledge': stock_data.promoter_pledge_pct_qtr,
                    'pledge_change': stock_data.promoter_pledge_change_qoq_pct,
                    'risk_level': self.assess_pledge_risk()
                },
                'interpretation': self.interpret_promoter_behavior(),
                'confidence_signal': self.calculate_promoter_confidence()
            },

            'fii_activity': {
                'current_holding': stock_data.fii_holding_current_qtr_pct,
                'flow_analysis': {
                    'qoq': stock_data.fii_holding_change_qoq_pct,
                    '1yr': stock_data.fii_holding_change_4qtr_pct,
                    '2yr': stock_data.fii_holding_change_8qtr_pct,
                    'momentum': self.calculate_fii_momentum()
                },
                'interpretation': self.interpret_fii_behavior(),
                'signal_strength': self.calculate_fii_signal()
            },

            'mutual_fund_activity': {
                'current_holding': stock_data.mf_holding_current_qtr_pct,
                'recent_activity': {
                    '1_month': stock_data.mf_holding_change_1month_pct,
                    '2_month': stock_data.mf_holding_change_2month_pct,
                    '3_month': stock_data.mf_holding_change_3month_pct,
                    'qoq': stock_data.mf_holding_change_qoq_pct
                },
                'trend': self.determine_mf_trend(),
                'accumulation_phase': self.identify_accumulation_distribution()
            },

            'combined_institutional': {
                'total_holding': stock_data.institutional_holding_current_qtr_pct,
                'combined_trend': self.analyze_combined_institutional(),
                'smart_money_signal': self.calculate_smart_money_indicator(),
                'retail_vs_institutional': self.compare_retail_institutional()
            },

            'fo_positioning': {
                'pcr_analysis': {
                    'oi_pcr': contract_stock_data.fno_pcr_oi,
                    'oi_pcr_change': contract_stock_data.fno_pcr_oi_change_pct,
                    'volume_pcr': contract_stock_data.fno_pcr_vol,
                    'volume_pcr_change': contract_stock_data.fno_pcr_vol_change_pct,
                    'interpretation': self.interpret_pcr()
                },
                'open_interest': {
                    'total_oi': contract_stock_data.fno_total_oi,
                    'oi_change': contract_stock_data.fno_total_oi_change_pct,
                    'call_oi_change': contract_stock_data.fno_call_oi_change_pct,
                    'put_oi_change': contract_stock_data.fno_put_oi_change_pct,
                    'buildup': self.identify_oi_buildup()
                },
                'mwpl_analysis': {
                    'current': contract_stock_data.fno_mwpl_pct,
                    'previous': contract_stock_data.fno_mwpl_prev_pct,
                    'risk': 'HIGH' if contract_stock_data.fno_mwpl_pct > 80 else 'NORMAL'
                },
                'rollover': {
                    'cost': contract_stock_data.fno_rollover_cost_pct,
                    'percentage': contract_stock_data.fno_rollover_pct,
                    'interpretation': self.interpret_rollover()
                }
            }
        }

        return analysis
```

### D. TECHNICAL DEEP-DIVE

```python
class TechnicalDeepDive:
    def analyze(self, stock_data, historical_data):
        analysis = {
            'trend_analysis': {
                'primary_trend': self.identify_primary_trend(historical_data),
                'intermediate_trend': self.identify_intermediate_trend(),
                'short_term_trend': self.identify_short_term_trend(),

                'moving_averages': {
                    'sma_analysis': {
                        '5d': stock_data.day5_sma,
                        '30d': stock_data.day30_sma,
                        '50d': stock_data.day50_sma,
                        '100d': stock_data.day100_sma,
                        '200d': stock_data.day200_sma,
                        'alignment': self.check_ma_alignment(),
                        'golden_cross': self.check_golden_cross(),
                        'death_cross': self.check_death_cross()
                    },
                    'ema_analysis': {
                        '12d': stock_data.day12_ema,
                        '20d': stock_data.day20_ema,
                        '50d': stock_data.day50_ema,
                        '100d': stock_data.day100_ema,
                        'ema_stack': self.check_ema_stack()
                    }
                },

                'support_resistance': {
                    'pivot_levels': {
                        'pivot': stock_data.pivot_point,
                        's1': stock_data.first_support_s1,
                        's2': stock_data.second_support_s2,
                        's3': stock_data.third_support_s3,
                        'r1': stock_data.first_resistance_r1,
                        'r2': stock_data.second_resistance_r2,
                        'r3': stock_data.third_resistance_r3
                    },
                    'distance_analysis': {
                        'to_s1': stock_data.first_support_s1_to_price_diff_pct,
                        'to_r1': stock_data.first_resistance_r1_to_price_diff_pct,
                        'position': self.determine_price_position()
                    },
                    'historical_levels': self.calculate_historical_sr(historical_data),
                    'volume_profile': self.analyze_volume_profile()
                }
            },

            'momentum_indicators': {
                'rsi': {
                    'value': stock_data.day_rsi,
                    'zone': 'OVERBOUGHT' if stock_data.day_rsi > 70 else 'OVERSOLD' if stock_data.day_rsi < 30 else 'NEUTRAL',
                    'divergence': self.check_rsi_divergence()
                },
                'macd': {
                    'macd': stock_data.day_macd,
                    'signal': stock_data.day_macd_signal_line,
                    'histogram': stock_data.day_macd - stock_data.day_macd_signal_line,
                    'crossover': self.check_macd_crossover()
                },
                'mfi': {
                    'value': stock_data.day_mfi,
                    'interpretation': self.interpret_mfi()
                },
                'adx': {
                    'value': stock_data.day_adx,
                    'trend_strength': 'STRONG' if stock_data.day_adx > 25 else 'WEAK'
                },
                'roc': {
                    '21_day': stock_data.day_roc21,
                    '125_day': stock_data.day_roc125,
                    'momentum': self.interpret_roc()
                }
            },

            'volatility_analysis': {
                'atr': stock_data.day_atr,
                'annualized': stock_data.annualized_volatility if hasattr(stock_data, 'annualized_volatility') else None,
                'beta_analysis': {
                    '1m': stock_data.beta_1month,
                    '3m': stock_data.beta_3month,
                    '1y': stock_data.beta_1year,
                    '3y': stock_data.beta_3year,
                    'stability': self.assess_beta_stability()
                },
                'volatility_regime': self.identify_volatility_regime()
            },

            'price_action': {
                'ranges': {
                    'day': {'low': stock_data.day_low, 'high': stock_data.day_high, 'change': stock_data.day_change_pct},
                    'week': {'low': stock_data.week_low, 'high': stock_data.week_high, 'change': stock_data.week_change_pct},
                    'month': {'low': stock_data.month_low, 'high': stock_data.month_high, 'change': stock_data.month_change_pct},
                    'quarter': {'low': stock_data.qtr_low, 'high': stock_data.qtr_high, 'change': stock_data.qtr_change_pct},
                    'year': {'low': stock_data.one_year_low, 'high': stock_data.one_year_high, 'change': stock_data.one_year_change_pct}
                },
                'position_in_range': self.calculate_position_in_ranges(),
                'breakout_analysis': self.check_for_breakouts(),
                'pattern_recognition': self.identify_chart_patterns()
            },

            'volume_analysis': {
                'current_volume': stock_data.day_volume,
                'relative_volume': {
                    'vs_week_avg': stock_data.day_volume / stock_data.week_volume_avg if stock_data.week_volume_avg else 0,
                    'vs_month_avg': stock_data.day_volume / stock_data.month_volume_avg if stock_data.month_volume_avg else 0,
                    'volume_surge': stock_data.day_volume_multiple_of_week
                },
                'delivery_analysis': {
                    'delivery_pct': stock_data.delivery_volume_pct_eod,
                    'prev_delivery': stock_data.delivery_volume_pct_prev_eod,
                    'avg_delivery': stock_data.delivery_volume_avg_month,
                    'interpretation': self.interpret_delivery_data()
                },
                'vwap': {
                    'current': stock_data.vwap_day,
                    'position': 'ABOVE' if stock_data.current_price > stock_data.vwap_day else 'BELOW'
                }
            }
        }

        return analysis
```

### E. RISK ASSESSMENT

```python
class RiskAssessment:
    def analyze(self, stock_data, all_analysis):
        risk_analysis = {
            'market_risk': {
                'beta_risk': self.assess_beta_risk(stock_data),
                'volatility_risk': self.assess_volatility_risk(stock_data),
                'liquidity_risk': self.assess_liquidity_risk(stock_data),
                'correlation_risk': self.assess_correlation_risk()
            },

            'fundamental_risks': {
                'valuation_risk': self.assess_valuation_risk(all_analysis['valuation']),
                'earnings_risk': self.assess_earnings_volatility(stock_data),
                'debt_risk': self.assess_debt_levels(stock_data),
                'sector_risk': self.assess_sector_headwinds()
            },

            'technical_risks': {
                'overbought_risk': self.check_overbought_conditions(all_analysis['technical']),
                'support_breach_risk': self.calculate_support_breach_probability(),
                'trend_reversal_risk': self.assess_reversal_probability(),
                'volume_divergence_risk': self.check_volume_divergence()
            },

            'event_risks': {
                'earnings_date': self.get_next_earnings_date(),
                'corporate_actions': self.check_upcoming_events(),
                'regulatory_risks': self.assess_regulatory_environment(),
                'global_factors': self.assess_global_risks()
            },

            'position_sizing_recommendation': {
                'risk_score': self.calculate_overall_risk_score(),
                'max_position_size': self.recommend_position_size(),
                'stop_loss_levels': self.calculate_stop_losses(),
                'risk_reward_ratio': self.calculate_risk_reward()
            }
        }

        return risk_analysis
```

### F. COMPREHENSIVE REPORT GENERATOR

```python
class Level2ReportGenerator:
    def __init__(self, symbol, expiry, level1_results):
        self.symbol = symbol
        self.expiry = expiry
        self.level1_results = level1_results

    def generate_report(self):
        # Gather all data
        stock_data = TLStockData.objects.get(nsecode=self.symbol)
        contract_stock = ContractStockData.objects.get(nse_code=self.symbol)

        # Run all analyses
        fundamental = FinancialPerformanceAnalyzer().analyze(stock_data)
        valuation = ValuationDeepDive().analyze(stock_data)
        institutional = InstitutionalBehaviorAnalyzer().analyze(stock_data, contract_stock)
        technical = TechnicalDeepDive().analyze(stock_data, self.get_historical_data())
        risk = RiskAssessment().analyze(stock_data, {
            'fundamental': fundamental,
            'valuation': valuation,
            'technical': technical
        })

        # Generate comprehensive report
        report = {
            'metadata': {
                'symbol': self.symbol,
                'expiry': self.expiry,
                'analysis_timestamp': datetime.now(),
                'level1_score': self.level1_results['composite_score'],
                'level1_direction': self.level1_results['direction']
            },

            'executive_summary': self.generate_executive_summary(fundamental, valuation, institutional, technical, risk),

            'detailed_analysis': {
                'fundamental_analysis': fundamental,
                'valuation_analysis': valuation,
                'institutional_behavior': institutional,
                'technical_analysis': technical,
                'risk_assessment': risk
            },

            'trading_recommendation': {
                'conviction_level': self.calculate_conviction_score(),
                'entry_strategy': self.recommend_entry_strategy(),
                'position_sizing': self.recommend_position_size(risk),
                'stop_loss': self.calculate_stop_loss_levels(),
                'profit_targets': self.calculate_profit_targets(),
                'time_horizon': self.recommend_holding_period(),
                'key_monitorables': self.identify_key_monitorables()
            },

            'decision_matrix': {
                'bullish_factors': self.compile_bullish_factors(),
                'bearish_factors': self.compile_bearish_factors(),
                'key_risks': self.identify_key_risks(),
                'catalysts': self.identify_potential_catalysts()
            },

            'visual_summary': self.generate_visual_summary()
        }

        return report

    def generate_executive_summary(self, fundamental, valuation, institutional, technical, risk):
        return {
            'one_line_verdict': self.create_verdict(),
            'conviction_score': self.calculate_overall_conviction(),
            'key_strengths': self.identify_top_strengths(),
            'key_concerns': self.identify_top_concerns(),
            'recommended_action': self.recommend_action(),
            'critical_levels': self.identify_critical_levels()
        }
```

## UI Integration for Deep-Dive

### 1. Frontend Components

```javascript
// Level 1 Results Component with Deep-Dive Trigger
const Level1Results = ({ data }) => {
    const [showDeepDive, setShowDeepDive] = useState(false);
    const [deepDiveData, setDeepDiveData] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleDeepDive = async () => {
        setLoading(true);
        const response = await api.post('/api/futures/deep-dive', {
            symbol: data.symbol,
            expiry: data.expiry,
            level1_results: data
        });
        setDeepDiveData(response.data);
        setShowDeepDive(true);
        setLoading(false);
    };

    return (
        <div className="level1-results">
            <div className="verdict-section">
                <h3>Level 1 Analysis: {data.verdict}</h3>
                <p>Score: {data.composite_score}/100</p>
                <p>Direction: {data.direction}</p>

                {data.verdict === 'PASS' && (
                    <button
                        onClick={handleDeepDive}
                        className="deep-dive-btn"
                        disabled={loading}
                    >
                        {loading ? 'Analyzing...' : 'Perform Deep-Dive Analysis'}
                    </button>
                )}
            </div>

            {showDeepDive && deepDiveData && (
                <DeepDiveReport data={deepDiveData} />
            )}
        </div>
    );
};

// Deep-Dive Report Component
const DeepDiveReport = ({ data }) => {
    const [activeTab, setActiveTab] = useState('summary');

    return (
        <div className="deep-dive-report">
            <div className="report-header">
                <h2>Deep-Dive Analysis Report</h2>
                <p>Generated: {data.metadata.analysis_timestamp}</p>
            </div>

            <div className="executive-summary">
                <h3>{data.executive_summary.one_line_verdict}</h3>
                <div className="conviction-meter">
                    <ConvictionMeter score={data.executive_summary.conviction_score} />
                </div>

                <div className="summary-grid">
                    <div className="strengths">
                        <h4>Key Strengths</h4>
                        <ul>
                            {data.executive_summary.key_strengths.map(s => (
                                <li key={s}>{s}</li>
                            ))}
                        </ul>
                    </div>

                    <div className="concerns">
                        <h4>Key Concerns</h4>
                        <ul>
                            {data.executive_summary.key_concerns.map(c => (
                                <li key={c}>{c}</li>
                            ))}
                        </ul>
                    </div>
                </div>
            </div>

            <div className="report-tabs">
                <button onClick={() => setActiveTab('fundamental')}>Fundamental</button>
                <button onClick={() => setActiveTab('valuation')}>Valuation</button>
                <button onClick={() => setActiveTab('institutional')}>Institutional</button>
                <button onClick={() => setActiveTab('technical')}>Technical</button>
                <button onClick={() => setActiveTab('risk')}>Risk</button>
                <button onClick={() => setActiveTab('recommendation')}>Recommendation</button>
            </div>

            <div className="tab-content">
                {activeTab === 'fundamental' && <FundamentalTab data={data.detailed_analysis.fundamental_analysis} />}
                {activeTab === 'valuation' && <ValuationTab data={data.detailed_analysis.valuation_analysis} />}
                {/* ... other tabs ... */}
            </div>

            <div className="action-section">
                <h3>Recommended Action</h3>
                <div className="recommendation-card">
                    <p>{data.trading_recommendation.entry_strategy}</p>
                    <div className="levels">
                        <span>Entry: {data.trading_recommendation.entry_level}</span>
                        <span>Stop: {data.trading_recommendation.stop_loss}</span>
                        <span>Target: {data.trading_recommendation.profit_targets[0]}</span>
                    </div>
                </div>

                <div className="action-buttons">
                    <button className="execute-btn">Execute Trade</button>
                    <button className="modify-btn">Modify Parameters</button>
                    <button className="reject-btn">Reject</button>
                    <button className="save-btn">Save Analysis</button>
                </div>
            </div>
        </div>
    );
};
```

### 2. API Implementation

```python
# views.py
from rest_framework.views import APIView
from rest_framework.response import Response

class FuturesDeepDiveView(APIView):
    def post(self, request):
        symbol = request.data.get('symbol')
        expiry = request.data.get('expiry')
        level1_results = request.data.get('level1_results')

        # Verify Level 1 passed
        if level1_results.get('verdict') != 'PASS':
            return Response({
                'error': 'Deep-dive analysis only available for PASS verdicts'
            }, status=400)

        # Generate deep-dive report
        report_generator = Level2ReportGenerator(symbol, expiry, level1_results)
        report = report_generator.generate_report()

        # Save to database for audit
        DeepDiveAnalysis.objects.create(
            symbol=symbol,
            expiry=expiry,
            level1_score=level1_results['composite_score'],
            report=report,
            user=request.user,
            created_at=timezone.now()
        )

        return Response(report)

# urls.py
urlpatterns = [
    path('api/futures/analyze/', FuturesAnalysisView.as_view()),  # Level 1
    path('api/futures/deep-dive/', FuturesDeepDiveView.as_view()),  # Level 2
]
```

## Data Models for Deep-Dive

```python
# models.py
class DeepDiveAnalysis(models.Model):
    """Store deep-dive analysis reports"""
    symbol = models.CharField(max_length=50)
    expiry = models.DateField()
    level1_score = models.IntegerField()
    report = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    # User decision tracking
    decision = models.CharField(
        max_length=20,
        choices=[
            ('EXECUTED', 'Executed'),
            ('MODIFIED', 'Modified'),
            ('REJECTED', 'Rejected'),
            ('PENDING', 'Pending')
        ],
        default='PENDING'
    )
    decision_notes = models.TextField(blank=True)
    decision_timestamp = models.DateTimeField(null=True)

    # Actual trade tracking
    trade_executed = models.BooleanField(default=False)
    entry_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    exit_price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    pnl = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['symbol', 'expiry']),
            models.Index(fields=['user', '-created_at']),
        ]
```

## Performance Tracking

```python
class DeepDivePerformanceTracker:
    """Track the effectiveness of deep-dive analysis"""

    def track_decision(self, analysis_id, decision, notes=''):
        """Track user decision on deep-dive analysis"""
        analysis = DeepDiveAnalysis.objects.get(id=analysis_id)
        analysis.decision = decision
        analysis.decision_notes = notes
        analysis.decision_timestamp = timezone.now()
        analysis.save()

    def track_trade_outcome(self, analysis_id, entry_price, exit_price):
        """Track actual trade results"""
        analysis = DeepDiveAnalysis.objects.get(id=analysis_id)
        analysis.trade_executed = True
        analysis.entry_price = entry_price
        analysis.exit_price = exit_price
        analysis.pnl = ((exit_price - entry_price) / entry_price) * 100
        analysis.save()

    def calculate_effectiveness(self):
        """Calculate how effective deep-dive recommendations are"""
        executed_trades = DeepDiveAnalysis.objects.filter(
            trade_executed=True,
            pnl__isnull=False
        )

        metrics = {
            'total_analyses': DeepDiveAnalysis.objects.count(),
            'executed_trades': executed_trades.count(),
            'execution_rate': executed_trades.count() / DeepDiveAnalysis.objects.count(),
            'win_rate': executed_trades.filter(pnl__gt=0).count() / executed_trades.count(),
            'avg_profit': executed_trades.filter(pnl__gt=0).aggregate(Avg('pnl'))['pnl__avg'],
            'avg_loss': executed_trades.filter(pnl__lt=0).aggregate(Avg('pnl'))['pnl__avg'],
            'total_pnl': executed_trades.aggregate(Sum('pnl'))['pnl__sum']
        }

        return metrics
```

## Summary

This redesigned system maintains Level 1 as a pure filter and adds Level 2 as a comprehensive deep-dive analysis tool that:

1. **Only runs on PASSED stocks** from Level 1
2. **Provides exhaustive analysis** using ALL available Trendlyne data fields
3. **Generates actionable reports** with clear recommendations
4. **Allows human judgment** before trade execution
5. **Tracks decisions and outcomes** for continuous improvement

The deep-dive covers:
- Complete fundamental analysis
- Comprehensive valuation metrics
- Institutional behavior patterns
- Advanced technical indicators
- Multi-dimensional risk assessment
- Clear trading recommendations

The system presents all this information in a digestible format, allowing you to make informed decisions based on comprehensive data analysis rather than automated filtering.