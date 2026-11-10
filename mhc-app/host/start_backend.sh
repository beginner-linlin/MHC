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
  # 确认确实是我们的进程，而不是 PID 被复用。
  # 注意 nohup exec 成 python 有几十毫秒延迟，这期间 cmdline 还是 nohup 的，
  # 所以两种都认——否则刚启动就会被误判成「进程已死」。
  if grep -qa "serve.py" "/proc/$pid/cmdline" 2>/dev/null; then
    return 0
  fi
  if grep -qa "nohup" "/proc/$pid/cmdline" 2>/dev/null; then
    return 0
  fi
  return 1
}

port_busy() {
  ss -ltn 2>/dev/null | grep -q ":$PORT "
}

# 找出正在监听 $PORT 的进程 pid（可能是丢了 pid 文件的孤儿 serve.py）
port_pid() {
  ss -ltnp 2>/dev/null | grep ":$PORT " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2
}

# 判断某个 pid 是不是「我们自己的 serve.py」
is_our_serve() {
  local p=${1:-}
  [ -n "$p" ] || return 1
  grep -qa "serve.py" "/proc/$p/cmdline" 2>/dev/null || return 1
  grep -qa "$APP_DIR" "/proc/$p/cmdline" 2>/dev/null || return 1
  return 0
}

# 杀掉占着端口却丢了 pid 文件的孤儿进程（自愈）
# 只在确认是本应用进程时才动手，避免误杀别人的服务
reap_orphan() {
  local p
  p=$(port_pid)
  if is_our_serve "$p"; then
    echo "发现残留后端进程 (pid $p) 占用端口 $PORT，正在清理…"
    kill "$p" 2>/dev/null
    for _ in $(seq 1 30); do
      kill -0 "$p" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
    for _ in $(seq 1 20); do
      port_busy || return 0
      sleep 0.1
    done
    return 0
  fi
  return 1
}

do_start() {
  if is_running; then
    echo "后端已在运行 (pid $(cat "$PID_FILE"))"
    return 0
  fi
  if port_busy; then
    if ! reap_orphan; then
      echo "端口 $PORT 已被其他进程占用（非本应用），请先释放"
      return 1
    fi
  fi
  cd "$APP_DIR" || return 1
  export MHC_APP_ROOT="$APP_DIR"
  export MHC_PORT="$PORT"
  export MHC_HOST="$HOST"
  export PYTHONUNBUFFERED=1
  export PYTHONDONTWRITEBYTECODE=1
  nohup "$VENV_PY" "$APP_DIR/serve.py" >>"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  # 等待端口就绪，最多 20 秒。
  # 前 10 轮（约 2 秒）不判 is_running 失败——python 启动 + Flask 绑定端口
  # 需要时间，过早判定会把成功启动误报成失败，还会把 pid 文件删掉。
  for i in $(seq 1 100); do
    if port_busy; then
      echo "后端已启动 (pid $(cat "$PID_FILE")) → http://$HOST:$PORT"
      return 0
    fi
    if [ "$i" -gt 10 ] && ! is_running; then
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
  local stopped=0
  if is_running; then
    local pid
    pid=$(cat "$PID_FILE")
    kill "$pid" 2>/dev/null
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null
    stopped=1
  fi
  rm -f "$PID_FILE"
  # pid 文件丢了但进程还在（孤儿）→ 一并清理
  if port_busy; then
    local p
    p=$(port_pid)
    if is_our_serve "$p"; then
      kill "$p" 2>/dev/null
      for _ in $(seq 1 30); do
        kill -0 "$p" 2>/dev/null || break
        sleep 0.1
      done
      kill -0 "$p" 2>/dev/null && kill -9 "$p" 2>/dev/null
      stopped=1
    fi
  fi
  if [ "$stopped" = "1" ]; then
    echo "后端已停止"
  else
    echo "后端未运行"
  fi
  return 0
}

do_status() {
  if is_running; then
    echo "RUNNING pid=$(cat "$PID_FILE") port=$PORT"
    return 0
  fi
  # pid 文件可能丢了但进程还活着（例如启动竞态时被删）——用端口兜底
  local p
  p=$(port_pid)
  if [ -n "$p" ] && is_our_serve "$p"; then
    echo "$p" >"$PID_FILE"
    echo "RUNNING pid=$p port=$PORT（pid 文件已回填）"
    return 0
  fi
  echo "STOPPED port=$PORT"
  return 3
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
