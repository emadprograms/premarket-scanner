import React, { useEffect, useRef } from 'react';
import { Button } from './core';
import { X, AlertTriangle } from 'lucide-react';

interface ModalProps {
    isOpen: boolean;
    onClose: () => void;
    title: string;
    children: React.ReactNode;
    footer?: React.ReactNode;
    variant?: 'default' | 'destructive' | 'warning';
}

export function Modal({ isOpen, onClose, title, children, footer, variant = 'default' }: ModalProps) {
    const modalRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };

        if (isOpen) {
            document.addEventListener('keydown', handleEscape);
            document.body.style.overflow = 'hidden';
        }

        return () => {
            document.removeEventListener('keydown', handleEscape);
            document.body.style.overflow = 'unset';
        };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div
                ref={modalRef}
                className="relative w-full max-w-4xl bg-background/95 border border-border rounded-xl shadow-2xl animate-in zoom-in-95 slide-in-from-bottom-4 duration-300"
            >
                <div className="flex items-center justify-between p-6 border-b border-border/50">
                    <div className="flex items-center gap-3">
                        {variant === 'warning' && <AlertTriangle className="w-5 h-5 text-yellow-500" />}
                        {variant === 'destructive' && <AlertTriangle className="w-5 h-5 text-destructive" />}
                        <h2 className="text-lg font-bold tracking-tight">{title}</h2>
                    </div>
                    <button
                        onClick={onClose}
                        className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6">
                    {children}
                </div>

                {footer && (
                    <div className="flex items-center justify-end gap-3 p-6 pt-0 bg-transparent">
                        {footer}
                    </div>
                )}
            </div>
        </div>
    );
}
