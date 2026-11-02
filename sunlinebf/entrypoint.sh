#!/bin/bash
set -u

python3 /opt/sunlinebf/server.py &
history_pid=$!
/usr/local/bin/librespeed-rs --config /opt/librespeed/configs.toml &
speedtest_pid=$!

stop_services() {
    kill "$history_pid" "$speedtest_pid" 2>/dev/null || true
    wait "$history_pid" 2>/dev/null || true
    wait "$speedtest_pid" 2>/dev/null || true
}
trap stop_services TERM INT

# Keep both HTTP services in one container. If either exits, stop the other so
# RouterOS can restart the complete application as a unit.
wait -n "$history_pid" "$speedtest_pid"
status=$?
stop_services
exit "$status"
