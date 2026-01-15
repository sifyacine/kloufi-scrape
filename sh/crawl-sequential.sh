#!/bin/bash
LOGFILE="/var/log/crawl.log"
echo "=== START crawl-sequential.sh at $(date) ===" >> "$LOGFILE"

for script in voiture electromenager immobilier emploi multimedia; do
    echo "Starting crawl-$script.sh at $(date)" >> "$LOGFILE"
    
    /home/joaquim/kloufi-scrap/sh/crawl-$script.sh >> "$LOGFILE" 2>&1
    EXIT_CODE=$?

    if [ $EXIT_CODE -ne 0 ]; then
        echo "ERROR: crawl-$script.sh failed with exit code $EXIT_CODE at $(date)" >> "$LOGFILE"
    else
        echo "Finished crawl-$script.sh at $(date)" >> "$LOGFILE"
    fi
done

echo "=== END crawl-sequential.sh at $(date) ===" >> "$LOGFILE"
