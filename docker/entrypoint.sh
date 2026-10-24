#!/usr/bin/env bash
set -eo pipefail
source /opt/ros/jazzy/setup.bash
set -u

# Keep Gazebo and all display services in the same lifecycle.
pids=()
cleanup() {
    trap - EXIT TERM INT
    for pid in "${pids[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    wait || true
}
trap cleanup EXIT TERM INT

mkdir -p "${XDG_RUNTIME_DIR}"
chmod 700 "${XDG_RUNTIME_DIR}"
Xvfb "${DISPLAY}" -screen 0 "${DESKTOP_RESOLUTION:-1280x800x24}" -nolisten tcp -ac &
pids+=("$!")
for attempt in $(seq 1 100); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then break; fi
    sleep 0.1
done
xdpyinfo -display "${DISPLAY}" >/dev/null

openbox &
pids+=("$!")
x11vnc -display "${DISPLAY}" -forever -shared -nopw -localhost -rfbport 5900 &
pids+=("$!")
websockify --web /usr/share/novnc/ 6080 localhost:5900 &
pids+=("$!")
ros2 launch /workspace/simulation/launch/simulation.launch.py &
pids+=("$!")

echo 'Gazebo desktop: http://localhost:6080/vnc.html?autoconnect=true&resize=scale'
# A failed display or launch process must not leave a misleading healthy container.
set +e
wait -n "${pids[@]}"
status=$?
set -e
if [ "$status" -eq 0 ]; then status=1; fi
exit "$status"
