"use client";

import React from 'react';
import { Badge } from '@/components/ui/core';
import {
    Target,
    Zap,
    Brain,
    TrendingUp,
    TrendingDown,
    ArrowRight,
    Shield,
    Activity
} from 'lucide-react';

interface ScreenerBriefingViewProps {
    /** The screener briefing — either a string (key: value per line) or a parsed dict */
    briefing: string | Record<string, any>;
    /** Plan A/B data from the backend response (extracted by card_extractor) */
    planAText?: string;
    planBText?: string;
    planALevel?: number | null;
    planBLevel?: number | null;
    planANature?: string;
    planBNature?: string;
    setupBias?: string;
    ticker?: string;
}

export default function ScreenerBriefingView({
    briefing,
    planAText,
    planBText,
    planALevel,
    planBLevel,
    planANature,
    planBNature,
    setupBias,
    ticker
}: ScreenerBriefingViewProps) {

    // Parse briefing if it's a string
    const parsed: Record<string, string> = {};
    if (typeof briefing === 'string') {
        briefing.split('\n').forEach(line => {
            const idx = line.indexOf(':');
            if (idx > 0) {
                const key = line.slice(0, idx).trim();
                const val = line.slice(idx + 1).trim();
                if (key && val) parsed[key] = val;
            }
        });
    } else if (briefing && typeof briefing === 'object') {
        Object.entries(briefing).forEach(([k, v]) => {
            parsed[k] = String(v);
        });
    }

    const bias = setupBias || parsed.Setup_Bias || 'Neutral';
    const isBullish = /bull|long/i.test(bias);
    const isBearish = /bear|short/i.test(bias);

    const justification = parsed.Justification || parsed.Reasoning || '';
    const catalyst = parsed.Catalyst || '';
    const pattern = parsed.Pattern || '';

    const getPlanColor = (nature?: string) => {
        if (nature === 'SUPPORT') return { text: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20', icon: TrendingUp };
        if (nature === 'RESISTANCE') return { text: 'text-rose-400', bg: 'bg-rose-500/10', border: 'border-rose-500/20', icon: TrendingDown };
        return { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/20', icon: Activity };
    };

    const planAColor = getPlanColor(planANature);
    const planBColor = getPlanColor(planBNature);
    const PlanAIcon = planAColor.icon;
    const PlanBIcon = planBColor.icon;

    return (
        <div className="space-y-5 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Header: Bias Badge */}
            <div className="flex items-center gap-3">
                <Badge
                    variant={isBullish ? 'success' : isBearish ? 'error' : 'warning'}
                    className={`text-[11px] font-black italic tracking-[0.15em] uppercase px-3 py-1 border-none ${isBullish ? 'bg-emerald-500/15 text-emerald-400' :
                            isBearish ? 'bg-rose-500/15 text-rose-400' :
                                'bg-amber-500/15 text-amber-400'
                        }`}
                >
                    {bias}
                </Badge>
                <div className="h-px flex-1 bg-white/5" />
            </div>

            {/* Justification — The Core Story */}
            {justification && (
                <div className="bg-blue-500/5 p-4 rounded-xl border border-blue-500/10 space-y-2">
                    <h3 className="text-[9px] font-black uppercase text-blue-400/60 tracking-widest flex items-center gap-1.5">
                        <Brain className="w-3 h-3" /> Today&apos;s Story
                    </h3>
                    <p className="text-[13px] text-zinc-200 leading-relaxed font-medium">
                        {justification}
                    </p>
                </div>
            )}

            {/* Catalyst + Pattern Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {catalyst && (
                    <div className="bg-amber-500/5 p-3.5 rounded-xl border border-amber-500/10 space-y-1.5">
                        <h3 className="text-[9px] font-black uppercase text-amber-400/60 tracking-widest flex items-center gap-1.5">
                            <Zap className="w-3 h-3" /> Catalyst
                        </h3>
                        <p className="text-[12px] text-zinc-300 leading-relaxed font-semibold">{catalyst}</p>
                    </div>
                )}
                {pattern && (
                    <div className="bg-violet-500/5 p-3.5 rounded-xl border border-violet-500/10 space-y-1.5">
                        <h3 className="text-[9px] font-black uppercase text-violet-400/60 tracking-widest flex items-center gap-1.5">
                            <Target className="w-3 h-3" /> Pattern
                        </h3>
                        <p className="text-[12px] text-zinc-300 leading-relaxed font-semibold">{pattern}</p>
                    </div>
                )}
            </div>

            {/* Plan A & Plan B Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Plan A */}
                <div className={`${planAColor.bg} p-4 rounded-xl border ${planAColor.border} space-y-3 relative overflow-hidden`}>
                    <div className={`absolute top-0 left-0 w-1 h-full ${planANature === 'SUPPORT' ? 'bg-emerald-500' : planANature === 'RESISTANCE' ? 'bg-rose-500' : 'bg-blue-500'}`} />
                    <div className="flex items-center justify-between">
                        <h3 className={`text-[10px] font-black uppercase tracking-[0.15em] ${planAColor.text} flex items-center gap-1.5`}>
                            <Shield className="w-3 h-3" /> Plan A
                        </h3>
                        {planANature && planANature !== 'UNKNOWN' && (
                            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${planAColor.bg} ${planAColor.text} border ${planAColor.border}`}>
                                {planANature}
                            </span>
                        )}
                    </div>
                    <div>
                        <p className="text-[13px] font-bold text-white leading-snug">
                            {planAText || parsed.Plan_A || 'N/A'}
                        </p>
                        {planALevel !== null && planALevel !== undefined && (
                            <div className="flex items-center gap-2 mt-2">
                                <PlanAIcon className={`w-4 h-4 ${planAColor.text}`} />
                                <span className={`font-mono font-black text-lg ${planAColor.text}`}>
                                    ${planALevel.toFixed(2)}
                                </span>
                            </div>
                        )}
                    </div>
                </div>

                {/* Plan B */}
                <div className={`${planBColor.bg} p-4 rounded-xl border ${planBColor.border} space-y-3 relative overflow-hidden`}>
                    <div className={`absolute top-0 left-0 w-1 h-full ${planBNature === 'SUPPORT' ? 'bg-emerald-500' : planBNature === 'RESISTANCE' ? 'bg-rose-500' : 'bg-blue-500'}`} />
                    <div className="flex items-center justify-between">
                        <h3 className={`text-[10px] font-black uppercase tracking-[0.15em] ${planBColor.text} flex items-center gap-1.5`}>
                            <ArrowRight className="w-3 h-3" /> Plan B
                        </h3>
                        {planBNature && planBNature !== 'UNKNOWN' && (
                            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${planBColor.bg} ${planBColor.text} border ${planBColor.border}`}>
                                {planBNature}
                            </span>
                        )}
                    </div>
                    <div>
                        <p className="text-[13px] font-bold text-white leading-snug">
                            {planBText || parsed.Plan_B || 'N/A'}
                        </p>
                        {planBLevel !== null && planBLevel !== undefined && (
                            <div className="flex items-center gap-2 mt-2">
                                <PlanBIcon className={`w-4 h-4 ${planBColor.text}`} />
                                <span className={`font-mono font-black text-lg ${planBColor.text}`}>
                                    ${planBLevel.toFixed(2)}
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
