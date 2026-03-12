#!/bin/bash
echo "Stopping existing services..."
lsof -i :8000 -t | xargs kill -9 2>/dev/null || true
lsof -i :3000 -t | xargs kill -9 2>/dev/null || true
sleep 2

echo "Starting Backend..."
export PYTHONPATH=$PYTHONPATH:.
nohup python3 backend/main.py > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

echo "Waiting for Backend to listen on 8000..."
for i in {1..20}; do
    if lsof -i :8000 > /dev/null; then
        echo "Backend is up!"
        break
    fi
    sleep 1
done

echo "Starting Frontend..."
cd frontend
nohup npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

echo "Verifying..."
sleep 10
lsof -i :8000
lsof -i :3000
