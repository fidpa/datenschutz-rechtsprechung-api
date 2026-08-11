#!/bin/bash
# Comprehensive backup system für Datenschutz-Rechtsprechung API

set -e

# Configuration
BACKUP_DIR="/backups/datenschutz-rechtsprechung-api"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)
COMPOSE_FILE="/opt/datenschutz-rechtsprechung-api/docker-compose.production.yml"

# Load environment
source /opt/datenschutz-rechtsprechung-api/.env

echo "💾 Starting Datenschutz-Rechtsprechung API backup - $DATE"

# Create backup directory
mkdir -p $BACKUP_DIR/{database,redis,config,logs}

# Function: Database Backup
backup_database() {
    echo "🗃️  Backing up PostgreSQL database..."
    
    docker-compose -f $COMPOSE_FILE exec -T postgres pg_dump \
        -U $POSTGRES_USER \
        -d $POSTGRES_DB \
        --clean --if-exists --verbose \
        > $BACKUP_DIR/database/dsr_db_$DATE.sql
    
    # Compress database backup
    gzip $BACKUP_DIR/database/dsr_db_$DATE.sql
    
    echo "✅ Database backup: dsr_db_$DATE.sql.gz"
}

# Function: Redis Backup
backup_redis() {
    echo "📦 Backing up Redis data..."
    
    # Create Redis dump
    docker-compose -f $COMPOSE_FILE exec -T redis redis-cli \
        --rdb /data/dump_$DATE.rdb \
        > /dev/null 2>&1
    
    # Copy dump file
    docker cp $(docker-compose -f $COMPOSE_FILE ps -q redis):/data/dump_$DATE.rdb \
        $BACKUP_DIR/redis/redis_dump_$DATE.rdb
    
    echo "✅ Redis backup: redis_dump_$DATE.rdb"
}

# Function: Configuration Backup
backup_config() {
    echo "⚙️  Backing up configuration files..."
    
    # Create config archive
    tar -czf $BACKUP_DIR/config/config_$DATE.tar.gz \
        -C /opt/datenschutz-rechtsprechung-api \
        docker-compose.production.yml \
        .env \
        config/ \
        ssl/ \
        scripts/ \
        --exclude=ssl/certbot/conf/archive \
        --exclude=ssl/certbot/conf/live
    
    echo "✅ Config backup: config_$DATE.tar.gz"
}

# Function: Application Data Backup
backup_app_data() {
    echo "📁 Backing up application data..."
    
    # Backup uploads and sessions
    if [ -d "/opt/datenschutz-rechtsprechung-api/data" ]; then
        tar -czf $BACKUP_DIR/app_data_$DATE.tar.gz \
            -C /opt/datenschutz-rechtsprechung-api \
            data/
        
        echo "✅ App data backup: app_data_$DATE.tar.gz"
    fi
}

# Function: Cleanup old backups
cleanup_old_backups() {
    echo "🧹 Cleaning up old backups (older than $RETENTION_DAYS days)..."
    
    find $BACKUP_DIR -type f -mtime +$RETENTION_DAYS -delete
    
    echo "✅ Cleanup completed"
}

# Function: Verify backups
verify_backups() {
    echo "🔍 Verifying backup integrity..."
    
    # Check if backups were created
    latest_db_backup=$(find $BACKUP_DIR/database -name "*.sql.gz" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    latest_redis_backup=$(find $BACKUP_DIR/redis -name "*.rdb" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    
    if [ -n "$latest_db_backup" ] && [ -s "$latest_db_backup" ]; then
        echo "✅ Database backup verified: $(basename $latest_db_backup)"
    else
        echo "❌ Database backup verification failed"
        exit 1
    fi
    
    if [ -n "$latest_redis_backup" ] && [ -s "$latest_redis_backup" ]; then
        echo "✅ Redis backup verified: $(basename $latest_redis_backup)"
    else
        echo "❌ Redis backup verification failed"
        exit 1
    fi
}

# Function: Send backup report
send_backup_report() {
    if [ -n "$BACKUP_EMAIL" ]; then
        BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
        
        cat <<EOF | mail -s "Datenschutz-Rechtsprechung API Backup Report - $DATE" $BACKUP_EMAIL
Backup completed successfully at $(date)

Backup location: $BACKUP_DIR
Total backup size: $BACKUP_SIZE

Files created:
- Database: dsr_db_$DATE.sql.gz
- Redis: redis_dump_$DATE.rdb  
- Config: config_$DATE.tar.gz
- App Data: app_data_$DATE.tar.gz

Retention: $RETENTION_DAYS days

System Health:
$(curl -s http://localhost/system/health | jq -r '.status // "unknown"')

Next backup: $(date -d "tomorrow" '+%Y-%m-%d %H:%M')
EOF
        
        echo "✅ Backup report sent to $BACKUP_EMAIL"
    fi
}

# Execute backup functions
backup_database
backup_redis
backup_config
backup_app_data
verify_backups
cleanup_old_backups
send_backup_report

echo "🎉 Backup completed successfully!"
echo "📊 Backup summary:"
echo "   Location: $BACKUP_DIR"
echo "   Size: $(du -sh $BACKUP_DIR | cut -f1)"
echo "   Files: $(find $BACKUP_DIR -type f -name "*$DATE*" | wc -l)"