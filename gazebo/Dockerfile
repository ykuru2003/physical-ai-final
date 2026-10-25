FROM ros:jazzy-ros-base-noble

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ros-jazzy-ros-gz \
        ros-jazzy-teleop-twist-keyboard \
        xvfb x11-utils x11vnc novnc websockify openbox xterm \
        libgl1-mesa-dri libglx-mesa0 mesa-utils \
        fonts-dejavu-core fonts-noto-cjk dbus-x11 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV DISPLAY=:99 \
    QT_X11_NO_MITSHM=1 \
    LIBGL_ALWAYS_SOFTWARE=1 \
    GALLIUM_DRIVER=llvmpipe \
    XDG_RUNTIME_DIR=/tmp/runtime-root

COPY --chmod=755 gazebo/entrypoint.sh /usr/local/bin/start-simulator
RUN printf '\nsource /opt/ros/jazzy/setup.bash\n' >> /root/.bashrc
WORKDIR /workspace
EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/start-simulator"]
