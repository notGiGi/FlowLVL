#!/bin/sh

# Replace environment variables in the built JS files
echo "Configuring dashboard with environment variables..."

# Find the main.xxxx.js file
MAIN_JS_FILE=$(find /usr/share/nginx/html/static/js -name "main.*.js" | head -n 1)
if [ -z "$MAIN_JS_FILE" ]; then
  echo "Error: main.js file not found!"
  exit 1
fi

# Replace the API URL and other environment variables
if [ ! -z "$API_URL" ]; then
  echo "Setting API_URL to $API_URL"
  sed -i "s|__API_URL__|$API_URL|g" $MAIN_JS_FILE
else
  echo "API_URL not defined, using default"
  sed -i "s|__API_URL__|http://localhost:8000|g" $MAIN_JS_FILE
fi

if [ ! -z "$GRAFANA_URL" ]; then
  echo "Setting GRAFANA_URL to $GRAFANA_URL"
  sed -i "s|__GRAFANA_URL__|$GRAFANA_URL|g" $MAIN_JS_FILE
else
  echo "GRAFANA_URL not defined, using default"
  sed -i "s|__GRAFANA_URL__|http://localhost:3000|g" $MAIN_JS_FILE
fi

# Additional environment variables can be replaced here
if [ ! -z "$DEFAULT_API_KEY" ]; then
  echo "Setting DEFAULT_API_KEY"
  sed -i "s|__DEFAULT_API_KEY__|$DEFAULT_API_KEY|g" $MAIN_JS_FILE
else
  echo "DEFAULT_API_KEY not defined, using default"
  sed -i "s|__DEFAULT_API_KEY__|test_key|g" $MAIN_JS_FILE
fi

# Start Nginx
echo "Starting Nginx..."
exec "$@"