"use client";

import React, { useState } from 'react';
import { useMission } from '@/lib/context';
import { Card } from '@/components/ui/core';
import {
    Settings,
    Globe,
    ChevronDown,
    ChevronUp,
    Cpu,
    Calendar,
    Clock,
    Zap,
    Activity,
    RefreshCw,
    ShieldCheck,
    AlertTriangle,
    Target,
    History as HistoryIcon,
    Layers,
    HelpCircle
} from 'lucide-react';

const Tooltip = ({ text }: { text: string }) => (
    <div className="group relative ml-1.5 inline-block">
        <HelpCircle className="w-3 h-3 text-muted-foreground/50 cursor-help hover:text-primary transition-colors" />
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 p-2 bg-zinc-900 border border-primary/20 rounded shadow-2xl opacity-0 group-hover:opacity-100 pointer-events-none transition-all z-50 text-[10px] text-zinc-300 font-medium leading-relaxed">
            {text}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-8 border-transparent border-t-zinc-900" />
        </div>
    </div>
);

const AVAILABLE_MODELS = [
    "gemini-3-flash-free",
    "gemini-3-flash-paid",
    "gemini-3-pro-paid",
    "gemini-2.5-flash-free",
    "gemini-2.5-flash-lite-free",
    "gemma-3-27b",
    "gemma-3-12b"
];

