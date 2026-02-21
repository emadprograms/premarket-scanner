import axios from 'axios';

// Debug API Base URL selection - Sanitize inputs (remove quotes/trailing spaces that cause fatal URL parsing errors)
const rawApiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export const API_BASE_URL = rawApiUrl.trim().replace(/['"]+/g, '');
console.log(`[API] Initializing client with Base URL: ${API_BASE_URL}`);

const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
        'ngrok-skip-browser-warning': 'true',
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

export const getWorkbenchNextDate = async () => {
    const { data } = await api.get('/api/workbench/pipeline/next-date');
    return data;
};

export const getDailyInput = async (date: string) => {
    const { data } = await api.get(`/api/workbench/daily-input/${date}`);
    return data;
};

export const saveDailyInput = async (date: string, newsText: string) => {
    const { data } = await api.post('/api/workbench/daily-input/save', null, {
        params: { date, news_text: newsText }
    });
    return data;
};

export const generateEconomyCard = async (date: string, newsText: string, modelConfig: string = "gemini-3-flash-free") => {
    const { data } = await api.post('/api/workbench/economy/generate', null, {
        params: { date, news_text: newsText, model_config: modelConfig }
    });
    return data;
};

export const generateCompanyCard = async (date: string, ticker: string, modelConfig: string = "gemini-3-flash-free") => {
    const { data } = await api.post('/api/workbench/company/generate', null, {
        params: { date, ticker, model_config: modelConfig }
    });
    return data;
};

export const getCards = async (category: string, date?: string) => {
    const { data } = await api.get(`/api/workbench/cards/${category}`, {
        params: { date }
    });
    return data;
};

export const updateCard = async (category: string, date: string, ticker: string | null, cardData: any) => {
    const { data } = await api.post(`/api/workbench/cards/${category}/update`, cardData, {
        params: { date, ticker }
    });
    return data;
};
export const deleteCard = async (category: string, date: string, ticker: string | null) => {
    const { data } = await api.delete(`/api/workbench/cards/${category}/delete`, {
        params: { date, ticker }
    });
    return data;
};
