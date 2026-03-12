import axios from 'axios';

// Debug API Base URL selection - Sanitize inputs (remove quotes/trailing spaces that cause fatal URL parsing errors)
const getBaseUrl = () => {
    // 1. Explicit env var always wins (set this in Vercel project settings)
    if (process.env.NEXT_PUBLIC_API_URL) {
        return process.env.NEXT_PUBLIC_API_URL.trim().replace(/['"]+/g, '').replace(/\/+$/, '');
    }

    // 2. Fallback logic for browser environments
    if (typeof window !== 'undefined') {
        const hostname = window.location.hostname;
        const protocol = window.location.protocol;

        // Local development
        if (hostname === 'localhost' || hostname === '127.0.0.1') {
            return `${protocol}//127.0.0.1:8000`;
        }

        // Codespaces: rewrite port in hostname
        if (hostname.includes('.app.github.dev')) {
            const backendHost = hostname.replace(/-\d+\./, '-8000.');
            return `${protocol}//${backendHost}`;
        }

        // Production (Vercel, custom domain, etc.): NEXT_PUBLIC_API_URL MUST be set.
        // Don't guess — appending :8000 to a Vercel domain will never work.
        console.error(
            '[API] NEXT_PUBLIC_API_URL is not set. The frontend cannot reach the backend. ' +
            'Set this environment variable in your Vercel project settings to your Cloudflare Tunnel domain ' +
            '(e.g., https://api.yourdomain.com).'
        );
        // Return a placeholder that will fail fast with a clear error
        return `${protocol}//${hostname}`;
    }

    return 'http://127.0.0.1:8000';
};

export const API_BASE_URL = getBaseUrl();
console.log(`[API] Initializing client with Base URL: ${API_BASE_URL}`);

const api = axios.create({
    baseURL: API_BASE_URL,
    timeout: 30000, // 30s — backend can be slow during startup/key sync
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add Interceptor to catch and log specific Network Errors
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.message === 'Network Error') {
            console.warn('[API] Backend unreachable.');
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
    const { data } = await api.post('/api/scanner/scan', params, { timeout: 60000 }); // 60s — scan processes many tickers
    return data;
};

export const getChartBars = async (ticker: string, days: number = 1, resolution: string = 'MINUTE_5') => {
    const { data } = await api.get(`/api/scanner/bars/${ticker}`, { params: { days, resolution }, timeout: 15000 });
    return data;
};

export const getYahooChartBars = async (ticker: string, days: number = 3, resolution: string = 'MINUTE_5') => {
    const { data } = await api.get(`/api/scanner/bars/yahoo/${ticker}`, { params: { days, resolution }, timeout: 15000 });
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
