import axios from 'axios';

// Debug API Base URL selection
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
console.log(`[API] Initializing client with Base URL: ${API_BASE_URL}`);

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export default api;

export const fetchConfig = async () => {
    const { data } = await api.get('/api/config');
    return data;
};

export const runMacroAnalysis = async (params: any) => {
    const { data } = await api.post('/api/macro/run', params);
    return data;
};

export const runSelectionScan = async (params: any) => {
    const { data } = await api.post('/api/scanner/scan', params);
    return data;
};

export const runRankingSynthesis = async (params: any) => {
    const { data } = await api.post('/api/ranking/rank', params);
    return data;
};

export const getSystemStatus = async () => {
    const { data } = await api.get('/api/system/status');
    return data;
};

export const syncKeys = async () => {
    const { data } = await api.post('/api/system/sync-keys');
    return data;
};

export const getWatchlistStatus = async () => {
    const { data } = await api.get('/api/system/watchlist-status');
    return data;
};
