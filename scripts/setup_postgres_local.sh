#!/bin/bash
# Setup PostgreSQL local pour JENEZIS Genesis v2.0
# Usage: bash scripts/setup_postgres_local.sh

set -e  # Exit on error

echo "========================================================================"
echo "JENEZIS Genesis v2.0 - PostgreSQL Local Setup"
echo "========================================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
DB_NAME="jenezis_genesis_test"
DB_USER="${USER}"  # Use current Mac user
DB_HOST="localhost"
DB_PORT="5432"

echo "Configuration:"
echo "  Database: ${DB_NAME}"
echo "  User: ${DB_USER}"
echo "  Host: ${DB_HOST}:${DB_PORT}"
echo ""

# Check if PostgreSQL is running
echo "Step 1: Checking PostgreSQL status..."
if pg_isready -h $DB_HOST -p $DB_PORT &>/dev/null; then
    echo -e "${GREEN}✓ PostgreSQL is running${NC}"
else
    echo -e "${RED}✗ PostgreSQL is not running${NC}"
    echo ""
    echo "Please start PostgreSQL:"
    echo "  brew services start postgresql@16"
    echo "  # or"
    echo "  brew services start postgresql"
    exit 1
fi

# Check if database exists
echo ""
echo "Step 2: Checking if database exists..."
if psql -U $DB_USER -lqt | cut -d \| -f 1 | grep -qw $DB_NAME; then
    echo -e "${YELLOW}⚠  Database '$DB_NAME' already exists${NC}"
    read -p "Do you want to drop and recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Dropping database..."
        dropdb -U $DB_USER $DB_NAME || true
        echo "Creating fresh database..."
        createdb -U $DB_USER $DB_NAME
        echo -e "${GREEN}✓ Database recreated${NC}"
    else
        echo "Using existing database"
    fi
else
    echo "Creating database '$DB_NAME'..."
    createdb -U $DB_USER $DB_NAME
    echo -e "${GREEN}✓ Database created${NC}"
fi

# Check/Install pgvector extension
echo ""
echo "Step 3: Installing pgvector extension..."
if psql -U $DB_USER -d $DB_NAME -c "CREATE EXTENSION IF NOT EXISTS vector;" &>/dev/null; then
    echo -e "${GREEN}✓ pgvector extension installed${NC}"
else
    echo -e "${RED}✗ Failed to install pgvector extension${NC}"
    echo ""
    echo "Please install pgvector:"
    echo "  brew install pgvector"
    echo ""
    echo "Then re-run this script."
    exit 1
fi

# Set environment variable
echo ""
echo "Step 4: Setting environment..."
export DATABASE_URL="postgresql://${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# Update .env file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# PostgreSQL Local Configuration (auto-generated)
DATABASE_URL=postgresql://${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# OpenAI API (optional - add your key)
OPENAI_API_KEY=

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# Auth (optional)
API_AUTH_TOKEN=
EOF
    echo -e "${GREEN}✓ .env file created${NC}"
else
    echo -e "${YELLOW}⚠  .env file already exists (not modified)${NC}"
    echo "   Manual update required:"
    echo "   DATABASE_URL=postgresql://${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
fi

echo ""
echo "========================================================================"
echo -e "${GREEN}✓ PostgreSQL setup complete!${NC}"
echo "========================================================================"
echo ""
echo "Database URL:"
echo "  ${DATABASE_URL}"
echo ""
echo "Next steps:"
echo "  1. Run migration:"
echo "     export DATABASE_URL=\"${DATABASE_URL}\""
echo "     poetry run alembic upgrade head"
echo ""
echo "  2. Validate migration:"
echo "     poetry run python scripts/validate_migration.py --database ${DB_NAME}"
echo ""
echo "  3. Test connection:"
echo "     psql -U ${DB_USER} -d ${DB_NAME} -c \"\\dt\""
echo ""
echo "========================================================================"
