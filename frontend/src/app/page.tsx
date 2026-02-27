"use client";

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Card, Badge } from '@/components/ui/core';
import { Modal } from '@/components/ui/Modal';
import {
  TrendingUp,
  TrendingDown,
  Target,
  Zap,
  Wifi
} from 'lucide-react';
import { socketService } from '@/lib/socket';
import { runSelectionScan } from '@/lib/api';
import { useMission } from '@/lib/context';
import CardEditorView from '@/components/layout/CardEditorView';
import CompanyCardView from '@/components/layout/CompanyCardView';

export default function UnifiedCommandPage() {
  const { settings, capitalStreaming } = useMission();
  const [isLoading, setIsLoading] = useState(true);

  // Core Scanner State
  const [marketData, setMarketData] = useState<any[]>([]);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);

  // Real-time Price State
  const priceMapRef = useRef<Record<string, number>>({});
  const [lastSortTime, setLastSortTime] = useState(Date.now());

  // 1. Auto-load baseline data on mount
  useEffect(() => {
    const loadBaseline = async () => {
      setIsLoading(true);
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
        }
      } catch (err) {
        console.error("Auto-load scan failed:", err);
      } finally {
        setIsLoading(false);
      }
    };

    loadBaseline();
  }, []);

  // 2. Listen for WebSocket price updates when streaming
  useEffect(() => {
    if (!capitalStreaming) return;

    const handler = (update: { ticker: string; price: number }) => {
      priceMapRef.current[update.ticker] = update.price;
    };

    socketService.onPriceUpdate(handler);

    // No cleanup needed — handlers accumulate on the singleton
    // But we trigger an immediate sort when connecting
    setLastSortTime(Date.now());
  }, [capitalStreaming]);

  // 3. Periodic Re-sort every 5 seconds (only when streaming)
  useEffect(() => {
    if (!capitalStreaming) return;

    const interval = setInterval(() => {
      setLastSortTime(Date.now());
    }, 5000);
    return () => clearInterval(interval);
  }, [capitalStreaming]);

  // 4. Proximity Calculation
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

      // If streaming: use live price, otherwise use scan price
      let currentPrice: number | null = null;
      if (capitalStreaming) {
        currentPrice = priceMapRef.current[ticker] || parseFloat(item.prox_alert.Price.replace('$', ''));
      } else {
        currentPrice = parseFloat(item.prox_alert.Price.replace('$', ''));
      }

      const planA = item.card?.screener_briefing?.Plan_A_Level ? parseFloat(item.card.screener_briefing.Plan_A_Level) : null;
      const planB = item.card?.screener_briefing?.Plan_B_Level ? parseFloat(item.card.screener_briefing.Plan_B_Level) : null;
      const atr = item.atr || 0;

      const score = calculateProximity(currentPrice, planA, planB, atr);

      let nearestLevel = 'N/A';
      let nearestLevelValue: number | null = null;

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

    // Sort by Proximity Score only when streaming
    if (capitalStreaming) {
      return data.sort((a, b) => {
        if (a.proximityScore !== b.proximityScore) {
          return a.proximityScore - b.proximityScore;
        }
        return a.nearestLevel === 'PLAN A' ? -1 : 1;
      });
    }

    return data;
  }, [marketData, lastSortTime, capitalStreaming]);

  // Archive mode
  if (settings.workstation === 'Archive') return <CardEditorView />;

  return (
    <div className="space-y-8 max-w-7xl mx-auto relative animate-in fade-in duration-500">
      {/* Loading State */}
      {isLoading ? (
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
            Click the <span className="text-emerald-400 font-bold">Connect</span> button in the header to stream live prices from Capital.com and rank cards by proximity to Plan A/B levels.
          </p>
        </div>
      ) : (
        /* Ranked Cards Dashboard */
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6 animate-in fade-in slide-in-from-right-4 duration-500">
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
                {/* Rank Badge — only when streaming */}
                {capitalStreaming && (
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
                    <div className={`text-xl font-black font-mono ${item.proximityScore < 0.5 ? 'text-emerald-400 animate-pulse' : 'text-primary'}`}>
                      {item.proximityScore === 999 ? 'N/A' : item.proximityScore.toFixed(2)}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 mt-4 bg-black/20 p-3 rounded-lg border border-white/5">
                  <div className="flex justify-between items-baseline">
                    <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Live Price</span>
                    <span className="font-mono font-bold text-lg text-white">
                      {capitalStreaming ? `$${item.livePrice.toFixed(2)}` : '--'}
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
