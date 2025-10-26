#!/bin/bash

echo "🚀 Starting Ontology Harmonization Service Monitoring"
echo "=================================================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Start Grafana
echo "📊 Starting Grafana dashboard..."
docker-compose up -d

# Wait for Grafana to be ready
echo "⏳ Waiting for Grafana to initialize..."
sleep 10

# Check if Grafana is running
if docker-compose ps | grep -q "erwin-grafana.*Up"; then
    echo "✅ Grafana is running!"
    echo ""
    echo "📈 Access your dashboard at: http://localhost:3000"
    echo "   Username: admin"
    echo "   Password: erwin123"
    echo ""
    echo "📊 Dashboard: Ontology Harmonization Service - Health Dashboard"
    echo ""
    echo "To stop monitoring: docker-compose down"
else
    echo "❌ Failed to start Grafana. Check logs with: docker-compose logs"
    exit 1
fi
