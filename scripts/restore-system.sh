#!/bin/bash
# System restore script

set -e

BACKUP_DIR="/backups/datenschutz-rechtsprechung-api"
BACKUP_DATE=${1:-"latest"}

if [ "$BACKUP_DATE" = "latest" ]; then
    BACKUP_DATE=$(find $BACKUP_DIR/database -name "*.sql.gz" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2- | grep -o '[0-9]\{8\}_[0-9]\{6\}')
fi

echo "🔄 Restoring Datenschutz-Rechtsprechung API from backup: $BACKUP_DATE"

# Stop services
echo "⏹️  Stopping services..."
docker-compose -f docker-compose.production.yml down

# Restore database
echo "🗃️  Restoring database..."
if [ -f "$BACKUP_DIR/database/dsr_db_$BACKUP_DATE.sql.gz" ]; then
    docker-compose -f docker-compose.production.yml up -d postgres
    sleep 10
    
    gunzip -c $BACKUP_DIR/database/dsr_db_$BACKUP_DATE.sql.gz | \
        docker-compose -f docker-compose.production.yml exec -T postgres \
        psql -U $POSTGRES_USER -d $POSTGRES_DB
    
    echo "✅ Database restored"
else
    echo "❌ Database backup not found: $BACKUP_DATE"
    exit 1
fi

# Restore Redis
echo "📦 Restoring Redis..."
if [ -f "$BACKUP_DIR/redis/redis_dump_$BACKUP_DATE.rdb" ]; then
    docker-compose -f docker-compose.production.yml up -d redis
    sleep 5
    
    docker cp $BACKUP_DIR/redis/redis_dump_$BACKUP_DATE.rdb \
        $(docker-compose -f docker-compose.production.yml ps -q redis):/data/dump.rdb
    
    docker-compose -f docker-compose.production.yml restart redis
    echo "✅ Redis restored"
fi

# Start all services
echo "🚀 Starting all services..."
docker-compose -f docker-compose.production.yml up -d

echo "✅ System restoration completed!"