type LogHandler = (log: any) => void;

class SocketService {
    private socket: WebSocket | null = null;
    private handlers: LogHandler[] = [];

    connect(url: string) {
        this.socket = new WebSocket(url);

        this.socket.onmessage = (event) => {
            try {
                const log = JSON.parse(event.data);
                this.handlers.forEach((handler) => handler(log));
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
        this.handlers.push(handler);
    }

    offLog(handler: LogHandler) {
        this.handlers = this.handlers.filter(h => h !== handler);
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }
}

export const socketService = new SocketService();
