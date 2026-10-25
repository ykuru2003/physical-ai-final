"""Start the local Gazebo world and its ROS 2 bridge."""

from pathlib import Path

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, Shutdown
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    simulation = Path(__file__).resolve().parents[1]
    return LaunchDescription([
        DeclareLaunchArgument("gui", default_value="true"),
        ExecuteProcess(
            cmd=["gz", "sim", "-s", "-r", "-v", "3", str(simulation / "worlds" / "practice.sdf")],
            output="screen",
            on_exit=Shutdown(reason="Gazebo server stopped"),
        ),
        ExecuteProcess(
            cmd=["gz", "sim", "-g", "-v", "2"],
            condition=IfCondition(LaunchConfiguration("gui")),
            output="screen",
            on_exit=Shutdown(reason="Gazebo GUI stopped"),
        ),
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            name="simulation_bridge",
            parameters=[{
                "config_file": str(simulation / "config" / "bridge.yaml"),
                "use_sim_time": True,
            }],
            output="screen",
            on_exit=Shutdown(reason="ROS-Gazebo bridge stopped"),
        ),
    ])
