"use client";

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Card, Button, Badge } from '@/components/ui/core';
import { Modal } from '@/components/ui/Modal';
import {
  Search,
  Zap,
  AlertTriangle,
  Layers,
  HelpCircle,
  TrendingUp,
  TrendingDown,
  Clock,
  Target,
  BarChart3
} from 'lucide-react';
import { socketService } from '@/lib/socket';
import { runSelectionScan, getWatchlistStatus } from '@/lib/api';
import { useMission } from '@/lib/context';
import { MissionControl } from '@/components/layout/MissionControl';
import CardEditorView from '@/components/layout/CardEditorView';
import CompanyCardView from '@/components/layout/CompanyCardView';

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
  const [isRunning, setIsRunning] = useState(false);
  const [logs, setLogs] = useState<any[]>([]);

  // Core Scanner State
  const [marketData, setMarketData] = useState<any[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [watchlistStatus, setWatchlistStatus] = useState<any[]>([]);

  // Real-time Price State (Ref for high-frequency updates, State for UI sync)
  const priceMapRef = useRef<Record<string, number>>({});
  const [lastSortTime, setLastSortTime] = useState(Date.now());

  const logsEndRef = useRef<HTMLDivElement>(null);

  // 1. Initialize Watchlist and Socket
  useEffect(() => {
    socketService.onLog((log) => {
      setLogs((prev) => [...prev, log].slice(-50));
    });

    socketService.onPriceUpdate((update) => {
      // Update price map ref
      priceMapRef.current[update.ticker] = update.price;
    });

    getWatchlistStatus().then(res => {
      if (res.status === 'success') setWatchlistStatus(res.data);
    }).catch(() => { });
  }, []);

  // 2. Periodic Re-sort (Every 5 seconds if prices changed)
  useEffect(() => {
    const interval = setInterval(() => {
      setLastSortTime(Date.now());
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // 3. Proximity Calculation Logic (Matching Backend Logic)
  const calculateProximity = (ticker: string, currentPrice: number, planA: number | null, planB: number | null, atr: number) => {
    if (!currentPrice || (!planA && !planB)) return 999;

    const distA = planA ? Math.abs(currentPrice - planA) : Infinity;
    const distB = planB ? Math.abs(currentPrice - planB) : Infinity;

    const nearestDist = Math.min(distA, distB);

    // ATR Normalization
    if (atr > 0) {
      return nearestDist / atr;
    }
    return (nearestDist / currentPrice) * 100;
  };

  // 4. Ranked Data Computation
  const rankedData = useMemo(() => {
    if (!marketData.length) return [];

    const data = marketData.map(item => {
      const ticker = item.ticker;
      // Get latest price from WS ref or use initial price from scan
      const currentPrice = priceMapRef.current[ticker] || parseFloat(item.prox_alert.Price.replace('$', ''));

      // These come from the initial scan results (EOD Cards in DB)
      const planA = item.card?.screener_briefing?.Plan_A_Level ? parseFloat(item.card.screener_briefing.Plan_A_Level) : null;
      const planB = item.card?.screener_briefing?.Plan_B_Level ? parseFloat(item.card.screener_briefing.Plan_B_Level) : null;
      const atr = item.atr || 0; // Backend needs to provide this in initial scan

      const score = calculateProximity(ticker, currentPrice, planA, planB, atr);

      let nearestLevel = 'N/A';
      let nearestLevelValue = null;

      if (planA !== null || planB !== null) {
        const distA = planA !== null ? Math.abs(currentPrice - planA) : Infinity;
        const distB = planB !== null ? Math.abs(currentPrice - planB) : Infinity;
        if (distA <= distB) {
          nearestLevel = 'PLAN A';
          nearestLevelValue = planA;
        } else {
          nearestLevel = 'PLAN B';
          nearestLevelValue = planB;
        }
      }

      return {
        ...item,
        livePrice: currentPrice,
        proximityScore: score,
        nearestLevel,
        nearestLevelValue
      };
    });

    // Sort by Proximity Score (ATR Normalised)
    return data.sort((a, b) => {
      if (a.proximityScore !== b.proximityScore) {
        return a.proximityScore - b.proximityScore;
      }
      // Tie-breaker: Plan A priority
      return a.nearestLevel === 'PLAN A' ? -1 : 1;
    });
  }, [marketData, lastSortTime]);

  const handleRunFullMission = async () => {
    setIsRunning(true);
    setLogs([]);
    setMarketData([]);

    try {
      setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), level: 'INFO', icon: '📡', message: "Initializing Proximity Scan..." }]);

      const scanRes = await runSelectionScan({
        benchmark_date: settings.benchmark_date,
        simulation_cutoff: settings.simulation_cutoff,
        threshold: settings.proximity_threshold,
        mode: settings.mode,
        db_fallback: settings.db_fallback,
        refresh_tickers: [], // Not used in proximity engine
        plan_only: true // Always use plans for proximity ranking
      });

      if (scanRes.status === "success") {
        setMarketData(scanRes.data.results || []);
        setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), level: 'SUCCESS', icon: '✅', message: `Proximity Scan Complete. ${scanRes.data.results?.length || 0} tickers ranked.` }]);
      } else {
        setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), level: 'ERROR', icon: '❌', message: `Scan failed: ${scanRes.message || 'Unknown error'}` }]);
      }
    } catch (err) {
      console.error(err);
      setLogs(prev => [...prev, { timestamp: new Date().toLocaleTimeString(), level: 'ERROR', icon: '❌', message: "Scan failed. Check console." }]);
    } finally {
      setIsRunning(false);
    }
  };

  if (settings.workstation === 'Archive') return <CardEditorView />;

  return (
    <div className="space-y-8 max-w-7xl mx-auto relative animate-in fade-in duration-500">
      <MissionControl />

      {/* Header Section */}
      <div className="flex justify-between items-center bg-background sticky top-0 z-50 h-16 border-b border-border shadow-md -mx-8 px-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-primary">Pre-Market Scanner</h1>
          <p className="text-muted-foreground mt-0.5 text-xs uppercase tracking-widest font-bold">Proximity Ranking Engine</p>
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
                RANKING...
              </>
            ) : (
              <>
                <Search className="w-6 h-6" />
                ENGAGE PROXIMITY RANK
              </>
            )}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-8">
        {/* Left Console */}
        <div className="col-span-12 lg:col-span-3 space-y-8">
          <Card className="flex flex-col h-[600px] border-primary/20 shadow-inner bg-black/20">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-bold flex items-center gap-2 text-primary text-sm uppercase tracking-widest">
                <BarChart3 className="w-4 h-4" /> Live Ranking Feed
              </h3>
            </div>
            <div className="flex-1 bg-black/40 rounded-lg p-4 font-mono text-xs overflow-y-auto terminal-scroll space-y-2 border border-white/5">
              {logs.length === 0 ? (
                <p className="text-muted-foreground italic">Awaiting scanner parameters. Engage ranking engine to begin.</p>
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
        </div>

        {/* Right Dashboard: Ranked Cards */}
        <div className="col-span-12 lg:col-span-9">
          {rankedData.length === 0 && !isRunning ? (
            <div className="h-full flex flex-col items-center justify-center text-center p-20 border-2 border-dashed border-border rounded-3xl bg-muted/5">
              <div className="bg-primary/10 p-8 rounded-full mb-8 text-primary">
                <Target className="w-16 h-16" />
              </div>
              <h2 className="text-3xl font-bold mb-4 tracking-tight">Proximity Engine Idle</h2>
              <p className="text-muted-foreground max-w-sm text-lg leading-relaxed">
                Connect to Capital.com via Engage button to begin real-time tradability ranking based on Plan A/B proximity.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
              {rankedData.map((item, i) => {
                const isBullish = /bull|long/i.test(item.prox_alert.Bias || "");
                const isBearish = /bear|short/i.test(item.prox_alert.Bias || "");
                const isSupport = item.nearestLevelValue !== null ? item.nearestLevelValue < item.livePrice : false;

                const cardClasses = isSupport
                  ? "border-l-emerald-500 bg-emerald-500/8 hover:bg-emerald-500/12"
                  : "border-l-rose-500 bg-rose-500/8 hover:bg-rose-500/12";

                return (
                  <Card
                    key={item.ticker}
                    className={`p-5 border-l-4 group transition-all hover:scale-[1.02] duration-200 shadow-xl cursor-pointer !bg-opacity-100 relative overflow-hidden ${cardClasses}`}
                    onClick={() => setSelectedTicker(item.ticker)}
                  >
                    {/* Rank Badge */}
                    <div className="absolute top-0 right-0 bg-primary/20 px-2 py-1 rounded-bl-lg">
                      <span className="text-[10px] font-black text-primary">#{i + 1}</span>
                    </div>

                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <h4 className="font-black text-2xl tracking-tighter">{item.ticker}</h4>
                        <Badge variant={isBullish ? 'success' : isBearish ? 'error' : 'default'} className="text-[9px] px-1.5 py-0 font-bold uppercase">
                          {item.prox_alert.Bias}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-tighter">Proximity</div>
                        <div className={`text-xl font-black font-mono ${item.proximityScore < 0.5 ? 'text-emerald-400 animate-pulse' : 'text-primary'}`}>
                          {item.proximityScore === 999 ? 'N/A' : item.proximityScore.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-3 mt-4 bg-black/20 p-3 rounded-lg border border-white/5">
                      <div className="flex justify-between items-baseline">
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Live Price</span>
                        <span className="font-mono font-bold text-lg text-white">
                          ${item.livePrice.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between items-baseline">
                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Nearest Plan</span>
                        <span className={`font-mono font-bold text-lg ${isSupport ? 'text-emerald-400' : 'text-rose-400'}`}>
                          {item.nearestLevelValue !== null ? `$${item.nearestLevelValue.toFixed(2)}` : 'N/A'}
                        </span>
                      </div>
                      <div className="flex justify-between items-center pt-1 border-t border-white/5">
                        <span className="text-[9px] font-black text-muted-foreground uppercase">{item.nearestLevel}</span>
                        <div className="flex items-center gap-1">
                          {isSupport ? <TrendingUp className="w-3 h-3 text-emerald-500" /> : <TrendingDown className="w-3 h-3 text-rose-500" />}
                          <span className={`text-[10px] font-bold ${isSupport ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {isSupport ? 'SUPPORT' : 'RESISTANCE'}
                          </span>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Modal for Full Briefing */}
      <Modal
        isOpen={!!selectedTicker}
        onClose={() => setSelectedTicker(null)}
        title={`🔬 ${selectedTicker} - Strategic Briefing`}
        variant="default"
      >
        <div className="space-y-4 max-h-[70vh] overflow-y-auto terminal-scroll pr-2 pt-4">
          {selectedTicker && rankedData.find(d => d.ticker === selectedTicker)?.card ? (
            <CompanyCardView
              card={rankedData.find(d => d.ticker === selectedTicker)?.card}
              ticker={selectedTicker}
              date={settings.benchmark_date}
            />
          ) : (
            <div className="flex flex-col items-center justify-center p-8 text-center">
              <Zap className="w-8 h-8 text-muted-foreground mb-2" />
              <p className="text-muted-foreground italic">Plan data unavailable for this ticker.</p>
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
}
