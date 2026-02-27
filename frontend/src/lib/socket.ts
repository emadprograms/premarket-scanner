type LogHandler = (log: any) => void;
type PriceHandler = (update: { ticker: string, price: number, timestamp: string }) => void;

class SocketService {
    private socket: WebSocket | null = null;
    private logHandlers: LogHandler[] = [];
    private priceHandlers: PriceHandler[] = [];
    private _autoReconnect = false;
    private _url: string | null = null;

    connect(url: string) {
        if (this.socket?.readyState === WebSocket.OPEN) return;

        this._url = url;
        this._autoReconnect = true;

        try {
            this.socket = new WebSocket(url);
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            return;
        }

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.type === 'PRICE_UPDATE') {
                    this.priceHandlers.forEach(h => h(data));
                } else {
                    this.logHandlers.forEach(h => h(data));
                }
            } catch (err) {
                console.error('Failed to parse socket message:', err);
            }
        };

        this.socket.onclose = () => {
            if (this._autoReconnect && this._url) {
                console.log('Socket closed. Reconnecting in 5s...');
                setTimeout(() => this.connect(this._url!), 5000);
            } else {
                console.log('Socket closed (manual disconnect).');
            }
        };
    }

    onLog(handler: LogHandler) {
        this.logHandlers.push(handler);
    }

    onPriceUpdate(handler: PriceHandler) {
        this.priceHandlers.push(handler);
    }

    disconnect() {
        this._autoReconnect = false;
        this._url = null;
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }

    isConnected(): boolean {
        return this.socket?.readyState === WebSocket.OPEN;
    }
}

export const socketService = new SocketService();
