#!/usr/bin/env python

# Copyright (c) 2020 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

"""Open3D Lidar visuialization example for CARLA"""

import glob
import os
import sys
import argparse
import time
from datetime import datetime
import random
import numpy as np
from matplotlib import cm
import open3d as o3d

try:
    sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
        sys.version_info.major,
        sys.version_info.minor,
        'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
except IndexError:
    pass

import carla

POINT_DIFF_THRESHOLD = 100  # FOR RECORDING. Difference in number of points from prev point cloud to capture.

VIRIDIS = np.array(cm.get_cmap('plasma').colors)
VID_RANGE = np.linspace(0.0, 1.0, VIRIDIS.shape[0])
LABEL_COLORS = np.array([
    (255, 255, 255), # None [0]
    (128, 64, 128),  # Roads [1]
    (244, 35, 232),  # Sidewalks [2]
    (70, 70, 70),    # Buildings [3]
    (102, 102, 156), # Walls [4]
    (100, 40, 40),   # Fences [5]
    (153, 153, 153), # Poles [6]
    (250, 170, 30),  # TrafficLight [7]
    (220, 220, 0),   # TrafficSigns [8]
    (107, 142, 35),  # Vegetation [9]
    (145, 170, 100), # Terrain [10]
    (70, 130, 180),  # Sky [11]
    (220, 20, 60),   # Pedestrians [12]
    (255, 0, 0),     # Rider [13]
    (0, 0, 142),     # Car [14]
    (0, 60, 100),    # Truck [15]
    (0, 80, 100),    # Bus [16]
    (0, 0, 230),     # Train [17]
    (119, 11, 32),   # Motorcycle [18]
    (81, 0, 81),     # Bicycle [19]
    (110, 190, 160), # Static [20]
    (170, 120, 50),  # Dynamic [21]
    (55, 90, 80),    # Other [22]
    (45, 60, 150),   # Water [23]
    (157, 234, 50),  # RoadLines [24]
    (81, 0, 81),     # Ground [25]
    (150, 100, 100), # Bridge [26]
    (230, 150, 140), # RailTrack [27]
    (180, 165, 180), # GuardRail[28]
]) / 255.0 # normalize each channel [0-1] since this is what Open3D uses

# DISABLING OBJECTS FROM POINTCLOUD:

LABEL_COLORS[0] = [0.0, 0.0, 0.0]  # None
LABEL_COLORS[1] = [0.0, 0.0, 0.0]  # Roads
LABEL_COLORS[2] = [0.0, 0.0, 0.0]  # Sidewalks
LABEL_COLORS[10] = [0.0, 0.0, 0.0] # Terrain
LABEL_COLORS[11] = [0.0, 0.0, 0.0] # Sky
LABEL_COLORS[24] = [0.0, 0.0, 0.0] # RoadLines
LABEL_COLORS[26] = [0.0, 0.0, 0.0] # Ground
LABEL_COLORS[27] = [0.0, 0.0, 0.0] # RailTrack

def lidar_callback(point_cloud, point_list):
    """Prepares a point cloud with intensity
    colors ready to be consumed by Open3D"""
    data = np.copy(np.frombuffer(point_cloud.raw_data, dtype=np.dtype('f4')))
    data = np.reshape(data, (int(data.shape[0] / 4), 4))

    # Isolate the intensity and compute a color for it
    intensity = data[:, -1]
    intensity_col = 1.0 - np.log(intensity) / np.log(np.exp(-0.004 * 100))
    int_color = np.c_[
        np.interp(intensity_col, VID_RANGE, VIRIDIS[:, 0]),
        np.interp(intensity_col, VID_RANGE, VIRIDIS[:, 1]),
        np.interp(intensity_col, VID_RANGE, VIRIDIS[:, 2])]

    # Isolate the 3D data
    points = data[:, :-1]

    # We're negating the y to correclty visualize a world that matches
    # what we see in Unreal since Open3D uses a right-handed coordinate system
    points[:, :1] = -points[:, :1]

    # # An example of converting points from sensor to vehicle space if we had
    # # a carla.Transform variable named "tran":
    # points = np.append(points, np.ones((points.shape[0], 1)), axis=1)
    # points = np.dot(tran.get_matrix(), points.T).T
    # points = points[:, :-1]

    point_list.points = o3d.utility.Vector3dVector(points)
    point_list.colors = o3d.utility.Vector3dVector(int_color)


