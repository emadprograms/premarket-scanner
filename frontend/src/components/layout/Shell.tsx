"use client";

import React, { useEffect } from 'react';
import { socketService } from '@/lib/socket';
import { Bell, Search, User, Activity } from 'lucide-react';
import { useMission } from '@/lib/context';

interface ShellProps {
    children: React.ReactNode;
}

export default function Shell({ children }: ShellProps) {
    const { systemStatus } = useMission();

    useEffect(() => {
        // Connect to WebSocket on mount
        socketService.connect('ws://127.0.0.1:8000/ws/logs');
        return () => socketService.disconnect();
    }, []);

    const apiConnected = systemStatus?.capital_connected;
    const dbConnected = systemStatus?.db_connected;

    return (
        <div className="flex h-screen bg-background overflow-hidden font-sans">
            <main className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
                {/* Scrollable Container */}
                <div className="flex-1 overflow-y-auto terminal-scroll">
                    {/* Top Header - Sticky inside scroll container */}
                    <header className="sticky top-0 h-16 border-b border-border flex items-center justify-between px-8 bg-background z-[40] shadow-sm">
                        <div className="flex items-center gap-8 flex-1">
                            <div className="flex items-center gap-3">
                                <div className="bg-primary/20 p-1.5 rounded-lg">
                                    <Activity className="w-5 h-5 text-primary" />
                                </div>
                                <span className="font-black text-xl tracking-tighter">PREMARKET</span>
                            </div>

                            <div className="relative w-80 group">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground group-focus-within:text-primary transition-colors" />
                                <input
                                    type="text"
                                    placeholder="Search markets..."
                                    className="w-full bg-muted/20 border border-border rounded-lg py-1.5 pl-10 pr-4 text-sm focus:outline-none focus:ring-1 focus:ring-primary transition-all shadow-inner"
                                />
                            </div>
                        </div>

                        <div className="flex items-center gap-6">
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono text-muted-foreground bg-muted px-2.5 py-1 rounded tracking-tighter">UTC 14:04:12</span>
                            </div>

                            <button className="relative text-muted-foreground hover:text-foreground transition-colors">
                                <Bell className="w-5 h-5" />
                                <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-primary rounded-full border-2 border-background"></span>
                            </button>

                            <div className="flex items-center gap-3 pl-6 border-l border-border">
                                <div className="text-right">
                                    <p className="text-sm font-semibold leading-none">Emad Arshad</p>
                                    <p className="text-xs text-muted-foreground mt-1">Institutional Analyst</p>
                                </div>
                                <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-primary to-emerald-400 p-0.5">
                                    <div className="w-full h-full rounded-full bg-background flex items-center justify-center">
                                        <User className="w-4 h-4 text-primary" />
                                    </div>
                                </div>
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
                        <span className="text-primary font-bold">V1.0.0-PRO</span>
                    </div>
                </footer>
            </main>
        </div>
    );
}
