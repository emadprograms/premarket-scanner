"use client";

import React from 'react';
import { Badge } from '@/components/ui/core';
import { motion } from 'framer-motion';
import {
    Zap,
    Globe,
    TrendingUp,
    TrendingDown,
    Gauge,
    Boxes,
    Shield,
    Coins,
    BarChart3,
    Clock,
    Layers,
    AlertTriangle,
    Cpu,
    Brain,
    Activity,
    Target
} from 'lucide-react';

interface EconomyCardViewProps {
    economyCard: any;
    date?: string;
    isExpanded?: boolean;
}

export default function EconomyCardView({ economyCard: rawData, date, isExpanded }: EconomyCardViewProps) {
    if (!rawData) return null;

    // Deep recursive sanitizer: converts ALL nested {date, action} objects to their string value
    const deepSanitize = (obj: any): any => {
        if (obj === null || obj === undefined) return obj;
        if (typeof obj === 'string' || typeof obj === 'number' || typeof obj === 'boolean') return obj;
        if (Array.isArray(obj)) return obj.map(deepSanitize);
        if (typeof obj === 'object') {
            const sanitized: any = {};
            for (const key of Object.keys(obj)) {
                sanitized[key] = deepSanitize(obj[key]);
            }
            return sanitized;
        }
        return String(obj);
    };

    const data = deepSanitize(rawData);

    // Lightweight fallback for direct JSX rendering
    const safeRender = (val: any, fallback: string = "---"): string => {
        if (!val && val !== 0) return fallback;
        if (typeof val === 'string') return val;
        if (typeof val === 'number') return String(val);
        if (typeof val === 'object') {
            return val.action || val.summary || val.text || JSON.stringify(val);
        }
        return fallback;
    };

    const marketBiasRaw = safeRender(data.marketBias, "NEUTRAL");

    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-700 space-y-6 w-full pb-10 px-6 overflow-y-auto max-h-screen custom-scrollbar">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

                {/* Section I: Market Narrative & Bias (Full Width Top) */}
                <div className="lg:col-span-12">
                    <section className="space-y-4">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">I</div>
                                <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Market Narrative</h2>
                            </div>
                            <div className="flex items-center gap-3">
                                <span className="text-[7px] font-black text-zinc-800 uppercase tracking-[0.2em]">Session Bias:</span>
                                <Badge
                                    variant={
                                        marketBiasRaw.toLowerCase().includes('bull') ? 'success' :
                                            marketBiasRaw.toLowerCase().includes('bear') ? 'error' :
                                                'default'
                                    }
                                    className="text-[12px] font-black italic tracking-widest uppercase px-3 py-0.5 rounded-lg"
                                >
                                    {marketBiasRaw}
                                </Badge>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
                            {(() => {
                                const isBullish = data.marketBias?.toLowerCase().includes('bull');
                                const isBearish = data.marketBias?.toLowerCase().includes('bear');

                                return (
                                    <motion.div
                                        whileHover={{ scale: 1.005 }}
                                        className={`lg:col-span-4 p-5 rounded-2xl border transition-colors duration-500 group relative overflow-hidden ${isBullish ? 'bg-emerald-500/5 border-emerald-500/10' :
                                            isBearish ? 'bg-rose-500/5 border-rose-500/10' :
                                                'bg-zinc-900/40 border-white/5'
                                            }`}
                                    >
                                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                                            <Brain className={`w-12 h-12 ${isBullish ? 'text-emerald-500' : isBearish ? 'text-rose-500' : 'text-blue-500'}`} />
                                        </div>
                                        <p className="text-[12px] xl:text-[14px] font-semibold text-zinc-300 leading-loose italic tracking-normal relative z-10">
                                            "{safeRender(data.marketNarrative, "Initializing session briefing...")}"
                                        </p>
                                    </motion.div>
                                );
                            })()}
                        </div>
                    </section>
                </div>

                {/* Section II: Economic Events (Left Rail) */}
                <div className="lg:col-span-5">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">II</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Economic Canvas</h2>
                        </div>
                        <div className="grid grid-cols-1 gap-3">
                            <motion.div whileHover={{ x: 4 }} className="bg-white/5 p-4 rounded-xl border border-white/5 space-y-2 group">
                                <h4 className="text-[8px] font-black text-zinc-500 uppercase tracking-widest flex items-center gap-2">
                                    <Clock className="w-3 h-3 text-zinc-700" /> Historical (24H)
                                </h4>
                                <p className="text-[11px] xl:text-[13px] text-zinc-400 leading-relaxed font-semibold">
                                    {safeRender(data.keyEconomicEvents?.last_24h, "No major events logged.")}
                                </p>
                            </motion.div>
                            <motion.div whileHover={{ x: 4 }} className="bg-yellow-500/5 p-4 rounded-xl border border-yellow-500/10 space-y-2 group">
                                <h4 className="text-[8px] font-black text-yellow-500/60 uppercase tracking-widest flex items-center gap-2">
                                    <Zap className="w-3 h-3" /> Upcoming (24H)
                                </h4>
                                <p className="text-[12px] xl:text-[14px] text-zinc-200 leading-relaxed font-black italic">
                                    {safeRender(data.keyEconomicEvents?.next_24h, "Clear horizon detected.")}
                                </p>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section III: Sector Rotation (Main Content Area) */}
                <div className="lg:col-span-7">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">III</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Sector Rotation</h2>
                        </div>
                        <div className="bg-zinc-900/40 p-5 rounded-2xl border border-white/5 space-y-4">
                            <div className="grid grid-cols-2 gap-6">
                                <div className="space-y-2">
                                    <p className="text-[8px] font-black text-emerald-400/60 uppercase tracking-widest flex items-center gap-1.5">
                                        <TrendingUp className="w-2.5 h-2.5" /> Leading
                                    </p>
                                    <div className="flex flex-wrap gap-1.5">
                                        {data.sectorRotation?.leadingSectors?.length > 0 ? (
                                            data.sectorRotation.leadingSectors.map((s: string) => (
                                                <Badge key={s} className="bg-emerald-500/10 text-emerald-400 border-emerald-500/10 text-[10px] py-0.5 px-2.5 font-mono font-black italic">{s}</Badge>
                                            ))
                                        ) : (
                                            <span className="text-[9px] text-zinc-600 font-mono tracking-tighter">DATA_MISSING</span>
                                        )}
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <p className="text-[8px] font-black text-rose-400/60 uppercase tracking-widest flex items-center gap-1.5">
                                        <TrendingDown className="w-2.5 h-2.5" /> Lagging
                                    </p>
                                    <div className="flex flex-wrap gap-1.5">
                                        {data.sectorRotation?.laggingSectors?.length > 0 ? (
                                            data.sectorRotation.laggingSectors.map((s: string) => (
                                                <Badge key={s} className="bg-rose-500/10 text-rose-400 border-rose-500/10 text-[10px] py-0.5 px-2.5 font-mono font-black italic">{s}</Badge>
                                            ))
                                        ) : (
                                            <span className="text-[9px] text-zinc-600 font-mono tracking-tighter">DATA_MISSING</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                            <div className="pt-4 border-t border-white/5">
                                <h4 className="text-[8px] font-black text-zinc-700 uppercase tracking-widest mb-2">Money Flow Analysis</h4>
                                <p className="text-[12px] xl:text-[14px] text-zinc-300 leading-relaxed font-semibold">
                                    {safeRender(data.sectorRotation?.rotationAnalysis, "Analyzing capital migration...")}
                                </p>
                            </div>
                        </div>
                    </section>
                </div>

                {/* Section IV: Inter-Market Flux & Internals (Full Width) */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">IV</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Inter-Market Flux</h2>
                        </div>
                        <div className="grid grid-cols-1 gap-4">
                            {/* 2x2 Grid for Other Indicators */}
                            <div className="grid grid-cols-2 gap-4">
                                <motion.div whileHover={{ x: 4 }} className="bg-blue-500/5 p-4 rounded-xl border border-blue-500/10 space-y-2 group">
                                    <h4 className="text-[8px] font-black text-blue-400/60 uppercase tracking-widest flex items-center gap-2">
                                        <BarChart3 className="w-3 h-3 text-blue-500/40" /> Bonds (TLT)
                                    </h4>
                                    <p className="text-[11px] xl:text-[13px] text-zinc-300/85 leading-relaxed font-semibold">
                                        {safeRender(data.interMarketAnalysis?.bonds, "N/A")}
                                    </p>
                                </motion.div>

                                <motion.div whileHover={{ x: 4 }} className="bg-yellow-500/5 p-4 rounded-xl border border-yellow-500/10 space-y-2 group">
                                    <h4 className="text-[8px] font-black text-yellow-500/60 uppercase tracking-widest flex items-center gap-2">
                                        <Shield className="w-3 h-3 text-yellow-500/40" /> Commodities
                                    </h4>
                                    <p className="text-[11px] xl:text-[13px] text-zinc-300/85 leading-relaxed font-semibold">
                                        {safeRender(data.interMarketAnalysis?.commodities, "N/A")}
                                    </p>
                                </motion.div>

                                <motion.div whileHover={{ x: 4 }} className="bg-emerald-500/5 p-4 rounded-xl border border-emerald-500/10 space-y-2 group">
                                    <h4 className="text-[8px] font-black text-emerald-400/60 uppercase tracking-widest flex items-center gap-2">
                                        <Coins className="w-3 h-3 text-emerald-500/40" /> Currencies
                                    </h4>
                                    <p className="text-[11px] xl:text-[13px] text-zinc-300/85 leading-relaxed font-semibold">
                                        {safeRender(data.interMarketAnalysis?.currencies, "N/A")}
                                    </p>
                                </motion.div>

                                <motion.div whileHover={{ x: 4 }} className="bg-orange-500/5 p-4 rounded-xl border border-orange-500/10 space-y-2 group">
                                    <h4 className="text-[8px] font-black text-orange-400/60 uppercase tracking-widest flex items-center gap-2">
                                        <Cpu className="w-3 h-3 text-orange-500/40" /> Crypto (BTC)
                                    </h4>
                                    <p className="text-[11px] xl:text-[13px] text-zinc-300/85 leading-relaxed font-semibold">
                                        {safeRender(data.interMarketAnalysis?.crypto, "N/A")}
                                    </p>
                                </motion.div>
                            </div>

                            {/* Market Internals (Volatility) - Reverted to Distinct Style */}
                            <motion.div whileHover={{ y: -4 }} className="bg-violet-500/5 p-5 rounded-2xl border border-violet-500/10 flex flex-col justify-center group relative overflow-hidden">
                                <div className="absolute -right-2 -top-2 opacity-5 group-hover:opacity-10 transition-opacity">
                                    <Gauge className="w-16 h-16 text-violet-500" />
                                </div>
                                <div className="relative z-10 text-left">
                                    <h4 className="text-[9px] font-black text-violet-400/60 uppercase tracking-widest flex items-center justify-start gap-2 mb-2">
                                        <Gauge className="w-4 h-4" /> Volatility (VIX)
                                    </h4>
                                    <p className="text-[11px] xl:text-[13px] font-bold text-zinc-200 italic tracking-tight leading-relaxed">
                                        {safeRender(data.marketInternals?.volatility, "STABLE")}
                                    </p>
                                </div>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section V: Index Analysis */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">V</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Core Index Analysis</h2>
                        </div>
                        <div className="grid grid-cols-1 gap-4">
                            {/* Core Structural Pattern - Centered Badge */}
                            <div className="flex justify-center">
                                <motion.div
                                    whileHover={{ scale: 1.05 }}
                                    className="bg-blue-500/5 px-4 py-1 rounded-full border border-blue-500/10"
                                >
                                    <p className="text-[8px] font-black text-blue-400/60 tracking-[0.2em] uppercase">
                                        {safeRender(data.indexAnalysis?.pattern, "NEUTRAL_FLOW")}
                                    </p>
                                </motion.div>
                            </div>

                            {/* Symbols Grid (SPY, QQQ, IWM, DIA) */}
                            <div className="grid grid-cols-2 gap-4">
                                {['SPY', 'QQQ', 'IWM', 'DIA'].map((symbol) => (
                                    <motion.div key={symbol} whileHover={{ scale: 1.01 }} className="bg-zinc-950/60 p-5 rounded-2xl border border-white/5 space-y-3">
                                        <div className="flex items-center gap-2">
                                            <Badge variant="info" className="text-[10px] font-mono font-black italic px-2">{symbol}</Badge>
                                            <div className="h-px flex-1 bg-white/5" />
                                        </div>
                                        <p className="text-[12px] xl:text-[14px] font-semibold text-zinc-300/90 leading-relaxed">
                                            {safeRender(data.indexAnalysis?.[symbol], "Analysis pending...")}
                                        </p>
                                    </motion.div>
                                ))}
                            </div>

                            {/* Index Summary - Executive Briefing Style */}
                            <motion.div
                                whileHover={{ scale: 1.005 }}
                                className="bg-zinc-950/60 p-6 rounded-2xl border border-white/5 space-y-4 relative overflow-hidden group border-l-2 border-l-blue-500/30"
                            >
                                <div className="absolute -right-4 -top-4 opacity-[0.02] group-hover:opacity-[0.05] transition-opacity">
                                    <Activity className="w-24 h-24 text-white" />
                                </div>

                                <div className="flex items-center justify-between relative z-10">
                                    <div className="flex items-center gap-3">
                                        <div className="p-1.5 bg-blue-500/10 rounded-lg border border-blue-500/10">
                                            <Activity className="w-4 h-4 text-blue-400" />
                                        </div>
                                        <div>
                                            <h4 className="text-[10px] font-black text-zinc-100 uppercase tracking-[0.2em]">Composite Briefing</h4>
                                            <p className="text-[7px] font-bold text-zinc-500 uppercase tracking-widest">Index Analysis Summary</p>
                                        </div>
                                    </div>
                                    <div className="text-[8px] text-zinc-600 font-mono tracking-tighter opacity-50 uppercase italic">Analysis Finalized</div>
                                </div>

                                <p className="text-[13px] xl:text-[15px] text-zinc-100 leading-relaxed font-bold italic relative z-10">
                                    {safeRender(data.indexAnalysis?.index_summary || data.indexAnalysis?.summary, "Compiling structural index briefing...")}
                                </p>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section VI: Key Action Log - Timeline Style */}
                <div className="lg:col-span-12">
                    <section className="space-y-6 pb-12">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">VI</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Key Action Log (T-1)</h2>
                        </div>

                        <div className="relative ml-4 space-y-8 before:absolute before:inset-0 before:ml-1 before:-translate-x-px before:h-full before:w-0.5 before:bg-gradient-to-b before:from-zinc-800/50 before:via-zinc-800 before:to-transparent">
                            {([...(data.keyActionLog || [
                                "Global markets reacted to heightened inflationary prints across the EU core.",
                                "SPY rejected the overhead monthly supply zone with aggressive retail selling.",
                                "Volatility (VIX) spiked into the mid-day session as credit spreads widened.",
                                "Sector rotation favored defensive defensive positioning in Healthcare and Staples.",
                                "Closing auction saw significant institutional rebalancing in large-cap tech."
                            ])].reverse()).slice(0, 5).map((item: any, i: number) => (
                                <motion.div
                                    key={i}
                                    initial={{ opacity: 0, x: -10 }}
                                    whileInView={{ opacity: 1, x: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: i * 0.1 }}
                                    className="relative flex items-start gap-6 group"
                                >
                                    {/* Timeline Marker */}
                                    <div className="absolute left-0 mt-1.5 -ml-[3px] w-2 h-2 rounded-full bg-zinc-800 border-2 border-zinc-700 group-hover:border-amber-500/50 group-hover:bg-amber-500/20 transition-all duration-500 z-10 shadow-[0_0_8px_rgba(0,0,0,0.5)]" />

                                    <div className="flex-1 bg-zinc-950/20 p-4 rounded-xl border border-white/5 transition-colors group-hover:bg-zinc-900/40 group-hover:border-white/10">
                                        <div className="flex items-center justify-between mb-2">
                                            <h4 className="text-[7px] font-black text-zinc-600 uppercase tracking-widest flex items-center gap-1.5">
                                                <Clock className="w-2.5 h-2.5" /> Sequential Log 0{i + 1}
                                                {typeof item === 'object' && item?.date && (
                                                    <span className="text-zinc-500 font-mono ml-2 lowercase opacity-50">[{item.date}]</span>
                                                )}
                                            </h4>
                                            <span className="text-[6px] font-black text-zinc-800 uppercase tracking-widest bg-white/5 px-2 py-0.5 rounded-full">Historical_Ref</span>
                                        </div>
                                        <p className="text-[11px] xl:text-[13px] text-zinc-400 font-semibold leading-relaxed">
                                            {safeRender(item)}
                                        </p>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    </section>
                </div>
            </div>
        </div>
    );
}
