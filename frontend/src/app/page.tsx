"use client";

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Card, Badge } from '@/components/ui/core';
import { Modal } from '@/components/ui/Modal';
import {
  TrendingUp,
  TrendingDown,
  Zap,
  Wifi,
  Calendar,
  FileText
} from 'lucide-react';
import { socketService } from '@/lib/socket';
import { runSelectionScan } from '@/lib/api';
import { useMission } from '@/lib/context';
import CardEditorView from '@/components/layout/CardEditorView';
import CompanyCardView from '@/components/layout/CompanyCardView';
import ScreenerBriefingView from '@/components/layout/ScreenerBriefingView';

export default function UnifiedCommandPage() {
  const { settings, systemStatus, capitalStreaming } = useMission();
  const [isLoading, setIsLoading] = useState(true);
  const [isBackendError, setIsBackendError] = useState(false);

  // Core Scanner State
  const [marketData, setMarketData] = useState<any[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [showFullCard, setShowFullCard] = useState(false);

  // Real-time Price State
  const priceMapRef = useRef<Record<string, number>>({});
  const [lastSortTime, setLastSortTime] = useState(Date.now());

  // 1. Auto-load baseline data on mount
  useEffect(() => {
    const loadBaseline = async () => {
      setIsLoading(true);
      setIsBackendError(false);
      try {
        const scanRes = await runSelectionScan({
          benchmark_date: settings.benchmark_date,
          simulation_cutoff: settings.simulation_cutoff,
          threshold: settings.proximity_threshold,
          mode: settings.mode,
          db_fallback: settings.db_fallback,
          refresh_tickers: [],
          plan_only: true
        });

        if (scanRes.status === "success") {
          setMarketData(scanRes.data.results || []);
        } else {
          // Handle API-level error status
          setIsBackendError(true);
        }
      } catch (err) {
        // Silent — Connection Offline UI handles this
        setIsBackendError(true);
      } finally {
        setIsLoading(false);
      }
    };

    loadBaseline();
  }, []);

  // Sync isBackendError with systemStatus from context as a backup
  useEffect(() => {
    if (systemStatus === null && !isLoading) {
      // If we finished loading and status is still null, backend might be unreachable
      // But we give it a bit of a grace period or wait for the fetch to actually fail
    }
  }, [systemStatus, isLoading]);

  // 2. Listen for WebSocket price updates when streaming
  useEffect(() => {
    if (!capitalStreaming) return;

    const handler = (update: { ticker: string; price: number }) => {
      priceMapRef.current[update.ticker] = update.price;
      // Trigger a re-render so the useMemo picks up the new price
      setLastSortTime(Date.now());
    };

    socketService.onPriceUpdate(handler);

    return () => {
      socketService.offPriceUpdate(handler);
    };
  }, [capitalStreaming]);

  // 3. Periodic Re-sort every 2 seconds as a safety net (only when streaming)
  useEffect(() => {
    if (!capitalStreaming) return;

    const interval = setInterval(() => {
      setLastSortTime(Date.now());
    }, 2000);
    return () => clearInterval(interval);
  }, [capitalStreaming]);

  // 4. Proximity Calculation (client-side, for live re-ranking)
  const calculateProximity = (currentPrice: number, planA: number | null, planB: number | null, atr: number) => {
    if (!currentPrice || (!planA && !planB)) return 999;

    const distA = planA ? Math.abs(currentPrice - planA) : Infinity;
    const distB = planB ? Math.abs(currentPrice - planB) : Infinity;
    const nearestDist = Math.min(distA, distB);

    if (atr > 0) return nearestDist / atr;
    return (nearestDist / currentPrice) * 100;
  };

  // 5. Ranked Data Computation
  const rankedData = useMemo(() => {
    if (!marketData.length) return [];

    const data = marketData.map(item => {
      const ticker = item.ticker;

      // Use backend-computed plan levels directly
      const planA = item.plan_a ?? null;
      const planB = item.plan_b ?? null;
      const atr = item.atr || 0;
      const cardDate = item.card_date || "N/A";

      // Price: backend provides prox_alert.Price, or live WS price if streaming
      const backendPrice = item.prox_alert.Price !== "N/A"
        ? parseFloat(item.prox_alert.Price.replace('$', ''))
        : null;

      let currentPrice: number | null = null;
      if (capitalStreaming) {
        currentPrice = priceMapRef.current[ticker] || backendPrice;
      } else {
        currentPrice = backendPrice;
      }

      // Backend-computed nearest level (used as default, overridden if live)
      let nearestLevel = item.prox_alert.Type || 'N/A';
      let nearestLevelValue = item.prox_alert.Level ?? null;
      let proximityScore = item.prox_alert["Dist %"] ?? 999;
      let nature = item.prox_alert.Nature || 'N/A';

      // If streaming and we have a live price, recalculate proximity client-side
      if (capitalStreaming && currentPrice && (planA || planB)) {
        proximityScore = calculateProximity(currentPrice, planA, planB, atr);

        const distA = planA !== null ? Math.abs(currentPrice - planA) : Infinity;
        const distB = planB !== null ? Math.abs(currentPrice - planB) : Infinity;
        if (distA <= distB) {
          nearestLevel = 'PLAN A';
          nearestLevelValue = planA;
        } else {
          nearestLevel = 'PLAN B';
          nearestLevelValue = planB;
        }
        nature = nearestLevelValue !== null && nearestLevelValue < currentPrice ? 'SUPPORT' : 'RESISTANCE';
      }

      return {
        ...item,
        livePrice: currentPrice,
        proximityScore,
        nearestLevel,
        nearestLevelValue,
        nature,
        cardDate,
        hasPriceData: currentPrice !== null
      };
    });

    // Sort by Proximity Score only when streaming
    if (capitalStreaming) {
      return data.sort((a, b) => {
        // no-price tickers go to the end
        if (a.hasPriceData && !b.hasPriceData) return -1;
        if (!a.hasPriceData && b.hasPriceData) return 1;
        if (a.proximityScore !== b.proximityScore) return a.proximityScore - b.proximityScore;
        return a.nearestLevel === 'PLAN A' ? -1 : 1;
      });
    }

    return data;
  }, [marketData, lastSortTime, capitalStreaming]);

  // Archive mode
  if (settings.workstation === 'Archive') return <CardEditorView />;

  return (
    <div className="space-y-8 max-w-7xl mx-auto relative animate-in fade-in duration-500">
      {/* Backend Offline State */}
      {isBackendError ? (
        <div className="h-[60vh] flex flex-col items-center justify-center text-center p-20 border-2 border-dashed border-rose-500/20 rounded-3xl bg-rose-500/5">
          <div className="bg-rose-500/10 p-8 rounded-full mb-8 text-rose-500">
            <Zap className="w-16 h-16" />
          </div>
          <h2 className="text-3xl font-bold mb-4 tracking-tight text-rose-400">Connection Offline</h2>
          <p className="text-muted-foreground max-w-md text-lg leading-relaxed">
            The system is offline. Please contact the administrator to restore the connection.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-8 px-6 py-2 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 rounded-xl text-rose-400 text-sm font-bold transition-all"
          >
            Retry Connection
          </button>
        </div>
      ) : isLoading ? (
        <div className="h-[60vh] flex flex-col items-center justify-center text-center">
          <div className="relative">
            <Zap className="w-16 h-16 text-primary animate-pulse" />
            <div className="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150 animate-pulse" />
          </div>
          <h2 className="text-3xl font-bold mt-8 mb-4 tracking-tight">Loading Market Data</h2>
          <p className="text-muted-foreground max-w-sm text-lg leading-relaxed">
            Fetching watchlist, plan levels, and historical data...
          </p>
        </div>
      ) : marketData.length === 0 ? (
        /* Empty State — No Data */
        <div className="h-[60vh] flex flex-col items-center justify-center text-center p-20 border-2 border-dashed border-border rounded-3xl bg-muted/5">
          <div className="bg-primary/10 p-8 rounded-full mb-8 text-primary">
            <Wifi className="w-16 h-16" />
          </div>
          <h2 className="text-3xl font-bold mb-4 tracking-tight">No Market Data Available</h2>
          <p className="text-muted-foreground max-w-md text-lg leading-relaxed">
            Click the <span className="text-emerald-400 font-bold">Connect</span> button in the header to stream live prices from Capital.com and rank cards by proximity.
          </p>
        </div>
      ) : (
        /* Ranked Cards Dashboard */
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
          {rankedData.map((item, i) => {
            const isBullish = /bull|long/i.test(item.prox_alert.Bias || "");
            const isBearish = /bear|short/i.test(item.prox_alert.Bias || "");
            const isSupport = item.nature === 'SUPPORT';

            const cardClasses = !item.hasPriceData
              ? "border-l-zinc-500 bg-zinc-500/5 hover:bg-zinc-500/10"
              : isSupport
                ? "border-l-emerald-500 bg-emerald-500/8 hover:bg-emerald-500/12"
                : "border-l-rose-500 bg-rose-500/8 hover:bg-rose-500/12";

            return (
              <Card
                key={item.ticker}
                className={`p-5 border-l-4 group transition-all hover:scale-[1.02] duration-200 shadow-xl cursor-pointer !bg-opacity-100 relative overflow-hidden ${cardClasses}`}
                onClick={() => setSelectedTicker(item.ticker)}
              >
                {/* Rank Badge — only when streaming and has price */}
                {capitalStreaming && item.hasPriceData && (
                  <div className="absolute top-0 right-0 bg-primary/20 px-2 py-1 rounded-bl-lg">
                    <span className="text-[10px] font-black text-primary">#{i + 1}</span>
                  </div>
                )}

                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h4 className="font-black text-2xl tracking-tighter">{item.ticker}</h4>
                    <Badge variant={isBullish ? 'success' : isBearish ? 'error' : 'default'} className="text-[9px] px-1.5 py-0 font-bold uppercase">
                      {item.prox_alert.Bias}
                    </Badge>
                  </div>
                  <div className="text-right">
                    <div className="text-[10px] font-bold text-muted-foreground uppercase tracking-tighter">Proximity</div>
                    <div className={`text-xl font-black font-mono ${!item.hasPriceData ? 'text-muted-foreground' :
                      item.proximityScore < 0.5 ? 'text-emerald-400 animate-pulse' : 'text-primary'
                      }`}>
                      {!item.hasPriceData ? '--' : item.proximityScore === 999 ? 'N/A' : item.proximityScore.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 mt-4 bg-black/20 p-3 rounded-lg border border-white/5">
                  <div className="flex justify-between items-baseline">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Live Price</span>
                    <span className="font-mono font-bold text-lg text-white">
                      {capitalStreaming && item.hasPriceData ? `$${item.livePrice.toFixed(2)}` : '--'}
                    </span>
                  </div>
                  <div className="flex justify-between items-baseline">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Nearest Plan</span>
                    <span className={`font-mono font-bold text-lg ${!item.hasPriceData ? 'text-muted-foreground' :
                      isSupport ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                      {item.nearestLevelValue !== null ? `$${item.nearestLevelValue.toFixed(2)}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center pt-1 border-t border-white/5">
                    <span className="text-[9px] font-black text-muted-foreground uppercase">{item.nearestLevel}</span>
                    <div className="flex items-center gap-3">
                      {/* Plan Classification (what the analyst plan says) */}
                      {item.prox_alert.PlanNature && item.prox_alert.PlanNature !== 'N/A' && (
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${item.prox_alert.PlanNature === 'SUPPORT'
                          ? 'text-emerald-400 border-emerald-500/30 bg-emerald-500/10'
                          : item.prox_alert.PlanNature === 'RESISTANCE'
                            ? 'text-rose-400 border-rose-500/30 bg-rose-500/10'
                            : 'text-zinc-400 border-zinc-500/30 bg-zinc-500/10'
                          }`}>
                          PLAN: {item.prox_alert.PlanNature}
                        </span>
                      )}
                      {/* Price-Relative Behavior (live price vs level) */}
                      {item.hasPriceData && (
                        <div className="flex items-center gap-1">
                          {isSupport ? <TrendingUp className="w-3 h-3 text-emerald-500" /> : <TrendingDown className="w-3 h-3 text-rose-500" />}
                          <span className={`text-[9px] font-bold ${isSupport ? 'text-emerald-500' : 'text-rose-500'}`}>
                            {isSupport ? '↑ ABOVE' : '↓ BELOW'}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Card Date Indicator */}
                <div className="mt-3 flex items-center gap-1.5 text-[9px] text-muted-foreground/60">
                  <Calendar className="w-3 h-3" />
                  <span className="font-mono">Card: {item.cardDate}</span>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Modal: Screener Briefing (default) → Full Card (toggle) */}
      <Modal
        isOpen={!!selectedTicker}
        onClose={() => { setSelectedTicker(null); setShowFullCard(false); }}
        title={`🔬 ${selectedTicker} - ${showFullCard ? 'Full Card' : 'Screener Briefing'}`}
        variant="default"
      >
        <div className="space-y-4 max-h-[70vh] overflow-y-auto terminal-scroll pr-2 pt-4">
          {selectedTicker && (() => {
            const item = rankedData.find(d => d.ticker === selectedTicker);
            if (!item) return (
              <div className="flex flex-col items-center justify-center p-8 text-center">
                <Zap className="w-8 h-8 text-muted-foreground mb-2" />
                <p className="text-muted-foreground italic">Plan data unavailable for this ticker.</p>
              </div>
            );

            return (
              <>
                {/* Toggle Button */}
                <div className="flex items-center gap-2 mb-4">
                  <button
                    onClick={() => setShowFullCard(!showFullCard)}
                    className="flex items-center gap-2 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-[10px] font-bold uppercase tracking-widest text-zinc-400 hover:text-white transition-all"
                  >
                    <FileText className="w-3 h-3" />
                    {showFullCard ? 'Show Briefing' : 'Show Full Card'}
                  </button>
                  <div className="h-px flex-1 bg-white/5" />
                </div>

                {showFullCard ? (
                  <CompanyCardView
                    card={item.card}
                    ticker={selectedTicker}
                    date={settings.benchmark_date}
                  />
                ) : (
                  <ScreenerBriefingView
                    briefing={item.card?.screener_briefing || ''}
                    planAText={item.plan_a_text}
                    planBText={item.plan_b_text}
                    planALevel={item.plan_a}
                    planBLevel={item.plan_b}
                    planANature={item.plan_a_nature}
                    planBNature={item.plan_b_nature}
                    setupBias={item.prox_alert?.Bias}
                    ticker={selectedTicker}
                  />
                )}
              </>
            );
          })()}
        </div>
      </Modal>
    </div>
  );
}