def semantic_lidar_callback(point_cloud, point_list, actor_colors):
    """Prepares a point cloud with semantic segmentation
    colors ready to be consumed by Open3D"""
    data = np.frombuffer(point_cloud.raw_data, dtype=np.dtype([
        ('x', np.float32), ('y', np.float32), ('z', np.float32),
        ('CosAngle', np.float32), ('ObjIdx', np.uint32), ('ObjTag', np.uint32)]))

    # We're negating the y to correclty visualize a world that matches
    # what we see in Unreal since Open3D uses a right-handed coordinate system
    points = np.array([data['x'], -data['y'], data['z']]).T


    # # An example of adding some noise to our data if needed:
    # points += np.random.uniform(-0.05, 0.05, size=points.shape)

    # Colorize the pointcloud based on the CityScapes color palette
    labels = data['ObjTag']
    int_color = LABEL_COLORS[labels]

    # Assign unique colors based on actor ID
    unique_actor_ids = np.unique(data['ObjIdx'])
    for actor_id in unique_actor_ids:
        if actor_id in actor_colors:
            int_color[data['ObjIdx'] == actor_id] = actor_colors[actor_id]


    # Filter out points with the color (0.0, 0.0, 0.0) which correspond to object we don't want in pointcloud.
    mask = ~np.all(int_color == [0.0, 0.0, 0.0], axis=1)
    points = points[mask]
    int_color = int_color[mask]

    # # In case you want to make the color intensity depending
    # # of the incident ray angle, you can use:
    # int_color *= np.array(data['CosAngle'])[:, None]

    point_list.points = o3d.utility.Vector3dVector(points)
    point_list.colors = o3d.utility.Vector3dVector(int_color)


def generate_lidar_bp(arg, world, blueprint_library, delta):
    """Generates a CARLA blueprint based on the script parameters"""
    if arg.semantic:
        lidar_bp = world.get_blueprint_library().find('sensor.lidar.ray_cast_semantic')
    else:
        lidar_bp = blueprint_library.find('sensor.lidar.ray_cast')
        if arg.no_noise:
            lidar_bp.set_attribute('dropoff_general_rate', '0.0')
            lidar_bp.set_attribute('dropoff_intensity_limit', '1.0')
            lidar_bp.set_attribute('dropoff_zero_intensity', '0.0')
        else:
            lidar_bp.set_attribute('noise_stddev', '0.2')

    lidar_bp.set_attribute('upper_fov', str(arg.upper_fov))
    lidar_bp.set_attribute('lower_fov', str(arg.lower_fov))
    lidar_bp.set_attribute('channels', str(arg.channels))
    lidar_bp.set_attribute('range', str(arg.range))
    lidar_bp.set_attribute('rotation_frequency', str(1.0 / delta))
    lidar_bp.set_attribute('points_per_second', str(arg.points_per_second))
    return lidar_bp


def add_open3d_axis(vis):
    """Add a small 3D axis on Open3D Visualizer"""
    axis = o3d.geometry.LineSet()
    axis.points = o3d.utility.Vector3dVector(np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]]))
    axis.lines = o3d.utility.Vector2iVector(np.array([
        [0, 1],
        [0, 2],
        [0, 3]]))
    axis.colors = o3d.utility.Vector3dVector(np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0]]))
    vis.add_geometry(axis)


