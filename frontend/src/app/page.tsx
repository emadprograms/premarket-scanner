"use client";

import React, { useState, useEffect, useRef } from 'react';
import { Card, Button, Badge } from '@/components/ui/core';
import { Modal } from '@/components/ui/Modal';
import { CustomChartModal } from '@/components/ui/CustomChartModal';
import {
  Search,
  Play,
  Terminal as TerminalIcon,
  Globe,
  BarChart3,
  Zap,
  AlertTriangle,
  History,
  Activity,
  TrendingUp,
  TrendingDown,
  Brain,
  Layers,
  Target,
  Trophy,
  ArrowRight,
  ChevronRight,
  RefreshCw,
  Clock,
  HelpCircle
} from 'lucide-react';
import { socketService } from '@/lib/socket';
import { runMacroAnalysis, runSelectionScan, runRankingSynthesis, getWatchlistStatus } from '@/lib/api';
import { useMission } from '@/lib/context';
import { MissionControl } from '@/components/layout/MissionControl';

const Tooltip = ({ text }: { text: string }) => (
  <div className="group relative ml-1.5 inline-block">
    <HelpCircle className="w-3 h-3 text-muted-foreground/50 cursor-help hover:text-primary transition-colors" />
    <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-zinc-900 border border-primary/20 rounded shadow-2xl opacity-0 group-hover:opacity-100 pointer-events-none transition-all z-50 text-[10px] text-zinc-300 font-medium leading-relaxed normal-case">
      {text}
      <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-zinc-900" />
    </div>
  </div>
);

