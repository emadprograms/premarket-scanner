"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import dayjs from 'dayjs';

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
    updateSettings: (updates: Partial<MissionSettings>) => void;
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
    force_economy_refresh: false
};

const MissionContext = createContext<MissionContextType | undefined>(undefined);

import { getSystemStatus } from './api';

export function MissionProvider({ children }: { children: React.ReactNode }) {
    const [settings, setSettings] = useState<MissionSettings>(defaultSettings);
    const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);

    const refreshStatus = async () => {
        try {
            console.log("MissionProvider: Fetching system status...");
            const result = await getSystemStatus();
            console.log("MissionProvider: Status Result:", result);
            if (result.status === 'success') {
                setSystemStatus(result.data);
            }
        } catch (err) {
            console.error("MissionProvider: Failed to fetch system status:", err);
        }
    };

    useEffect(() => {
        refreshStatus();
        const interval = setInterval(refreshStatus, 30000); // 30s poll
        return () => clearInterval(interval);
    }, []);

    const updateSettings = (updates: Partial<MissionSettings>) => {
        setSettings(prev => {
            const newSettings = { ...prev, ...updates };

            // Auto-update cutoff if benchmark date changes
            if (updates.benchmark_date && !updates.simulation_cutoff) {
                newSettings.simulation_cutoff = `${updates.benchmark_date} 09:30:00`;
            }

            return newSettings;
        });
    };

    return (
        <MissionContext.Provider value={{ settings, systemStatus, updateSettings }}>
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
