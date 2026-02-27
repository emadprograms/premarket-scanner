import axios from 'axios';

// Debug API Base URL selection - Sanitize inputs (remove quotes/trailing spaces that cause fatal URL parsing errors)
const getBaseUrl = () => {
    if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL.trim().replace(/['"]+/g, '');
    }
    // Fallback logic for browser environments
    if (typeof window !== 'undefined') {
        // If we are on localhost, use 127.0.0.1 to avoid IPv6/localhost ambiguity on some systems
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            return `${window.location.protocol}//127.0.0.1:8000`;
        }
        return `${window.location.protocol}//${window.location.hostname}:8000`;
    }
    return 'http://127.0.0.1:8000';
};

export const API_BASE_URL = getBaseUrl();
console.log(`[API] Initializing client with Base URL: ${API_BASE_URL}`);

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
    },
});

// Add Interceptor to catch and log specific Network Errors
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.message === 'Network Error') {
            console.error('[API] Network Error detected. Possible causes:');
            console.error('1. Backend is not running on ' + API_BASE_URL);
            console.error('2. CORS preflight (OPTIONS) failed.');
            console.error('3. Browser blocked the request (Mixed Content or AdBlock).');
        }
        return Promise.reject(error);
    }
);

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

export const getCards = async (category: string, date?: string) => {
    const { data } = await api.get(`/api/archive/cards/${category}`, {
        params: { date }
    });
    return data;
};

export const updateCard = async (category: string, date: string, ticker: string | null, cardData: any) => {
    const { data } = await api.post(`/api/archive/cards/${category}/update`, cardData, {
        params: { date, ticker }
    });
    return data;
};
export const deleteCard = async (category: string, date: string, ticker: string | null) => {
    const { data } = await api.delete(`/api/archive/cards/${category}/delete`, {
        params: { date, ticker }
    });
    return data;
};
