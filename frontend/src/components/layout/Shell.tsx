"use client";

import React, { useEffect } from 'react';
import {
    Bell,
    Search,
    User,
    Target,
    History,
    ShieldAlert,
    Wifi,
    WifiOff,
    HelpCircle,
    ChevronUp,
    ChevronDown
} from 'lucide-react';
import { useMission } from '@/lib/context';

interface ShellProps {
    children: React.ReactNode;
}

export default function Shell({ children }: ShellProps) {
    const { settings, updateSettings, systemStatus, capitalStreaming, toggleCapitalStream } = useMission();

    const [time, setTime] = React.useState<string>('--:--:--');
    const [mounted, setMounted] = React.useState(false);

    useEffect(() => {
        setMounted(true);

        setTime(new Date().toLocaleTimeString());
        const timer = setInterval(() => {
            setTime(new Date().toLocaleTimeString());
        }, 1000);

        return () => {
            clearInterval(timer);
        };
    }, []);

    const apiConnected = systemStatus?.capital_connected;
    const dbConnected = systemStatus?.db_connected;

    const navItems = [
        { id: 'Scanner', icon: Target, label: 'Strategic HQ', color: 'text-primary' },
        { id: 'Archive', icon: History, label: 'Archive Room', color: 'text-blue-400' },
    ];

    const getMarketStatus = () => {
        if (!time) return { label: 'LOADING...', color: 'bg-zinc-500/10 text-zinc-500' };

        const now = new Date();
        const etString = now.toLocaleString("en-US", { timeZone: "America/New_York" });
        const etDate = new Date(etString);

        const day = etDate.getDay();
        const hours = etDate.getHours();
        const minutes = etDate.getMinutes();
        const timeAsMinutes = hours * 60 + minutes;

        const isWeekend = day === 0 || day === 6;
        if (isWeekend) return { label: 'MARKET CLOSED', color: 'bg-zinc-500/10 text-zinc-500' };

        if (timeAsMinutes >= 240 && timeAsMinutes < 570) {
            return { label: 'PRE-MARKET', color: 'bg-yellow-500/10 text-yellow-500' };
        }
        if (timeAsMinutes >= 570 && timeAsMinutes < 960) {
            return { label: 'MARKET OPEN', color: 'bg-emerald-500/10 text-emerald-500 font-bold' };
        }
        if (timeAsMinutes >= 960 && timeAsMinutes < 1200) {
            return { label: 'POST-MARKET', color: 'bg-blue-500/10 text-blue-500' };
        }

        return { label: 'MARKET CLOSED', color: 'bg-zinc-500/10 text-zinc-500' };
    };

    if (!mounted) return <div className="h-screen bg-background" />;

    const marketStatus = getMarketStatus();

    const adjustCapital = (amount: number) => {
        const current = settings.accountAmount || 0;
        updateSettings({ accountAmount: Math.max(0, current + amount) });
    };

    const adjustRisk = (amount: number) => {
        const current = settings.riskPercentage || 0;
        updateSettings({ riskPercentage: Math.max(0, Number((current + amount).toFixed(1))) });
    };

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans text-[13px]">
            {/* Navigation Sidebar - Ultra Slim */}
            <aside className="w-12 border-r border-border bg-zinc-950/50 flex flex-col items-center py-3 gap-5 z-50">
                <div className="bg-primary/20 p-1 rounded-lg mb-1">
                    <ShieldAlert className="w-4 h-4 text-primary" />
                </div>

                <nav className="flex flex-col gap-3.5">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = settings.workstation === item.id;
                        return (
                            <button
                                key={item.id}
                                onClick={() => updateSettings({ workstation: item.id as any })}
                                className={`group relative p-2 rounded-lg transition-all duration-300 ${isActive
                                    ? `bg-white/10 ${item.color} shadow-lg shadow-white/5`
                                    : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                                    }`}
                                title={item.label}
                            >
                                <Icon className="w-4.5 h-4.5" />
                                <div className={`absolute left-full ml-4 px-2 py-1 bg-zinc-900 border border-white/10 rounded text-[10px] font-bold whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-[60]`}>
                                    {item.label.toUpperCase()}
                                </div>
                                {isActive && (
                                    <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-current rounded-r-full`} />
                                )}
                            </button>
                        );
                    })}
                </nav>

                <div className="mt-auto flex flex-col gap-4 items-center pb-2">
                    <button className="p-2 text-muted-foreground hover:text-foreground transition-colors">
                        <Bell className="w-4 h-4" />
                    </button>
                    <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-primary to-violet-400 p-0.5">
                        <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
                            <User className="w-3 h-3 text-primary" />
                        </div>
                    </div>
                </div>
            </aside>

            <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Scrollable Container */}
                <div className="flex-1 overflow-y-auto terminal-scroll">
                    {/* Top Header - Ultra Compact */}
                    <header className="sticky top-0 h-10 border-b border-border flex items-center justify-between px-5 bg-background z-[40] shadow-sm">
                        <div className="flex items-center gap-6 flex-1">
                            <div className="flex items-center gap-3">
                                <span className="font-black text-base tracking-tighter uppercase">
                                    {navItems.find(n => n.id === settings.workstation)?.label || 'PREMARKET'}
                                </span>
                            </div>

                            {settings.workstation === 'Scanner' && (
                                <div className="flex items-center gap-6 border-l border-border pl-4">
                                    <div className="flex items-center gap-2">
                                        <div className="flex items-center gap-1 group relative">
                                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest cursor-default">Capital</span>
                                            <HelpCircle className="w-3 h-3 text-muted-foreground/50 hover:text-primary transition-colors cursor-help" />
                                            <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 w-48 p-2.5 bg-zinc-900 border border-white/10 rounded-lg text-[10px] leading-relaxed text-zinc-300 opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-300 z-50 shadow-xl">
                                                <div className="font-black text-white mb-1 uppercase tracking-widest">Base Capital</div>
                                                Your total trading account size. Used to calculate exactly how many shares you should buy based on your selected Risk %.
                                            </div>
                                        </div>
                                        <div className="relative flex items-center group/input rounded bg-muted/30 border border-border focus-within:border-primary/50 transition-colors">
                                            <span className="pl-2 pr-1 text-[10px] text-muted-foreground font-mono">$</span>
                                            <input
                                                type="number"
                                                value={settings.accountAmount || 10000}
                                                onChange={(e) => updateSettings({ accountAmount: Number(e.target.value) })}
                                                className="w-16 bg-transparent py-0.5 text-[11px] font-mono focus:outline-none transition-colors"
                                            />
                                            <div className="flex flex-col border-l border-border w-4 justify-center items-center">
                                                <button onClick={() => adjustCapital(500)} className="h-1/2 w-full flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-white/5 border-b border-border transition-colors">
                                                    <ChevronUp className="w-2.5 h-2.5" />
                                                </button>
                                                <button onClick={() => adjustCapital(-500)} className="h-1/2 w-full flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-white/5 transition-colors">
                                                    <ChevronDown className="w-2.5 h-2.5" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className="flex items-center gap-1 group relative">
                                            <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest cursor-default">Risk</span>
                                            <HelpCircle className="w-3 h-3 text-muted-foreground/50 hover:text-primary transition-colors cursor-help" />
                                            <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 w-48 p-2.5 bg-zinc-900 border border-white/10 rounded-lg text-[10px] leading-relaxed text-zinc-300 opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-300 z-50 shadow-xl">
                                                <div className="font-black text-white mb-1 uppercase tracking-widest">Risk Tolerance</div>
                                                The percentage of your total capital you are willing to lose if the trade invalidates (stops out). Common values are 0.5% - 2.0%.
                                            </div>
                                        </div>
                                        <div className="relative flex items-center group/input rounded bg-muted/30 border border-border focus-within:border-primary/50 transition-colors">
                                            <input
                                                type="number"
                                                step="0.1"
                                                value={settings.riskPercentage || 1}
                                                onChange={(e) => updateSettings({ riskPercentage: Number(e.target.value) })}
                                                className="w-10 bg-transparent py-0.5 pl-2 text-[11px] font-mono focus:outline-none transition-colors"
                                            />
                                            <span className="pr-1 text-[10px] text-muted-foreground font-mono">%</span>
                                            <div className="flex flex-col border-l border-border w-4 justify-center items-center">
                                                <button onClick={() => adjustRisk(0.1)} className="h-1/2 w-full flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-white/5 border-b border-border transition-colors">
                                                    <ChevronUp className="w-2.5 h-2.5" />
                                                </button>
                                                <button onClick={() => adjustRisk(-0.1)} className="h-1/2 w-full flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-white/5 transition-colors">
                                                    <ChevronDown className="w-2.5 h-2.5" />
                                                </button>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>

                        <div className="flex items-center gap-3">
                            {/* Connect / Disconnect Capital.com Button — only on Scanner */}
                            {settings.workstation === 'Scanner' && (
                                <div className="flex items-center gap-1 group relative">
                                    <button
                                        onClick={toggleCapitalStream}
                                        className={`group/btn inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded text-[9px] font-black uppercase tracking-wider border transition-all duration-300 ${capitalStreaming
                                            ? 'bg-rose-500/10 border-rose-500/30 text-rose-400 hover:bg-rose-500/20'
                                            : 'bg-violet-500/10 border-violet-500/30 text-violet-400 hover:bg-violet-500/20'
                                            }`}
                                    >
                                        {capitalStreaming ? (
                                            <>
                                                <WifiOff className="w-3 h-3" />
                                                Disconnect
                                            </>
                                        ) : (
                                            <>
                                                <div className="relative flex items-center gap-1">
                                                    <Wifi className="w-3 h-3" />
                                                    <div className="absolute inset-0 bg-violet-500/30 blur-md rounded-full scale-150 animate-pulse" />
                                                </div>
                                                Connect
                                            </>
                                        )}
                                    </button>
                                    <HelpCircle className="w-3 h-3 text-muted-foreground/50 hover:text-primary transition-colors cursor-help" />
                                    <div className="absolute top-full mt-2 right-0 w-64 p-2.5 bg-zinc-900 border border-white/10 rounded-lg text-[10px] leading-relaxed text-zinc-300 opacity-0 group-hover:opacity-100 pointer-events-none transition-all duration-300 z-50 shadow-xl">
                                        <div className="font-black text-white mb-1 uppercase tracking-widest flex items-center gap-1.5">
                                            Capital.com Broker Stream <Wifi className="w-3 h-3 text-violet-400" />
                                        </div>
                                        Connect via WebSocket to Capital.com to stream live market prices directly into the scanner. This enables proximity ranking and live position size updates for all active cards.
                                    </div>
                                </div>
                            )}

                            <div className="flex items-center gap-2">
                                <span className="text-[9px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded tracking-tighter">
                                    EST {time || '--:--:--'}
                                </span>
                            </div>

                            <div className="flex items-center gap-2 pl-3 border-l border-border">
                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[8px] font-black uppercase tracking-widest border border-white/5 transition-colors duration-500 ${marketStatus.color}`}>
                                    <div className={`w-1 h-1 rounded-full mr-1 shadow-[0_0_8px_currentColor] ${marketStatus.label === 'MARKET OPEN' ? 'animate-pulse' : ''}`} />
                                    {marketStatus.label}
                                </span>
                            </div>
                        </div>
                    </header>

                    {/* Main Content with padding */}
                    <div className="p-6">
                        {children}
                    </div>
                </div>

                {/* Global Footer / Status Bar */}
                <footer className="h-8 border-t border-border bg-muted/20 px-4 flex items-center justify-between text-[10px] font-mono text-muted-foreground">
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-1">
                            <span className={`w-2 h-2 rounded-full ${systemStatus ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}></span>
                            <span className={systemStatus ? '' : 'text-destructive font-bold'}>BACKEND: {systemStatus ? 'ONLINE' : 'OFFLINE'}</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <span className={`w-2 h-2 rounded-full ${apiConnected ? 'bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}></span>
                            <span className={apiConnected ? '' : 'text-destructive font-bold'}>CAPITAL: {apiConnected ? 'CONNECTED' : 'DISCONNECTED'}</span>
                        </div>
                        <div className="flex items-center gap-1">
                            <span className={`w-2 h-2 rounded-full ${dbConnected ? 'bg-emerald-300 shadow-[0_0_8px_rgba(110,231,183,0.5)]' : 'bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}></span>
                            <span className={dbConnected ? '' : 'text-destructive font-bold'}>DB: {dbConnected ? 'TURSO_LIVE' : 'DISCONNECTED'}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="flex items-center gap-1">
                            <span className={`w-2 h-2 rounded-full ${systemStatus?.economy_card_status?.active ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-destructive shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`}></span>
                            <span className={systemStatus?.economy_card_status?.active ? '' : 'text-destructive font-bold'}>ECONOMY_CARD: {systemStatus?.economy_card_status?.active ? 'CACHED' : 'MISSING'}</span>
                            <span className="text-muted-foreground ml-1">({systemStatus?.economy_card_status?.updated || 'N/A'})</span>
                        </div>
                        <span className="text-primary font-bold uppercase tracking-tight">System Status: {settings.workstation?.toUpperCase()} Workstation</span>
                        <span className="text-primary font-bold">V1.0.0-PRO</span>
                    </div>
                </footer>
            </main>
        </div>
    );
}

