import React, { useState } from 'react';
import { Badge } from '@/components/ui/core';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Zap,
    Brain,
    Target,
    Activity,
    ArrowRight,
    ChevronDown,
    ChevronUp,
    ShieldAlert,
    X
} from 'lucide-react';

interface CompanyCardViewProps {
    card: any;
    ticker?: string;
    date?: string;
    isExpanded?: boolean;
    onLaunchChart?: (ticker: string) => void;
    isArchive?: boolean;
}

export default function CompanyCardView({ card, ticker, date, isExpanded, onLaunchChart, isArchive }: CompanyCardViewProps) {
    const [selectedPlan, setSelectedPlan] = useState<any>(null);

    if (!card) return null;

    const data = typeof card === 'string' ? JSON.parse(card) : card;

    const getPlanStyles = (text: string | null) => {
        if (!text) return { border: 'border-l-[#3b82f6]/50', badge: 'bg-[#3b82f6]/10 text-blue-400', text: 'text-blue-400' };
        const t = text.toLowerCase();
        const isShort = /short|bear|sell|put|below|failure|resistance|rejection|reject|fade/i.test(t);
        const isLong = /long|bull|buy|call|above|support|bounce|break|cross/i.test(t);

        if (isShort) return { border: 'border-l-rose-500', badge: 'bg-rose-500/10 text-rose-400', text: 'text-rose-400' };
        if (isLong) return { border: 'border-l-emerald-500', badge: 'bg-emerald-500/10 text-emerald-400', text: 'text-emerald-400' };
        return { border: 'border-l-blue-500/50', badge: 'bg-blue-500/10 text-blue-400', text: 'text-blue-400' };
    };

    // Parser for Behavioral Acts (Act I, Act II, Act III)
    const parseActs = (text: string | undefined) => {
        if (!text) return [];
        // Match things like **(Act I)** or (Act I) or Act I:
        const acts = text.split(/\*\*\(Act (?:I|II|III)\)\*\*/g).filter(s => s.trim().length > 0);
        const labels = text.match(/\*\*\(Act (?:I|II|III)\)\*\*/g) || [];

        // If no acts found, try a simpler regex or return the whole thing as one
        if (labels.length === 0) {
            // Fallback to secondary act markers
            const secondaryMatch = text.match(/\(Act (?:I|II|III)\)/g);
            if (secondaryMatch) {
                return text.split(/\(Act (?:I|II|III)\)/g).filter(s => s.trim().length > 0).map((content, i) => ({
                    label: secondaryMatch[i]?.replace(/[()]/g, '') || `PART ${i + 1}`,
                    content: content.trim().replace(/^\*\*|\*\*$/g, '').trim()
                }));
            }
            return [{ label: "ANALYSIS", content: text }];
        }

        return labels.map((label, i) => ({
            label: label.replace(/\*\*|\(|\)/g, '').trim(),
            content: acts[i]?.trim().replace(/^\*\*|\*\*$/g, '').trim()
        }));
    };

    // Parser for Structural Zones [price (label), price (label)]
    const parseZones = (text: string | undefined) => {
        if (!text) return [];
        const clean = text.replace(/[\[\]]/g, '');
        const levels = clean.split(/,(?![^\(]*\))/);
        return levels.map(l => l.trim()).filter(l => l.length > 0);
    };

    // Parser for Trend Narrative (Confidence Field)
    const parseConfidence = (text: string | undefined) => {
        const result = { bias: 'NEUTRAL', level: 'MEDIUM', reasoning: '' };
        if (!text) return result;

        // Try to extract Bias (Handles "Bias:" or "Trend_Bias:")
        const biasMatch = text.match(/(?:Trend_)?Bias:\s*([\w\s]+?)(?=\.|$|Confidence:|Reasoning:|[\-\(\)])/i);
        if (biasMatch) result.bias = biasMatch[1].trim().toUpperCase();

        // Try to extract Confidence Level (Handles "Confidence:" or "Story_Confidence:")
        const levelMatch = text.match(/(?:Story_)?Confidence:\s*([\w\s]+?)(?=\.|$|Reasoning:|[\-\(\)])/i);
        if (levelMatch) result.level = levelMatch[1].trim().toUpperCase();

        // Try to extract Reasoning
        const reasoningMatch = text.match(/Reasoning:\s*([\s\S]+)/i);
        if (reasoningMatch) {
            result.reasoning = reasoningMatch[1].trim();
        } else {
            // fallback: take everything after Bias/Level or the whole thing
            result.reasoning = text.split(/(?:Trend_)?Bias:|(?:Story_)?Confidence:/i).pop()?.trim() || text;
        }

        return result;
    };

    // Parser for screener_briefing Data Packet
    const parseScreenerBriefing = (text: string | undefined) => {
        const result: any = {};
        if (!text) return result;

        const lines = text.split('\n');
        lines.forEach(line => {
            const [key, ...valueParts] = line.split(':');
            if (key && valueParts.length > 0) {
                result[key.trim()] = valueParts.join(':').trim();
            }
        });
        return result;
    };

    const screenerData = parseScreenerBriefing(data.screener_briefing);
    const confidenceData = parseConfidence(data.confidence);

    const stylesA = getPlanStyles(data.openingTradePlan?.planName || data.screener_briefing?.Plan_A);
    const stylesB = getPlanStyles(data.alternativePlan?.planName || data.screener_briefing?.Plan_B);
    const sentimentActs = parseActs(data.behavioralSentiment?.emotionalTone?.includes('Reasoning:')
        ? data.behavioralSentiment.emotionalTone.split('Reasoning:')[1].trim()
        : data.behavioralSentiment?.emotionalTone);

    const supportLevels = parseZones(data.technicalStructure?.majorSupport);
    const resistanceLevels = parseZones(data.technicalStructure?.majorResistance);

    return (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-700 space-y-6 w-full pb-10 px-6">
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Section I: Trend Narrative (Full Width Top) */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">I</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Trend Narrative</h2>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                            <motion.div whileHover={{ scale: 1.01 }} className="bg-zinc-900/40 p-4 rounded-xl border border-white/5 space-y-2 group">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Activity className="w-2.5 h-2.5 text-blue-500/40" /> Trend Bias
                                </h3>
                                <Badge
                                    variant={confidenceData.bias.includes('BULL') ? 'success' : confidenceData.bias.includes('BEAR') ? 'error' : 'default'}
                                    className="text-[12px] font-black italic tracking-widest uppercase px-2 py-0.5"
                                >
                                    {confidenceData.bias}
                                </Badge>
                            </motion.div>
                            <motion.div whileHover={{ scale: 1.01 }} className="bg-zinc-900/40 p-4 rounded-xl border border-white/5 space-y-2 group">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Brain className="w-2.5 h-2.5 text-purple-500/40" /> Story Confidence
                                </h3>
                                <div className="flex items-center gap-2">
                                    <span className="text-[14px] font-black text-white italic">{confidenceData.level}</span>
                                    <div className="flex gap-0.5">
                                        {[1, 2, 3].map(i => (
                                            <div key={i} className={`w-1.5 h-3 rounded-sm ${i <= (confidenceData.level.includes('HIGH') ? 3 : confidenceData.level.includes('MEDIUM') ? 2 : 1) ? 'bg-primary' : 'bg-white/10'}`} />
                                        ))}
                                    </div>
                                </div>
                            </motion.div>
                            <motion.div whileHover={{ scale: 1.01 }} className="bg-zinc-900/40 p-4 rounded-xl border border-white/5 space-y-2 group md:col-span-1">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Brain className="w-2.5 h-2.5 text-blue-500/40" /> Narrative Reasoning
                                </h3>
                                <p className="text-[11.5px] xl:text-[13.5px] text-zinc-300 leading-relaxed font-medium italic line-clamp-2 group-hover:line-clamp-none transition-all">
                                    {confidenceData.reasoning}
                                </p>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section II: Screener Briefing (Full Width) */}
                <div className="lg:col-span-12 transition-all duration-300">
                    <section className="space-y-3">
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2">
                                <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">II</div>
                                <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Screener Briefing</h2>
                            </div>
                            {(() => {
                                const bias = (screenerData.Setup_Bias || 'LONG/SHORT').toUpperCase();
                                const isBull = bias.includes('BULL') || bias.includes('LONG');
                                const isBear = bias.includes('BEAR') || bias.includes('SHORT');
                                return (
                                    <Badge
                                        variant={isBull ? 'success' : isBear ? 'error' : 'warning'}
                                        className={`text-[10px] font-black italic tracking-widest uppercase px-2 py-0 border-none ${isBull ? 'bg-emerald-500/10 text-emerald-400' :
                                            isBear ? 'bg-rose-500/10 text-rose-400' :
                                                'bg-amber-500/10 text-amber-400'
                                            }`}
                                    >
                                        {bias}
                                    </Badge>
                                );
                            })()}
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <motion.div whileHover={{ y: -2 }} className="md:col-span-1 bg-amber-500/5 p-3 rounded-xl border border-amber-500/10 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-yellow-500/60 tracking-widest flex items-center gap-1.5">
                                    <Zap className="w-2.5 h-2.5" /> Recent Catalyst
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-200 leading-relaxed font-semibold`}>
                                    {screenerData.Catalyst || data.basicContext?.recentCatalyst || 'No primary catalyst detected.'}
                                </p>
                            </motion.div>

                            <motion.div whileHover={{ y: -2 }} className="md:col-span-2 bg-blue-500/5 p-3 rounded-xl border border-blue-500/10 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-blue-400/60 tracking-widest flex items-center gap-1.5">
                                    <Brain className="w-2.5 h-2.5 text-blue-500/40" /> Briefing
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold`}>
                                    {screenerData.Justification || screenerData.Reasoning || screenerData.Impact || 'Tactical context loading...'}
                                </p>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section III: Fundamental Context (Full Width) */}
                <div className="lg:col-span-12 transition-all duration-300">
                    <section className="space-y-3 h-full">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">III</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Fundamental Context</h2>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <motion.div whileHover={{ y: -2 }} className="bg-zinc-900/40 p-3 rounded-xl border border-white/5 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Activity className="w-2.5 h-2.5 text-zinc-500/40" /> Valuation
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold`}>
                                    {data.fundamentalContext?.valuation || 'Metric analysis pending...'}
                                </p>
                            </motion.div>

                            <motion.div whileHover={{ y: -2 }} className="bg-zinc-900/40 p-3 rounded-xl border border-white/5 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Target className="w-2.5 h-2.5 text-emerald-500/40" /> Peer Performance
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold`}>
                                    {data.fundamentalContext?.peerPerformance || 'Sector stability maintained.'}
                                </p>
                            </motion.div>

                            <motion.div whileHover={{ y: -2 }} className="bg-zinc-900/40 p-3 rounded-xl border border-white/5 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Zap className="w-2.5 h-2.5 text-amber-500/40" /> Insider Activity
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold`}>
                                    {data.fundamentalContext?.insiderActivity || 'No significant liquidation or accumulation detected.'}
                                </p>
                            </motion.div>

                            <motion.div whileHover={{ y: -2 }} className="bg-zinc-900/40 p-3 rounded-xl border border-white/5 space-y-1.5 group cursor-default">
                                <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                    <Brain className="w-2.5 h-2.5 text-blue-500/40" /> Analyst Sentiment
                                </h3>
                                <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold`}>
                                    {data.fundamentalContext?.analystSentiment || 'Consensus remains neutral.'}
                                </p>
                            </motion.div>
                        </div>
                    </section>
                </div>

                {/* Section IV: Behavioral Sentiment (Full Width) */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">IV</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Behavioral Sentiment</h2>
                        </div>
                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
                            {/* The 3 Acts */}
                            <div className="lg:col-span-6 bg-violet-900/5 p-4 rounded-xl border border-violet-500/5 relative overflow-hidden">
                                <div className="relative space-y-4">
                                    {sentimentActs.map((act, i) => (
                                        <motion.div
                                            key={i}
                                            whileHover={{ x: 4 }}
                                            className="relative pl-5 border-l border-violet-500/20 last:border-l-transparent pb-0.5 group cursor-default"
                                        >
                                            <div className="absolute -left-[4.5px] top-1 w-2 h-2 rounded-full bg-zinc-950 border border-violet-500 flex items-center justify-center group-hover:scale-125 transition-transform">
                                                <div className="w-0.5 h-0.5 rounded-full bg-violet-500" />
                                            </div>
                                            <h6 className="text-[8px] font-black text-violet-500/80 uppercase tracking-widest mb-0.5">{act.label}</h6>
                                            <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} text-zinc-300 leading-relaxed font-semibold transition-all`}>
                                                {act.content}
                                            </p>
                                        </motion.div>
                                    ))}
                                </div>
                            </div>
                            {/* Buyer Vs Seller & News Reaction (Conviction Row) */}
                            <div className="lg:col-span-6 space-y-4">
                                <motion.div
                                    whileHover={{ y: -4, scale: 1.01 }}
                                    className="bg-blue-500/5 p-4 rounded-xl border border-blue-500/10 space-y-2 group cursor-default"
                                >
                                    <h3 className="text-[8px] font-black uppercase text-blue-400/50 tracking-widest flex items-center gap-1.5">
                                        <Activity className="w-2.5 h-2.5" /> Buyer Vs Seller
                                    </h3>
                                    <p className={`${isArchive ? 'text-[13px]' : 'text-[12px]'} text-zinc-300 leading-relaxed font-semibold transition-all`}>
                                        {data.behavioralSentiment?.buyerVsSeller || 'Net neutral.'}
                                    </p>
                                </motion.div>

                                <motion.div
                                    whileHover={{ y: -4, scale: 1.01 }}
                                    className="bg-orange-500/5 p-4 rounded-xl border border-orange-500/10 space-y-2 group cursor-default"
                                >
                                    <h3 className="text-[8px] font-black uppercase text-orange-400/50 tracking-widest flex items-center gap-1.5">
                                        <Zap className="w-2.5 h-2.5" /> News Reaction
                                    </h3>
                                    <p className={`${isArchive ? 'text-[13px]' : 'text-[12px]'} text-zinc-300 leading-relaxed font-semibold transition-all`}>
                                        {data.behavioralSentiment?.newsReaction || 'Stability maintained post-data.'}
                                    </p>
                                </motion.div>
                            </div>
                        </div>
                    </section>
                </div>

                {/* Section V: Technical Structure */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">V</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Technical Structure</h2>
                        </div>

                        <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                            {/* Core Setup (Main Space) */}
                            <div className="lg:col-span-6">
                                <motion.div
                                    whileHover={{ y: -4 }}
                                    className="bg-zinc-900/40 p-4 rounded-xl border border-white/5 h-full space-y-3 group cursor-default shadow-sm hover:shadow-primary/5 transition-all duration-75"
                                >
                                    <h3 className="text-[8px] font-black uppercase text-zinc-500 tracking-widest flex items-center gap-1.5">
                                        <Target className="w-2.5 h-2.5 text-primary/30" /> Pattern
                                    </h3>
                                    <p className={`${isArchive ? 'text-[13.5px]' : 'text-[12.5px]'} font-semibold text-zinc-300 leading-relaxed transition-all duration-75`}>
                                        {data.technicalStructure?.pattern || 'SEARCHING...'}
                                    </p>
                                    {data.technicalStructure?.volumeMomentum && (
                                        <div className="pt-2.5 border-t border-white/5">
                                            <h4 className="text-[8px] font-black text-zinc-500 uppercase tracking-widest mb-2.5">Volume Momentum</h4>
                                            <p className="text-[13.5px] text-zinc-300 leading-relaxed font-medium italic transition-all duration-75">{data.technicalStructure.volumeMomentum}</p>
                                        </div>
                                    )}
                                </motion.div>
                            </div>

                            {/* Zones (Stacked side rail) */}
                            <div className="lg:col-span-6 space-y-2">
                                <motion.div
                                    whileHover={{ y: -4 }}
                                    className="bg-rose-500/5 p-2.5 rounded-lg border border-rose-500/10 transition-all duration-75"
                                >
                                    <h3 className="text-[8px] font-black uppercase text-rose-500/30 mb-1.5 tracking-widest">Major Resistance</h3>
                                    <div className="flex flex-wrap gap-1">
                                        {resistanceLevels.map((lvl, i) => (
                                            <div key={i} className="bg-rose-500/10 border border-rose-500/20 px-1.5 py-0.5 rounded-md">
                                                <span className="text-[11px] font-black text-rose-400 font-mono tracking-tighter">{lvl}</span>
                                            </div>
                                        ))}
                                    </div>
                                </motion.div>
                                <motion.div
                                    whileHover={{ y: -4 }}
                                    className="bg-emerald-500/5 p-2.5 rounded-lg border border-emerald-500/10 transition-all duration-75"
                                >
                                    <h3 className="text-[8px] font-black uppercase text-emerald-500/30 mb-1.5 tracking-widest">Major Support</h3>
                                    <div className="flex flex-wrap gap-1">
                                        {supportLevels.map((lvl, i) => (
                                            <div key={i} className="bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-md">
                                                <span className="text-[11px] font-black text-emerald-400 font-mono tracking-tighter">{lvl}</span>
                                            </div>
                                        ))}
                                    </div>
                                </motion.div>
                            </div>
                        </div>
                    </section>
                </div>

                {/* Section VI: Tactical Operations */}
                <div className="lg:col-span-12">
                    <section className="space-y-3">
                        <div className="flex items-center gap-2">
                            <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">VI</div>
                            <h2 className="text-[9px] font-black uppercase text-zinc-600 tracking-[0.2em]">Tactical operations</h2>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            {data.openingTradePlan && (
                                <motion.div
                                    whileHover={{ y: -4, scale: 1.01 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={() => setSelectedPlan({ ...data.openingTradePlan, label: 'MISSION PLAN A', styles: stylesA })}
                                    className={`bg-zinc-900/60 p-3.5 rounded-lg border border-white/5 border-l-2 ${stylesA.border} transition-all cursor-pointer hover:bg-zinc-800/80 group shadow-lg`}
                                >
                                    <div className="flex justify-between items-center mb-1.5">
                                        <span className={`text-[8px] font-black ${stylesA.text} opacity-50 uppercase tracking-widest flex items-center gap-1.5`}>
                                            MISSION PLAN A
                                            <Zap className="w-2 h-2" />
                                        </span>
                                        <span className={`font-mono font-black text-[12px] ${stylesA.text} italic`}>
                                            {data.openingTradePlan.trigger?.match(/\d+\.?\d*/)?.[0] ? `$${data.openingTradePlan.trigger.match(/\d+\.?\d*/)?.[0]}` : 'EXECUTE'}
                                        </span>
                                    </div>
                                    <h4 className="text-[11px] group-hover:text-[13px] font-black text-zinc-300 mb-1.5 leading-none uppercase italic tracking-widest group-hover:text-white transition-all duration-75">
                                        {data.openingTradePlan.planName}
                                    </h4>
                                    <div className="flex items-start gap-1.5 pt-1.5 border-t border-white/5 opacity-40 group-hover:opacity-100 transition-opacity">
                                        <Target className="w-2 h-2 text-zinc-700 mt-0.5" />
                                        <p className="text-[9px] group-hover:text-[11px] font-bold text-zinc-400 tracking-tight leading-tight line-clamp-1 transition-all duration-75">Click to view mission details</p>
                                    </div>
                                </motion.div>
                            )}
                            {data.alternativePlan && (
                                <motion.div
                                    whileHover={{ y: -4, scale: 1.01 }}
                                    whileTap={{ scale: 0.98 }}
                                    onClick={() => setSelectedPlan({ ...data.alternativePlan, label: 'MISSION PLAN B', styles: stylesB })}
                                    className={`bg-zinc-900/60 p-3.5 rounded-lg border border-white/5 border-l-2 ${stylesB.border} transition-all cursor-pointer hover:bg-zinc-800/80 group shadow-lg`}
                                >
                                    <div className="flex justify-between items-center mb-1.5">
                                        <span className={`text-[8px] font-black ${stylesB.text} opacity-50 uppercase tracking-widest flex items-center gap-1.5`}>
                                            MISSION PLAN B
                                            <Activity className="w-2 h-2" />
                                        </span>
                                        <span className={`font-mono font-black text-[12px] ${stylesB.text} italic`}>
                                            {data.alternativePlan.trigger?.match(/\d+\.?\d*/)?.[0] ? `$${data.alternativePlan.trigger.match(/\d+\.?\d*/)?.[0]}` : 'EXECUTE'}
                                        </span>
                                    </div>
                                    <h4 className="text-[11px] group-hover:text-[13px] font-black text-zinc-300 mb-1.5 leading-none uppercase italic tracking-widest group-hover:text-white transition-all duration-75">
                                        {data.alternativePlan.planName}
                                    </h4>
                                    <div className="flex items-start gap-1.5 pt-1.5 border-t border-white/5 opacity-40 group-hover:opacity-100 transition-opacity">
                                        <Activity className="w-2 h-2 text-zinc-700 mt-0.5" />
                                        <p className="text-[9px] group-hover:text-[11px] font-bold text-zinc-400 tracking-tight leading-tight line-clamp-1 transition-all duration-75">Click to view mission details</p>
                                    </div>
                                </motion.div>
                            )}
                        </div>
                    </section>
                </div>

                {
                    data.technicalStructure?.keyActionLog && data.technicalStructure.keyActionLog.length > 0 && (
                        <div className="lg:col-span-12">
                            <section className="space-y-4 pt-5 border-t border-white/5">
                                <div className="flex items-center gap-2 text-zinc-700">
                                    <div className="bg-primary/20 text-primary px-1.5 py-0.5 text-[8px] font-black italic">VII</div>
                                    <h2 className="text-[9px] font-black uppercase tracking-widest">Action Log</h2>
                                </div>
                                <div className="relative pl-4 space-y-6 pb-2">
                                    {/* Timeline Line */}
                                    <div className="absolute left-[7px] top-2 bottom-2 w-px bg-gradient-to-b from-primary/50 via-primary/20 to-transparent" />

                                    {data.technicalStructure.keyActionLog.slice(-5).reverse().map((entry: any, i: number) => (
                                        <motion.div
                                            key={i}
                                            initial={{ opacity: 0, x: -10 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: i * 0.1 }}
                                            className="relative pl-6 group"
                                        >
                                            {/* Timeline Dot */}
                                            <div className="absolute left-[-13.5px] top-1.5 w-3 h-3 rounded-full bg-zinc-950 border-2 border-primary/50 flex items-center justify-center transition-all group-hover:border-primary group-hover:shadow-[0_0_8px_rgba(0,204,150,0.3)]">
                                                <div className="w-1 h-1 rounded-full bg-primary/30 group-hover:bg-primary transition-all" />
                                            </div>

                                            <div className="space-y-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[8px] font-black text-primary/60 group-hover:text-primary uppercase tracking-widest transition-colors">{entry.date}</span>
                                                    <div className="h-px flex-1 bg-white/5" />
                                                </div>
                                                <p className={`${isExpanded ? 'text-[12.5px] xl:text-[14.5px] 2xl:text-[16.5px]' : 'text-[10.5px] xl:text-[12.5px]'} text-zinc-400 leading-relaxed italic group-hover:text-zinc-200 transition-colors`}>
                                                    {entry.action}
                                                </p>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            </section>
                        </div>
                    )
                }
                {/* Plan Detail Modal */}
                <AnimatePresence>
                    {selectedPlan && (
                        <>
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                exit={{ opacity: 0 }}
                                onClick={() => setSelectedPlan(null)}
                                className="fixed inset-0 bg-black/60 backdrop-blur-md z-[100] flex items-center justify-center p-4"
                            >
                                <motion.div
                                    initial={{ scale: 0.95, opacity: 0, y: 20 }}
                                    animate={{ scale: 1, opacity: 1, y: 0 }}
                                    exit={{ scale: 0.95, opacity: 0, y: 20 }}
                                    onClick={(e) => e.stopPropagation()}
                                    className={`w-full max-w-lg bg-zinc-950/90 border border-white/10 rounded-2xl p-6 shadow-2xl relative overflow-hidden`}
                                >
                                    {/* Decorative Gradient Background */}
                                    <div className={`absolute top-0 left-0 w-full h-1 ${selectedPlan.styles.border.replace('border-l-', 'bg-')} opacity-30`} />

                                    <button
                                        onClick={() => setSelectedPlan(null)}
                                        className="absolute top-4 right-4 text-zinc-600 hover:text-white transition-colors"
                                    >
                                        <X className="w-5 h-5" />
                                    </button>

                                    <div className="space-y-6">
                                        <div className="space-y-1.5">
                                            <div className="flex items-center gap-2">
                                                <span className={`text-[9px] font-black ${selectedPlan.styles.text} bg-white/5 px-2 py-0.5 rounded italic tracking-[0.2em]`}>
                                                    {selectedPlan.label}
                                                </span>
                                                <span className="text-[9px] font-mono text-zinc-600 font-bold tracking-widest">TACTICAL_INTEL_LOADED</span>
                                            </div>
                                            <h2 className="text-[14px] font-black text-white italic tracking-widest uppercase">
                                                {selectedPlan.planName}
                                            </h2>
                                        </div>

                                        <div className="space-y-5">
                                            <div className="bg-white/5 p-4 rounded-xl border border-white/5 space-y-2.5">
                                                <div className="flex items-center gap-2">
                                                    <Target className={`w-4 h-4 ${selectedPlan.styles.text}`} />
                                                    <h3 className="text-[10px] font-black uppercase text-zinc-500 tracking-widest">Mission Trigger</h3>
                                                </div>
                                                <p className="text-[12px] text-zinc-200 leading-relaxed font-medium">
                                                    {selectedPlan.trigger || 'Validation required before execution.'}
                                                </p>
                                            </div>

                                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                                <div className="bg-rose-500/5 p-4 rounded-xl border border-rose-500/10 space-y-2">
                                                    <div className="flex items-center gap-2">
                                                        <ShieldAlert className="w-3.5 h-3.5 text-rose-500/60" />
                                                        <h3 className="text-[9px] font-black uppercase text-rose-500/40 tracking-widest">Abort Level</h3>
                                                    </div>
                                                    <p className="text-[11px] text-rose-200/80 font-bold font-mono">
                                                        {selectedPlan.invalidation || 'Break of structural floor.'}
                                                    </p>
                                                </div>
                                                <div className="bg-emerald-500/5 p-4 rounded-xl border border-emerald-500/10 space-y-2">
                                                    <div className="flex items-center gap-2">
                                                        <Activity className="w-3.5 h-3.5 text-emerald-500/60" />
                                                        <h3 className="text-[9px] font-black uppercase text-emerald-500/40 tracking-widest">Target Flow</h3>
                                                    </div>
                                                    <p className="text-[11px] text-emerald-200/80 font-bold italic">
                                                        {selectedPlan.expectedParticipant || selectedPlan.scenario || 'Searching...'}
                                                    </p>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="pt-4 border-t border-white/5 flex justify-end">
                                            <button
                                                onClick={() => setSelectedPlan(null)}
                                                className="px-6 py-2 bg-white/5 hover:bg-white/10 text-white text-[10px] font-black uppercase tracking-widest rounded-lg transition-all border border-white/5 italic"
                                            >
                                                Acknowledge Intel
                                            </button>
                                        </div>
                                    </div>
                                </motion.div>
                            </motion.div>
                        </>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}
