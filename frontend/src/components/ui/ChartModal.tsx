import React, { useEffect, useRef } from 'react';
import { Modal } from './Modal';

interface ChartModalProps {
    isOpen: boolean;
    onClose: () => void;
    symbol: string;
}

declare global {
    interface Window {
        TradingView: any;
    }
}

export function ChartModal({ isOpen, onClose, symbol }: ChartModalProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!isOpen || !symbol) return;

        const script = document.createElement('script');
        script.src = 'https://s3.tradingview.com/tv.js';
        script.async = true;
        script.onload = () => {
            if (window.TradingView && containerRef.current) {
                new window.TradingView.widget({
                    autosize: true,
                    symbol: symbol.includes(':') ? symbol : `NASDAQ:${symbol}`, // Default to NASDAQ if no exchange provided, but TV handles symbol search well usually
                    interval: "5",
                    timezone: "Etc/UTC",
                    theme: "dark",
                    style: "1",
                    locale: "en",
                    toolbar_bg: "#f1f3f6",
                    enable_publishing: false,
                    allow_symbol_change: true,
                    container_id: containerRef.current.id,
                    hide_side_toolbar: false,
                    studies: [
                        "RSI@tv-basicstudies"
                    ]
                });
            }
        };
        document.head.appendChild(script);

        return () => {
            if (script.parentNode) {
                script.parentNode.removeChild(script);
            }
        };
    }, [isOpen, symbol]);

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={`📈 ${symbol} - Live Chart`}
            variant="default"
        >
            <div className="w-full h-[60vh] min-h-[500px] bg-black/20 rounded-lg overflow-hidden border border-border/30 relative">
                <div id={`tradingview_${symbol}`} ref={containerRef} className="absolute inset-0 w-full h-full" />
            </div>
        </Modal>
    );
}
