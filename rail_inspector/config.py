"""Central configuration for the Rail Track Inspection Robot.

All physical values are in millimetres / metres / seconds unless noted.
Change these to match your real hardware and the maintenance standard
your railway division follows.
"""

# ---------------------------------------------------------------- track
NOMINAL_GAUGE_MM = 1676          # Indian Broad Gauge (inner face to inner face)
GAUGE_TOLERANCE_MM = 10          # +/- deviation that raises a GAUGE defect
RAIL_HEAD_MM = 72                # width of the rail head seen from the top
SLEEPER_SPACING_MM = 600
SLEEPER_WIDTH_MM = 250

# ---------------------------------------------------------- track camera
# Down-looking camera mounted under the robot chassis.
CAM_W, CAM_H = 720, 480
MM_PER_PX = 3.1                  # calibrate with a checkerboard on the real robot
LEFT_RAIL_X = 70                 # pixel column of the left rail's outer edge (nominal)

# ---------------------------------------------------------- front camera
FRONT_W, FRONT_H = 480, 270
FRONT_HORIZON_Y = 95
FRONT_FOCAL_PX = 300
FRONT_CAM_HEIGHT_M = 0.5

# --------------------------------------------------------------- robot
MAX_SPEED_MPS = 1.5
CRUISE_SPEED_MPS = 1.2
ACCEL_MPS2 = 0.8
OBSTACLE_WARN_M = 15.0           # camera sees obstacle -> slow down
OBSTACLE_SLOW_FACTOR = 0.45
OBSTACLE_STOP_M = 2.0            # range sensor distance -> full stop
RANGE_SENSOR_MAX_M = 4.0         # HC-SR04 ~4 m, TF-Luna LiDAR ~8 m
RESUME_CLEAR_S = 2.0             # obstacle must be gone this long before resuming

# ---------------------------------------------------------- detection
CRACK_MIN_FRAMES = 2             # frames a crack must be seen before it is logged
DEFECT_MERGE_MM = 300            # detections closer than this are the same defect
CRACK_MINOR_FRAC = 0.35          # crack length / rail head width
CRACK_MAJOR_FRAC = 0.55
CRACK_CRITICAL_FRAC = 0.80

# ---------------------------------------------------------- location
# Chainage of the start point and a reference GPS point (demo values).
START_CHAINAGE_KM = 142.300
START_LAT, START_LON = 13.0827, 80.2707
HEADING_DEG = 225.0