export function MissionControl() {
    const [isOpen, setIsOpen] = useState(false);
    const [isRefreshingKeys, setIsRefreshingKeys] = useState(false);
    const { settings, systemStatus, updateSettings } = useMission();

    const isLive = settings.mode === 'Live';
    const capitalConnected = systemStatus?.capital_connected;
    const keysAvailable = systemStatus?.gemini_keys_available || 0;

    return (
        <div className="w-full mb-8">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between p-4 bg-muted/30 border border-border rounded-xl hover:bg-muted/50 transition-all group"
            >
                <div className="flex items-center gap-4">
                    <div className="p-2 bg-primary/10 rounded-lg text-primary text-2xl">
                        <Settings className="w-5 h-5" />
                    </div>
                    <div className="text-left">
                        <h3 className="text-sm font-bold tracking-tight text-foreground/90 uppercase tracking-[0.1em]">Scanner Control</h3>
                        <p className="text-[10px] text-muted-foreground uppercase tracking-wider font-mono">
                            Scan Mode: <span className={isLive ? 'text-primary' : 'text-yellow-500'}>{settings.mode}</span> •
                            Model: <span className="text-foreground">{settings.model_name}</span> •
                            Strict: <span className={settings.plan_only_proximity ? 'text-primary' : 'text-muted-foreground'}>{settings.plan_only_proximity ? 'ON' : 'OFF'}</span> •
                            Live Macro: <span className={settings.force_economy_refresh ? 'text-primary' : 'text-muted-foreground'}>{settings.force_economy_refresh ? 'ON' : 'OFF'}</span>
                        </p>
                    </div>
                </div>
                {isOpen ? <ChevronUp className="w-4 h-4 text-muted-foreground" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
            </button>

            {isOpen && (
                <div className="mt-4 animate-in slide-in-from-top-4 duration-300">
                    <Card className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8 border-primary/20 bg-muted/10 backdrop-blur-xl">
                        {/* Operational Mode */}
                        <div className="space-y-4">
                            <h4 className="flex items-center gap-2 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                                <Activity className="w-3 h-3 text-primary" /> Operational Mode
                                <Tooltip text="LIVE: Stream real-time price feeds. SIMULATION: Replay historical market data for testing." />
                            </h4>
                            <div className="flex p-1 bg-muted rounded-lg border border-border/50">
                                <button
                                    onClick={() => updateSettings({ mode: 'Live' })}
                                    className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${isLive ? 'bg-background text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                                >
                                    LIVE
                                </button>
                                <button
                                    onClick={() => updateSettings({ mode: 'Simulation' })}
                                    className={`flex-1 py-2 text-xs font-bold rounded-md transition-all ${!isLive ? 'bg-background text-yellow-500 shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                                >
                                    SIMULATION
                                </button>
                            </div>

                            <div className="pt-2 space-y-2">
                                {isLive ? (
                                    <>
                                        <div className="flex flex-col justify-between p-2 rounded-lg border border-emerald-500/10 bg-emerald-500/5 transition-all">
                                            <div className="flex items-center gap-1.5 mb-1.5">
                                                <ShieldCheck className="w-3 h-3 text-emerald-500 shrink-0" />
                                                <span className="text-[10px] font-black uppercase text-emerald-500 leading-none">DB Fallback</span>
                                                <Tooltip text="If live data fails, force the system to use the most recent historical data from the database." />
                                            </div>
                                            <div className="flex items-center justify-between">
                                                <span className="text-[8px] text-muted-foreground mr-1">Emergency Mode</span>
                                                <button
                                                    onClick={() => updateSettings({ db_fallback: !settings.db_fallback })}
                                                    className={`relative w-8 h-4 rounded-full transition-all duration-300 shrink-0 ${settings.db_fallback ? 'bg-emerald-500' : 'bg-muted-foreground/20'}`}
                                                >
                                                    <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all duration-300`} style={{ left: settings.db_fallback ? '18px' : '2px' }} />
                                                </button>
                                            </div>
                                        </div>

                                        <div className="flex flex-col justify-between p-2 rounded-lg border border-primary/10 bg-primary/5 transition-all">
                                            <div className="flex items-center gap-1.5 mb-1.5">
                                                <Globe className="w-3 h-3 text-primary shrink-0" />
                                                <span className="text-[10px] font-black uppercase text-primary leading-none">Live Economy Card</span>
                                                <Tooltip text="Force the system to generate a fresh global economy card, bypassing the 2.5-hour cache." />
                                            </div>
                                            <div className="flex items-center justify-between">
                                                <span className="text-[8px] text-muted-foreground mr-1">Bypass Cache</span>
                                                <button
                                                    onClick={() => updateSettings({ force_economy_refresh: !settings.force_economy_refresh })}
                                                    className={`relative w-8 h-4 rounded-full transition-all duration-300 shrink-0 ${settings.force_economy_refresh ? 'bg-primary' : 'bg-muted-foreground/20'}`}
                                                >
                                                    <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all duration-300`} style={{ left: settings.force_economy_refresh ? '18px' : '2px' }} />
                                                </button>
                                            </div>
                                        </div>
                                    </>
                                ) : (
                                    <div className="flex items-center gap-2 px-1 bg-yellow-500/5 p-2 rounded-lg border border-yellow-500/10">
                                        <HistoryIcon className="w-3 h-3 text-yellow-500" />
                                        <span className="text-[10px] text-yellow-500 font-bold uppercase tracking-tighter">Historical Database Active</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Logical Model */}
                        <div className="flex flex-col gap-1.5 flex-1 min-w-[200px]">
                            <div className="flex items-center gap-1.5 px-1">
                                <Cpu className="w-3 h-3 text-muted-foreground" />
                                <span className="text-[10px] text-muted-foreground font-black uppercase tracking-tighter">Synthesis Engine</span>
                                <Tooltip text="The LLM model used to analyze structure and write the tactical plan." />
                            </div>
                            <div className="space-y-2">
                                <div className="relative">
                                    <select
                                        value={settings.model_name}
                                        onChange={(e) => updateSettings({ model_name: e.target.value })}
                                        className="w-full bg-zinc-900 border border-primary/20 rounded-lg p-2.5 text-xs font-medium focus:ring-1 focus:ring-primary focus:border-primary appearance-none cursor-pointer transition-all hover:bg-zinc-800"
                                    >
                                        {AVAILABLE_MODELS.map(model => (
                                            <option key={model} value={model}>{model.toUpperCase()}</option>
                                        ))}
                                    </select>
                                    <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground pointer-events-none" />
                                </div>
                                <div className="flex items-center justify-between gap-2 px-3 py-2 bg-emerald-500/5 border border-emerald-500/10 rounded-lg group">
                                    <div className="flex items-center gap-2">
                                        <Zap className="w-3 h-3 text-emerald-400 group-hover:scale-110 transition-transform" />
                                        <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-tighter">
                                            Active Rotation Pool: <span className="text-white ml-1">{keysAvailable} Keys Available</span>
                                        </span>
                                    </div>
                                    <button
                                        onClick={async () => {
                                            setIsRefreshingKeys(true);
                                            try {
                                                const { syncKeys } = await import('@/lib/api');
                                                await syncKeys();
                                            } catch (err) {
                                                console.error(err);
                                            } finally {
                                                setIsRefreshingKeys(false);
                                            }
                                        }}
                                        className="p-1 hover:bg-emerald-500/20 rounded-md transition-colors"
                                        title="Refresh Keys from Infisical"
                                        disabled={isRefreshingKeys}
                                    >
                                        {isRefreshingKeys ? (
                                            <RefreshCw className="w-3 h-3 text-emerald-400 animate-spin" />
                                        ) : (
                                            <RefreshCw className="w-3 h-3 text-emerald-400" />
                                        )}
                                    </button>
                                </div>
                            </div>
                        </div>
                        {/* Simulation Parameters */}
                        <div className="space-y-4">
                            <h4 className="flex items-center gap-2 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                                <Calendar className="w-3 h-3 text-primary" /> Timeline {isLive && <span className="text-[8px] text-muted-foreground/50 lowercase ml-auto">(Locked in Live)</span>}
                                <Tooltip text="Benchmark: The start date for analysis. Cutoff: High-precision timestamp for simulation feeds." />
                            </h4>
                            <div className={`grid grid-cols-1 gap-3 transition-opacity ${isLive ? 'opacity-50 pointer-events-none' : 'opacity-100'}`}>
                                <div className="relative">
                                    <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
                                    <input
                                        type="date"
                                        disabled={isLive}
                                        value={settings.benchmark_date}
                                        onChange={(e) => updateSettings({ benchmark_date: e.target.value })}
                                        className="w-full bg-muted border border-border rounded-lg py-2.5 pl-9 pr-3 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed"
                                    />
                                </div>
                                <div className="relative">
                                    <Clock className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
                                    <input
                                        type="text"
                                        disabled={isLive}
                                        value={settings.simulation_cutoff}
                                        onChange={(e) => updateSettings({ simulation_cutoff: e.target.value })}
                                        placeholder="YYYY-MM-DD HH:MM:SS"
                                        className="w-full bg-muted border border-border rounded-lg py-2.5 pl-9 pr-3 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary disabled:cursor-not-allowed"
                                    />
                                </div>
                            </div>
                        </div>

                        {/* Strategic Guard */}
                        <div className="space-y-4">
                            <h4 className="flex items-center gap-2 text-xs font-bold text-muted-foreground uppercase tracking-widest">
                                <Target className="w-3 h-3 text-primary" /> Strategic Guard
                                <Tooltip text="Automated safety filters that control when the scanner notifies you." />
                            </h4>

                            <div className="space-y-3">
                                <div className="space-y-3">
                                    <div className="flex justify-between items-center">
                                        <div className="flex items-center">
                                            <span className="text-xs text-muted-foreground">Proximity Threshold</span>
                                            <Tooltip text="Only alert if price is within this % range of a Key Level (Support/Resistance)." />
                                        </div>
                                        <span className="text-[10px] font-mono font-bold text-primary">{settings.proximity_threshold}%</span>
                                    </div>
                                    <input
                                        type="range"
                                        min="0.1"
                                        max="5.0"
                                        step="0.1"
                                        className="w-full h-1 bg-secondary rounded-lg appearance-none cursor-pointer accent-primary"
                                        value={settings.proximity_threshold}
                                        onChange={(e) => updateSettings({ proximity_threshold: parseFloat(e.target.value) })}
                                    />

                                    <div className="flex flex-col justify-between p-2 rounded-lg border border-primary/10 bg-primary/5 transition-all h-full">
                                        <div className="flex items-center gap-1.5 mb-1.5">
                                            <Target className="w-3 h-3 text-primary shrink-0" />
                                            <span className="text-[10px] font-black uppercase text-primary leading-none">Strict Mode</span>
                                            <Tooltip text="If enabled, alerts only trigger for tickers that have a high-conviction trade plan (Plan A or B)." />
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span className="text-[8px] text-muted-foreground mr-1">Plan A/B Only</span>
                                            <button
                                                onClick={() => updateSettings({ plan_only_proximity: !settings.plan_only_proximity })}
                                                className={`relative w-8 h-4 rounded-full transition-all duration-300 shrink-0 ${settings.plan_only_proximity ? 'bg-primary' : 'bg-muted-foreground/20'}`}
                                            >
                                                <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white shadow transition-all duration-300 ${settings.plan_only_proximity ? 'left-4.5' : 'left-0.5'}`} style={{ left: settings.plan_only_proximity ? '18px' : '2px' }} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </Card>
                </div>
            )
            }
        </div >
    );
}
