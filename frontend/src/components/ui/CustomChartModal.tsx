import React, { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, LineStyle, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { Modal } from './Modal';
import { Button } from './core';
import { RefreshCw, Activity } from 'lucide-react';
import { ChartModal } from './ChartModal';

interface CustomChartModalProps {
    isOpen: boolean;
    onClose: () => void;
    ticker: string;
    marketCard: any; // Full card data for levels & plans
    simulationCutoff?: string; // Optional context time
}

export function CustomChartModal({ isOpen, onClose, ticker, marketCard, simulationCutoff }: CustomChartModalProps) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

    const [loading, setLoading] = useState(false);
    const [useTradingView, setUseTradingView] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [planAColor, setPlanAColor] = useState('#3b82f6');
    const [planBColor, setPlanBColor] = useState('#be123c');

    // Reset fallback state when opening new ticker
    useEffect(() => {
        if (isOpen) {
            setUseTradingView(false);
            setError(null);
        }
    }, [isOpen, ticker]);

    useEffect(() => {
        if (!isOpen || !ticker || useTradingView) return;

        const fetchHistory = async () => {
            setLoading(true);
            setError(null);
            try {
                // Determine cutoff param
                const cutoff = simulationCutoff ? `&simulation_cutoff=${encodeURIComponent(simulationCutoff)}` : '';
                const res = await fetch(`http://localhost:8000/api/scanner/history/${ticker}?days=5${cutoff}`);
                const json = await res.json();

                if (json.status === 'success' && json.data.length > 0) {
                    renderChart(json.data);
                } else {
                    setError("No historical data available.");
                }
            } catch (err) {
                console.error("Chart fetch error:", err);
                setError("Failed to load chart data.");
            } finally {
                setLoading(false);
            }
        };

        fetchHistory();

        return () => {
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
            }
        };
    }, [isOpen, ticker, useTradingView]);

    const renderChart = (data: any[]) => {
        if (!chartContainerRef.current) return;

        // Cleanup previous instance
        if (chartRef.current) {
            chartRef.current.remove();
        }

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: '#09090b' }, // Zinc-950
                textColor: '#a1a1aa',
            },
            grid: {
                vertLines: { color: '#27272a' },
                horzLines: { color: '#27272a' },
            },
            width: chartContainerRef.current.clientWidth,
            height: 500,
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
                barSpacing: 10, // Will be overridden by setVisibleLogicalRange zoom
                rightOffset: 5,
                tickMarkFormatter: (time: number) => {
                    const date = new Date(time * 1000);
                    // Force US Eastern Time
                    return new Intl.DateTimeFormat('en-US', {
                        timeZone: 'America/New_York',
                        hour: 'numeric',
                        minute: 'numeric',
                        hour12: false,
                    }).format(date);
                },
            },
        });

        // 1. Background Series (Histogram) - Added FIRST to render behind
        const bgSeries = chart.addSeries(HistogramSeries as any, {
            priceScaleId: 'bg',
            priceFormat: { type: 'volume' },
        });

        chart.priceScale('bg').applyOptions({
            scaleMargins: { top: 0, bottom: 0 },
            visible: false,
        });

        // 2. Candlestick Series
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#10b981', // Emerald-500
            downColor: '#ef4444', // Red-500
            borderVisible: false,
            wickUpColor: '#10b981',
            wickDownColor: '#ef4444',
        });

        // Ensure data is sorted by time and unique
        const sortedData = data.sort((a, b) => a.time - b.time);
        const uniqueData = sortedData.filter((item, index, self) =>
            index === self.findIndex((t) => t.time === item.time)
        );

        // Prepare Background Data
        const bgData = uniqueData.map((item) => {
            const date = new Date(item.time * 1000);
            const parts = new Intl.DateTimeFormat('en-US', {
                timeZone: 'America/New_York',
                hour: 'numeric',
                minute: 'numeric',
                hour12: false,
            }).formatToParts(date);

            const hour = parseInt(parts.find(p => p.type === 'hour')?.value || '0');
            const minute = parseInt(parts.find(p => p.type === 'minute')?.value || '0');
            const totalMinutes = hour * 60 + minute;

            let color = 'transparent';
            if (totalMinutes >= 240 && totalMinutes < 570) color = 'rgba(250, 204, 21, 0.15)';
            else if (totalMinutes >= 960 && totalMinutes < 1200) color = 'rgba(59, 130, 246, 0.15)';

            return { time: item.time, value: 1, color: color };
        });

        bgSeries.setData(bgData);
        candlestickSeries.setData(uniqueData);
        candleSeriesRef.current = candlestickSeries;
        chartRef.current = chart;

        // --- PARSE LEVELS & PLANS ---
        const briefing = marketCard?.screener_briefing;
        let planALevelStr: string | null = null;
        let planBLevelStr: string | null = null;
        let narrativeText = "";

        if (marketCard) {
            if (typeof briefing === 'object' && briefing !== null) {
                planALevelStr = briefing.Plan_A_Level;
                planBLevelStr = briefing.Plan_B_Level;
                if (briefing.narrative) narrativeText = briefing.narrative;
            } else if (typeof briefing === 'string') {
                narrativeText = briefing;
            }

            if (narrativeText) {
                const getSection = (key: string) => {
                    const match = narrativeText.match(new RegExp(`${key}:\\s*(.*?)(?=\\n[A-Z][a-zA-Z0-9_]*:|$)`, 's'));
                    return match ? match[1].trim() : null;
                };

                if (!planALevelStr) planALevelStr = getSection('Plan_A_Level');
                if (!planBLevelStr) planBLevelStr = getSection('Plan_B_Level');

                const planAText = getSection('Plan_A');
                const planBText = getSection('Plan_B');

                const getBiasColor = (text: string | null, defColor: string) => {
                    if (!text) return defColor;
                    const t = text.toLowerCase();
                    if (/short|bear|sell|put|below|failure|resistance|rejection|reject|fade/i.test(t)) return '#ef4444';
                    if (/long|bull|buy|call|above|support|bounce|break|cross/i.test(t)) return '#10b981';
                    return defColor;
                };

                const colorA = getBiasColor(planAText, '#3b82f6');
                const colorB = getBiasColor(planBText, '#be123c');
                setPlanAColor(colorA);
                setPlanBColor(colorB);

                const levelA = parseLevel(planALevelStr);
                const levelB = parseLevel(planBLevelStr);

                if (levelA) {
                    candlestickSeries.createPriceLine({
                        price: levelA,
                        color: colorA,
                        lineWidth: 2,
                        lineStyle: LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'PLAN A',
                    });
                }

                if (levelB) {
                    candlestickSeries.createPriceLine({
                        price: levelB,
                        color: colorB,
                        lineWidth: 2,
                        lineStyle: LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'PLAN B',
                    });
                }
            }
        }

        const totalBars = uniqueData.length;
        const barsToShow = Math.min(78, totalBars);
        chart.timeScale().setVisibleLogicalRange({
            from: totalBars - barsToShow,
            to: totalBars + 5,
        });
    };

    const parseLevel = (str: string | undefined | null) => {
        if (!str) return null;
        const match = str.match(/[\d.]+/);
        return match ? parseFloat(match[0]) : null;
    };

    if (useTradingView) {
        return <ChartModal isOpen={isOpen} onClose={onClose} symbol={ticker} />;
    }

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={`🔬 ${ticker} - Structural Analysis Chart`}
            variant="default"
        >
            <div className="relative w-full h-[500px] bg-zinc-950 rounded-lg border border-border/50 overflow-hidden">
                {loading && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/50 z-10">
                        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
                    </div>
                )}

                {error ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 text-center p-8">
                        <p className="text-destructive font-bold">{error}</p>
                        <Button onClick={() => setUseTradingView(true)} variant="outline">
                            Use Standard TradingView Chart
                        </Button>
                    </div>
                ) : (
                    <div ref={chartContainerRef} className="w-full h-full" />
                )}
            </div>

            <div className="flex justify-between items-center mt-4 pt-4 border-t border-border/30">
                <div className="flex gap-4 text-xs font-mono">
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-0.5 border-t-2 border-dashed" style={{ borderColor: planAColor }}></div>
                        Plan A
                    </div>
                    <div className="flex items-center gap-1">
                        <div className="w-3 h-0.5 border-t-2 border-dashed" style={{ borderColor: planBColor }}></div>
                        Plan B
                    </div>
                </div>
                <Button
                    variant="ghost"
                    onClick={() => setUseTradingView(true)}
                    className="text-xs text-muted-foreground hover:text-foreground"
                >
                    Switch to Standard View
                </Button>
            </div>
        </Modal>
    );
}
