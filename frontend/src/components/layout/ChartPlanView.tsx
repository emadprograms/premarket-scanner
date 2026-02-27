"use client";

import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ColorType, CandlestickSeries } from 'lightweight-charts';
import { Badge } from '@/components/ui/core';
import { getChartBars } from '@/lib/api';
import {
    Target,
    BookOpen,
    ArrowUpDown,
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
    onShowBriefing,
}: ChartPlanViewProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const [chartLoading, setChartLoading] = useState(true);
    const [chartError, setChartError] = useState<string | null>(null);
    const [barCount, setBarCount] = useState(0);

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
                },
                timeScale: {
                    borderColor: 'rgba(255,255,255,0.1)',
                    timeVisible: true,
                    secondsVisible: false,
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
                // Use real Capital.com data
                series.setData(bars);
                setBarCount(bars.length);
            } else {
                // Fallback: generate synthetic candles around plan levels
                setChartError('Capital.com data unavailable — showing estimated levels');
                generateFallbackData(series, planALevel, planBLevel, livePrice ?? null);
                setBarCount(0);
            }

            // Plot Plan A line
            if (planALevel !== null && planALevel !== undefined) {
                series.createPriceLine({
                    price: planALevel,
                    color: planANature === 'SUPPORT' ? '#22c55e' : planANature === 'RESISTANCE' ? '#ef4444' : '#8b5cf6',
                    lineWidth: 2,
                    lineStyle: 0,
                    axisLabelVisible: true,
                    title: `PLAN A — $${planALevel.toFixed(2)}`,
                });
            }

            // Plot Plan B line
            if (planBLevel !== null && planBLevel !== undefined) {
                series.createPriceLine({
                    price: planBLevel,
                    color: planBNature === 'SUPPORT' ? '#22c55e' : planBNature === 'RESISTANCE' ? '#ef4444' : '#6366f1',
                    lineWidth: 2,
                    lineStyle: 2,
                    axisLabelVisible: true,
                    title: `PLAN B — $${planBLevel.toFixed(2)}`,
                });
            }

            // Plot live price line
            if (livePrice) {
                series.createPriceLine({
                    price: livePrice,
                    color: '#fbbf24',
                    lineWidth: 1,
                    lineStyle: 1,
                    axisLabelVisible: true,
                    title: `NOW $${livePrice.toFixed(2)}`,
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

            {/* Plan Level Cards */}
            <div className="grid grid-cols-2 gap-3">
                {/* Plan A */}
                <div className={`p-3 rounded-xl border space-y-1.5 ${planANature === 'SUPPORT' ? 'bg-emerald-500/5 border-emerald-500/20' :
                    planANature === 'RESISTANCE' ? 'bg-rose-500/5 border-rose-500/20' :
                        'bg-violet-500/5 border-violet-500/20'
                    }`}>
                    <div className="flex items-center justify-between">
                        <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1">
                            <Target className="w-3 h-3" /> Plan A
                        </span>
                        {planANature && planANature !== 'UNKNOWN' && (
                            <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded-full ${planANature === 'SUPPORT' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                                }`}>
                                {planANature}
                            </span>
                        )}
                    </div>
                    <div className="font-mono font-black text-lg text-white">
                        {planALevel !== null && planALevel !== undefined ? `$${planALevel.toFixed(2)}` : 'N/A'}
                    </div>
                    {planAText && (
                        <p className="text-[11px] text-zinc-400 leading-snug line-clamp-2">{planAText}</p>
                    )}
                    {distA !== null && (
                        <div className="flex items-center gap-1 text-[9px] text-muted-foreground">
                            <ArrowUpDown className="w-3 h-3" />
                            <span className="font-mono">${distA.toFixed(2)} away</span>
                        </div>
                    )}
                </div>

                {/* Plan B */}
                <div className={`p-3 rounded-xl border space-y-1.5 ${planBNature === 'SUPPORT' ? 'bg-emerald-500/5 border-emerald-500/20' :
                    planBNature === 'RESISTANCE' ? 'bg-rose-500/5 border-rose-500/20' :
                        'bg-indigo-500/5 border-indigo-500/20'
                    }`}>
                    <div className="flex items-center justify-between">
                        <span className="text-[9px] font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1">
                            <Target className="w-3 h-3" /> Plan B
                        </span>
                        {planBNature && planBNature !== 'UNKNOWN' && (
                            <span className={`text-[8px] font-bold px-1.5 py-0.5 rounded-full ${planBNature === 'SUPPORT' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-rose-500/15 text-rose-400'
                                }`}>
                                {planBNature}
                            </span>
                        )}
                    </div>
                    <div className="font-mono font-black text-lg text-white">
                        {planBLevel !== null && planBLevel !== undefined ? `$${planBLevel.toFixed(2)}` : 'N/A'}
                    </div>
                    {planBText && (
                        <p className="text-[11px] text-zinc-400 leading-snug line-clamp-2">{planBText}</p>
                    )}
                    {distB !== null && (
                        <div className="flex items-center gap-1 text-[9px] text-muted-foreground">
                            <ArrowUpDown className="w-3 h-3" />
                            <span className="font-mono">${distB.toFixed(2)} away</span>
                        </div>
                    )}
                </div>
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
