#!/bin/bash
# إعداد Talabat Home على PythonAnywhere (خطة مجانية بدون بطاقة)
# يُنفّذ من Bash console داخل PythonAnywhere
set -e

USER_NAME=$(whoami)
HOME_DIR="/home/$USER_NAME"
APP_DIR="$HOME_DIR/talabat-home"
DOMAIN="$USER_NAME.pythonanywhere.com"

echo "== Talabat Home =="
echo "User : $USER_NAME"
echo "App  : $APP_DIR"
echo "URL  : https://$DOMAIN"
echo

if [ ! -d "$APP_DIR/server" ]; then
  echo "ERROR: لم أجد مجلد المشروع في $APP_DIR"
  echo "نفّذ أولاً: git clone https://github.com/msz11911/talabat-home.git ~/talabat-home"
  exit 1
fi

if [ ! -d "$HOME_DIR/.virtualenvs/talabat" ]; then
  echo ">> Creating virtualenv..."
  mkvirtualenv talabat --python=python3.10
fi

echo ">> Installing dependencies..."
pip install --upgrade pip pythonanywhere
pip install -r "$APP_DIR/server/requirements.txt"

echo ">> Writing start.sh..."
cat > "$APP_DIR/start.sh" <<EOF
#!/bin/bash
export HUSBAND_PIN=1234
export WIFE_PIN=5678
export APP_SECRET=talabat-home-secret-2026-ChangeMe123
export DATA_DIR=$APP_DIR/data
exec $HOME_DIR/.virtualenvs/talabat/bin/uvicorn --app-dir $APP_DIR/server --uds \${DOMAIN_SOCKET} app:app
EOF
chmod +x "$APP_DIR/start.sh"

echo ">> Creating / reloading website..."
pa website create --domain "$DOMAIN" --command "bash $APP_DIR/start.sh" \
  || pa website reload --domain "$DOMAIN"

echo
echo "DONE ✅"
echo "افتح: https://$DOMAIN/api/health"
echo "يجب أن يظهر: {\"ok\":true,\"app\":\"Talabat Home\",\"version\":\"1.0.0\"}"
