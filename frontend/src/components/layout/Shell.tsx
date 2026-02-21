"use client";

import React, { useEffect } from 'react';
import { socketService } from '@/lib/socket';
import {
    Bell,
    Search,
    User,
    Activity,
    Target,
    Cpu,
    History,
    ShieldAlert
} from 'lucide-react';
import { useMission } from '@/lib/context';

interface ShellProps {
    children: React.ReactNode;
}

export default function Shell({ children }: ShellProps) {
    const { settings, updateSettings, systemStatus } = useMission();

    // Use empty string or constant on first render to prevent SSR/CSR hydration mismatch
    const [time, setTime] = React.useState<string>('--:--:--');
    const [mounted, setMounted] = React.useState(false);

    useEffect(() => {
        setMounted(true);
        // Connect to WebSocket on mount
        const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
        const wsProtocol = apiBase.startsWith('https') ? 'wss' : 'ws';
        const wsUrl = `${wsProtocol}://${apiBase.replace(/^https?:\/\//, '')}/ws/logs`;
        socketService.connect(wsUrl);

        setTime(new Date().toLocaleTimeString());
        const timer = setInterval(() => {
            setTime(new Date().toLocaleTimeString());
        }, 1000);

        return () => {
            socketService.disconnect();
            clearInterval(timer);
        };
    }, []);

    const apiConnected = systemStatus?.capital_connected;
    const dbConnected = systemStatus?.db_connected;

    const navItems = [
        { id: 'Scanner', icon: Target, label: 'Strategic HQ', color: 'text-primary' },
        { id: 'Workbench', icon: Cpu, label: 'Intelligence Lab', color: 'text-violet-400' },
        { id: 'Archive', icon: History, label: 'Archive Room', color: 'text-blue-400' },
    ];

    const getMarketStatus = () => {
        if (!time) return { label: 'LOADING...', color: 'bg-zinc-500/10 text-zinc-500' };

        // Current time in ET
        const now = new Date();
        const etString = now.toLocaleString("en-US", { timeZone: "America/New_York" });
        const etDate = new Date(etString);

        const day = etDate.getDay();
        const hours = etDate.getHours();
        const minutes = etDate.getMinutes();
        const timeAsMinutes = hours * 60 + minutes;

        const isWeekend = day === 0 || day === 6;
        if (isWeekend) return { label: 'MARKET CLOSED', color: 'bg-zinc-500/10 text-zinc-500' };

        // Pre-Market: 4:00 AM - 9:30 AM
        if (timeAsMinutes >= 240 && timeAsMinutes < 570) {
            return { label: 'PRE-MARKET', color: 'bg-yellow-500/10 text-yellow-500' };
        }
        // Market Open: 9:30 AM - 4:00 PM
        if (timeAsMinutes >= 570 && timeAsMinutes < 960) {
            return { label: 'MARKET OPEN', color: 'bg-emerald-500/10 text-emerald-500 font-bold' };
        }
        // Post-Market: 4:00 PM - 8:00 PM
        if (timeAsMinutes >= 960 && timeAsMinutes < 1200) {
            return { label: 'POST-MARKET', color: 'bg-blue-500/10 text-blue-500' };
        }

        return { label: 'MARKET CLOSED', color: 'bg-zinc-500/10 text-zinc-500' };
    };

    const marketStatus = getMarketStatus();

    // Prevent hydration mismatch by returning a shell or null until first client mount
    if (!mounted) return <div className="h-screen bg-background" />;

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans">
            {/* NEW: Navigation Sidebar */}
            <aside className="w-16 border-r border-border bg-zinc-950/50 flex flex-col items-center py-6 gap-8 z-50">
                <div className="bg-primary/20 p-2 rounded-xl mb-4">
                    <ShieldAlert className="w-6 h-6 text-primary" />
                </div>

                <nav className="flex flex-col gap-6">
                    {navItems.map((item) => {
                        const Icon = item.icon;
                        const isActive = settings.workstation === item.id;
                        return (
                            <button
                                key={item.id}
                                onClick={() => updateSettings({ workstation: item.id as any })}
                                className={`group relative p-3 rounded-xl transition-all duration-300 ${isActive
                                    ? `bg-white/10 ${item.color} shadow-lg shadow-white/5`
                                    : 'text-muted-foreground hover:bg-white/5 hover:text-foreground'
                                    }`}
                                title={item.label}
                            >
                                <Icon className="w-6 h-6" />
                                <div className={`absolute left-full ml-4 px-2 py-1 bg-zinc-900 border border-white/10 rounded text-[10px] font-bold whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-[60]`}>
                                    {item.label.toUpperCase()}
                                </div>
                                {isActive && (
                                    <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-current rounded-r-full`} />
                                )}
                            </button>
                        );
                    })}
                </nav>

                <div className="mt-auto flex flex-col gap-6 items-center">
                    <button className="p-3 text-muted-foreground hover:text-foreground transition-colors">
                        <Bell className="w-5 h-5" />
                    </button>
                    <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary to-emerald-400 p-0.5">
                        <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
                            <User className="w-4 h-4 text-primary" />
                        </div>
                    </div>
                </div>
            </aside>

            <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Scrollable Container */}
                <div className="flex-1 overflow-y-auto terminal-scroll">
                    {/* Top Header - Sticky inside scroll container */}
                    <header className="sticky top-0 h-16 border-b border-border flex items-center justify-between px-8 bg-background z-[40] shadow-sm">
                        <div className="flex items-center gap-8 flex-1">
                            <div className="flex items-center gap-3">
                                <span className="font-black text-xl tracking-tighter uppercase">
                                    {navItems.find(n => n.id === settings.workstation)?.label || 'PREMARKET'}
                                </span>
                            </div>

                            <div className="relative w-80 group">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                                <input
                                    type="text"
                                    placeholder="Search command..."
                                    className="w-full bg-muted/20 border border-border rounded-lg py-1.5 pl-10 pr-4 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all shadow-inner"
                                />
                            </div>
                        </div>

                        <div className="flex items-center gap-6">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-muted-foreground bg-muted px-2.5 py-1 rounded tracking-tighter">
                                    EST {time || '--:--:--'}
                                </span>
                            </div>

                            <div className="flex items-center gap-2 pl-6 border-l border-border">
                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border border-white/5 transition-colors duration-500 ${marketStatus.color}`}>
                                    <div className={`w-1.5 h-1.5 rounded-full mr-2 shadow-[0_0_8px_currentColor] ${marketStatus.label === 'MARKET OPEN' ? 'animate-pulse' : ''}`} />
                                    {marketStatus.label}
                                </span>
                            </div>
                        </div>
                    </header>

                    {/* Main Content with padding */}
                    <div className="p-8">
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
