#!/bin/bash
# Setup initial client directory structure

CLIENTS_DIR="/data/clients"
CLIENT_NAME="bcomm"

echo "Creating client directory structure..."

mkdir -p "$CLIENTS_DIR"
mkdir -p "$CLIENTS_DIR/$CLIENT_NAME/credentials"

cat > "$CLIENTS_DIR/$CLIENT_NAME/config.yaml" << YAMLEOF
name: "BCOMM Comunicação Inteligente"
instance: "BCOMM"
hermes_profile: "bcomm-atendente"
timezone: "America/Sao_Paulo"
business_hours:
  start: "09:00"
  end: "18:00"
  days: [mon, tue, wed, thu, fri]
meeting_duration: 30
welcome_message: "Olá! Sou a Ana, da BCOMM. Como posso ajudar?"
google_calendar:
  enabled: true
  credentials_path: "/data/clients/$CLIENT_NAME/credentials/"
YAMLEOF

echo "Created $CLIENTS_DIR/$CLIENT_NAME/config.yaml"

if [ -f "/home/hermes/.hermes/google_token.json" ]; then
    cp /home/hermes/.hermes/google_token.json "$CLIENTS_DIR/$CLIENT_NAME/credentials/"
    echo "Copied google_token.json"
fi

if [ -f "/home/hermes/.hermes/google_client_secret.json" ]; then
    cp /home/hermes/.hermes/google_client_secret.json "$CLIENTS_DIR/$CLIENT_NAME/credentials/"
    echo "Copied google_client_secret.json"
fi

echo "Done!"
