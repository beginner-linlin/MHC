#!/bin/bash
# MHC 工作台后端进程管理（WSL 内）
# 用法: start_backend.sh {start|stop|restart|status|logs|port}

set -u

APP_DIR=/opt/bio/app
VENV_PY=$APP_DIR/venv/bin/python
PID_FILE=$APP_DIR/run/backend.pid
LOG_FILE=$APP_DIR/run/backend.log
PORT=${MHC_PORT:-8008}
HOST=${MHC_HOST:-127.0.0.1}

mkdir -p "$APP_DIR/run"

is_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid=$(cat "$PID_FILE" 2>/dev/null)
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  # 确认确实是我们的进程，而不是 PID 被复用
  grep -qa "serve.py" "/proc/$pid/cmdline" 2>/dev/null || return 1
  return 0
}

port_busy() {
  ss -ltn 2>/dev/null | grep -q ":$PORT "
}

do_start() {
  if is_running; then
    echo "后端已在运行 (pid $(cat "$PID_FILE"))"
    return 0
  fi
  if port_busy; then
    echo "端口 $PORT 已被其他进程占用，请先释放"
    return 1
  fi
  cd "$APP_DIR" || return 1
  export MHC_APP_ROOT="$APP_DIR"
  export MHC_PORT="$PORT"
  export MHC_HOST="$HOST"
  export PYTHONUNBUFFERED=1
  export PYTHONDONTWRITEBYTECODE=1
  nohup "$VENV_PY" "$APP_DIR/serve.py" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  # 等待端口就绪，最多 20 秒
  for _ in $(seq 1 100); do
    if port_busy; then
      echo "后端已启动 (pid $(cat "$PID_FILE")) → http://$HOST:$PORT"
      return 0
    fi
    if ! is_running; then
      echo "启动失败，最后 20 行日志："
      tail -20 "$LOG_FILE"
      rm -f "$PID_FILE"
      return 1
    fi
    sleep 0.2
  done
  echo "启动超时（端口 $PORT 未监听），最后 20 行日志："
  tail -20 "$LOG_FILE"
  return 1
}

do_stop() {
  if ! is_running; then
    echo "后端未运行"
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid=$(cat "$PID_FILE")
  kill "$pid" 2>/dev/null
  for _ in $(seq 1 30); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null
  fi
  rm -f "$PID_FILE"
  echo "后端已停止"
}

do_status() {
  if is_running; then
    echo "RUNNING pid=$(cat "$PID_FILE") port=$PORT"
    exit 0
  else
    echo "STOPPED port=$PORT"
    exit 3
  fi
}

case "${1:-start}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; sleep 0.5; do_start ;;
  status)  do_status ;;
  logs)    tail -n "${2:-60}" "$LOG_FILE" ;;
  port)    echo "$PORT" ;;
  *)
    echo "用法: $0 {start|stop|restart|status|logs [行数]|port}"
    exit 2
    ;;
esac
