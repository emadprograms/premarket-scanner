"use client";

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, Button, Badge } from '@/components/ui/core';
import {
    History,
    Search,
    FileJson,
    Save,
    ArrowLeft,
    Calendar,
    SearchCode,
    ChevronRight,
    Filter,
    Loader2,
    RefreshCcw,
    PanelLeftClose,
    PanelLeftOpen,
    Trash2,
    AlertTriangle,
    X,
    TrendingUp,
    TrendingDown,
    Minus
} from 'lucide-react';
import { useMission } from '@/lib/context';
import { getCards, updateCard, deleteCard } from '@/lib/api';
import EconomyCardView from './EconomyCardView';
import CompanyCardView from './CompanyCardView';

export default function CardEditorView() {
    const { settings } = useMission();
    const [selectedType, setSelectedType] = useState<'economy' | 'company'>('economy');
    const [viewMode, setViewMode] = useState<'edit' | 'study'>('study');
    const [searchTerm, setSearchTerm] = useState("");
    const [cards, setCards] = useState<any[]>([]);
    const [selectedCard, setSelectedCard] = useState<any>(null);
    const [editorContent, setEditorContent] = useState("");
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);
    const [deletingCard, setDeletingCard] = useState<any>(null);

    useEffect(() => {
        fetchCards();
    }, [selectedType]);

    const fetchCards = async () => {
        setIsLoading(true);
        try {
            const res = await getCards(selectedType);
            if (res.status === 'success') {
                setCards(res.data);
                if (res.data.length > 0) {
                    handleSelectCard(res.data[0]);
                } else {
                    setSelectedCard(null);
                    setEditorContent("");
                }
            }
        } catch (error) {
            console.error("Failed to fetch cards:", error);
        } finally {
            setIsLoading(false);
        }
    };

    const handleSelectCard = (card: any) => {
        setSelectedCard(card);
        const jsonContent = selectedType === 'economy'
            ? card.economy_card_json
            : card.company_card_json;

        try {
            const parsed = typeof jsonContent === 'string' ? JSON.parse(jsonContent) : jsonContent;
            setEditorContent(JSON.stringify(parsed, null, 2));
        } catch (e) {
            setEditorContent(jsonContent || "{}");
        }
    };

    const handleSave = async () => {
        if (!selectedCard) return;
        setIsSaving(true);
        try {
            const data = JSON.parse(editorContent);
            const date = selectedType === 'economy' ? selectedCard.date : selectedCard.date;
            const ticker = selectedType === 'company' ? selectedCard.ticker : null;

            await updateCard(selectedType, date, ticker, data);
            // Refresh list to show updated status/time if needed
            fetchCards();
            setViewMode('study'); // Switch back to study mode after saving
        } catch (error) {
            alert("Invalid JSON format or Save Failed");
        } finally {
            setIsSaving(false);
        }
    };

    const handleDeleteCard = (e: React.MouseEvent, card: any) => {
        e.stopPropagation();
        setDeletingCard(card);
    };

    const confirmDeletion = async () => {
        if (!deletingCard) return;

        try {
            await deleteCard(selectedType, deletingCard.date, deletingCard.ticker || null);

            // If the currently selected card is the one being deleted, clear the selection
            const isCurrent = selectedType === 'economy'
                ? selectedCard?.date === deletingCard.date
                : selectedCard?.date === deletingCard.date && selectedCard?.ticker === deletingCard.ticker;

            if (isCurrent) {
                setSelectedCard(null);
                setEditorContent("");
            }

            setDeletingCard(null);
            fetchCards();
        } catch (error) {
            alert("Failed to delete card");
        }
    };

    const filteredCards = cards.filter(card => {
        const date = String(card.date || "");
        const ticker = String(card.ticker || "");
        const search = searchTerm.toLowerCase().trim();

        if (!search) return true;

        return date.toLowerCase().includes(search) ||
            ticker.toLowerCase().includes(search);
    });

    return (
        <div className="space-y-8 animate-in fade-in duration-700 relative w-full">
            {/* Floating Expand Button (Visible when sidebar closed) */}
            {!isSidebarOpen && (
                <button
                    onClick={() => setIsSidebarOpen(true)}
                    className="fixed left-20 top-1/2 -translate-y-1/2 p-2 bg-blue-500/20 hover:bg-blue-500/40 border border-blue-500/30 rounded-r-xl transition-all duration-300 z-[60] group shadow-2xl shadow-blue-500/20 backdrop-blur-md animate-in slide-in-from-left-4"
                >
                    <PanelLeftOpen className="w-5 h-5 text-blue-400 group-hover:scale-110 transition-transform" />
                </button>
            )}

            <div className="flex gap-4 items-start relative">
                {/* Search & List (Left Sidebar) */}
                <div
                    className={`transition-all duration-200 ease-in-out shrink-0 sticky top-24 self-start ${isSidebarOpen ? 'w-[320px] opacity-100 translate-x-0' : 'w-0 opacity-0 -translate-x-12 pointer-events-none overflow-hidden'}`}
                >
                    <Card className="border-blue-500/10 bg-zinc-900/40 backdrop-blur-md shadow-2xl overflow-hidden relative group h-[calc(100vh-120px)] flex flex-col">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/5 blur-[60px] pointer-events-none" />

                        {/* Pinned Sticky Header Section */}
                        <div className="flex-none bg-zinc-900/40 backdrop-blur-md z-20">
                            {/* Integrated Controls (NEW ROW 1: Toggle, Search, Refresh) */}
                            <div className="px-3 pt-3 pb-2 relative z-10 border-b border-white/5 bg-black/20 flex items-center gap-2">
                                <button
                                    onClick={() => setIsSidebarOpen(false)}
                                    className="p-1.5 hover:bg-blue-500/10 rounded-lg transition-colors group/toggle shrink-0"
                                    title="Collapse Sidebar"
                                >
                                    <PanelLeftClose className="w-4 h-4 text-blue-400/60 group-hover/toggle:text-blue-400 transition-colors" />
                                </button>

                                <div className="relative flex-1 group/search">
                                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground group-focus-within/search:text-blue-400 transition-colors" />
                                    <input
                                        type="text"
                                        placeholder="SEARCH ARCHIVE..."
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                        onKeyDown={(e) => e.key === 'Enter' && fetchCards()}
                                        className="w-full bg-black/60 border border-white/5 rounded-lg py-2 pl-9 pr-2 text-[9px] font-black uppercase tracking-widest focus:outline-none focus:ring-1 focus:ring-blue-500/50 focus:border-blue-500/30 transition-all shadow-inner placeholder:text-muted-foreground/30"
                                    />
                                </div>

                                <Button
                                    onClick={() => fetchCards()}
                                    variant="outline"
                                    className="h-8 w-8 p-0 border-white/5 bg-black/40 hover:bg-blue-500/10 hover:border-blue-500/30 transition-all duration-300 shrink-0"
                                    title="Refresh"
                                >
                                    <RefreshCcw className={`w-3 h-3 text-blue-400/60 ${isLoading ? 'animate-spin text-blue-400' : ''}`} />
                                </Button>
                            </div>

                            {/* Integrated Controls (NEW ROW 2: Type Switcher + JSON Toggle) */}
                            <div className="p-3 border-b border-white/5 bg-black/20 flex items-center gap-3 relative z-10">
                                {/* Card Type Switcher */}
                                <div className="flex flex-1 bg-black/40 p-1 rounded-xl shadow-inner border border-white/5">
                                    <button
                                        onClick={() => {
                                            setSelectedType('economy');
                                            setSearchTerm("");
                                        }}
                                        className={`flex-1 py-1.5 text-[9px] font-black uppercase tracking-tighter rounded-lg transition-all duration-300 ${selectedType === 'economy' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-muted-foreground hover:text-white hover:bg-white/5 border border-transparent'}`}
                                    >
                                        ECONOMY
                                    </button>
                                    <button
                                        onClick={() => {
                                            setSelectedType('company');
                                            setSearchTerm("");
                                        }}
                                        className={`flex-1 py-1.5 text-[9px] font-black uppercase tracking-tighter rounded-lg transition-all duration-300 ${selectedType === 'company' ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' : 'text-muted-foreground hover:text-white hover:bg-white/5 border border-transparent'}`}
                                    >
                                        COMPANY
                                    </button>
                                </div>

                                {/* View Mode Toggle */}
                                <div className="flex items-center gap-2 shrink-0">
                                    <span className={`text-[9px] font-bold uppercase tracking-tight transition-colors ${viewMode === 'edit' ? 'text-white' : 'text-muted-foreground/40'}`}>
                                        JSON
                                    </span>
                                    <button
                                        onClick={() => setViewMode(viewMode === 'edit' ? 'study' : 'edit')}
                                        className={`relative w-10 h-5 rounded-full transition-all duration-300 shadow-inner border group ${viewMode === 'edit'
                                            ? 'bg-blue-600 border-blue-500 shadow-blue-500/20'
                                            : 'bg-zinc-800 border-white/5 hover:border-white/10'
                                            }`}
                                    >
                                        <motion.div
                                            animate={{ x: viewMode === 'edit' ? 20 : 2 }}
                                            transition={{ type: "spring", stiffness: 500, damping: 30 }}
                                            className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full shadow-md ${viewMode === 'edit' ? 'bg-white' : 'bg-muted-foreground group-hover:bg-zinc-300'
                                                }`}
                                        />
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Scrollable Records Section */}
                        <div className="flex-1 overflow-y-auto terminal-scroll pr-1 relative z-10 mx-0 px-4 pt-2">
                            {isLoading ? (
                                <div className="flex flex-col items-center justify-center p-20 gap-4">
                                    <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                                    <span className="text-[10px] font-black uppercase tracking-[0.2em] text-blue-500/50">Accessing Records...</span>
                                </div>
                            ) : filteredCards.length === 0 ? (
                                <div className="text-center p-12 border border-dashed border-white/5 rounded-2xl bg-black/20">
                                    <SearchCode className="w-8 h-8 text-muted-foreground/20 mx-auto mb-3" />
                                    <p className="text-[10px] font-black uppercase tracking-widest text-muted-foreground opacity-40 italic">Query returned no parameters</p>
                                </div>
                            ) : (
                                filteredCards.map((card, idx) => {
                                    const isSelected = selectedType === 'economy'
                                        ? selectedCard?.date === card.date
                                        : selectedCard?.date === card.date && selectedCard?.ticker === card.ticker;

                                    // Parse Setup Bias from screener_briefing for company cards
                                    let setupBias = null;
                                    if (selectedType === 'company' && card.company_card_json) {
                                        try {
                                            const cardData = typeof card.company_card_json === 'string'
                                                ? JSON.parse(card.company_card_json)
                                                : card.company_card_json;

                                            if (cardData?.screener_briefing) {
                                                const lines = cardData.screener_briefing.split('\n');
                                                for (const line of lines) {
                                                    if (line.includes('Setup_Bias:')) {
                                                        setupBias = line.split(':')[1]?.trim().toUpperCase();
                                                        break;
                                                    }
                                                }
                                            }
                                        } catch (e) {
                                            console.error("Failed to parse card data for sidebar", e);
                                        }
                                    }

                                    const renderBiasIcon = (bias: string | null) => {
                                        if (!bias) return null;
                                        const b = bias.toLowerCase();
                                        const isBullish = b === 'bullish';
                                        const isBearish = b === 'bearish';
                                        const isNeutralBullish = b.includes('neutral') && b.includes('bullish');
                                        const isNeutralBearish = b.includes('neutral') && b.includes('bearish');
                                        const isNeutral = b === 'neutral' || b === '-';

                                        if (isBullish) return <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />;
                                        if (isBearish) return <TrendingDown className="w-3.5 h-3.5 text-rose-500" />;
                                        if (isNeutralBullish) return <TrendingUp className="w-3.5 h-3.5 text-muted-foreground/30" />;
                                        if (isNeutralBearish) return <TrendingDown className="w-3.5 h-3.5 text-muted-foreground/30" />;
                                        if (isNeutral) return <Minus className="w-3.5 h-3.5 text-muted-foreground/30" />;

                                        // Fallback for complex strings
                                        if (b.includes('bull')) return <TrendingUp className="w-3.5 h-3.5 text-emerald-500/60" />;
                                        if (b.includes('bear')) return <TrendingDown className="w-3.5 h-3.5 text-rose-500/60" />;

                                        return <Minus className="w-3.5 h-3.5 text-muted-foreground/20" />;
                                    };

                                    return (
                                        <motion.div
                                            key={idx}
                                            initial="initial"
                                            whileHover="hover"
                                            onClick={() => handleSelectCard(card)}
                                            className={`w-full flex items-center justify-between py-1.5 border-b border-white/5 transition-all group relative cursor-pointer ${isSelected ? 'bg-blue-500/10 -mx-4 px-6 border-l-2 border-l-blue-500 border-b-transparent' : 'hover:bg-white/5 -mx-4 px-6'}`}
                                        >
                                            <div className="flex items-center relative z-10 overflow-hidden flex-1 shrink-0">
                                                <motion.div
                                                    variants={{
                                                        initial: { width: 0, opacity: 0, x: -10 },
                                                        hover: { width: 'auto', opacity: 1, x: 0 }
                                                    }}
                                                    className="flex items-center"
                                                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                                                >
                                                    <button
                                                        onClick={(e) => handleDeleteCard(e, card)}
                                                        className="p-1.5 rounded-md hover:bg-rose-500/20 text-rose-500/60 hover:text-rose-500 transition-all mr-2"
                                                        title="Delete Record"
                                                    >
                                                        <Trash2 className="w-3.5 h-3.5" />
                                                    </button>
                                                </motion.div>

                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-2">
                                                        <span className={`text-xs font-black tracking-tight ${isSelected ? 'text-blue-400' : 'text-foreground/90 group-hover:text-blue-400'} transition-colors truncate`}>
                                                            {selectedType === 'company' ? card.ticker : 'EOD_REPORT'}
                                                        </span>
                                                        {selectedType === 'company' && setupBias && (
                                                            <div className="flex items-center">
                                                                {renderBiasIcon(setupBias)}
                                                            </div>
                                                        )}
                                                        <span className={`text-[10px] font-mono shrink-0 ${isSelected ? 'text-blue-400/60' : 'text-muted-foreground/60'}`}>
                                                            {card.date}
                                                        </span>
                                                    </div>
                                                </div>
                                            </div>

                                            <ChevronRight className={`w-4 h-4 transition-all duration-300 shrink-0 ${isSelected ? 'text-blue-400 translate-x-1 opacity-100' : 'text-muted-foreground opacity-20 group-hover:opacity-100 group-hover:translate-x-1 group-hover:text-blue-400'}`} />

                                            {isSelected && (
                                                <div className="absolute inset-y-0 left-0 w-1 bg-blue-500 shadow-[2px_0_15px_rgba(59,130,246,0.5)]" />
                                            )}
                                        </motion.div>
                                    );
                                })
                            )}
                        </div>
                    </Card>
                </div>

                {/* Display Area (Right / Main) */}
                <div className="flex-1 min-w-0">
                    <Card className="flex flex-col border-blue-500/10 bg-zinc-900/40 backdrop-blur-md shadow-2xl relative group/display">
                        <div className="absolute bottom-0 right-0 w-64 h-64 bg-blue-600/5 blur-[100px] pointer-events-none" />
                        <div className="absolute top-0 left-0 w-64 h-64 bg-blue-400/5 blur-[100px] pointer-events-none" />

                        {viewMode === 'edit' ? (
                            <>
                                <div className="flex items-center justify-between p-6 pb-4 border-b border-white/5 relative z-10 bg-black/20">
                                    <div className="flex items-center gap-4">
                                        <div className="p-2 bg-blue-500/10 rounded-lg">
                                            <FileJson className="w-5 h-5 text-blue-400" />
                                        </div>
                                        <div>
                                            <h3 className="font-black text-xl italic text-foreground tracking-tighter uppercase">JSON Editing Mode</h3>
                                            <div className="flex items-center gap-2 mt-1">
                                                <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                                                <span className="text-[10px] font-mono text-blue-400/60 font-black">ACTIVE_INSTANCE: {selectedCard?.ticker || 'GLOBAL'}_{selectedCard?.date}</span>
                                            </div>
                                        </div>
                                    </div>
                                    <Button
                                        onClick={handleSave}
                                        disabled={isSaving || !selectedCard}
                                        className="gap-3 bg-blue-600 hover:bg-blue-500 text-white shadow-xl shadow-blue-600/20 font-black py-5 px-6 rounded-xl transition-all active:scale-95 group/save"
                                    >
                                        {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4 group-hover/save:scale-110 transition-transform" />}
                                        COMMIT TO DATABASE
                                    </Button>
                                </div>

                                <div className="min-h-[600px] bg-black/60 border border-white/5 rounded-2xl m-6 mt-4 p-8 font-mono text-xs overflow-hidden flex flex-col shadow-inner backdrop-blur-xl relative group/textarea">
                                    <div className="absolute top-4 right-4 text-[10px] font-black text-blue-500/20 pointer-events-none group-hover/textarea:text-blue-500/40 transition-colors">JSON_V1</div>
                                    <textarea
                                        value={editorContent}
                                        onChange={(e) => setEditorContent(e.target.value)}
                                        className="flex-1 w-full bg-transparent text-blue-200/80 resize-none focus:outline-none terminal-scroll selection:bg-blue-500/30 leading-relaxed font-mono"
                                        spellCheck={false}
                                    />
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 relative z-10">
                                {selectedCard ? (
                                    <div className="p-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                        <div className="flex items-center justify-between mb-8 pb-4 border-b border-white/5">
                                            <div className="flex items-center gap-3">
                                                <History className="w-5 h-5 text-blue-400" />
                                                <h3 className="font-black text-xl italic uppercase tracking-tighter">
                                                    {selectedType === 'company' ? selectedCard.ticker : 'EOD_REPORT'}
                                                </h3>
                                            </div>
                                            <div className="flex items-center gap-3 text-[10px] font-black uppercase italic">
                                                {(() => {
                                                    const cardData = selectedType === 'economy'
                                                        ? (typeof selectedCard.economy_card_json === 'string' ? JSON.parse(selectedCard.economy_card_json) : selectedCard.economy_card_json)
                                                        : (typeof selectedCard.company_card_json === 'string' ? JSON.parse(selectedCard.company_card_json) : selectedCard.company_card_json);

                                                    let bias = selectedType === 'economy'
                                                        ? cardData?.marketBias
                                                        : cardData?.confidence?.split('(')[0].replace('Trend_Bias:', '').trim();

                                                    // Safe handling if bias is an object
                                                    if (typeof bias === 'object' && bias !== null) {
                                                        bias = bias.action || bias.marketBias || JSON.stringify(bias);
                                                    }

                                                    if (!bias || typeof bias !== 'string') return null;

                                                    const isBull = bias.toLowerCase().includes('bull');
                                                    const isBear = bias.toLowerCase().includes('bear');

                                                    return (
                                                        <Badge variant={isBull ? 'success' : isBear ? 'error' : 'default'}
                                                            className="text-[9px] px-2 py-0.5 font-black italic tracking-widest uppercase border-white/10">
                                                            {bias}
                                                        </Badge>
                                                    );
                                                })()}
                                                <div className="flex items-center gap-1.5 px-3 py-1 bg-white/5 rounded-full border border-white/5 uppercase italic text-muted-foreground opacity-60">
                                                    <Calendar className="w-3 h-3" />
                                                    {selectedCard.date}
                                                </div>
                                            </div>
                                        </div>

                                        {selectedType === 'economy' ? (
                                            <EconomyCardView
                                                economyCard={typeof selectedCard.economy_card_json === 'string' ? JSON.parse(selectedCard.economy_card_json) : selectedCard.economy_card_json}
                                                date={selectedCard.date}
                                                isExpanded={!isSidebarOpen}
                                            />
                                        ) : (
                                            <CompanyCardView
                                                card={typeof selectedCard.company_card_json === 'string' ? JSON.parse(selectedCard.company_card_json) : selectedCard.company_card_json}
                                                ticker={selectedCard.ticker}
                                                date={selectedCard.date}
                                                isExpanded={!isSidebarOpen}
                                                isArchive={true}
                                            />
                                        )}
                                    </div>
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center p-20 text-center">
                                        <div className="relative mb-8">
                                            <div className="absolute inset-0 bg-blue-500/20 blur-[60px] rounded-full animate-pulse" />
                                            <div className="bg-zinc-950/80 backdrop-blur-xl p-10 rounded-full border border-white/10 relative z-10 shadow-2xl group-hover/display:scale-105 transition-transform duration-700">
                                                <History className="w-16 h-16 text-blue-400 opacity-80" />
                                            </div>
                                        </div>
                                        <h3 className="text-2xl font-black italic tracking-tighter uppercase mb-3 text-white">Select a Record to Study</h3>
                                        <p className="text-[10px] text-muted-foreground max-w-[280px] mx-auto uppercase tracking-widest leading-relaxed opacity-60">
                                            Access historical market intelligence and EOD narratives from the encrypted Turso vault.
                                        </p>
                                        <div className="mt-10 flex gap-2">
                                            <div className="w-2 h-2 rounded-full bg-blue-500/40" />
                                            <div className="w-8 h-2 rounded-full bg-blue-500/20" />
                                            <div className="w-2 h-2 rounded-full bg-blue-500/40" />
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </Card>
                </div>

                {/* Custom Confirmation Modal */}
                <AnimatePresence>
                    {deletingCard && (
                        <div className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
                            <motion.div
                                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                                animate={{ opacity: 1, scale: 1, y: 0 }}
                                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                                className="w-full max-w-md bg-zinc-950 border border-white/10 rounded-2xl p-6 shadow-2xl relative overflow-hidden"
                            >
                                {/* Warning Header Decoration */}
                                <div className="absolute top-0 left-0 w-full h-1 bg-rose-500" />

                                <button
                                    onClick={() => setDeletingCard(null)}
                                    className="absolute top-4 right-4 text-zinc-500 hover:text-white transition-colors"
                                >
                                    <X className="w-5 h-5" />
                                </button>

                                <div className="space-y-6">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 rounded-xl bg-rose-500/10 flex items-center justify-center border border-rose-500/20">
                                            <AlertTriangle className="w-6 h-6 text-rose-500" />
                                        </div>
                                        <div>
                                            <h2 className="text-[14px] font-black text-white italic tracking-widest uppercase">
                                                Confirm Deletion
                                            </h2>
                                            <p className="text-[9px] font-mono text-rose-500/60 font-black tracking-widest uppercase mt-0.5">
                                                Irreversible Command
                                            </p>
                                        </div>
                                    </div>

                                    <div className="bg-white/5 p-4 rounded-xl border border-white/5 space-y-3">
                                        <p className="text-[12px] text-zinc-300 leading-relaxed font-medium">
                                            Are you sure you wish to permanently delete the <span className="text-white font-black">{selectedType}</span> record
                                            {deletingCard.ticker && <span className="text-blue-400 font-black"> {deletingCard.ticker}</span>} for
                                            <span className="text-blue-400 font-black"> {deletingCard.date}</span>?
                                        </p>
                                        <p className="text-[10px] text-zinc-500 italic">
                                            All historical context and analysis associated with this card will be removed from the vault.
                                        </p>
                                    </div>

                                    <div className="flex gap-3">
                                        <button
                                            onClick={() => setDeletingCard(null)}
                                            className="flex-1 px-4 py-2.5 bg-white/5 hover:bg-white/10 text-white text-[10px] font-black uppercase tracking-widest rounded-xl transition-all border border-white/5 italic"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            onClick={confirmDeletion}
                                            className="flex-1 px-4 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-[10px] font-black uppercase tracking-widest rounded-xl shadow-lg shadow-rose-900/20 transition-all italic"
                                        >
                                            Delete Record
                                        </button>
                                    </div>
                                </div>
                            </motion.div>
                        </div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    );
}

