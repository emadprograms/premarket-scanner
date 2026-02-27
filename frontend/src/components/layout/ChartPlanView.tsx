"use client";

import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ColorType, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { Badge } from '@/components/ui/core';
import { getChartBars } from '@/lib/api';
import {
    Target,
    BookOpen,
    ArrowUpDown,
    ChevronDown,
    ShieldAlert,
    Activity,
    Crosshair,
} from 'lucide-react';

interface ChartPlanViewProps {
    ticker: string;
    planALevel: number | null;
    planBLevel: number | null;
    planAText?: string;
    planBText?: string;
    planANature?: string;
    planBNature?: string;
    livePrice?: number | null;
    setupBias?: string;
    card?: any;
    onShowBriefing?: () => void;
}

export default function ChartPlanView({
    ticker,
    planALevel,
    planBLevel,
    planAText,
    planBText,
    planANature,
    planBNature,
    livePrice,
    setupBias,
    card,
    onShowBriefing,
}: ChartPlanViewProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const [chartLoading, setChartLoading] = useState(true);
    const [chartError, setChartError] = useState<string | null>(null);
    const [barCount, setBarCount] = useState(0);
    const [expandedPlan, setExpandedPlan] = useState<'A' | 'B' | null>(null);
    const [showLevels, setShowLevels] = useState(false);

    // Fetch real bars and build chart
    useEffect(() => {
        if (!chartContainerRef.current) return;
        let cancelled = false;

        const buildChart = async () => {
            setChartLoading(true);
            setChartError(null);

            // Fetch Capital.com bars
            let bars: any[] = [];
            try {
                const res = await getChartBars(ticker, 1);
                if (res.status === 'success' && res.data?.bars?.length > 0) {
                    bars = res.data.bars;
                }
            } catch (e) {
                // Capital.com unavailable — will show fallback
            }

            if (cancelled || !chartContainerRef.current) return;

            const chart = createChart(chartContainerRef.current, {
                layout: {
                    background: { type: ColorType.Solid, color: '#09090b' },
                    textColor: '#a1a1aa',
                    fontSize: 11,
                },
                grid: {
                    vertLines: { color: 'rgba(255,255,255,0.03)' },
                    horzLines: { color: 'rgba(255,255,255,0.03)' },
                },
                crosshair: {
                    mode: 0,
                    vertLine: { color: 'rgba(139,92,246,0.3)', width: 1 },
                    horzLine: { color: 'rgba(139,92,246,0.3)', width: 1 },
                },
                rightPriceScale: {
                    borderColor: 'rgba(255,255,255,0.1)',
                    scaleMargins: { top: 0.1, bottom: 0.1 },
                    minimumWidth: 100, // Plenty of space for plan level labels
                },
                timeScale: {
                    borderColor: 'rgba(255,255,255,0.1)',
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 15,
                    barSpacing: 20, // Fat candles
                },
                width: chartContainerRef.current.clientWidth,
                height: 350,
            });

            const series = chart.addSeries(CandlestickSeries, {
                upColor: '#22c55e',
                downColor: '#ef4444',
                borderUpColor: '#22c55e',
                borderDownColor: '#ef4444',
                wickUpColor: '#22c55e',
                wickDownColor: '#ef4444',
            });

            if (bars.length > 0) {
                series.setData(bars);
                setBarCount(bars.length);

                // Add session background bands: pre-market (amber) + post-market (blue)
                // Classify bars by session and create colored background rectangles via histogram
                const ET_OFFSET = -5 * 3600; // ET = UTC-5
                const preMarketBg: any[] = [];
                const postMarketBg: any[] = [];

                for (const bar of bars) {
                    const utcHour = new Date(bar.time * 1000).getUTCHours();
                    const etHour = (utcHour + 24 + Math.floor(ET_OFFSET / 3600)) % 24;
                    const etMinute = new Date(bar.time * 1000).getUTCMinutes();
                    const etTime = etHour + etMinute / 60;

                    if (etTime >= 4 && etTime < 9.5) {
                        // Pre-market: amber background
                        preMarketBg.push({ time: bar.time, value: 1 });
                        postMarketBg.push({ time: bar.time, value: 0 });
                    } else if (etTime >= 16 && etTime < 20) {
                        // Post-market: blue background
                        preMarketBg.push({ time: bar.time, value: 0 });
                        postMarketBg.push({ time: bar.time, value: 1 });
                    } else {
                        preMarketBg.push({ time: bar.time, value: 0 });
                        postMarketBg.push({ time: bar.time, value: 0 });
                    }
                }

                // Pre-market amber background band
                const preBgSeries = chart.addSeries(HistogramSeries, {
                    color: 'rgba(217, 119, 6, 0.15)',
                    priceScaleId: 'bg',
                    lastValueVisible: false,
                    priceLineVisible: false,
                });
                preBgSeries.setData(preMarketBg);

                // Post-market blue background band
                const postBgSeries = chart.addSeries(HistogramSeries, {
                    color: 'rgba(59, 130, 246, 0.15)',
                    priceScaleId: 'bg',
                    lastValueVisible: false,
                    priceLineVisible: false,
                });
                postBgSeries.setData(postMarketBg);

                // Hide the bg price scale and make it fill the full chart height
                chart.priceScale('bg').applyOptions({
                    visible: false,
                    scaleMargins: { top: 0, bottom: 0 },
                });

                // Show only the last ~60 bars so barSpacing stays fat
                const from = Math.max(0, bars.length - 60);
                chart.timeScale().setVisibleLogicalRange({ from, to: bars.length + 10 });
            } else {
                setChartError('Capital.com data unavailable — showing estimated levels');
                generateFallbackData(series, planALevel, planBLevel, livePrice ?? null);
                setBarCount(0);
            }

            // Only plot the NEAREST plan (the one closer to live price — the actionable trade)
            const distToA = (livePrice && planALevel) ? Math.abs(livePrice - planALevel) : Infinity;
            const distToB = (livePrice && planBLevel) ? Math.abs(livePrice - planBLevel) : Infinity;
            const showPlanA = distToA <= distToB;

            const nearestLevel = showPlanA ? planALevel : planBLevel;
            const nearestNature = showPlanA ? planANature : planBNature;
            const nearestLabel = showPlanA ? 'PLAN A' : 'PLAN B';

            if (nearestLevel !== null && nearestLevel !== undefined) {
                series.createPriceLine({
                    price: nearestLevel,
                    color: nearestNature === 'RESISTANCE' ? '#ef4444' : '#8b5cf6',
                    lineWidth: 2,
                    lineStyle: 2, // Dashed
                    axisLabelVisible: true,
                    title: `${nearestLabel} — $${nearestLevel.toFixed(2)}`,
                });
            }

            // Plot S/R levels from the card as subtle dotted markers
            if (card) {
                const srLevels: { price: number; type: 'S' | 'R' }[] = [];
                const parsePrice = (s: string) => {
                    const m = s.match(/\$?([\d,.]+)/);
                    return m ? parseFloat(m[1].replace(',', '')) : null;
                };
                let supZones = parseZones(card?.technicalStructure?.majorSupport);
                let resZones = parseZones(card?.technicalStructure?.majorResistance);
                // Fallback to screener_briefing S_Levels/R_Levels
                if (supZones.length === 0 || resZones.length === 0) {
                    const briefing = typeof card?.screener_briefing === 'string' ? card.screener_briefing : '';
                    if (supZones.length === 0) {
                        const sMatch = briefing.match(/S_Levels?:\s*\[?([^\]\n]+)/i);
                        if (sMatch) supZones = sMatch[1].split(',').map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                    }
                    if (resZones.length === 0) {
                        const rMatch = briefing.match(/R_Levels?:\s*\[?([^\]\n]+)/i);
                        if (rMatch) resZones = rMatch[1].split(',').map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                    }
                }
                supZones.forEach((z: string) => {
                    const p = parsePrice(z);
                    if (p && p !== planALevel && p !== planBLevel) srLevels.push({ price: p, type: 'S' });
                });
                resZones.forEach((z: string) => {
                    const p = parsePrice(z);
                    if (p && p !== planALevel && p !== planBLevel) srLevels.push({ price: p, type: 'R' });
                });
                srLevels.forEach(({ price, type }) => {
                    series.createPriceLine({
                        price,
                        color: type === 'R' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(139, 92, 246, 0.25)',
                        lineWidth: 1,
                        lineStyle: 3, // Dotted
                        axisLabelVisible: false,
                        title: '',
                    });
                });
            }

            chartRef.current = chart;
            setChartLoading(false);

            // Resize handler
            const handleResize = () => {
                if (chartContainerRef.current) {
                    chart.applyOptions({ width: chartContainerRef.current.clientWidth });
                }
            };
            window.addEventListener('resize', handleResize);

            // Cleanup stored for unmount
            (chartContainerRef.current as any).__cleanup = () => {
                window.removeEventListener('resize', handleResize);
                chart.remove();
                chartRef.current = null;
            };
        };

        buildChart();

        return () => {
            cancelled = true;
            if ((chartContainerRef.current as any)?.__cleanup) {
                (chartContainerRef.current as any).__cleanup();
            }
        };
    }, [ticker]);

    const bias = setupBias || 'Neutral';
    const isBullish = /bull|long/i.test(bias);
    const isBearish = /bear|short/i.test(bias);

    const distA = (livePrice && planALevel) ? Math.abs(livePrice - planALevel) : null;
    const distB = (livePrice && planBLevel) ? Math.abs(livePrice - planBLevel) : null;

    return (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Chart Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <h3 className="font-black text-xl tracking-tighter">{ticker}</h3>
                    <Badge
                        variant={isBullish ? 'success' : isBearish ? 'error' : 'warning'}
                        className={`text-[9px] font-black italic tracking-[0.15em] uppercase px-2 py-0.5 ${isBullish ? 'bg-emerald-500/15 text-emerald-400' :
                            isBearish ? 'bg-rose-500/15 text-rose-400' :
                                'bg-amber-500/15 text-amber-400'
                            }`}
                    >
                        {bias}
                    </Badge>
                </div>
                <div className="flex items-center gap-3">
                    {barCount > 0 && (
                        <span className="text-[9px] text-zinc-500 font-mono">{barCount} bars • Capital.com</span>
                    )}
                    {livePrice && (
                        <span className="font-mono font-black text-lg text-white">
                            ${livePrice.toFixed(2)}
                        </span>
                    )}
                </div>
            </div>

            {/* Chart */}
            <div className="relative">
                <div
                    ref={chartContainerRef}
                    className="w-full rounded-xl overflow-hidden border border-white/10 bg-zinc-950"
                />
                {chartLoading && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950 rounded-xl border border-white/10" style={{ minHeight: 350 }}>
                        <div className="relative mb-4">
                            <div className="w-12 h-12 rounded-full bg-violet-500/10 flex items-center justify-center">
                                <svg className="w-6 h-6 text-violet-400 animate-pulse" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                                </svg>
                            </div>
                            <div className="absolute -inset-1 rounded-full border border-violet-500/20 animate-ping" style={{ animationDuration: '2s' }} />
                        </div>
                        <div className="w-32 h-1 rounded-full bg-zinc-800 overflow-hidden mb-3">
                            <div className="h-full bg-gradient-to-r from-violet-500/0 via-violet-500 to-violet-500/0 animate-[shimmer_1.5s_ease-in-out_infinite]"
                                style={{ width: '50%', animation: 'shimmer 1.5s ease-in-out infinite' }} />
                        </div>
                        <span className="text-[11px] text-zinc-600 font-mono tracking-wider">LOADING CHART</span>
                    </div>
                )}
            </div>

            {/* Data source note */}
            {chartError && (
                <div className="text-[10px] text-amber-500/80 font-mono text-center">{chartError}</div>
            )}

            {/* Price Ladder */}
            {card && (() => {
                // Primary source: technicalStructure
                let supZones = parseZones(card.technicalStructure?.majorSupport);
                let resZones = parseZones(card.technicalStructure?.majorResistance);

                // Fallback: parse S_Levels/R_Levels from screener_briefing text
                if (supZones.length === 0 || resZones.length === 0) {
                    const briefing = typeof card.screener_briefing === 'string' ? card.screener_briefing : '';
                    if (supZones.length === 0) {
                        const sMatch = briefing.match(/S_Levels?:\s*\[?([^\]\n]+)/i);
                        if (sMatch) supZones = sMatch[1].split(',').map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                    }
                    if (resZones.length === 0) {
                        const rMatch = briefing.match(/R_Levels?:\s*\[?([^\]\n]+)/i);
                        if (rMatch) resZones = rMatch[1].split(',').map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                    }
                }

                if (supZones.length === 0 && resZones.length === 0) return null;

                // Parse prices and build a sorted ladder
                const parsePrice = (s: string) => {
                    const m = s.match(/\$?([\d,.]+)/);
                    return m ? parseFloat(m[1].replace(',', '')) : null;
                };
                const allLevels: { price: number; label: string; type: 'R' | 'S' }[] = [];
                resZones.forEach((z: string) => { const p = parsePrice(z); if (p) allLevels.push({ price: p, label: z, type: 'R' }); });
                supZones.forEach((z: string) => { const p = parsePrice(z); if (p) allLevels.push({ price: p, label: z, type: 'S' }); });
                allLevels.sort((a, b) => b.price - a.price);

                // Find where current price fits
                const now = livePrice ?? 0;
                let insertIdx = allLevels.findIndex(l => l.price < now);
                if (insertIdx === -1) insertIdx = allLevels.length;

                return (
                    <div className="rounded-xl border border-white/10 overflow-hidden">
                        <button
                            onClick={() => setShowLevels(!showLevels)}
                            className="w-full flex items-center justify-between px-4 py-2.5 bg-zinc-900/50 hover:bg-zinc-800/50 transition-colors cursor-pointer"
                        >
                            <span className="text-xs font-bold uppercase tracking-widest text-zinc-400 font-sans">Price Ladder</span>
                            <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${showLevels ? 'rotate-180' : ''}`} />
                        </button>
                        {showLevels && (
                            <div className="animate-in fade-in slide-in-from-top-2 duration-200">
                                {allLevels.map((lvl, i) => (
                                    <React.Fragment key={i}>
                                        {/* Insert NOW row right before first level below price */}
                                        {i === insertIdx && now > 0 && (
                                            <div className="flex items-center gap-3 px-4 py-2 bg-emerald-500/10 border-y border-emerald-500/30">
                                                <div className="w-1 h-5 rounded-full bg-emerald-400" />
                                                <span className="text-sm font-mono font-black text-emerald-400">
                                                    ${now.toFixed(2)}
                                                </span>
                                                <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60 font-mono">NOW</span>
                                            </div>
                                        )}
                                        <div className={`flex items-center gap-3 px-4 py-1.5 ${lvl.type === 'R' ? 'hover:bg-rose-500/5' : 'hover:bg-violet-500/5'
                                            } transition-colors`}>
                                            <div className={`w-1 h-4 rounded-full ${lvl.type === 'R' ? 'bg-rose-500/40' : 'bg-violet-500/40'}`} />
                                            <span className={`text-sm font-mono font-bold w-20 ${lvl.type === 'R' ? 'text-rose-400' : 'text-violet-400'
                                                }`}>
                                                ${lvl.price.toFixed(2)}
                                            </span>
                                            <span className="text-xs text-zinc-500 font-mono truncate">
                                                {lvl.label.replace(/\$?[\d,.]+\s*/, '').replace(/^\(/, '').replace(/\)$/, '')}
                                            </span>
                                        </div>
                                    </React.Fragment>
                                ))}
                                {/* NOW row at bottom if price is below all levels */}
                                {insertIdx === allLevels.length && now > 0 && (
                                    <div className="flex items-center gap-3 px-4 py-2 bg-emerald-500/10 border-t border-emerald-500/30">
                                        <div className="w-1 h-5 rounded-full bg-emerald-400" />
                                        <span className="text-sm font-mono font-black text-emerald-400">
                                            ${now.toFixed(2)}
                                        </span>
                                        <span className="text-[10px] font-bold uppercase tracking-widest text-emerald-500/60 font-mono">NOW</span>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })()}

            {/* Plan Level Cards */}
            <div className="grid grid-cols-2 gap-3">
                {/* Plan A */}
                <button
                    onClick={() => setExpandedPlan(expandedPlan === 'A' ? null : 'A')}
                    className={`text-left p-4 rounded-xl border transition-all duration-300 cursor-pointer ${planANature === 'RESISTANCE' ? 'bg-rose-500/5 border-rose-500/20 hover:border-rose-500/50 hover:bg-rose-500/10' :
                        'bg-violet-500/5 border-violet-500/20 hover:border-violet-500/50 hover:bg-violet-500/10'
                        } ${expandedPlan === 'A' ? 'col-span-2 ring-1 ring-violet-500/30' : ''}`}
                >
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-sans">
                            <Target className="w-3.5 h-3.5" /> Plan A
                        </span>
                        <div className="flex items-center gap-2">
                            {planANature && planANature !== 'UNKNOWN' && (
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${planANature === 'SUPPORT' ? 'bg-violet-500/15 text-violet-400' : 'bg-rose-500/15 text-rose-400'
                                    }`}>
                                    {planANature}
                                </span>
                            )}
                            <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${expandedPlan === 'A' ? 'rotate-180' : ''}`} />
                        </div>
                    </div>
                    <div className="font-mono font-black text-2xl text-white mb-1">
                        {planALevel !== null && planALevel !== undefined ? `$${planALevel.toFixed(2)}` : 'N/A'}
                    </div>
                    {expandedPlan !== 'A' && planAText && (
                        <p className="text-sm text-zinc-400 leading-relaxed line-clamp-1">{planAText}</p>
                    )}
                    {expandedPlan !== 'A' && distA !== null && (
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2">
                            <ArrowUpDown className="w-3.5 h-3.5" />
                            <span className="font-mono">${distA.toFixed(2)} away</span>
                        </div>
                    )}
                    {expandedPlan === 'A' && (
                        <PlanDetailSection plan={card?.openingTradePlan} fallbackText={planAText} dist={distA} />
                    )}
                </button>

                {/* Plan B */}
                <button
                    onClick={() => setExpandedPlan(expandedPlan === 'B' ? null : 'B')}
                    className={`text-left p-4 rounded-xl border transition-all duration-300 cursor-pointer ${planBNature === 'RESISTANCE' ? 'bg-rose-500/5 border-rose-500/20 hover:border-rose-500/50 hover:bg-rose-500/10' :
                        'bg-violet-500/5 border-violet-500/20 hover:border-violet-500/50 hover:bg-violet-500/10'
                        } ${expandedPlan === 'B' ? 'col-span-2 ring-1 ring-indigo-500/30' : ''}`}
                >
                    <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-sans">
                            <Target className="w-3.5 h-3.5" /> Plan B
                        </span>
                        <div className="flex items-center gap-2">
                            {planBNature && planBNature !== 'UNKNOWN' && (
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${planBNature === 'SUPPORT' ? 'bg-violet-500/15 text-violet-400' : 'bg-rose-500/15 text-rose-400'
                                    }`}>
                                    {planBNature}
                                </span>
                            )}
                            <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${expandedPlan === 'B' ? 'rotate-180' : ''}`} />
                        </div>
                    </div>
                    <div className="font-mono font-black text-2xl text-white mb-1">
                        {planBLevel !== null && planBLevel !== undefined ? `$${planBLevel.toFixed(2)}` : 'N/A'}
                    </div>
                    {expandedPlan !== 'B' && planBText && (
                        <p className="text-sm text-zinc-400 leading-relaxed line-clamp-1">{planBText}</p>
                    )}
                    {expandedPlan !== 'B' && distB !== null && (
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-2">
                            <ArrowUpDown className="w-3.5 h-3.5" />
                            <span className="font-mono">${distB.toFixed(2)} away</span>
                        </div>
                    )}
                    {expandedPlan === 'B' && (
                        <PlanDetailSection plan={card?.alternativePlan} fallbackText={planBText} dist={distB} />
                    )}
                </button>
            </div>

            {/* Read Screener Briefing Button */}
            {onShowBriefing && (
                <button
                    onClick={onShowBriefing}
                    className="w-full flex items-center justify-center gap-3 py-3.5 bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 hover:border-violet-500/40 rounded-xl text-violet-400 font-bold text-sm tracking-wide transition-all duration-300 group"
                >
                    <BookOpen className="w-4 h-4 group-hover:scale-110 transition-transform" />
                    Read Screener Briefing
                </button>
            )}
        </div>
    );
}

/**
 * Renders full plan details: name, trigger, abort, target flow, description.
 */
function PlanDetailSection({ plan, fallbackText, dist }: { plan: any; fallbackText?: string; dist: number | null }) {
    return (
        <div className="mt-3 space-y-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
            {/* Description (only if no structured plan data) */}
            {fallbackText && (
                <p className="text-base text-zinc-400 leading-relaxed font-mono font-medium">{fallbackText}</p>
            )}

            {/* Trigger */}
            {plan?.trigger && (
                <div className="bg-white/5 p-3 rounded-lg border border-white/5 space-y-1.5">
                    <div className="flex items-center gap-2">
                        <Crosshair className="w-3.5 h-3.5 text-violet-400" />
                        <span className="text-xs font-bold uppercase text-zinc-500 tracking-widest font-mono">Trigger</span>
                    </div>
                    <p className="text-sm text-zinc-200 leading-relaxed font-mono font-medium">{plan.trigger}</p>
                </div>
            )}

            <div className="grid grid-cols-2 gap-2">
                {/* Abort / Invalidation */}
                {plan?.invalidation && (
                    <div className="bg-rose-500/5 p-3 rounded-lg border border-rose-500/10 space-y-1.5">
                        <div className="flex items-center gap-1.5">
                            <ShieldAlert className="w-3.5 h-3.5 text-rose-500/60" />
                            <span className="text-xs font-bold uppercase text-rose-500/50 tracking-widest font-mono">Abort</span>
                        </div>
                        <p className="text-sm text-rose-200/80 font-mono font-medium">{plan.invalidation}</p>
                    </div>
                )}

                {/* Target Flow / Expected Participant */}
                {(plan?.expectedParticipant || plan?.scenario) && (
                    <div className="bg-emerald-500/5 p-3 rounded-lg border border-emerald-500/10 space-y-1.5">
                        <div className="flex items-center gap-1.5">
                            <Activity className="w-3.5 h-3.5 text-emerald-500/60" />
                            <span className="text-xs font-bold uppercase text-emerald-500/50 tracking-widest font-mono">Target Flow</span>
                        </div>
                        <p className="text-sm text-emerald-200/80 font-mono font-medium">{plan.expectedParticipant || plan.scenario}</p>
                    </div>
                )}
            </div>

            {/* Distance */}
            {dist !== null && (
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <ArrowUpDown className="w-3.5 h-3.5" />
                    <span className="font-mono">${dist.toFixed(2)} away from current price</span>
                </div>
            )}

            <div className="text-[10px] text-zinc-600 text-center pt-1 font-mono">Tap to close</div>
        </div>
    );
}

/**
 * Parser for structural zones like "$305.50 (Prior Floor), $303 (Critical Support)"
 */
function parseZones(text: string | undefined): string[] {
    if (!text || text === 'None' || text === 'none' || text === 'N/A') return [];
    const clean = text.replace(/[\[\]]/g, '');
    const levels = clean.split(/,(?![^(]*\))/);
    return levels.map(l => l.trim()).filter(l => l.length > 0 && l !== 'None' && l !== 'N/A');
}

/**
 * Fallback: Generate synthetic candles when Capital.com is unavailable.
 */
function generateFallbackData(
    series: any,
    planA: number | null,
    planB: number | null,
    livePrice: number | null,
) {
    const prices = [planA, planB, livePrice].filter((p): p is number => p !== null && p !== undefined);
    if (prices.length === 0) return;

    const center = prices.reduce((a, b) => a + b, 0) / prices.length;
    const range = Math.max(...prices) - Math.min(...prices);
    const volatility = Math.max(range * 0.15, center * 0.005);

    const candles: any[] = [];
    const now = Math.floor(Date.now() / 1000);
    let price = center - range * 0.3;

    for (let i = 0; i < 60; i++) {
        const time = now - (60 - i) * 300;
        const change = (Math.random() - 0.48) * volatility;
        const open = price;
        const close = open + change;
        const high = Math.max(open, close) + Math.random() * volatility * 0.5;
        const low = Math.min(open, close) - Math.random() * volatility * 0.5;
        candles.push({ time, open, high, low, close });
        price = close;
    }

    if (livePrice && candles.length > 0) {
        const last = candles[candles.length - 1];
        last.close = livePrice;
        last.high = Math.max(last.high, livePrice);
        last.low = Math.min(last.low, livePrice);
    }

    series.setData(candles);
}
