"use client";

import React, { useState, useEffect } from 'react';
import { Card, Button, Badge } from '@/components/ui/core';
import {
    Cpu,
    Play,
    Calendar,
    Zap,
    CheckCircle2,
    ListTodo,
    ChevronRight,
    Search,
    AlertTriangle,
    ArrowRight,
    Terminal as TerminalIcon,
    Activity,
    Globe,
    TrendingUp,
    TrendingDown,
    Gauge,
    Boxes,
    Shield,
    Coins,
    BarChart3,
    History,
    Clock,
    Layers
} from 'lucide-react';
import { useMission } from '@/lib/context';
import { getWorkbenchNextDate, getDailyInput, saveDailyInput, generateEconomyCard, generateCompanyCard } from '@/lib/api';
import { socketService } from '@/lib/socket';
import EconomyCardView from './EconomyCardView';

export default function WorkbenchView() {
    const { settings } = useMission();
    const [date, setDate] = useState("");
    const [lastProcessedDate, setLastProcessedDate] = useState<string | null>(null);
    const [suggestedNextDate, setSuggestedNextDate] = useState<string | null>(null);
    const [news, setNews] = useState("");
    const [step, setStep] = useState(1);
    const [isRunning, setIsRunning] = useState(false);
    const [logs, setLogs] = useState<any[]>([]);
    const [economyCard, setEconomyCard] = useState<any>(null); // New result state
    const [tickers, setTickers] = useState<string[]>([]);
    const [selectedTickers, setSelectedTickers] = useState<string[]>([]); // New selection state
    const [selectedModel, setSelectedModel] = useState("gemini-3-flash-free"); // New model state
    const [activeView, setActiveView] = useState<'terminal' | 'economy' | 'company'>('terminal');
    const logsEndRef = React.useRef<HTMLDivElement>(null);

    useEffect(() => {
        const init = async () => {
            try {
                const res = await getWorkbenchNextDate();
                if (res.status === 'success') {
                    const nextDate = res.data.next_date;
                    setSuggestedNextDate(nextDate);
                    setLastProcessedDate(res.data.last_date);
                    setDate(nextDate);

                    // Fetch existing news for the suggested date
                    const newsRes = await getDailyInput(nextDate);
                    if (newsRes.status === 'success') {
                        setNews(newsRes.data.news_text || "");
                    }
                }

                // Fetch Watchlist for Step 2
                const { getWatchlistStatus } = await import('@/lib/api');
                const watchlistRes = await getWatchlistStatus();
                if (watchlistRes.status === 'success') {
                    setTickers(watchlistRes.data.map((t: any) => t.ticker));
                }
            } catch (err) {
                console.error("Failed to fetch workbench init data", err);
                setDate(settings.benchmark_date);
            }
        };
        init();

        // Socket Listener for Logs
        const handleLog = (log: any) => {
            setLogs((prev) => [...prev, log].slice(-100));
        };

        socketService.onLog(handleLog);
        return () => socketService.offLog(handleLog); // Cleanup to prevent duplicates
    }, []);

    useEffect(() => {
        logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

    // Handle Date Change: Load existing news
    const handleDateChange = async (newDate: string) => {
        setDate(newDate);
        try {
            const res = await getDailyInput(newDate);
            if (res.status === 'success') {
                setNews(res.data.news_text || "");
            }
        } catch (err) {
            console.error("Failed to fetch news for date", newDate, err);
        }
    };

    const isSkippingDay = suggestedNextDate && date > suggestedNextDate;

    const handleRunStep = async () => {
        setIsRunning(true);
        setActiveView('terminal'); // Always show terminal while running

        if (step === 1) {
            setLogs([]);
            setEconomyCard(null);
        }

        try {
            if (step === 1) {
                // Step 1: Save Input and Generate Economy Card
                await saveDailyInput(date, news);
                const res = await generateEconomyCard(date, news, selectedModel);
                if (res.status === 'success') {
                    setEconomyCard(res.data.card); // Store result
                    setIsRunning(false);
                    setStep(2);
                    setActiveView('economy'); // Switch to results after completion
                }
            } else if (step === 2) {
                // Step 2: Structural Audit
                await generateCompanyCard(date, "ALL", selectedModel);
                setIsRunning(false);
                setStep(3);
                setActiveView('company');
            } else if (step === 3) {
                // Step 3: Tactical Briefing
                await new Promise(resolve => setTimeout(resolve, 2000));
                setIsRunning(false);
                setStep(4); // Completed
            }
        } catch (err) {
            console.error("Workbench Action Failed:", err);
            setIsRunning(false);
        }
    };

    return (
        <div className="space-y-8 max-w-7xl mx-auto animate-in fade-in duration-500">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight text-violet-400">Intelligence Lab</h1>
                    <p className="text-muted-foreground mt-0.5 text-xs uppercase tracking-widest font-bold">EOD Pipeline & Global Synthesis</p>
                </div>
                <div className="flex items-center gap-6">
                    {isSkippingDay && (
                        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/30 px-4 py-2 rounded-xl animate-in fade-in slide-in-from-right-4">
                            <AlertTriangle className="w-4 h-4 text-amber-500" />
                            <div className="text-[10px] uppercase font-bold text-amber-200">
                                Sequential Gap Detected
                                <button
                                    onClick={() => setDate(suggestedNextDate || date)}
                                    className="ml-2 underline hover:text-white transition-colors"
                                >
                                    Fix: {suggestedNextDate}
                                </button>
                            </div>
                        </div>
                    )}
                    <div className="flex items-center gap-3 bg-muted/30 px-4 py-2 rounded-xl border border-border focus-within:ring-1 focus-within:ring-violet-500 transition-all">
                        <Cpu className="w-4 h-4 text-violet-400" />
                        <select
                            value={selectedModel}
                            onChange={(e) => setSelectedModel(e.target.value)}
                            className="bg-transparent text-sm font-bold outline-none text-violet-400 cursor-pointer"
                        >
                            <option value="gemini-3-pro-paid" className="bg-zinc-900">Gemini 3 Pro (Paid)</option>
                            <option value="gemini-3-pro-free" className="bg-zinc-900">Gemini 3 Pro (Free)</option>
                            <option value="gemini-3-flash-paid" className="bg-zinc-900">Gemini 3 Flash (Paid)</option>
                            <option value="gemini-3-flash-free" className="bg-zinc-900">Gemini 3 Flash (Free)</option>
                        </select>
                    </div>

                    <div className="flex items-center gap-3 bg-muted/30 px-4 py-2 rounded-xl border border-border focus-within:ring-1 focus-within:ring-violet-500 transition-all">
                        <Calendar className="w-4 h-4 text-violet-400" />
                        <input
                            type="date"
                            value={date}
                            onChange={(e) => handleDateChange(e.target.value)}
                            className="bg-transparent text-sm font-bold font-mono outline-none text-violet-400 [color-scheme:dark]"
                        />
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-12 gap-8">
                {/* Pipeline Logic (Left) */}
                <div className="col-span-12 lg:col-span-4 space-y-6">
                    <Card className={`border-l-4 transition-all ${step >= 1 ? 'border-l-violet-500' : 'border-l-muted'} bg-muted/10`}>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-bold uppercase tracking-widest flex items-center gap-2">
                                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${step > 1 ? 'bg-violet-500 text-black' : 'bg-muted text-muted-foreground'}`}>1</span>
                                Global Context
                            </h3>
                            {step > 1 && <CheckCircle2 className="w-4 h-4 text-violet-500" />}
                        </div>
                        <textarea
                            value={news}
                            onChange={(e) => setNews(e.target.value)}
                            placeholder="Paste overnight headlines and catalysts..."
                            className="w-full h-32 bg-zinc-950 border border-white/10 rounded-xl p-3 text-xs focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all resize-none font-mono"
                        />
                        <Button
                            className="w-full mt-4 bg-violet-500/10 text-violet-400 border border-violet-500/30 hover:bg-violet-500 hover:text-black transition-all"
                            onClick={handleRunStep}
                            disabled={isRunning || step !== 1 || !news.trim()}
                        >
                            {isRunning && step === 1 ? 'SYNTHESIZING...' : 'GENERATE ECONOMY CARD'}
                        </Button>
                    </Card>

                    <Card className={`border-l-4 transition-all ${step >= 2 ? 'border-l-violet-500' : 'border-l-muted'} bg-muted/10`}>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-bold uppercase tracking-widest flex items-center gap-2">
                                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${step > 2 ? 'bg-violet-500 text-black' : 'bg-muted text-muted-foreground'}`}>2</span>
                                Structural Audit
                            </h3>
                            {step > 2 && <CheckCircle2 className="w-4 h-4 text-violet-500" />}
                        </div>
                        <div className="grid grid-cols-4 gap-2 max-h-48 overflow-y-auto pr-2 terminal-scroll">
                            {tickers.map(ticker => {
                                const isSelected = selectedTickers.includes(ticker);
                                return (
                                    <button
                                        key={ticker}
                                        onClick={() => setSelectedTickers(prev =>
                                            isSelected ? prev.filter(t => t !== ticker) : [...prev, ticker]
                                        )}
                                        className={`border rounded-lg px-2 py-1.5 text-[10px] font-bold text-center transition-all ${isSelected
                                            ? 'bg-violet-500/20 border-violet-500 text-white'
                                            : 'bg-black/40 border-white/5 text-zinc-400 hover:border-violet-500/30'
                                            }`}
                                    >
                                        {ticker}
                                    </button>
                                );
                            })}
                        </div>
                        <Button
                            className="w-full mt-4 bg-violet-500/10 text-violet-400 border border-violet-500/30 hover:bg-violet-500 hover:text-black transition-all"
                            onClick={handleRunStep}
                            disabled={isRunning || step !== 2}
                        >
                            {isRunning && step === 2
                                ? `AUDITING ${selectedTickers.length || tickers.length} TARGETS...`
                                : selectedTickers.length > 0
                                    ? `RUN AUDIT FOR ${selectedTickers.length} COMPANIES`
                                    : 'RUN AUDIT (ALL COMPANIES)'}
                        </Button>
                    </Card>

                    <Card className={`border-l-4 transition-all ${step >= 3 ? 'border-l-violet-500' : 'border-l-muted'} bg-muted/10`}>
                        <div className="flex items-center justify-between mb-4">
                            <h3 className="text-sm font-bold uppercase tracking-widest flex items-center gap-2">
                                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] ${step > 3 ? 'bg-violet-500 text-black' : 'bg-muted text-muted-foreground'}`}>3</span>
                                Tactical Briefing
                            </h3>
                            {step > 3 && <CheckCircle2 className="w-4 h-4 text-violet-500" />}
                        </div>
                        <Button
                            className="w-full bg-violet-500/10 text-violet-400 border border-violet-500/30 hover:bg-violet-500 hover:text-black transition-all"
                            onClick={handleRunStep}
                            disabled={isRunning || step !== 3}
                        >
                            {isRunning && step === 3 ? 'DRAFTING...' : 'FINALIZE TRADE PLANS'}
                        </Button>
                    </Card>
                </div>

                {/* Output (Right) */}
                <div className="col-span-12 lg:col-span-8 space-y-6">
                    <Card className="flex flex-col h-[700px] border-violet-500/10 bg-black/40 overflow-hidden relative group">
                        <div className="flex items-center justify-between p-6 border-b border-white/5 bg-zinc-950/20 sticky top-0 z-10 transition-colors">
                            <div className="flex items-center gap-4">
                                <h3 className={`font-black text-xl flex items-center gap-3 italic tracking-tighter transition-all ${activeView === 'terminal' ? 'text-violet-400' : 'text-zinc-400'}`}>
                                    <TerminalIcon className="w-5 h-5 transition-transform group-hover:rotate-6" /> GLASS BOX TERMINAL
                                </h3>
                                {economyCard && (
                                    <>
                                        <div className="h-6 w-px bg-white/10" />
                                        <button
                                            onClick={() => setActiveView(activeView === 'economy' ? 'terminal' : 'economy')}
                                            className={`font-black text-xl flex items-center gap-3 italic tracking-tighter transition-all hover:text-violet-400 ${activeView === 'economy' ? 'text-violet-400' : 'text-zinc-400 opacity-50'}`}
                                        >
                                            <Zap className="w-5 h-5 text-yellow-500" /> ECONOMY CARD
                                        </button>
                                    </>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <Badge variant="success" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/20 px-2 py-0.5 whitespace-nowrap">LIVE_BROADCAST</Badge>
                                <div className={`w-2 h-2 rounded-full bg-emerald-500 shadow-lg ${isRunning ? 'animate-pulse shadow-emerald-500/50' : 'opacity-30'}`} />
                            </div>
                        </div>

                        {activeView === 'terminal' ? (
                            logs.length === 0 ? (
                                <div className="flex-1 flex flex-col items-center justify-center text-center p-20 opacity-40">
                                    <div className="bg-violet-500/5 p-8 rounded-full mb-6 border border-violet-500/10 group-hover:scale-110 transition-transform duration-500">
                                        <Cpu className="w-12 h-12 text-violet-500/50" />
                                    </div>
                                    <h2 className="text-xl font-bold mb-2 tracking-tight text-white/90">System Idle</h2>
                                    <p className="text-sm text-muted-foreground max-w-sm leading-relaxed font-mono">
                                        Initialize pipeline to monitor AI logic and data synthesis across Turso and Gemini clusters.
                                    </p>
                                </div>
                            ) : (
                                <div className="flex-1 overflow-y-auto p-6 font-mono text-[11px] space-y-2.5 terminal-scroll scroll-smooth bg-zinc-950/20">
                                    {logs.map((log, i) => (
                                        <div key={i} className="flex gap-4 animate-in fade-in slide-in-from-left-2 duration-300 border-l-2 border-transparent hover:border-violet-500/50 pl-2 transition-all group/line">
                                            <span className="text-zinc-600 shrink-0 font-bold tracking-tighter select-none">{log.timestamp}</span>
                                            <span className="shrink-0 select-none">{log.icon}</span>
                                            <span className={`leading-relaxed ${log.level === 'ERROR' ? 'text-rose-400 font-bold' :
                                                log.level === 'SUCCESS' ? 'text-emerald-400 font-bold' :
                                                    log.level === 'WARNING' ? 'text-amber-300' :
                                                        'text-zinc-300'
                                                }`}>
                                                {log.message}
                                            </span>
                                        </div>
                                    ))}
                                    <div ref={logsEndRef} />
                                </div>
                            )
                        ) : activeView === 'economy' && economyCard ? (
                            <div className="flex-1 overflow-y-auto p-8 animate-in slide-in-from-bottom-4 duration-500 terminal-scroll">
                                <EconomyCardView economyCard={economyCard} date={date} />
                            </div>
                        ) : null}

                        {/* Decoration lines */}
                        <div className="absolute top-0 right-0 w-32 h-32 bg-violet-500/5 blur-[80px] pointer-events-none" />
                        <div className="absolute bottom-0 left-0 w-32 h-32 bg-blue-500/5 blur-[80px] pointer-events-none" />
                    </Card>
                </div>
            </div>
        </div>
    );
}
