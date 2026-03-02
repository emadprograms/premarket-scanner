"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import dayjs from 'dayjs';
import { socketService } from './socket';
import { API_BASE_URL } from './api';

interface MissionSettings {
    model_name: string;
    mode: 'Live' | 'Simulation';
    benchmark_date: string;
    simulation_cutoff: string;
    db_fallback: boolean;
    proximity_threshold: number;
    plan_only_proximity: boolean;
    use_full_context: boolean;
    confluence_mode: 'Strict' | 'Flexible';
    force_economy_refresh: boolean;
    workstation: 'Scanner' | 'Archive';
    accountAmount: number;
    riskPercentage: number;
}

interface SystemStatus {
    gemini_keys_available: number;
    capital_connected: boolean;
    db_connected: boolean;
    economy_card_status: {
        active: boolean;
        updated: string;
    };
}

interface MissionContextType {
    settings: MissionSettings;
    systemStatus: SystemStatus | null;
    capitalStreaming: boolean;
    updateSettings: (updates: Partial<MissionSettings>) => void;
    toggleCapitalStream: () => void;
}

const defaultSettings: MissionSettings = {
    model_name: "gemini-3-flash-free",
    mode: 'Live',
    benchmark_date: dayjs().format('YYYY-MM-DD'),
    simulation_cutoff: dayjs().format('YYYY-MM-DD 09:30:00'),
    db_fallback: false,
    proximity_threshold: 2.5,
    plan_only_proximity: false,
    use_full_context: false,
    confluence_mode: "Strict",
    force_economy_refresh: false,
    workstation: 'Scanner',
    accountAmount: 10000,
    riskPercentage: 1.0
};

const MissionContext = createContext<MissionContextType | undefined>(undefined);

import { getSystemStatus } from './api';

export function MissionProvider({ children }: { children: React.ReactNode }) {
    const [settings, setSettings] = useState<MissionSettings>(defaultSettings);
    const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
    const [capitalStreaming, setCapitalStreaming] = useState(false);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
        setSettings(prev => ({
            ...prev,
            benchmark_date: dayjs().format('YYYY-MM-DD'),
            simulation_cutoff: dayjs().format('YYYY-MM-DD 09:30:00'),
        }));
    }, []);

    const refreshStatus = async () => {
        if (!mounted) return;
        try {
            const result = await getSystemStatus();
            if (result.status === 'success') {
                setSystemStatus(result.data);
            }
        } catch (err) {
            setSystemStatus(null); // Mark as offline so auto-recovery triggers when back
        }
    };

    // Adaptive polling: 10s when offline (fast recovery), 30s when connected
    useEffect(() => {
        if (!mounted) return;
        refreshStatus();
        const pollInterval = systemStatus ? 30000 : 10000;
        const interval = setInterval(refreshStatus, pollInterval);
        return () => clearInterval(interval);
    }, [mounted, systemStatus === null]);

    const toggleCapitalStream = useCallback(() => {
        setCapitalStreaming(prev => {
            const next = !prev;
            if (next) {
                // Connect WebSocket
                let wsProtocol = API_BASE_URL.startsWith('https') ? 'wss' : 'ws';
                if (API_BASE_URL.includes('ngrok')) wsProtocol = 'wss';
                const wsUrl = `${wsProtocol}://${API_BASE_URL.replace(/^https?:\/\//, '')}/ws/logs`;
                socketService.connect(wsUrl);
            } else {
                // Disconnect WebSocket
                socketService.disconnect();
            }
            return next;
        });
    }, []);

    const updateSettings = (updates: Partial<MissionSettings>) => {
        setSettings(prev => {
            const newSettings = { ...prev, ...updates };
            if (updates.benchmark_date && !updates.simulation_cutoff) {
                newSettings.simulation_cutoff = `${updates.benchmark_date} 09:30:00`;
            }
            return newSettings;
        });
    };

    return (
        <MissionContext.Provider value={{ settings, systemStatus, capitalStreaming, updateSettings, toggleCapitalStream }}>
            {children}
        </MissionContext.Provider>
    );
}

export function useMission() {
    const context = useContext(MissionContext);
    if (context === undefined) {
        throw new Error('useMission must be used within a MissionProvider');
    }
    return context;
}