def main(arg):
    """Main function of the script"""
    client = carla.Client(arg.host, arg.port)
    client.set_timeout(2.0)
    world = client.get_world()

     # Get the list of actors in the scene
    actors = world.get_actors()
    # print(actors)

    previous_num_points = None

    # Create a dictionary to store unique colors for each actor ID
    actor_colors = {}

    # Assign unique colors to each actor ID
    for actor in actors:
        actor_id = actor.id
        if actor_id not in actor_colors:
            actor_colors[actor_id] = np.random.random(3)

    try:
        original_settings = world.get_settings()
        settings = world.get_settings()
        traffic_manager = client.get_trafficmanager(8000)
        traffic_manager.set_synchronous_mode(True)

        delta = 0.05

        settings.fixed_delta_seconds = delta
        settings.synchronous_mode = True
        settings.no_rendering_mode = arg.no_rendering
        world.apply_settings(settings)

        blueprint_library = world.get_blueprint_library()
        vehicle_bp = blueprint_library.filter(arg.filter)[0]
        vehicle_transform = random.choice(world.get_map().get_spawn_points())
        vehicle = world.spawn_actor(vehicle_bp, vehicle_transform)
        vehicle.set_autopilot(arg.no_autopilot)

        lidar_bp = generate_lidar_bp(arg, world, blueprint_library, delta)

        user_offset = carla.Location(arg.x, arg.y, arg.z)
        lidar_transform = carla.Transform(carla.Location(x=-0.5, z=1.8) + user_offset)

        lidar = world.spawn_actor(lidar_bp, lidar_transform, attach_to=vehicle)

        point_list = o3d.geometry.PointCloud()
        if arg.semantic:
            lidar.listen(lambda data: semantic_lidar_callback(data, point_list, actor_colors))
        else:
            lidar.listen(lambda data: lidar_callback(data, point_list))

        vis = o3d.visualization.Visualizer()
        vis.create_window(
            window_name='Carla Lidar',
            width=960,
            height=540,
            left=480,
            top=270)
        vis.get_render_option().background_color = [0.05, 0.05, 0.05]
        vis.get_render_option().point_size = 1
        vis.get_render_option().show_coordinate_frame = True

        if arg.show_axis:
            add_open3d_axis(vis)

        frame = 0
        dt0 = datetime.now()

        if arg.record: # Make the point cloud recording folder if we plan to record
            recording_folder = os.path.join("recordings", dt0.strftime("%Y%m%d_%H%M%S"))
            os.makedirs(recording_folder, exist_ok=True)


        while True:
            if frame == 2:
                vis.add_geometry(point_list)
            vis.update_geometry(point_list)



            if arg.record:

                # Check if the number of points has changed significantly
                current_num_points = len(point_list.points)
                if previous_num_points is None or abs(current_num_points - previous_num_points) > POINT_DIFF_THRESHOLD:

                    # Record the point cloud
                    ply_file_name = os.path.join(recording_folder, f"frame_{frame:06d}.ply")
                    o3d.io.write_point_cloud(ply_file_name, point_list)

                    previous_num_points = current_num_points

            vis.poll_events()
            vis.update_renderer()
            # # This can fix Open3D jittering issues:
            time.sleep(0.005)
            world.tick()

            process_time = datetime.now() - dt0
            sys.stdout.write('\r' + 'FPS: ' + str(1.0 / process_time.total_seconds()))
            sys.stdout.flush()
            dt0 = datetime.now()
            frame += 1

    finally:
        world.apply_settings(original_settings)
        traffic_manager.set_synchronous_mode(False)

        vehicle.destroy()
        lidar.destroy()
        vis.destroy_window()


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(
        description=__doc__)
    argparser.add_argument(
        '--host',
        metavar='H',
        default='localhost',
        help='IP of the host CARLA Simulator (default: localhost)')
    argparser.add_argument(
        '-p', '--port',
        metavar='P',
        default=2000,
        type=int,
        help='TCP port of CARLA Simulator (default: 2000)')
    argparser.add_argument(
        '--no-rendering',
        action='store_true',
        help='use the no-rendering mode which will provide some extra'
        ' performance but you will lose the articulated objects in the'
        ' lidar, such as pedestrians')
    argparser.add_argument(
        '--semantic',
        action='store_true',
        help='use the semantic lidar instead, which provides ground truth'
        ' information')
    argparser.add_argument(
        '--no-noise',
        action='store_true',
        help='remove the drop off and noise from the normal (non-semantic) lidar')
    argparser.add_argument(
        '--no-autopilot',
        action='store_false',
        help='disables the autopilot so the vehicle will remain stopped')
    argparser.add_argument(
        '--show-axis',
        action='store_true',
        help='show the cartesian coordinates axis')
    argparser.add_argument(
        '--filter',
        metavar='PATTERN',
        default='model3',
        help='actor filter (default: "vehicle.*")')
    argparser.add_argument(
        '--upper-fov',
        default=15.0,
        type=float,
        help='lidar\'s upper field of view in degrees (default: 15.0)')
    argparser.add_argument(
        '--lower-fov',
        default=-25.0,
        type=float,
        help='lidar\'s lower field of view in degrees (default: -25.0)')
    argparser.add_argument(
        '--channels',
        default=64.0,
        type=float,
        help='lidar\'s channel count (default: 64)')
    argparser.add_argument(
        '--range',
        default=30.0, # Default value used to be 100
        type=float,
        help='lidar\'s maximum range in meters (default: 30.0)')
    argparser.add_argument(
        '--points-per-second',
        default=500000, # Default value used to be 500k
        type=int,
        help='lidar\'s points per second (default: 400000)')
    argparser.add_argument(
        '-x',
        default=0.0,
        type=float,
        help='offset in the sensor position in the X-axis in meters (default: 0.0)')
    argparser.add_argument(
        '-y',
        default=0.0,
        type=float,
        help='offset in the sensor position in the Y-axis in meters (default: 0.0)')
    argparser.add_argument(
        '-z',
        default=0.0,
        type=float,
        help='offset in the sensor position in the Z-axis in meters (default: 0.0)')

    argparser.add_argument(
    '--record',
    action='store_true',
    help='record the point clouds as PLY files'
)
    args = argparser.parse_args()

    try:
        main(args)
    except KeyboardInterrupt:
        print(' - Exited by user.')
