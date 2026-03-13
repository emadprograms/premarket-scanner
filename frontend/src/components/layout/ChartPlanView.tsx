"use client";

import React, { useEffect, useRef, useState } from 'react';
import { createChart, IChartApi, ColorType, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { Badge } from '@/components/ui/core';
import { getChartBars, getYahooChartBars } from '@/lib/api';
import { useMission } from '@/lib/context';
import {
    Target,
    BookOpen,
    ArrowUpDown,
    ChevronDown,
    ChevronRight,
    ShieldAlert,
    Activity,
    Crosshair,
    Maximize2,
    Minimize2,
} from 'lucide-react';

// Module-level constants (never re-created on render)
const LOOKBACK: Record<string, Record<string, number>> = {
    capital: { MINUTE: 1, MINUTE_5: 3, MINUTE_30: 14, HOUR: 31, HOUR_4: 31, DAY: 365 },
    yahoo:   { MINUTE: 7, MINUTE_5: 60, MINUTE_30: 60, HOUR: 730, HOUR_4: 730, DAY: 3650 },
};
const RESOLUTION_LABELS: { key: string; label: string }[] = [
    { key: 'MINUTE', label: '1m' },
    { key: 'MINUTE_5', label: '5m' },
    { key: 'MINUTE_30', label: '30m' },
    { key: 'HOUR', label: '1H' },
    { key: 'HOUR_4', label: '4H' },
    { key: 'DAY', label: '1D' },
];

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
    positionSize?: number | null;
    isBreached?: boolean;
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
    positionSize,
    isBreached,
}: ChartPlanViewProps) {
    const { settings: missionSettings } = useMission();
    const chartDefaults = missionSettings.chartDefaults;
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<any>(null);
    const cleanupRef = useRef<(() => void) | null>(null);
    const vpCleanupRef = useRef<(() => void) | null>(null);
    const vpCanvasRef = useRef<HTMLCanvasElement | null>(null);
    const chartWrapperRef = useRef<HTMLDivElement | null>(null);
    const [chartLoading, setChartLoading] = useState(true);
    const [chartError, setChartError] = useState<string | null>(null);
    const [barCount, setBarCount] = useState(0);
    const [isFullscreen, setIsFullscreen] = useState(false);
    const [expandedPlan, setExpandedPlan] = useState<'A' | 'B' | null>(null);
    const [showLevels, setShowLevels] = useState(true);
    const [ladderOpen, setLadderOpen] = useState(false);
    const [dataSource, setDataSource] = useState<'capital' | 'yahoo'>(chartDefaults.dataSource);
    const [chartSource, setChartSource] = useState<'capital' | 'yahoo'>(chartDefaults.dataSource);
    const [resolution, setResolution] = useState(chartDefaults.resolution);
    const [session, setSession] = useState<'ETH' | 'RTH'>(chartDefaults.session);
    const [technicals, setTechnicals] = useState<Set<string>>(new Set(chartDefaults.vpEnabled ? ['vp'] : []));
    const [highContrast, setHighContrast] = useState(chartDefaults.highContrast);
    const barsRef = useRef<any[]>([]);

    const toggleTechnical = (key: string) => {
        setTechnicals(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const toggleFullscreen = () => {
        if (!chartWrapperRef.current) return;
        if (!document.fullscreenElement) {
            chartWrapperRef.current.requestFullscreen().catch(() => {});
        } else {
            document.exitFullscreen().catch(() => {});
        }
    };

    // Track fullscreen state changes (including Esc key exits)
    useEffect(() => {
        const handleFSChange = () => setIsFullscreen(!!document.fullscreenElement);
        document.addEventListener('fullscreenchange', handleFSChange);
        return () => document.removeEventListener('fullscreenchange', handleFSChange);
    }, []);

    // Fetch real bars and build chart
    useEffect(() => {
        if (!chartContainerRef.current) return;
        let cancelled = false;

        const buildChart = async () => {
            setChartLoading(true);
            setChartError(null);

            // Fetch bars based on selected source
            let bars: any[] = [];
            const days = LOOKBACK[dataSource]?.[resolution] || 3;
            try {
                if (dataSource === 'yahoo') {
                    const res = await getYahooChartBars(ticker, days, resolution);
                    if (res.status === 'success' && res.data?.bars?.length > 0) {
                        bars = res.data.bars;
                        setChartSource('yahoo');
                    }
                } else {
                    const res = await getChartBars(ticker, days, resolution);
                    if (res.status === 'success' && res.data?.bars?.length > 0) {
                        bars = res.data.bars;
                        setChartSource('capital');
                    }
                }
            } catch (e) {
                // Handled below via empty bars array
            }

            // Filter to RTH (9:30-16:00 ET) if session is RTH
            // Skip for DAY resolution — daily bars have no intraday session concept
            if (session === 'RTH' && bars.length > 0 && resolution !== 'DAY') {
                const getETOffsetHours = () => {
                    const now = new Date();
                    const nyH = parseInt(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: 'numeric', hourCycle: 'h23' }).format(now));
                    const utcH = parseInt(new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', hour: 'numeric', hourCycle: 'h23' }).format(now));
                    let diff = nyH - utcH;
                    if (diff > 12) diff -= 24;
                    if (diff < -12) diff += 24;
                    return diff;
                };
                const etOff = getETOffsetHours();
                const filtered = bars.filter((bar: any) => {
                    const d = new Date(bar.time * 1000);
                    const etHour = (d.getUTCHours() + 24 + etOff) % 24;
                    const etMin = d.getUTCMinutes();
                    const etTime = etHour + etMin / 60;
                    return etTime >= 9.5 && etTime < 16;
                });
                // Safety: if filter removed ALL bars, fall back to ETH
                if (filtered.length > 0) {
                    bars = filtered;
                } else {
                    console.warn('RTH filter removed all bars — falling back to ETH');
                }
            }

            if (cancelled || !chartContainerRef.current) return;

            const chart = createChart(chartContainerRef.current, {
                layout: {
                    background: { type: ColorType.Solid, color: highContrast ? '#d4d4d4' : '#09090b' },
                    textColor: highContrast ? '#27272a' : '#a1a1aa',
                    fontSize: 11,
                },
                grid: {
                    vertLines: { color: highContrast ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.03)' },
                    horzLines: { color: highContrast ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.03)' },
                },
                crosshair: {
                    mode: 0,
                    vertLine: { color: highContrast ? 'rgba(0,0,0,0.8)' : 'rgba(139,92,246,0.6)', width: 1 },
                    horzLine: { color: highContrast ? 'rgba(0,0,0,0.8)' : 'rgba(139,92,246,0.6)', width: 1 },
                },
                rightPriceScale: {
                    borderColor: highContrast ? 'rgba(0,0,0,0.2)' : 'rgba(255,255,255,0.1)',
                    scaleMargins: { top: 0.1, bottom: 0.1 },
                },
                timeScale: {
                    borderColor: highContrast ? 'rgba(0,0,0,0.2)' : 'rgba(255,255,255,0.1)',
                    timeVisible: true,
                    secondsVisible: false,
                    rightOffset: 5,
                    barSpacing: 12,
                },
                width: chartContainerRef.current.clientWidth - 2,
                height: document.fullscreenElement ? (chartContainerRef.current.clientHeight || 500) : 500,
            });

            const series = chart.addSeries(CandlestickSeries, {
                upColor: highContrast ? '#ffffff' : '#22c55e',
                downColor: highContrast ? '#171717' : '#ef4444',
                borderUpColor: highContrast ? '#000000' : '#22c55e',
                borderDownColor: highContrast ? '#000000' : '#ef4444',
                wickUpColor: highContrast ? '#000000' : '#22c55e',
                wickDownColor: highContrast ? '#000000' : '#ef4444',
            });
            seriesRef.current = series;

            if (bars.length > 0) {
                series.setData(bars);
                setBarCount(bars.length);
                barsRef.current = bars;

                // Add session background bands: pre-market (amber) + post-market (blue)
                // Classify bars by session and create colored background rectangles via histogram
                // Dynamic ET offset calculation (handles DST automatically)
                const getETOffset = () => {
                    const now = new Date();
                    const nyTime = new Intl.DateTimeFormat('en-US', {
                        timeZone: 'America/New_York',
                        hour: 'numeric',
                        hour12: false
                    }).format(now);
                    const utcTime = new Intl.DateTimeFormat('en-US', {
                        timeZone: 'UTC',
                        hour: 'numeric',
                        hour12: false
                    }).format(now);
                    let diff = parseInt(nyTime) - parseInt(utcTime);
                    if (diff > 12) diff -= 24;
                    if (diff < -12) diff += 24;
                    return diff * 3600;
                };
                const ET_OFFSET = getETOffset();
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

                // Scroll to the most recent bars — candle width stays fixed via barSpacing
                chart.timeScale().scrollToRealTime();
            } else {
                setChartError(`${dataSource === 'yahoo' ? 'Yahoo Finance' : 'Capital.com'} data unavailable — showing estimated levels`);
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
                        // Ultra-robust: handles **S_Levels**, S-Levels, S Levels, multi-line brackets, or no brackets
                        const sMatch = briefing.match(/(?:\*\*|__)?S[_\-\s]Levels?(?:\*\*|__)?[:\-\=]?\s*(?:\[([\s\S]*?)\]|([^\n\r]+))/i);
                        const sRaw = sMatch ? (sMatch[1] || sMatch[2]) : '';
                        if (sRaw) supZones = sRaw.split(/[,;|]/).map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                    }
                    if (resZones.length === 0) {
                        const rMatch = briefing.match(/(?:\*\*|__)?R[_\-\s]Levels?(?:\*\*|__)?[:\-\=]?\s*(?:\[([\s\S]*?)\]|([^\n\r]+))/i);
                        const rRaw = rMatch ? (rMatch[1] || rMatch[2]) : '';
                        if (rRaw) resZones = rRaw.split(/[,;|]/).map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
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
                    const rColor = highContrast ? 'rgba(239, 68, 68, 0.7)' : 'rgba(239, 68, 68, 0.4)';
                    const sColor = highContrast ? 'rgba(139, 92, 246, 0.7)' : 'rgba(139, 92, 246, 0.4)';
                    series.createPriceLine({
                        price,
                        color: type === 'R' ? rColor : sColor,
                        lineWidth: 1,
                        lineStyle: 3, // Dotted
                        axisLabelVisible: false,
                        title: '',
                    });
                });
            }

            chartRef.current = chart;
            setChartLoading(false);

            // Resize handler — updates both width and height for fullscreen support
            const handleResize = () => {
                if (chartContainerRef.current) {
                    const w = chartContainerRef.current.clientWidth - 2; // 2px buffer to prevent price scale clipping
                    const inFullscreen = !!document.fullscreenElement;
                    const h = inFullscreen ? (chartContainerRef.current.clientHeight || 500) : 500;
                    chart.applyOptions({ width: w, height: h });
                }
            };
            window.addEventListener('resize', handleResize);
            const fullscreenTimers: ReturnType<typeof setTimeout>[] = [];
            const handleFullscreen = () => {
                // Fire at multiple intervals to guarantee CSS reflow has completed
                fullscreenTimers.push(setTimeout(handleResize, 50));
                fullscreenTimers.push(setTimeout(handleResize, 150));
                fullscreenTimers.push(setTimeout(handleResize, 300));
            };
            document.addEventListener('fullscreenchange', handleFullscreen);

            // Store cleanup in ref (not on DOM — DOM can detach on re-render)
            cleanupRef.current = () => {
                window.removeEventListener('resize', handleResize);
                document.removeEventListener('fullscreenchange', handleFullscreen);
                fullscreenTimers.forEach(clearTimeout);
                chart.remove();
                chartRef.current = null;
            };
        };

        buildChart();

        return () => {
            cancelled = true;
            if (cleanupRef.current) {
                cleanupRef.current();
                cleanupRef.current = null;
            }
        };
    }, [ticker, dataSource, resolution, session, highContrast]);

    // Volume Profile — canvas-based horizontal bars on the left of the chart
    useEffect(() => {
        // Cleanup previous VP
        if (vpCleanupRef.current) {
            vpCleanupRef.current();
            vpCleanupRef.current = null;
        }

        if (!technicals.has('vp') || !chartRef.current || !seriesRef.current || barsRef.current.length === 0 || !vpCanvasRef.current) return;

        const chart = chartRef.current;
        const series = seriesRef.current;
        const canvas = vpCanvasRef.current;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const VP_MAX_WIDTH = 120; // max width of biggest bar in pixels
        const BUCKET_COUNT = 70;

        const computeAndRenderVP = () => {
            const visibleRange = chart.timeScale().getVisibleLogicalRange();
            if (!visibleRange) return;
            const from = Math.max(0, Math.floor(visibleRange.from));
            const to = Math.min(barsRef.current.length - 1, Math.ceil(visibleRange.to));
            if (from >= to) return;

            const visibleBars = barsRef.current.slice(from, to + 1);

            // Find price range
            let minP = Infinity, maxP = -Infinity;
            for (const b of visibleBars) {
                if (b.low < minP) minP = b.low;
                if (b.high > maxP) maxP = b.high;
            }
            if (minP >= maxP) return;

            // Bucket volume
            const step = (maxP - minP) / BUCKET_COUNT;
            const buckets = new Array(BUCKET_COUNT).fill(0);

            for (const b of visibleBars) {
                const vol = b.volume || 1;
                const bLow = Math.max(0, Math.floor((b.low - minP) / step));
                const bHigh = Math.min(BUCKET_COUNT - 1, Math.floor((b.high - minP) / step));
                const spread = Math.max(1, bHigh - bLow + 1);
                for (let i = bLow; i <= bHigh; i++) {
                    buckets[i] += vol / spread;
                }
            }

            const maxVol = Math.max(...buckets);
            if (maxVol === 0) return;
            const pocIdx = buckets.indexOf(maxVol);

            // Size canvas to chart
            const chartEl = chartContainerRef.current;
            if (!chartEl) return;
            const rect = chartEl.getBoundingClientRect();
            const dpr = window.devicePixelRatio || 1;
            canvas.width = VP_MAX_WIDTH * dpr;
            canvas.height = rect.height * dpr;
            canvas.style.width = VP_MAX_WIDTH + 'px';
            canvas.style.height = rect.height + 'px';
            ctx.scale(dpr, dpr);

            // Clear
            ctx.clearRect(0, 0, VP_MAX_WIDTH, rect.height);

            // Draw horizontal bars
            for (let i = 0; i < BUCKET_COUNT; i++) {
                const priceTop = minP + (i + 1) * step;
                const priceBot = minP + i * step;

                const yTop = series.priceToCoordinate(priceTop);
                const yBot = series.priceToCoordinate(priceBot);
                if (yTop === null || yBot === null) continue;

                const barHeight = Math.max(1, Math.abs(yBot - yTop) - 0.5);
                const y = Math.min(yTop, yBot);
                const normalizedVol = buckets[i] / maxVol;
                const barWidth = normalizedVol * VP_MAX_WIDTH;

                if (barWidth < 1) continue;

                const isPOC = i === pocIdx;
                if (isPOC) {
                    ctx.fillStyle = highContrast ? `rgba(50, 50, 50, 0.60)` : `rgba(251, 191, 36, 0.60)`;
                } else {
                    ctx.fillStyle = highContrast
                        ? `rgba(80, 80, 80, ${0.20 + normalizedVol * 0.35})`
                        : `rgba(139, 92, 246, ${0.20 + normalizedVol * 0.35})`;
                }
                ctx.fillRect(0, y, barWidth, barHeight);
            }

            // Reset transform for next render
            ctx.setTransform(1, 0, 0, 1, 0, 0);
        };

        // Initial render
        const timer = setTimeout(computeAndRenderVP, 200);

        // Dynamic recalculation on scroll/zoom
        chart.timeScale().subscribeVisibleLogicalRangeChange(computeAndRenderVP);

        // Also rerender on cross-hair move (price scale changes affect Y coordinates)
        const handleCrosshair = () => computeAndRenderVP();
        chart.subscribeCrosshairMove(handleCrosshair);

        vpCleanupRef.current = () => {
            clearTimeout(timer);
            try { chart.timeScale().unsubscribeVisibleLogicalRangeChange(computeAndRenderVP); } catch {}
            try { chart.unsubscribeCrosshairMove(handleCrosshair); } catch {}
            if (ctx) {
                ctx.setTransform(1, 0, 0, 1, 0, 0);
                ctx.clearRect(0, 0, canvas.width, canvas.height);
            }
        };

        return () => {
            if (vpCleanupRef.current) {
                vpCleanupRef.current();
                vpCleanupRef.current = null;
            }
        };
    }, [technicals, chartLoading, highContrast]);

    const bias = setupBias || 'Neutral';
    const isBullish = /bull|long/i.test(bias);
    const isBearish = /bear|short/i.test(bias);

    const distA = (livePrice && planALevel) ? Math.abs(livePrice - planALevel) : null;
    const distB = (livePrice && planBLevel) ? Math.abs(livePrice - planBLevel) : null;

    return (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
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
                <div className="flex flex-col items-end gap-1">
                    {livePrice && (
                        <span className="font-mono font-black text-lg text-white">
                            ${livePrice.toFixed(2)}
                        </span>
                    )}
                </div>
            </div>

            {/* Timeframe + Data Source Row — wrapped with chart for fullscreen */}
            <div ref={chartWrapperRef} className={`${isFullscreen ? 'bg-zinc-950 flex flex-col h-screen' : ''}`}>
            <div className={`flex items-center justify-between ${isFullscreen ? 'px-4 pt-3 pb-2' : ''}`}>
                {/* Timeframe Selector — LEFT */}
                <div className="flex items-center gap-2">
                    <div className="flex items-center bg-zinc-900/50 p-1 rounded-lg border border-white/5">
                        {RESOLUTION_LABELS.map(({ key, label }) => (
                            <button
                                key={key}
                                onClick={() => setResolution(key)}
                                className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${resolution === key
                                    ? 'bg-violet-500/20 text-violet-400 shadow-sm'
                                    : 'text-zinc-500 hover:text-zinc-300'
                                    }`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <div className="flex items-center bg-zinc-900/50 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => setSession('ETH')}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${session === 'ETH'
                                ? 'bg-amber-500/20 text-amber-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            ETH
                        </button>
                        <button
                            onClick={() => setSession('RTH')}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${session === 'RTH'
                                ? 'bg-emerald-500/20 text-emerald-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            RTH
                        </button>
                    </div>
                    <div className="flex items-center bg-zinc-900/50 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => toggleTechnical('vp')}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${technicals.has('vp')
                                ? 'bg-violet-500/20 text-violet-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            VP
                        </button>
                        <button
                            onClick={() => setHighContrast(prev => !prev)}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${highContrast
                                ? 'bg-amber-500/20 text-amber-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            HC
                        </button>
                    </div>
                </div>

                {/* Position Size — CENTER */}
                {(positionSize !== null && positionSize !== undefined) || isBreached ? (
                    <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-zinc-900/50 border border-white/5">
                        <ArrowUpDown className="w-3.5 h-3.5 text-zinc-500" />
                        <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">Size:</span>
                        {isBreached ? (
                            <span className="text-[11px] font-mono font-bold text-zinc-400">N/A</span>
                        ) : positionSize ? (
                            <span className="text-[11px] font-mono font-bold text-violet-400">{positionSize}</span>
                        ) : null}
                    </div>
                ) : null}

                {/* Data Source + Bar Count — RIGHT */}
                <div className="flex items-center gap-2">
                    {barCount > 0 && (
                        <span className="text-[10px] text-zinc-500 font-mono">{barCount} bars</span>
                    )}
                    <div className="flex items-center bg-zinc-900/50 p-1 rounded-lg border border-white/5">
                        <button
                            onClick={() => setDataSource('capital')}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${dataSource === 'capital'
                                ? 'bg-violet-500/20 text-violet-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            Capital
                        </button>
                        <button
                            onClick={() => setDataSource('yahoo')}
                            className={`px-2.5 py-1 text-[10px] uppercase tracking-wider font-bold rounded-md transition-all ${dataSource === 'yahoo'
                                ? 'bg-indigo-500/20 text-indigo-400 shadow-sm'
                                : 'text-zinc-500 hover:text-zinc-300'
                                }`}
                        >
                            Yahoo
                        </button>
                    </div>
                </div>
            </div>

            {/* Chart */}
            <div className={`relative ${isFullscreen ? 'flex-1' : ''}`}>
                <canvas
                    ref={vpCanvasRef}
                    className="absolute left-0 top-0 z-10 pointer-events-none"
                    style={{ borderRadius: '0.75rem 0 0 0.75rem' }}
                />
                <div
                    ref={chartContainerRef}
                    className="w-full rounded-xl overflow-hidden border border-white/10 bg-zinc-950"
                    style={{ minHeight: isFullscreen ? undefined : 500, height: isFullscreen ? '100%' : undefined }}
                />
                {/* Fullscreen toggle */}
                <button
                    onClick={toggleFullscreen}
                    className="absolute top-2 right-2 z-20 p-1.5 rounded-lg bg-zinc-900/80 border border-white/10 text-zinc-400 hover:text-white hover:bg-zinc-800 transition-all"
                    title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                >
                    {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                {chartLoading && (
                    <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950 rounded-xl border border-white/10" style={{ minHeight: 500 }}>
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

                {/* Price Ladder — sidebar overlay */}
                {card && (() => {
                    let supZones = parseZones(card.technicalStructure?.majorSupport);
                    let resZones = parseZones(card.technicalStructure?.majorResistance);
                    if (supZones.length === 0 || resZones.length === 0) {
                        const briefing = typeof card.screener_briefing === 'string' ? card.screener_briefing : '';
                        if (supZones.length === 0) {
                            const sMatch = briefing.match(/(?:\*\*|__)?S[_\-\s]Levels?(?:\*\*|__)?[:\-\=]?\s*(?:\[([\s\S]*?)\]|([^\n\r]+))/i);
                            const sRaw = sMatch ? (sMatch[1] || sMatch[2]) : '';
                            if (sRaw) supZones = sRaw.split(/[,;|]/).map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                        }
                        if (resZones.length === 0) {
                            const rMatch = briefing.match(/(?:\*\*|__)?R[_\-\s]Levels?(?:\*\*|__)?[:\-\=]?\s*(?:\[([\s\S]*?)\]|([^\n\r]+))/i);
                            const rRaw = rMatch ? (rMatch[1] || rMatch[2]) : '';
                            if (rRaw) resZones = rRaw.split(/[,;|]/).map((s: string) => s.trim()).filter((s: string) => s && s !== 'None' && /\d/.test(s));
                        }
                    }
                    if (supZones.length === 0 && resZones.length === 0) return null;

                    const parsePrice = (s: string) => {
                        const m = s.match(/\$?([\d,.]+)/);
                        return m ? parseFloat(m[1].replace(',', '')) : null;
                    };
                    const allLevels: { price: number; label: string; type: 'R' | 'S' }[] = [];
                    resZones.forEach((z: string) => { const p = parsePrice(z); if (p) allLevels.push({ price: p, label: z, type: 'R' }); });
                    supZones.forEach((z: string) => { const p = parsePrice(z); if (p) allLevels.push({ price: p, label: z, type: 'S' }); });
                    allLevels.sort((a, b) => b.price - a.price);
                    const now = livePrice ?? 0;
                    let insertIdx = allLevels.findIndex(l => l.price < now);
                    if (insertIdx === -1) insertIdx = allLevels.length;

                    return (
                        <>
                            {/* Left sidebar toggle — top of chart */}
                            <button
                                onClick={() => setLadderOpen(!ladderOpen)}
                                className={`absolute top-2 z-30 flex items-center justify-center transition-all duration-300 ${ladderOpen ? 'left-[260px]' : 'left-0'
                                    } w-5 h-10 rounded-r-md bg-zinc-900/90 border border-l-0 border-white/10 hover:bg-zinc-800 text-zinc-400 hover:text-white backdrop-blur-sm`}
                                title={ladderOpen ? 'Close price ladder' : 'Open price ladder'}
                            >
                                <ChevronRight className={`w-3 h-3 transition-transform duration-300 ${ladderOpen ? 'rotate-180' : ''}`} />
                            </button>

                            {/* Tight sidebar panel */}
                            <div
                                className={`absolute left-0 top-0 z-20 w-[260px] bg-zinc-950/95 backdrop-blur-md border-r border-b border-white/10 rounded-tl-xl rounded-br-lg overflow-y-auto transition-transform duration-300 ease-in-out ${ladderOpen ? 'translate-x-0' : '-translate-x-full'
                                    }`}
                            >
                                <div className="py-1.5">
                                    {allLevels.map((lvl, i) => (
                                        <React.Fragment key={i}>
                                            {i === insertIdx && now > 0 && (
                                                <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border-y border-emerald-500/30">
                                                    <div className="w-0.5 h-3.5 rounded-full bg-emerald-400" />
                                                    <span className="text-xs font-mono font-black text-emerald-400">
                                                        ${now.toFixed(2)}
                                                    </span>
                                                    <span className="text-[8px] font-bold uppercase text-emerald-500/60">NOW</span>
                                                </div>
                                            )}
                                            <div className={`flex items-center gap-2 px-3 py-1 ${lvl.type === 'R' ? 'hover:bg-rose-500/5' : 'hover:bg-violet-500/5'} transition-colors`}>
                                                <div className={`w-0.5 h-3 rounded-full ${lvl.type === 'R' ? 'bg-rose-500/40' : 'bg-violet-500/40'}`} />
                                                <span className={`text-xs font-mono font-bold ${lvl.type === 'R' ? 'text-rose-400' : 'text-violet-400'}`}>
                                                    ${lvl.price.toFixed(2)}
                                                </span>
                                                <span className="text-[11px] text-zinc-500 font-mono truncate">
                                                    {lvl.label.replace(/\$?[\d,.]+\s*/, '').replace(/^\(/, '').replace(/\)$/, '')}
                                                </span>
                                            </div>
                                        </React.Fragment>
                                    ))}
                                    {insertIdx === allLevels.length && now > 0 && (
                                        <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-500/10 border-t border-emerald-500/30">
                                            <div className="w-0.5 h-3.5 rounded-full bg-emerald-400" />
                                            <span className="text-xs font-mono font-black text-emerald-400">
                                                ${now.toFixed(2)}
                                            </span>
                                            <span className="text-[8px] font-bold uppercase text-emerald-500/60">NOW</span>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </>
                    );
                })()}
            </div>

            {/* Data source note */}
            {chartError && (
                <div className="text-[10px] text-amber-500/80 font-mono text-center">{chartError}</div>
            )}
            </div>{/* end chartWrapperRef */}

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
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-sans">
                                <Target className="w-3.5 h-3.5" /> Plan A
                            </span>
                            {planANature && planANature !== 'UNKNOWN' && (
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${planANature === 'SUPPORT' ? 'bg-violet-500/15 text-violet-400' : 'bg-rose-500/15 text-rose-400'
                                    }`}>
                                    {planANature}
                                </span>
                            )}
                        </div>
                        <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${expandedPlan === 'A' ? 'rotate-180' : ''}`} />
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
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-black uppercase tracking-widest text-muted-foreground flex items-center gap-1.5 font-sans">
                                <Target className="w-3.5 h-3.5" /> Plan B
                            </span>
                            {planBNature && planBNature !== 'UNKNOWN' && (
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${planBNature === 'SUPPORT' ? 'bg-violet-500/15 text-violet-400' : 'bg-rose-500/15 text-rose-400'
                                    }`}>
                                    {planBNature}
                                </span>
                            )}
                        </div>
                        <ChevronDown className={`w-4 h-4 text-zinc-500 transition-transform duration-300 ${expandedPlan === 'B' ? 'rotate-180' : ''}`} />
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
    const levels = clean.split(/[,;|](?![^(]*\))/);
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