export default function UnifiedCommandPage() {
  const { settings } = useMission();
  const [news, setNews] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [currentStep, setCurrentStep] = useState<string | null>(null);
  const [logs, setLogs] = useState<any[]>([]);

  // Analysis Results
  const [economyCard, setEconomyCard] = useState<any>(null);
  const [proximityResults, setProximityResults] = useState<any[]>([]);
  const [marketData, setMarketData] = useState<any[]>([]);
  const [marketCards, setMarketCards] = useState<Record<string, any>>({}); // Promoted to state
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null); // For Modal
  const [chartTicker, setChartTicker] = useState<string | null>(null); // For Chart Modal
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [activeAlert, setActiveAlert] = useState<any>(null);
  const [cardCoverage, setCardCoverage] = useState<any[]>([]);

  // Company Selector
  const [watchlistStatus, setWatchlistStatus] = useState<any[]>([]);
  const [refreshTickers, setRefreshTickers] = useState<string[]>([]);

  // Gap Guard State
  const [showGapModal, setShowGapModal] = useState(false);
  const [gapWarnings, setGapWarnings] = useState<string[]>([]);
  const [pendingMacroParams, setPendingMacroParams] = useState<any>(null);

  const logsEndRef = useRef<HTMLDivElement>(null);

  // Auto-clear alert after 8 seconds
  useEffect(() => {
    if (activeAlert) {
      const timer = setTimeout(() => setActiveAlert(null), 8000);
      return () => clearTimeout(timer);
    }
  }, [activeAlert]);

  useEffect(() => {
    socketService.onLog((log) => {
      setLogs((prev) => [...prev, log].slice(-50));
    });
    // Fetch watchlist status on mount
    getWatchlistStatus().then(res => {
      if (res.status === 'success') setWatchlistStatus(res.data);
    }).catch(() => { });
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleRunFullMission = async () => {
    setIsRunning(true);
    setLogs([]);
    setEconomyCard(null);
    setProximityResults([]);
    setMarketData([]);
    setRecommendations([]);
    setCardCoverage([]);

    try {
      // STEP 1: Macro Context
      setCurrentStep("Macro Synthesis");

      const macroParams = {
        model_name: settings.model_name,
        benchmark_date: settings.benchmark_date,
        simulation_cutoff: settings.simulation_cutoff,
        news_text: news,
        mode: settings.mode,
        db_fallback: settings.db_fallback,
        force_execution: settings.force_economy_refresh
      };

      const macroRes = await runMacroAnalysis(macroParams);

      if (macroRes.status === "warning") {
        setPendingMacroParams(macroParams);
        setGapWarnings(macroRes.data.warnings || ["Unspecified Data Gap"]);
        setShowGapModal(true);
        setIsRunning(false);
        return; // HALT
      }

      let macroData = null;
      if (macroRes.status === "success") {
        setEconomyCard(macroRes.data);
        macroData = macroRes.data;
        await runPostMacroSteps(macroData);
      }
    } catch (err) {
      console.error(err);
      setIsRunning(false);
    }
  };

  const handleProceedAnyway = async () => {
    setShowGapModal(false);
    setGapWarnings([]);
    if (!pendingMacroParams) return;

    setIsRunning(true);

    // CASE 1: Resuming Ranking (DECOMMISSIONED)
    if (pendingMacroParams.step === "Ranking") {
      setLogs(prev => [...prev, {
        timestamp: new Date().toLocaleTimeString(),
        level: 'INFO',
        icon: 'ℹ️',
        message: "Ranking analysis skipped per mission parameters."
      }]);
      setIsRunning(false);
      setPendingMacroParams(null);
      return;
    }

    // CASE 2: Resuming Macro (from Gap Guard in Step 1)
    setCurrentStep("Forced Synthesis");
    try {
      const forceParams = { ...pendingMacroParams, force_execution: true };
      const macroRes = await runMacroAnalysis(forceParams);

      if (macroRes.status === "success" || macroRes.data) {
        setEconomyCard(macroRes.data);
        await runPostMacroSteps(macroRes.data);
      }
    } catch (err) {
      console.error(err);
      setIsRunning(false);
    }
  };
  ;

  const runPostMacroSteps = async (macroData: any) => {
    try {
      // STEP 2: Selection Hub (Scanner) — pass refresh_tickers
      setCurrentStep("Structural Scanning");
      const scanRes = await runSelectionScan({
        benchmark_date: settings.benchmark_date,
        simulation_cutoff: settings.simulation_cutoff,
        threshold: settings.proximity_threshold,
        mode: settings.mode,
        db_fallback: settings.db_fallback,
        refresh_tickers: refreshTickers,
        plan_only: settings.plan_only_proximity
      });

      let selectedTickers: string[] = [];
      let marketCardsMap: Record<string, any> = {};
      if (scanRes.status === "success") {
        // New response shape: { results, card_coverage, summary }
        const scanData = scanRes.data;
        const results = scanData.results || scanData; // fallback for flat array
        const coverage = scanData.card_coverage || [];

        // --- GAP GUARD & PLAN VALIDATION ---
        const warnings: string[] = [];

        // 1. Check for missing plan data (Strict Mode Only)
        if (settings.plan_only_proximity) {
          const missingPlans = results.filter((r: any) => r.missing_plan);
          if (missingPlans.length > 0) {
            warnings.push(`⚠️ ${missingPlans.length} tickers are missing Plan A/B levels (required for strict mode).`);
            missingPlans.forEach((r: any) => {
              warnings.push(`   - ${r.ticker}: No Plan A/B found`);
            });
          }
        }

        // 2. Check for missing data (Original Gap Guard)
        const missingData = results.filter((r: any) => r.missing_data || r.failed_analysis);
        if (missingData.length > 0) {
          warnings.push(`⚠️ ${missingData.length} tickers failed live data fetch.`);
        }

        if (warnings.length > 0) {
          setGapWarnings(warnings);
          setShowGapModal(true);
          // We STOP here. The user must click "Proceed Anyway" in the modal to continue.
          // But we need to save the state so they *can* proceed.
          // Actually, for Scanner step, we just show results. The "Proceed" usually refers to the NEXT step (Ranking).
          // But if the user wants to "cancel", they can just fix it.
          // Let's populate the results anyway so they can see what happened, but show the modal.
        }

        const alerts = results.filter((r: any) => r.prox_alert).map((r: any) => r.prox_alert);
        const rows = results.map((r: any) => r.table_row).filter(Boolean);
        setProximityResults(alerts);
        setMarketData(rows);
        setCardCoverage(coverage);

        // Build market_cards map: ticker -> card object (for ranking engine)
        const cardsMap: Record<string, any> = {};
        results.forEach((r: any) => {
          if (r.ticker && r.card) {
            cardsMap[r.ticker] = r.card;
          }
        });
        setMarketCards(cardsMap); // Save to state
        marketCardsMap = cardsMap; // Keep local ref for immediate ranking usage

        if (alerts.length > 0) {
          setActiveAlert({
            count: alerts.length,
            tickers: alerts.map((a: any) => a.Ticker).slice(0, 3).join(", ") + (alerts.length > 3 ? "..." : "")
          });
        }

        // Use proximity alert tickers for ranking; fall back to all valid results if none
        selectedTickers = alerts.length > 0
          ? alerts.map((a: any) => a.Ticker)
          : results.filter((r: any) => r.card && !r.failed_analysis).map((r: any) => r.ticker).slice(0, 10);

        // GAP GUARD HALT: If warnings exist, STOP here.
        // We save the "pending" state so the user can Click "Proceed" in the modal to continue.
        // The GapModal onProceed should trigger runRankingSynthesis or similar?
        if (warnings.length > 0) {
          setPendingMacroParams({
            step: "Ranking",
            data: {
              selectedTickers,
              macroData,
              marketCardsMap
            }
          });
          setIsRunning(false); // Pause spinner
          return; // STOP execution
        }
      }

      // SCAN COMPLETE - Workflow Ends Here
      setLogs(prev => [...prev, {
        timestamp: new Date().toLocaleTimeString(),
        level: 'SUCCESS',
        icon: '✅',
        message: "Structural Scanning Complete. Results populated in Tape."
      }]);
    } catch (err) {
      console.error("Scanner fail:", err);
    } finally {
      setIsRunning(false);
      setCurrentStep(null);
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto relative">
      {/* Floating Alert Notification */}
      {activeAlert && (
        <div className="fixed top-8 left-1/2 -translate-x-1/2 z-[100] animate-in fade-in slide-in-from-top-8 duration-500">
          <div className="bg-primary border border-white/20 shadow-2xl shadow-primary/40 rounded-2xl px-8 py-4 flex items-center gap-6 backdrop-blur-xl">
            <div className="bg-white/20 p-2 rounded-full animate-pulse">
              <AlertTriangle className="w-6 h-6 text-white" />
            </div>
            <div>
              <h4 className="text-white font-black text-lg leading-none">PROXIMITY THRESHOLD HIT</h4>
              <p className="text-white/80 text-sm mt-1 font-bold">
                {activeAlert.count} tickers detected: <span className="text-white underline">{activeAlert.tickers}</span>
              </p>
            </div>
            <Button
              variant="outline"
              className="h-10 border-white/20 bg-white/10 text-white hover:bg-white/20 text-xs font-bold px-4 rounded-xl"
              onClick={() => setActiveAlert(null)}
            >
              DISMISS
            </Button>
          </div>
        </div>
      )}

      {/* Gap Guard Modal */}
      <Modal
        isOpen={showGapModal}
        onClose={() => setShowGapModal(false)}
        title="Data Quality Guard"
        variant="warning"
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowGapModal(false)}>Cancel Mission</Button>
            <Button variant="primary" onClick={handleProceedAnyway} className="bg-yellow-500 text-black hover:bg-yellow-400">
              Proceed Anyway
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <p className="text-sm text-foreground/80">
            The Pre-Market Scanner detected potential issues that may affect the quality of the narrative generation.
          </p>
          <div className="bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-4 space-y-2">
            {gapWarnings.map((w, i) => (
              <div key={i} className="flex items-start gap-2 text-sm text-yellow-500">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{w}</span>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground italic">
            Proceeding may result in a "hallucinated" or generic economy card if no live data is available to ground the analysis.
          </p>
        </div>
      </Modal>

      <MissionControl />

      {/* Company Selector Panel */}
      {watchlistStatus.length > 0 && (
        <div className="animate-in fade-in duration-500">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <h3 className="text-sm font-bold uppercase tracking-widest text-foreground/80">Company Refresh Queue</h3>
              <Tooltip text="Select specific tickers to force a fresh data fetch from Capital.com. Unselected tickers will use cached/EOD data from the database to save time." />
              <span className="text-[10px] font-mono text-muted-foreground ml-2">({refreshTickers.length} selected for live fetch)</span>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setRefreshTickers(watchlistStatus.map((w: any) => w.ticker))}
                className="text-[10px] font-bold text-primary hover:text-primary/80 uppercase tracking-wider transition-colors"
              >
                Select All
              </button>
              <span className="text-muted-foreground text-[10px]">|</span>
              <button
                onClick={() => setRefreshTickers([])}
                className="text-[10px] font-bold text-muted-foreground hover:text-foreground uppercase tracking-wider transition-colors"
              >
                Clear
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {watchlistStatus.map((w: any) => {
              const isSelected = refreshTickers.includes(w.ticker);
              const isLiveCard = w.status === 'LIVE';
              return (
                <button
                  key={w.ticker}
                  onClick={() => setRefreshTickers(prev =>
                    prev.includes(w.ticker) ? prev.filter(t => t !== w.ticker) : [...prev, w.ticker]
                  )}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold transition-all duration-200 ${isSelected
                    ? 'bg-primary text-background border-primary shadow-lg shadow-primary/20 scale-105'
                    : 'bg-muted/40 text-foreground/70 border-border/50 hover:border-primary/40 hover:text-foreground'
                    }`}
                >
                  <span>{w.ticker}</span>
                  <span className={`text-[8px] font-black px-1 py-0.5 rounded ${isSelected ? 'bg-white/20 text-white' :
                    isLiveCard ? 'bg-emerald-500/20 text-emerald-400' : 'bg-muted text-muted-foreground'
                    }`}>
                    {isLiveCard ? 'LIVE' : 'EOD'}
                  </span>
                  {!isSelected && (
                    <span className="text-[8px] text-muted-foreground font-mono">{w.latest}</span>
                  )}
                </button>
              );
            })}
          </div>
          {refreshTickers.length === 0 && (
            <p className="text-[10px] text-muted-foreground mt-2 italic">
              No companies selected — scan will use DB cards for all 19. Select companies above to trigger a live API fetch.
            </p>
          )}
        </div>
      )}


      {/* Header Section */}
      <div className="flex justify-between items-center bg-background sticky top-0 z-50 h-16 border-b border-border shadow-md -mx-8 px-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-primary">Pre-Market Scanner</h1>
          <p className="text-muted-foreground mt-0.5 text-xs uppercase tracking-widest font-bold">Structural Context & Selection Engine</p>
        </div>
        <div className="flex gap-4">
          <Button
            variant="primary"
            className="gap-2 px-6 h-10 text-sm shadow-xl shadow-primary/20 bg-gradient-to-r from-primary to-emerald-600 border-0"
            onClick={handleRunFullMission}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <Zap className="w-5 h-5 animate-spin" />
                {currentStep?.toUpperCase()}...
              </>
            ) : (
              <>
                <Search className="w-6 h-6" />
                ENGAGE STRATEGIC SCAN
              </>
            )}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-8">
        {/* Left Profile: Input & Live Console */}
        <div className="col-span-12 lg:col-span-3 space-y-8">
          <Card className="flex flex-col gap-4 border-primary/10">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-sm font-bold flex items-center gap-2 whitespace-nowrap">
                <Globe className="w-4 h-4 text-primary" /> Global Narrative
              </h3>
              <Badge variant="info" className="text-[9px] px-1.5 py-0.5 whitespace-nowrap">Context Inputs</Badge>
            </div>
            <div className="relative group">
              {!settings.force_economy_refresh && (
                <div className="absolute inset-0 bg-zinc-950/80 backdrop-blur-[1px] z-10 rounded-xl flex flex-col items-center justify-center p-6 text-center cursor-not-allowed border border-white/5">
                  <div className="bg-primary/5 p-3 rounded-full mb-4 border border-primary/10">
                    <Globe className="w-6 h-6 text-primary/40" />
                  </div>
                  <h4 className="text-sm font-bold text-foreground/90 mb-1">Narrative input disabled</h4>
                  <p className="text-xs text-muted-foreground max-w-[240px] leading-relaxed">
                    Set <span className="text-primary font-bold">Live Economy Card</span> to <span className="text-primary font-bold">ON</span> in Scanner Control to input custom overnight data.
                  </p>
                </div>
              )}
              <textarea
                value={news}
                onChange={(e) => setNews(e.target.value)}
                disabled={!settings.force_economy_refresh}
                placeholder="Paste overnight headlines, catalysts, or market move summaries..."
                className={`w-full h-64 border border-border rounded-xl p-4 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all resize-none terminal-scroll ${!settings.force_economy_refresh ? 'bg-zinc-900/40 opacity-30 grayscale cursor-not-allowed' : 'bg-muted/20'}`}
              />
            </div>
          </Card>

          <Card className="flex flex-col h-[500px] border-primary/20 shadow-inner bg-black/20">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold flex items-center gap-2 text-primary">
                <TerminalIcon className="w-4 h-4" /> Operational Console
              </h3>
              <div className="flex gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/30" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/30" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-500/30" />
              </div>
            </div>
            <div className="flex-1 bg-black/40 rounded-lg p-4 font-mono text-xs overflow-y-auto terminal-scroll space-y-2 border border-white/5">
              {logs.length === 0 ? (
                <p className="text-muted-foreground italic">Awaiting scanner parameters. Engage synthesis engine to begin.</p>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="flex gap-3 border-l-2 border-primary/20 pl-3">
                    <span className="text-muted-foreground opacity-50">[{log.timestamp}]</span>
                    <span className={log.level === 'ERROR' ? 'text-destructive font-bold' : log.level === 'SUCCESS' ? 'text-emerald-400' : 'text-foreground'}>
                      {log.icon} {log.message}
                    </span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </Card>

          {/* Card Coverage Report — Moved to Left Column */}
          {cardCoverage.length > 0 && (
            <div className="space-y-4 pt-4 border-t border-border/50">
              <div className="flex items-center justify-between px-2">
                <h3 className="font-bold text-base flex items-center gap-3">
                  <BarChart3 className="w-4 h-4 text-primary" /> Coverage Report
                </h3>
              </div>
              <p className="text-[10px] font-mono text-muted-foreground px-2">
                {cardCoverage.filter((c: any) => c.source === 'LIVE_CARD').length} LIVE | {cardCoverage.filter((c: any) => c.source?.includes('DB') || c.source?.includes('EOD')).length} DB | {cardCoverage.reduce((sum: number, c: any) => sum + (c.migration_blocks || 0), 0)} BLOCKS
              </p>
              <Card className="p-0 overflow-hidden border-border/50">
                <div className="overflow-x-auto terminal-scroll max-h-[400px]">
                  <table className="w-full text-sm text-left">
                    <thead className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest bg-muted/40 sticky top-0 z-20 backdrop-blur-md">
                      <tr>
                        <th className="px-3 py-2">Ticker</th>
                        <th className="px-3 py-2">Stat</th>
                        <th className="px-3 py-2">Mig</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50">
                      {cardCoverage.map((row: any) => {
                        const isLiveCard = row.source === 'LIVE_CARD';
                        const isEod = row.source?.includes('EOD') || row.source?.includes('DB');
                        return (
                          <tr key={row.ticker} className="hover:bg-primary/5 transition-colors">
                            <td className="px-3 py-2 font-black text-xs">{row.ticker}</td>
                            <td className="px-3 py-2">
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-black uppercase ${isLiveCard ? 'bg-primary/10 text-primary' : isEod ? 'bg-muted text-muted-foreground' : 'bg-destructive/10 text-destructive'}`}>
                                {isLiveCard ? 'LIVE' : isEod ? 'DB' : 'MISS'}
                              </span>
                            </td>
                            <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                              {row.migration_blocks > 0 ? <span className="text-primary font-bold">{row.migration_blocks}</span> : '-'}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}
        </div>

        {/* Right Dashboard: Unified Results */}
        <div className="col-span-12 lg:col-span-9 space-y-8">
          {!economyCard && recommendations.length === 0 && !isRunning && (
            <div className="h-full flex flex-col items-center justify-center text-center p-20 border-2 border-dashed border-border rounded-3xl bg-muted/5">
              <div className="bg-primary/10 p-8 rounded-full mb-8 text-primary">
                <Search className="w-16 h-16" />
              </div>
              <h2 className="text-3xl font-bold mb-4 tracking-tight">Scanner Dashboard Idle</h2>
              <p className="text-muted-foreground max-w-sm text-lg leading-relaxed">
                Configure your strategic parameters and Headlines, then trigger the synthesis engine to generate context and rankings.
              </p>
            </div>
          )}

          {/* Step 1: Market Narrative Card */}
          {economyCard && (
            <Card className="relative overflow-hidden group border-primary/20 animate-in fade-in slide-in-from-right-4 duration-500">
              <div className="mb-6 flex justify-between items-start relative z-10">
                <div>
                  <Badge variant={economyCard.marketBias.includes('Bull') ? 'success' : economyCard.marketBias.includes('Bear') ? 'error' : 'warning'} className="mb-3 px-3 py-1">
                    STRATEGIC BIAS: {economyCard.marketBias.toUpperCase()}
                  </Badge>
                  <h2 className="text-base font-semibold leading-relaxed text-foreground/90 italic">"{economyCard.marketNarrative}"</h2>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-8 relative z-10 mb-6">
                <div className="space-y-4">
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                    <History className="w-3 h-3" /> Index Structure
                  </h4>
                  <p className="text-sm border-l-2 border-primary/30 pl-4 py-1 italic text-foreground/80">
                    {economyCard.indexAnalysis?.pattern || "Neutral structures detected."}
                  </p>
                </div>
                <div className="space-y-4">
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-2">
                    <Clock className="w-3 h-3" /> Key Catalyst
                  </h4>
                  <p className="text-sm font-medium bg-muted/50 p-3 rounded-lg border border-border">
                    {economyCard.keyEconomicEvents?.next_24h || "No major catalyst pending."}
                  </p>
                </div>
              </div>

              {/* Restored Sector Rotation Section */}
              <div className="grid grid-cols-2 gap-8 pt-6 border-t border-border/50 relative z-10">
                <div className="space-y-4">
                  <h4 className="font-bold flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
                    <Zap className="w-4 h-4 text-yellow-500" /> Sector Rotation
                  </h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground uppercase font-bold mb-2">Leading</p>
                      <div className="flex flex-wrap gap-1.5">
                        {economyCard.sectorRotation?.leadingSectors?.length > 0 ? (
                          economyCard.sectorRotation.leadingSectors.map((s: string) => (
                            <Badge key={s} variant="success" className="text-[9px] px-2 py-0">{s}</Badge>
                          ))
                        ) : (
                          <span className="text-[10px] text-muted-foreground italic">No leads detected</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground uppercase font-bold mb-2">Lagging</p>
                      <div className="flex flex-wrap gap-1.5">
                        {economyCard.sectorRotation?.laggingSectors?.length > 0 ? (
                          economyCard.sectorRotation.laggingSectors.map((s: string) => (
                            <Badge key={s} variant="error" className="text-[9px] px-2 py-0">{s}</Badge>
                          ))
                        ) : (
                          <span className="text-[10px] text-muted-foreground italic">No lags detected</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
                <div className="space-y-3">
                  <h4 className="text-xs font-bold text-muted-foreground uppercase tracking-widest">Rotation Analysis</h4>
                  <p className="text-sm text-foreground/70 leading-relaxed">
                    {economyCard.sectorRotation?.rotationAnalysis || "Awaiting structural flow data."}
                  </p>
                </div>
              </div>
            </Card>
          )}

          {/* Step 3 Component Removed - Stopping at Tape */}


          {/* Step 2: Market Structural Tape (Collapsible/Secondary) */}
          {(marketData.length > 0 || proximityResults.length > 0) && (
            <div className="space-y-6 pt-12 border-t border-border/50">
              <div className="flex items-center justify-between px-2">
                <h3 className="font-bold text-xl flex items-center gap-3">
                  <Layers className="w-5 h-5 text-primary" /> Market Structural Tape
                  <Badge variant="info" className="ml-2">{marketData.length} Actives</Badge>
                </h3>
              </div>

              <div className="grid grid-cols-12 gap-6">
                <div className="col-span-12">
                  {proximityResults.length === 0 ? (
                    <div className="text-center p-8 border border-dashed border-border/50 rounded-xl">
                      <p className="text-muted-foreground italic">No tickers within threshold ({settings.proximity_threshold}%) of Key Levels.</p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      {proximityResults
                        .sort((a, b) => a['Dist %'] - b['Dist %'])
                        .map((alert, i) => {
                          // Badge color logic: Short/Bearish -> Red, Long/Bullish -> Green
                          let badgeVariant: any = "default";
                          const isBearish = /bear|short/i.test(alert.Bias || "");
                          const isBullish = /bull|long/i.test(alert.Bias || "");

                          if (isBearish) badgeVariant = "error";
                          else if (isBullish) badgeVariant = "success";
                          else badgeVariant = alert.Nature === 'SUPPORT' ? 'success' : 'error';

                          const isLong = badgeVariant === 'success';
                          const isShort = badgeVariant === 'error';

                          // 8% tints as requested
                          const cardClasses = isLong
                            ? "border-l-emerald-500 bg-emerald-500/8 group-hover:bg-emerald-500/12"
                            : isShort
                              ? "border-l-rose-500 bg-rose-500/8 group-hover:bg-rose-500/12"
                              : "border-l-primary bg-primary/8 group-hover:bg-primary/12";

                          return (
                            <Card
                              key={i}
                              className={`p-4 border-l-4 group transition-all hover:scale-105 duration-200 shadow-xl cursor-pointer !bg-opacity-100 ${cardClasses}`}
                              style={{
                                background: isLong
                                  ? 'rgba(16, 185, 129, 0.08)'
                                  : isShort
                                    ? 'rgba(244, 63, 94, 0.08)'
                                    : undefined
                              }}
                              onClick={() => setSelectedTicker(alert.Ticker)}
                            >
                              <div className="flex justify-between items-start mb-2">
                                <h4 className="font-black text-2xl tracking-tight">{alert.Ticker}</h4>
                                <Badge variant={badgeVariant} className="text-[9px] px-2 py-0.5 font-bold uppercase">
                                  {alert.Type}
                                </Badge>
                              </div>
                              <div className="space-y-3 mt-4">
                                <div className="flex justify-between items-baseline pb-1">
                                  <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-tight whitespace-nowrap mr-2">Current Price</span>
                                  <span className="font-mono font-bold text-lg text-white">
                                    {alert.Price}
                                  </span>
                                </div>
                                <div className="flex justify-between items-baseline pb-1">
                                  <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-tight whitespace-nowrap mr-2">Key Level</span>
                                  <span className={`font-mono font-bold text-lg ${alert.Nature === 'SUPPORT' ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    ${alert.Level.toFixed(2)}
                                  </span>
                                </div>
                                <div className="flex justify-between items-baseline">
                                  <span className="text-[9px] font-bold text-muted-foreground uppercase tracking-tight whitespace-nowrap mr-2">Proximity</span>
                                  <span className={`font-mono font-bold text-xl ${alert['Dist %'] < 0.5 ? 'text-emerald-500 animate-pulse' : 'text-primary'}`}>
                                    {alert['Dist %']}%
                                  </span>
                                </div>
                              </div>
                            </Card>
                          );
                        })}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Modal for Screener Briefing */}
          <Modal
            isOpen={!!selectedTicker}
            onClose={() => setSelectedTicker(null)}
            title={`🔬 ${selectedTicker} - Structural Briefing`}
            variant="default"
          >
            <div className="space-y-4 max-h-[60vh] overflow-y-auto terminal-scroll">
              {selectedTicker && marketCards[selectedTicker] ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="bg-muted/10 p-3 rounded-lg border border-border/50">
                      <h4 className="text-xs font-bold uppercase text-muted-foreground mb-2">Key Levels (Support)</h4>
                      <div className="flex flex-wrap gap-2">
                        {marketCards[selectedTicker].screener_briefing?.S_Levels?.map((l: any, i: number) => (
                          <Badge key={i} variant="success" className="font-mono text-sm">{l}</Badge>
                        )) || <span className="text-xs italic text-muted-foreground">None</span>}
                      </div>
                    </div>
                    <div className="bg-muted/10 p-3 rounded-lg border border-border/50">
                      <h4 className="text-xs font-bold uppercase text-muted-foreground mb-2">Key Levels (Resistance)</h4>
                      <div className="flex flex-wrap gap-2">
                        {marketCards[selectedTicker].screener_briefing?.R_Levels?.map((l: any, i: number) => (
                          <Badge key={i} variant="error" className="font-mono text-sm">{l}</Badge>
                        )) || <span className="text-xs italic text-muted-foreground">None</span>}
                      </div>
                    </div>
                  </div>

                  <div className="mt-4">
                    <div className="text-sm leading-relaxed whitespace-pre-wrap font-mono text-foreground/80">
                      {(() => {
                        const briefing = marketCards[selectedTicker].screener_briefing;
                        if (!briefing) return <span className="text-muted-foreground italic">No briefing details available.</span>;

                        // Parse narrative string
                        let narrativeText = "";
                        if (typeof briefing === 'string') narrativeText = briefing;
                        else if (briefing.narrative) narrativeText = briefing.narrative;
                        else return JSON.stringify(briefing, null, 2).replace(/[{"}\[\],]/g, '');

                        // Extract sections using regex
                        const getSection = (key: string) => {
                          // Look for Key: Value followed by (newline + NextKey:) OR End of String
                          // Updated regex allows mixed case/numbers in keys (e.g., Plan_A, S_Levels)
                          const match = narrativeText.match(new RegExp(`${key}:\\s*(.*?)(?=\\n[A-Z][a-zA-Z0-9_]*:|$)`, 's'));
                          return match ? match[1].trim() : null;
                        };

                        const setupBias = getSection('Setup_Bias') || "Neutral";
                        const justification = getSection('Justification');
                        const catalyst = getSection('Catalyst');
                        const pattern = getSection('Pattern');
                        const planA = getSection('Plan_A');
                        const planALevel = getSection('Plan_A_Level');
                        const planB = getSection('Plan_B');
                        const planBLevel = getSection('Plan_B_Level');

                        // Clean up Pattern if it accidentally captured subsequent sections due to malformed newlines
                        // (Fallback safety: if Pattern is suspiciously long (> 100 chars), assume regex fail and truncate)
                        const cleanPattern = pattern && pattern.length > 200 ? pattern.substring(0, 100) + "..." : pattern;

                        return (
                          <div className="space-y-6">
                            {/* Header: Bias & Scope */}
                            <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-white/10 pb-4 gap-4">
                              <div className="space-y-1">
                                <h5 className="text-xs font-bold uppercase text-muted-foreground tracking-widest">Strategic Bias</h5>
                                <Badge variant={setupBias.includes('Bear') ? 'error' : setupBias.includes('Bull') ? 'success' : 'default'} className="text-base px-3 py-1">
                                  {setupBias.toUpperCase()}
                                </Badge>
                              </div>
                              {cleanPattern && (
                                <div className="text-left md:text-right space-y-1 flex-1 flex flex-col items-end">
                                  <h5 className="text-xs font-bold uppercase text-muted-foreground tracking-widest w-full text-left md:text-right">Detected Pattern</h5>
                                  <span className="text-sm font-mono text-primary bg-primary/5 px-3 py-1.5 rounded inline-block leading-relaxed w-fit max-w-full">
                                    {cleanPattern}
                                  </span>
                                </div>
                              )}
                            </div>

                            {/* Core Core Narrative */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                              {catalyst && (
                                <div className="bg-yellow-500/5 p-4 rounded-xl border border-yellow-500/20">
                                  <h5 className="text-xs font-bold uppercase text-yellow-500 mb-2 flex items-center gap-2">
                                    <Zap className="w-4 h-4" /> Catalyst
                                  </h5>
                                  <p className="text-sm leading-relaxed text-foreground/90">{catalyst}</p>
                                </div>
                              )}
                              {justification && (
                                <div className={`p-4 rounded-xl border ${!catalyst ? 'col-span-2' : ''} bg-muted/10 border-border/50`}>
                                  <h5 className="text-xs font-bold uppercase text-muted-foreground mb-2 flex items-center gap-2">
                                    <Brain className="w-4 h-4" /> Rationale
                                  </h5>
                                  <p className="text-sm leading-relaxed text-foreground/90">{justification}</p>
                                </div>
                              )}
                            </div>

                            {/* Execution Plans */}
                            {(planA || planB) ? (
                              <div className="space-y-3 pt-2">
                                <h5 className="text-xs font-bold uppercase text-muted-foreground tracking-widest mb-2">Execution Plans</h5>

                                {(() => {
                                  const getPlanStyles = (text: string | null) => {
                                    if (!text) return { border: 'border-l-primary/30', badge: 'bg-primary/10 text-primary', text: 'text-primary' };
                                    const t = text.toLowerCase();
                                    const isShort = /short|bear|sell|put|below|failure|resistance|rejection|reject|fade/i.test(t);
                                    const isLong = /long|bull|buy|call|above|support|bounce|break|cross/i.test(t);

                                    if (isShort) return { border: 'border-l-rose-500', badge: 'bg-rose-500/10 text-rose-400', text: 'text-rose-400' };
                                    if (isLong) return { border: 'border-l-emerald-500', badge: 'bg-emerald-500/10 text-emerald-400', text: 'text-emerald-400' };
                                    return { border: 'border-l-primary/30', badge: 'bg-primary/10 text-primary', text: 'text-primary' };
                                  };

                                  const stylesA = getPlanStyles(planA);
                                  const stylesB = getPlanStyles(planB);

                                  return (
                                    <>
                                      {planA && (
                                        <div className={`flex items-center gap-4 bg-gradient-to-r from-background to-muted/20 p-3 rounded-lg border-l-4 ${stylesA.border} border border-t-0 border-r-0 border-b-0 shadow-sm`}>
                                          <div className={`px-2 py-1 rounded font-black text-sm min-w-[60px] text-center ${stylesA.badge}`}>PLAN A</div>
                                          <div className="flex-1 text-sm font-medium">{planA}</div>
                                          {planALevel && <div className={`font-mono font-bold text-base ${stylesA.text}`}>{planALevel}</div>}
                                        </div>
                                      )}

                                      {planB && (
                                        <div className={`flex items-center gap-4 bg-gradient-to-r from-background to-muted/20 p-3 rounded-lg border-l-4 ${stylesB.border} border border-t-0 border-r-0 border-b-0 shadow-sm`}>
                                          <div className={`px-2 py-1 rounded font-black text-sm min-w-[60px] text-center ${stylesB.badge}`}>PLAN B</div>
                                          <div className="flex-1 text-sm font-medium text-foreground/80">{planB}</div>
                                          {planBLevel && <div className={`font-mono font-bold text-base ${stylesB.text}`}>{planBLevel}</div>}
                                        </div>
                                      )}
                                    </>
                                  );
                                })()}
                              </div>
                            ) : null}

                            {/* Fallback for unparsed sections / errors */}
                            {(!setupBias && !justification) && (
                              <div className="text-sm text-muted-foreground font-mono whitespace-pre-wrap">
                                {narrativeText}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center p-8 text-center">
                  <Zap className="w-8 h-8 text-muted-foreground mb-2" />
                  <p className="text-muted-foreground italic">Analysis data unavailable for this ticker.</p>
                </div>
              )}
            </div>
            {selectedTicker && (
              <div className="flex justify-between pt-4 border-t border-border/30">
                <Button
                  variant="ghost"
                  onClick={() => setChartTicker(selectedTicker)}
                  className="text-xs flex items-center gap-2 bg-rose-950/30 text-rose-400 border border-rose-900/50 hover:bg-rose-900/40 hover:text-rose-300 transition-all"
                >
                  <Activity className="w-4 h-4" /> Launch Chart
                </Button>
                <Button variant="outline" onClick={() => setSelectedTicker(null)} className="text-xs">Close Briefing</Button>
              </div>
            )}
          </Modal>

          {/* Chart Popup */}
          <CustomChartModal
            isOpen={!!chartTicker}
            onClose={() => setChartTicker(null)}
            ticker={chartTicker || ""}
            marketCard={chartTicker ? marketCards[chartTicker] : null}
            simulationCutoff={settings.simulation_cutoff}
          />
        </div>
      </div>
    </div>
  );
}
