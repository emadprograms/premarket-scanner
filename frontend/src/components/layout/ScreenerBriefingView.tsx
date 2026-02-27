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

        </div>
    );
}
