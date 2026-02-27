type LogHandler = (log: any) => void;
type PriceHandler = (update: { ticker: string, price: number, timestamp: string }) => void;

class SocketService {
    private socket: WebSocket | null = null;
    private logHandlers: LogHandler[] = [];
    private priceHandlers: PriceHandler[] = [];

    connect(url: string) {
        if (this.socket?.readyState === WebSocket.OPEN) return;

        try {
            this.socket = new WebSocket(url);
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            return;
        }

        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                
                // Route message based on type
                if (data.type === 'PRICE_UPDATE') {
                    this.priceHandlers.forEach(h => h(data));
                } else {
                    // Default to log handler for legacy support
                    this.logHandlers.forEach(h => h(data));
                }
            } catch (err) {
                console.error('Failed to parse socket message:', err);
            }
        };

        this.socket.onclose = () => {
            console.log('Socket closed. Reconnecting in 5s...');
            setTimeout(() => this.connect(url), 5000);
        };
    }

    onLog(handler: LogHandler) {
        this.logHandlers.push(handler);
    }

    onPriceUpdate(handler: PriceHandler) {
        this.priceHandlers.push(handler);
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
}

export const socketService = new SocketService();
